query "provedores/{id}/coletar-custos" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
    // Body opcional. `id` vem apenas do path (não é duplicado no corpo).
    text data_inicio? filters=trim
    text data_fim? filters=trim
  }

  stack {
    // ============================================================
    // 1) Autorização: coleta é operação administrativa (backend).
    // ============================================================
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

    // ============================================================
    // A) Elegibilidade do provedor (ANTES de decifrar credencial).
    // ============================================================
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

    precondition ($provedor.status == "ok") {
      error_type = "inputerror"
      error = "Provedor não está conectado (status != ok)"
    }

    precondition ($provedor.aws_access_key_id != null && $provedor.aws_access_key_id != "") {
      error_type = "inputerror"
      error = "Credencial AWS ausente"
    }

    precondition ($provedor.aws_secret_cifrado != null && $provedor.aws_secret_cifrado != "") {
      error_type = "inputerror"
      error = "Credencial AWS ausente"
    }

    // ============================================================
    // B) Decifra o secret (SÓ em memória, imediatamente antes de assinar).
    // ============================================================
    var $aws_secret {
      value = $provedor.aws_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"
    }

    // ============================================================
    // C) Resolve o intervalo. Start inclusivo, End exclusivo.
    //    Aritmética feita no timestamp NUMÉRICO; só então formata YYYY-MM-DD.
    // ============================================================
    var $agora_ts { value = now|to_int }
    var $inicio_ts { value = $agora_ts - 2592000000 }
    var $hoje { value = $agora_ts|format_timestamp:"Y-m-d":"UTC" }
    var $ha_30_dias { value = $inicio_ts|format_timestamp:"Y-m-d":"UTC" }

    var $inicio {
      value = ($input.data_inicio != null && $input.data_inicio != "") ? $input.data_inicio : $ha_30_dias
    }
    var $fim {
      value = ($input.data_fim != null && $input.data_fim != "") ? $input.data_fim : $hoje
    }

    precondition ($inicio < $fim) {
      error_type = "inputerror"
      error = "Intervalo inválido: data_inicio deve ser anterior a data_fim"
    }

    // Constantes SigV4 do Cost Explorer (service=ce, region=us-east-1).
    var $sig_service { value = "ce" }
    var $sig_region  { value = "us-east-1" }
    var $sig_host    { value = "ce.us-east-1.amazonaws.com" }
    var $sig_endpoint { value = "https://ce.us-east-1.amazonaws.com/" }
    var $amz_target  { value = "AWSInsightsIndexService.GetCostAndUsage" }
    var $content_type { value = "application/x-amz-json-1.1" }

    // ============================================================
    // D) Construção do payload inicial do Cost Explorer (sem NextPageToken).
    // ============================================================
    var $corpo {
      value = {
        TimePeriod : {Start: $inicio, End: $fim}
        Granularity: "DAILY"
        Metrics    : ["UnblendedCost"]
        GroupBy    : [{Type: "DIMENSION", Key: "SERVICE"}]
      }
    }

    var $corpo_json { value = $corpo|json_encode }

    // ============================================================
    // E) Preparação SigV4 para a primeira requisição.
    // ============================================================
    var $amz_date  { value = now|format_timestamp:"Ymd\\THis\\Z":"UTC" }
    var $datestamp { value = now|format_timestamp:"Ymd":"UTC" }

    var $payload_hash { value = $corpo_json|sha256 }
    var $canonical_headers {
      value = "content-type:" ~ $content_type ~ "\nhost:" ~ $sig_host ~ "\nx-amz-date:" ~ $amz_date ~ "\nx-amz-target:" ~ $amz_target ~ "\n"
    }
    var $signed_headers { value = "content-type;host;x-amz-date;x-amz-target" }
    var $canonical_request {
      value = "POST" ~ "\n" ~ "/" ~ "\n" ~ "" ~ "\n" ~ $canonical_headers ~ "\n" ~ $signed_headers ~ "\n" ~ $payload_hash
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

    // ============================================================
    // Chamada única à AWS Cost Explorer (POST com corpo assinado).
    // ============================================================
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
      timeout = 30
    } as $ce_result

    // ============================================================
    // F (mínimo) — teste de while + each. Executa uma única vez.
    // ============================================================
    var $continuar { value = true }
    var $iteracoes { value = 0 }
    var $max_iteracoes { value = 100 }
    var $next_token { value = null }
    var $resultados_acc { value = [] }
    var $falhou { value = false }

    while ($continuar == true && $iteracoes < $max_iteracoes) {
      each {
        var.update $iteracoes { value = $iteracoes + 1 }

        // Reconstrução do payload paginado (com NextPageToken quando existir).
        var $corpo_pag {
          value = {
            TimePeriod : {Start: $inicio, End: $fim}
            Granularity: "DAILY"
            Metrics    : ["UnblendedCost"]
            GroupBy    : [{Type: "DIMENSION", Key: "SERVICE"}]
          }
        }
        conditional {
          if ($next_token != null) {
            var.update $corpo_pag {
              value = {
                TimePeriod   : {Start: $inicio, End: $fim}
                Granularity  : "DAILY"
                Metrics      : ["UnblendedCost"]
                GroupBy      : [{Type: "DIMENSION", Key: "SERVICE"}]
                NextPageToken: $next_token
              }
            }
          }
        }

        var $corpo_pag_json { value = $corpo_pag|json_encode }

        // Nova assinatura SigV4 da página (o corpo muda com NextPageToken).
        var $amz_date_pag  { value = now|format_timestamp:"Ymd\\THis\\Z":"UTC" }
        var $datestamp_pag { value = now|format_timestamp:"Ymd":"UTC" }

        var $payload_hash_pag { value = $corpo_pag_json|sha256 }
        var $canonical_headers_pag {
          value = "content-type:" ~ $content_type ~ "\nhost:" ~ $sig_host ~ "\nx-amz-date:" ~ $amz_date_pag ~ "\nx-amz-target:" ~ $amz_target ~ "\n"
        }
        var $signed_headers_pag { value = "content-type;host;x-amz-date;x-amz-target" }
        var $canonical_request_pag {
          value = "POST" ~ "\n" ~ "/" ~ "\n" ~ "" ~ "\n" ~ $canonical_headers_pag ~ "\n" ~ $signed_headers_pag ~ "\n" ~ $payload_hash_pag
        }

        var $credential_scope_pag {
          value = $datestamp_pag ~ "/" ~ $sig_region ~ "/" ~ $sig_service ~ "/aws4_request"
        }
        var $string_to_sign_pag {
          value = "AWS4-HMAC-SHA256" ~ "\n" ~ $amz_date_pag ~ "\n" ~ $credential_scope_pag ~ "\n" ~ ($canonical_request_pag|sha256)
        }

        var $k_date_pag    { value = $datestamp_pag|hmac_sha256:("AWS4" ~ $aws_secret):true }
        var $k_region_pag  { value = $sig_region|hmac_sha256:$k_date_pag:true }
        var $k_service_pag { value = $sig_service|hmac_sha256:$k_region_pag:true }
        var $k_signing_pag { value = "aws4_request"|hmac_sha256:$k_service_pag:true }
        var $signature_pag { value = $string_to_sign_pag|hmac_sha256:$k_signing_pag }

        var $authorization_pag {
          value = "AWS4-HMAC-SHA256 Credential=" ~ $provedor.aws_access_key_id ~ "/" ~ $credential_scope_pag ~ ", SignedHeaders=" ~ $signed_headers_pag ~ ", Signature=" ~ $signature_pag
        }

        // Chamada à AWS Cost Explorer dentro do loop (sem leitura da resposta ainda).
        api.request {
          url = $sig_endpoint
          method = "POST"
          params = $corpo_pag
          headers = [
            "Content-Type: " ~ $content_type,
            "X-Amz-Target: " ~ $amz_target,
            "Host: " ~ $sig_host,
            "X-Amz-Date: " ~ $amz_date_pag,
            "Authorization: " ~ $authorization_pag
          ]
          timeout = 30
        } as $ce_result

        // Processamento da resposta necessário para a paginação.
        conditional {
          if ($ce_result.response.status == 200) {
            // Acumula os ResultsByTime desta página (sem normalizar ainda).
            var $pagina_resultados { value = ($ce_result.response.result.ResultsByTime ?? []) }
            var.update $resultados_acc { value = $resultados_acc|merge:$pagina_resultados }

            // Próxima página?
            var $token_resposta { value = ($ce_result.response.result.NextPageToken ?? null) }
            conditional {
              if ($token_resposta != null && $token_resposta != "") {
                var.update $next_token { value = $token_resposta }
              }
              else {
                var.update $continuar { value = false }
              }
            }
          }
          else {
            var.update $falhou { value = true }
            var.update $continuar { value = false }
          }
        }
      }
    }

    // ============================================================
    // G) Normalização dos ResultsByTime/Groups em memória.
    //    Sem persistência nesta etapa.
    // ============================================================
    var $normalizados { value = [] }

    foreach ($resultados_acc) {
      each as $rbt {
        var $dia { value = $rbt.TimePeriod.Start }
        var $estimado { value = ($rbt.Estimated ?? false) }

        foreach (($rbt.Groups ?? [])) {
          each as $grupo {
            var $servico { value = ($grupo.Keys|first) }
            var $valor { value = ($grupo.Metrics.UnblendedCost.Amount ?? "0") }
            var $moeda { value = ($grupo.Metrics.UnblendedCost.Unit ?? "USD") }

            var $item {
              value = {
                data    : $dia
                estimado: $estimado
                servico : $servico
                valor   : $valor
                moeda   : $moeda
                metrica : "unblended"
              }
            }
            var.update $normalizados { value = $normalizados|push:$item }
          }
        }
      }
    }

    // ============================================================
    // H) Upsert dos registros normalizados em `custos`.
    //    Chave natural: (provedor_id, data, servico, metrica).
    //    Atomicidade: só persiste quando a coleta completa teve sucesso.
    // ============================================================
    var $registros_gravados { value = 0 }

    conditional {
      if ($falhou == false) {
        foreach ($normalizados) {
      each as $item {
        db.query custos {
          where = $db.custos.provedor_id == $provedor.id && $db.custos.data == $item.data && $db.custos.servico == $item.servico && $db.custos.metrica == "unblended"
          return = {type: "single"}
        } as $existente

        conditional {
          if ($existente != null) {
            db.edit custos {
              field_name = "id"
              field_value = $existente.id
              data = {
                valor      : $item.valor
                moeda      : $item.moeda
                estimado   : $item.estimado
                coletado_em: now
              }
            }
          }
          else {
            db.add custos {
              data = {
                provedor_id: $provedor.id
                data       : $item.data
                servico    : $item.servico
                metrica    : "unblended"
                valor      : $item.valor
                moeda      : $item.moeda
                estimado   : $item.estimado
              }
            }
          }
        }

        var.update $registros_gravados { value = $registros_gravados + 1 }
      }
        }
      }
    }

    // ============================================================
    // I) Diagnóstico sanitizado, registro em coletas_custo e resposta final.
    // ============================================================
    // Diagnóstico: SOMENTE dados seguros. Nunca secret/PROV_ENC_KEY/
    // Authorization/signing keys/signature/JWE decifrado.
    var $diagnostico { value = null }
    var $mensagem { value = "" }

    conditional {
      if ($falhou == true) {
        var.update $mensagem { value = "Falha ao consultar o AWS Cost Explorer" }
        var.update $diagnostico {
          value = {
            http_status: $ce_result.response.status
            error_code : ($ce_result.response.result.Error.Code ?? null)
            error_msg  : ($ce_result.response.result.Error.Message ?? null)
            request_id : ($ce_result.response.result.RequestId ?? null)
          }
        }
      }
    }

    var $status_coleta { value = ($falhou == true) ? "erro" : "sucesso" }
    var $dias_processados { value = $resultados_acc|count }

    db.add coletas_custo {
      data = {
        provedor_id      : $provedor.id
        intervalo_inicio : $inicio
        intervalo_fim    : $fim
        status           : $status_coleta
        dias_processados : $dias_processados
        registros_gravados: $registros_gravados
        mensagem         : $mensagem
      }
    } as $registro_coleta

    var $resposta {
      value = {
        provedor_id      : $provedor.id
        intervalo        : {inicio: $inicio, fim: $fim}
        status           : $status_coleta
        dias_processados : $dias_processados
        registros_gravados: $registros_gravados
        mensagem         : $mensagem
        diagnostico      : $diagnostico
      }
    }
  }

  response = $resposta
  guid = "GDi2RfIkDnKVVZfym3nlxIoKdyY"
}
