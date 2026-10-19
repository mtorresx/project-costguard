query "provedores/{id}/descobrir-projetos" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
  }

  stack {
    // ============================================================
    // 1) Autorização: descoberta é operação administrativa (backend).
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

    precondition ($provedor.tag_alocacao_projeto != null && $provedor.tag_alocacao_projeto != "") {
      error_type = "inputerror"
      error = "Tag de alocação de projeto não configurada no provedor"
    }

    // ============================================================
    // B) Decifra o secret (SÓ em memória, imediatamente antes de assinar).
    // ============================================================
    var $aws_secret {
      value = $provedor.aws_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"
    }

    var $tag_key { value = $provedor.tag_alocacao_projeto }

    // ============================================================
    // B.1) Resolução do destino (AWS real x AWS Mock) e dos componentes da
    //      assinatura dependentes do destino. UMA única implementação SigV4:
    //      apenas host, canonical URI e URL mudam conforme usar_mock.
    //      usar_mock=false NÃO lê nem depende de MOCK_BASE_URL.
    // ============================================================
    var $eh_mock { value = ($provedor.usar_mock == true) }

    // Defaults = AWS real (comportamento atual, inalterado).
    var $sig_host { value = "ce.us-east-1.amazonaws.com" }
    var $canonical_uri { value = "/" }
    var $sig_endpoint { value = "https://ce.us-east-1.amazonaws.com/" }

    conditional {
      if ($eh_mock == true) {
        precondition ($env.MOCK_BASE_URL != null && $env.MOCK_BASE_URL != "") {
          error_type = "inputerror"
          error = "Ambiente Mock não configurado (MOCK_BASE_URL ausente)"
        }
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
        var.update $sig_host { value = $mock_host }
        var.update $canonical_uri { value = "/aws/" ~ $provedor.identificador_conta ~ "/ce/" }
        var.update $sig_endpoint { value = $mock_base_norm ~ "/aws/" ~ $provedor.identificador_conta ~ "/ce/" }
      }
    }

    // ============================================================
    // C) Intervalo (GetTags exige TimePeriod). Start inclusivo / End exclusivo;
    //    default: últimos 30 dias (coerente com as demais operações).
    // ============================================================
    var $agora_ts  { value = now|to_int }
    var $inicio_ts { value = $agora_ts - 2592000000 }
    var $fim    { value = $agora_ts|format_timestamp:"Y-m-d":"UTC" }
    var $inicio { value = $inicio_ts|format_timestamp:"Y-m-d":"UTC" }

    // Constantes SigV4 (service=ce, region=us-east-1). host/URI/endpoint vêm de B.1.
    var $sig_service { value = "ce" }
    var $sig_region  { value = "us-east-1" }
    var $amz_target  { value = "AWSInsightsIndexService.GetTags" }
    var $content_type { value = "application/x-amz-json-1.1" }

    // ============================================================
    // D) Paginação GetTags: consulta todas as páginas, reassinando cada uma.
    //    Acumula os valores brutos de Tags[] antes de normalizar.
    // ============================================================
    var $continuar { value = true }
    var $iteracoes { value = 0 }
    var $max_iteracoes { value = 100 }
    var $next_token { value = null }
    var $tags_acc { value = [] }
    var $falhou { value = false }
    var $gt_result { value = null }

    while ($continuar == true && $iteracoes < $max_iteracoes) {
      each {
        var.update $iteracoes { value = $iteracoes + 1 }

        // Corpo GetTags (com NextPageToken quando existir).
        var $corpo_pag {
          value = {
            TimePeriod: {Start: $inicio, End: $fim}
            TagKey    : $tag_key
          }
        }
        conditional {
          if ($next_token != null) {
            var.update $corpo_pag {
              value = {
                TimePeriod   : {Start: $inicio, End: $fim}
                TagKey       : $tag_key
                NextPageToken: $next_token
              }
            }
          }
        }

        var $corpo_pag_json { value = $corpo_pag|json_encode }

        // Assinatura SigV4 da página (coerente com o destino de B.1).
        var $amz_date_pag  { value = now|format_timestamp:"Ymd\\THis\\Z":"UTC" }
        var $datestamp_pag { value = now|format_timestamp:"Ymd":"UTC" }

        var $payload_hash_pag { value = $corpo_pag_json|sha256 }
        var $canonical_headers_pag {
          value = "content-type:" ~ $content_type ~ "\nhost:" ~ $sig_host ~ "\nx-amz-date:" ~ $amz_date_pag ~ "\nx-amz-target:" ~ $amz_target ~ "\n"
        }
        var $signed_headers_pag { value = "content-type;host;x-amz-date;x-amz-target" }
        var $canonical_request_pag {
          value = "POST" ~ "\n" ~ $canonical_uri ~ "\n" ~ "" ~ "\n" ~ $canonical_headers_pag ~ "\n" ~ $signed_headers_pag ~ "\n" ~ $payload_hash_pag
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
        } as $gt_result

        conditional {
          if ($gt_result.response.status == 200) {
            // Contrato GetTags: valores da Tag Key em Tags[] (strings).
            var $pagina_tags { value = ($gt_result.response.result.Tags ?? []) }
            var.update $tags_acc { value = $tags_acc|merge:$pagina_tags }

            var $token_resposta { value = ($gt_result.response.result.NextPageToken ?? null) }
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
    // E) Normalização + comparação (só em sucesso). Em falha, resposta de erro
    //    sanitizada, sem lista parcial. Um único `response` no final.
    // ============================================================
    var $descobertos { value = [] }
    var $diagnostico { value = null }

    conditional {
      if ($falhou == false) {
        // F) Normalização: trim + upper; descarta vazio; deduplica.
        //    (GetTags: valores já são o codigo candidato — NÃO usar parser "PRJ$".)
        var $codigos { value = [] }
        foreach ($tags_acc) {
          each as $valor_bruto {
            var $codigo_norm { value = ($valor_bruto|trim)|to_upper }
            conditional {
              if ($codigo_norm != "") {
                var $ja_tem { value = false }
                foreach ($codigos) {
                  each as $c {
                    conditional {
                      if ($c == $codigo_norm) {
                        var.update $ja_tem { value = true }
                      }
                    }
                  }
                }
                conditional {
                  if ($ja_tem == false) {
                    var.update $codigos { value = $codigos|push:$codigo_norm }
                  }
                }
              }
            }
          }
        }

        // Ordenação simples por codigo (segura; lista pequena de strings).
        var.update $codigos { value = $codigos|sort:"asc" }

        // G) Comparação com projetos.codigo (sem gravar nada).
        foreach ($codigos) {
          each as $codigo {
            db.query projetos {
              where = $db.projetos.codigo == $codigo
              return = {type: "single"}
            } as $proj

            var $item {
              value = {
                codigo    : $codigo
                existente : ($proj != null)
                projeto_id: ($proj.id ?? null)
              }
            }
            var.update $descobertos { value = $descobertos|push:$item }
          }
        }
      }
      else {
        // Falha: diagnóstico sanitizado (sem segredo/Authorization/JWE).
        var.update $diagnostico {
          value = {
            http_status: ($gt_result != null) ? $gt_result.response.status : null
            error_code : ($gt_result.response.result.Error.Code ?? null)
            error_msg  : ($gt_result.response.result.Error.Message ?? null)
            request_id : ($gt_result.response.result.RequestId ?? null)
          }
        }
      }
    }

    var $status_descoberta { value = ($falhou == true) ? "erro" : "sucesso" }
    var $mensagem { value = ($falhou == true) ? "Falha ao consultar GetTags no Cost Explorer" : "" }

    var $resposta {
      value = {
        provedor_id: $provedor.id
        tag_key    : $tag_key
        status     : $status_descoberta
        mensagem   : $mensagem
        descobertos: $descobertos
        diagnostico: $diagnostico
      }
    }
  }

  response = $resposta
}
