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

    precondition ($usuario_logado.status == "ativo" && $usuario_logado.role == "admin") {
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

    // Provedor desativado não é testado: o teste gravaria um novo status e
    // reativaria o provedor por efeito colateral.
    precondition ($provedor.status != "inativo") {
      error_type = "inputerror"
      error = "Provedor desativado; o teste de conexão não está disponível"
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
    // memória; nunca logado nem retornado.
    var $aws_secret {
      value = $provedor.aws_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"
    }

    var $novo_status { value = "erro" }
    var $mensagem    { value = "Falha ao autenticar a credencial AWS" }
    var $conectado   { value = false }
    var $diagnostico { value = null }

    // ============================================================
    // AWS: SigV4 STS GetCallerIdentity.
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
