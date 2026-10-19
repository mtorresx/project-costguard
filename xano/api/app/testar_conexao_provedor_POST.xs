query "provedores/{id}/testar-conexao" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
  }

  stack {
    // --- Autorização (admin, validada no backend) ---
    db.get usuarios {
      field_name = "id"
      field_value = $auth.id
    } as $usuario_logado

    precondition ($usuario_logado != null) {
      error_type = "unauthorized"
      error = "Token inválido ou expirado"
    }

    precondition ($usuario_logado.role == "admin") {
      error_type = "accessdenied"
      error = "Acesso negado"
    }

    // --- Carrega o provedor e valida pré-condições ---
    db.get provedores {
      field_name = "id"
      field_value = $input.id
    } as $provedor

    precondition ($provedor != null) {
      error_type = "notfound"
      error = "Provedor não encontrado"
    }

    precondition ($provedor.tipo == "aws") {
      error_type = "inputerror"
      error = "Tipo de provedor não suportado (apenas 'aws')"
    }

    precondition ($provedor.aws_access_key_id != null && $provedor.aws_access_key_id != "") {
      error_type = "inputerror"
      error = "Credencial AWS ausente"
    }

    precondition ($provedor.aws_secret_cifrado != null && $provedor.aws_secret_cifrado != "") {
      error_type = "inputerror"
      error = "Credencial AWS ausente"
    }

    // O secret é decifrado via JWE imediatamente antes da assinatura, só em
    // memória; nunca logado nem retornado (vale para AWS real e Mock).
    var $aws_secret {
      value = $provedor.aws_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"
    }

    var $eh_mock { value = ($provedor.usar_mock == true) }

    // Resultado comum aos dois ramos.
    var $novo_status { value = "erro" }
    var $mensagem    { value = "Falha ao autenticar a credencial AWS" }
    var $conectado   { value = false }
    var $diagnostico { value = null }

    conditional {
      if ($eh_mock == false) {
        // ============================================================
        // RAMO AWS REAL — inalterado: SigV4 STS GetCallerIdentity.
        // (service=sts, region=us-east-1)
        // ============================================================
        var $sig_service { value = "sts" }
        var $sig_region  { value = "us-east-1" }
        var $sig_host    { value = "sts.amazonaws.com" }
        var $sig_endpoint { value = "https://sts.amazonaws.com/" }
        var $sig_query   { value = "Action=GetCallerIdentity&Version=2011-06-15" }

        var $amz_date  { value = now|format_timestamp:"Ymd\\THis\\Z":"UTC" }
        var $datestamp { value = now|format_timestamp:"Ymd":"UTC" }

        // 1) Canonical request (GET, sem corpo => hash do payload vazio)
        var $payload_hash { value = ""|sha256 }

        var $canonical_headers {
          value = "host:" ~ $sig_host ~ "\nx-amz-date:" ~ $amz_date ~ "\n"
        }
        var $signed_headers { value = "host;x-amz-date" }

        var $canonical_request {
          value = "GET" ~ "\n" ~ "/" ~ "\n" ~ $sig_query ~ "\n" ~ $canonical_headers ~ "\n" ~ $signed_headers ~ "\n" ~ $payload_hash
        }

        // 2) String to sign
        var $credential_scope {
          value = $datestamp ~ "/" ~ $sig_region ~ "/" ~ $sig_service ~ "/aws4_request"
        }
        var $string_to_sign {
          value = "AWS4-HMAC-SHA256" ~ "\n" ~ $amz_date ~ "\n" ~ $credential_scope ~ "\n" ~ ($canonical_request|sha256)
        }

        // 3) Signing key encadeada (raw=true), a partir do secret decifrado.
        var $k_date    { value = $datestamp|hmac_sha256:("AWS4" ~ $aws_secret):true }
        var $k_region  { value = $sig_region|hmac_sha256:$k_date:true }
        var $k_service { value = $sig_service|hmac_sha256:$k_region:true }
        var $k_signing { value = "aws4_request"|hmac_sha256:$k_service:true }

        // 4) Assinatura (hex)
        var $signature { value = $string_to_sign|hmac_sha256:$k_signing }

        var $authorization {
          value = "AWS4-HMAC-SHA256 Credential=" ~ $provedor.aws_access_key_id ~ "/" ~ $credential_scope ~ ", SignedHeaders=" ~ $signed_headers ~ ", Signature=" ~ $signature
        }

        // --- Chamada à AWS STS (somente leitura) ---
        api.request {
          url = $sig_endpoint ~ "?" ~ $sig_query
          method = "GET"
          headers = [
            "Host: " ~ $sig_host,
            "X-Amz-Date: " ~ $amz_date,
            "Authorization: " ~ $authorization
          ]
          timeout = 20
        } as $sts_result

        // Diagnóstico sanitizado: SOMENTE status HTTP, Error.Code, Error.Message
        // e RequestId. Nunca secret, PROV_ENC_KEY, Authorization, signing keys,
        // assinatura ou JWE decifrado.
        var.update $diagnostico {
          value = {
            http_status: $sts_result.response.status
            error_code : ($sts_result.response.result.Error.Code ?? null)
            error_msg  : ($sts_result.response.result.Error.Message ?? null)
            request_id : ($sts_result.response.result.RequestId ?? null)
          }
        }

        conditional {
          if ($sts_result.response.status == 200) {
            var.update $novo_status { value = "ok" }
            var.update $mensagem    { value = "Credencial AWS autenticada com sucesso" }
            var.update $conectado   { value = true }
          }
        }
      }
      else {
        // ============================================================
        // RAMO AWS MOCK — NÃO chama STS. Usa o mesmo algoritmo SigV4
        // aplicado ao Cost Explorer do Mock (GetTags), assinando com host e
        // canonical URI do destino efetivo do Mock.
        //
        // LIMITAÇÃO: o AWS Mock Simulator atualmente NÃO valida SigV4. Portanto
        // este teste valida comunicação HTTPS, endpoint, Account ID, contrato
        // Cost Explorer e a geração/envio do fluxo SigV4 pelo CostGuard, mas
        // NÃO comprova que Access Key/Secret estejam corretas.
        // ============================================================
        var.update $mensagem { value = "Falha ao acessar o AWS Mock" }

        // MOCK_BASE_URL é obrigatória apenas no caminho Mock.
        precondition ($env.MOCK_BASE_URL != null && $env.MOCK_BASE_URL != "") {
          error_type = "inputerror"
          error = "Ambiente Mock não configurado (MOCK_BASE_URL ausente)"
        }

        // Normaliza UMA barra final (sem regex) e deriva o host (sem esquema).
        var $mock_base_raw { value = $env.MOCK_BASE_URL }
        var $mock_base_len { value = $mock_base_raw|strlen }
        var $mock_base_ultimo { value = $mock_base_raw|substr:($mock_base_len - 1) }
        var $mock_base_norm { value = $mock_base_raw }
        conditional {
          if ($mock_base_ultimo == "/") {
            var.update $mock_base_norm { value = $mock_base_raw|substr:0:($mock_base_len - 1) }
          }
        }
        var $mock_host { value = $mock_base_norm }
        conditional {
          if ($mock_base_norm|starts_with:"https://") {
            var.update $mock_host { value = $mock_base_norm|substr:8 }
          }
          else {
            conditional {
              if ($mock_base_norm|starts_with:"http://") {
                var.update $mock_host { value = $mock_base_norm|substr:7 }
              }
            }
          }
        }

        var $sig_service { value = "ce" }
        var $sig_region  { value = "us-east-1" }
        var $sig_host    { value = $mock_host }
        var $canonical_uri { value = "/aws/" ~ $provedor.identificador_conta ~ "/ce/" }
        var $sig_endpoint  { value = $mock_base_norm ~ "/aws/" ~ $provedor.identificador_conta ~ "/ce/" }
        var $amz_target  { value = "AWSInsightsIndexService.GetTags" }
        var $content_type { value = "application/x-amz-json-1.1" }

        // Corpo GetTags: TagKey = PRJ e um intervalo válido (últimos 30 dias).
        // Start inclusivo / End exclusivo. Lista de Tags vazia é sucesso.
        var $agora_ts  { value = now|to_int }
        var $inicio_ts { value = $agora_ts - 2592000000 }
        var $fim_mock    { value = $agora_ts|format_timestamp:"Y-m-d":"UTC" }
        var $inicio_mock { value = $inicio_ts|format_timestamp:"Y-m-d":"UTC" }

        var $corpo {
          value = {
            TimePeriod: {Start: $inicio_mock, End: $fim_mock}
            TagKey    : "PRJ"
          }
        }
        var $corpo_json { value = $corpo|json_encode }

        var $amz_date  { value = now|format_timestamp:"Ymd\\THis\\Z":"UTC" }
        var $datestamp { value = now|format_timestamp:"Ymd":"UTC" }

        var $payload_hash { value = $corpo_json|sha256 }
        var $canonical_headers {
          value = "content-type:" ~ $content_type ~ "\nhost:" ~ $sig_host ~ "\nx-amz-date:" ~ $amz_date ~ "\nx-amz-target:" ~ $amz_target ~ "\n"
        }
        var $signed_headers { value = "content-type;host;x-amz-date;x-amz-target" }
        var $canonical_request {
          value = "POST" ~ "\n" ~ $canonical_uri ~ "\n" ~ "" ~ "\n" ~ $canonical_headers ~ "\n" ~ $signed_headers ~ "\n" ~ $payload_hash
        }

        var $credential_scope {
          value = $datestamp ~ "/" ~ $sig_region ~ "/" ~ $sig_service ~ "/aws4_request"
        }
        var $string_to_sign {
          value = "AWS4-HMAC-SHA256" ~ "\n" ~ $amz_date ~ "\n" ~ $credential_scope ~ "\n" ~ ($canonical_request|sha256)
        }

        var $k_date    { value = $datestamp|hmac_sha256:("AWS4" ~ $aws_secret):true }
        var $k_region  { value = $sig_region|hmac_sha256:$k_date:true }
        var $k_service { value = $sig_service|hmac_sha256:$k_region:true }
        var $k_signing { value = "aws4_request"|hmac_sha256:$k_service:true }
        var $signature { value = $string_to_sign|hmac_sha256:$k_signing }

        var $authorization {
          value = "AWS4-HMAC-SHA256 Credential=" ~ $provedor.aws_access_key_id ~ "/" ~ $credential_scope ~ ", SignedHeaders=" ~ $signed_headers ~ ", Signature=" ~ $signature
        }

        api.request {
          url = $sig_endpoint
          method = "POST"
          params = $corpo
          headers = [
            "Content-Type: " ~ $content_type,
            "X-Amz-Target: " ~ $amz_target,
            "Host: " ~ $sig_host,
            "X-Amz-Date: " ~ $amz_date,
            "Authorization: " ~ $authorization
          ]
          timeout = 20
        } as $mock_result

        var.update $diagnostico {
          value = {
            http_status: $mock_result.response.status
            error_code : ($mock_result.response.result.Error.Code ?? null)
            error_msg  : ($mock_result.response.result.Error.Message ?? null)
            request_id : ($mock_result.response.result.RequestId ?? null)
          }
        }

        // Sucesso: HTTP 2xx e resposta compatível com o contrato GetTags
        // (presença do campo Tags, mesmo que seja lista vazia).
        var $tags_presentes { value = ($mock_result.response.result.Tags != null) }
        conditional {
          if ($mock_result.response.status == 200 && $tags_presentes == true) {
            var.update $novo_status { value = "ok" }
            var.update $mensagem    { value = "Endpoint Mock acessível e Account ID válido (SigV4 não validado pelo Mock)" }
            var.update $conectado   { value = true }
          }
        }
      }
    }

    db.edit provedores {
      field_name = "id"
      field_value = $input.id
      data = {status: $novo_status}
    } as $provedor_atualizado

    // Resposta sem segredo nem material de assinatura.
    var $resposta {
      value = {
        id         : $provedor_atualizado.id
        status     : $provedor_atualizado.status
        conectado  : $conectado
        mensagem   : $mensagem
        diagnostico: $diagnostico
      }
    }
  }

  response = $resposta
  guid = "16WwGCBDisc9vtO2wRO1jifTYyE"
}
