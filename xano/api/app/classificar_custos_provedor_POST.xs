query "provedores/{id}/classificar-custos" verb=POST {
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
    // 1) Autorização: classificação é operação administrativa (backend).
    // ============================================================
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

    // A Tag Key de alocação é obrigatória para a classificação por projeto.
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

    // ============================================================
    // B.1) Destino e componentes da assinatura SigV4 (AWS Cost Explorer,
    //      service=ce, region=us-east-1).
    // ============================================================
    var $sig_host { value = "ce.us-east-1.amazonaws.com" }
    var $canonical_uri { value = "/" }
    var $sig_endpoint { value = "https://ce.us-east-1.amazonaws.com/" }

    // Tag Key de alocação configurada no provedor (Key padrão/recomendada: "PRJ").
    // A Key identifica a finalidade da tag; o Value é diretamente projetos.codigo.
    var $tag_key { value = $provedor.tag_alocacao_projeto }
    // Prefixo que a resposta do Cost Explorer antepõe ao valor: "<TagKey>$".
    var $tag_prefixo { value = $tag_key ~ "$" }
    var $tag_prefixo_len { value = $tag_prefixo|strlen }

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
    // $sig_host, $canonical_uri e $sig_endpoint definidos em B.1.
    var $sig_service { value = "ce" }
    var $sig_region  { value = "us-east-1" }
    var $amz_target  { value = "AWSInsightsIndexService.GetCostAndUsage" }
    var $content_type { value = "application/x-amz-json-1.1" }

    // ============================================================
    // D) Paginação: busca todas as páginas antes de persistir.
    //    GroupBy = [ {TAG, <tag_key>}, {DIMENSION, SERVICE} ].
    // ============================================================
    var $continuar { value = true }
    var $iteracoes { value = 0 }
    var $max_iteracoes { value = 100 }
    var $next_token { value = null }
    var $resultados_acc { value = [] }
    var $falhou { value = false }
    var $ce_result { value = null }

    while ($continuar == true && $iteracoes < $max_iteracoes) {
      each {
        var.update $iteracoes { value = $iteracoes + 1 }

        // Reconstrução do payload paginado (com NextPageToken quando existir).
        var $corpo_pag {
          value = {
            TimePeriod : {Start: $inicio, End: $fim}
            Granularity: "DAILY"
            Metrics    : ["UnblendedCost"]
            GroupBy    : [{Type: "TAG", Key: $tag_key}, {Type: "DIMENSION", Key: "SERVICE"}]
          }
        }
        conditional {
          if ($next_token != null) {
            var.update $corpo_pag {
              value = {
                TimePeriod   : {Start: $inicio, End: $fim}
                Granularity  : "DAILY"
                Metrics      : ["UnblendedCost"]
                GroupBy      : [{Type: "TAG", Key: $tag_key}, {Type: "DIMENSION", Key: "SERVICE"}]
                NextPageToken: $next_token
              }
            }
          }
        }

        var $corpo_pag_json { value = $corpo_pag|json_encode }

        // Assinatura SigV4 da página (o corpo muda com NextPageToken).
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

        // Chamada à AWS Cost Explorer.
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
            var $pagina_resultados { value = ($ce_result.response.result.ResultsByTime ?? []) }
            var.update $resultados_acc { value = $resultados_acc|merge:$pagina_resultados }

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
    // E) Detecção de tag de alocação inativa/não propagada.
    //    Se a consulta por TAG não retornou nenhum grupo com a dimensão de
    //    tag esperada (nenhuma Key no formato "<tag_key>$..."), tratamos
    //    como tag inativa/não propagada — erro sanitizado, sem alterar a AWS.
    // ============================================================
    var $tag_dimensao_presente { value = false }

    conditional {
      if ($falhou == false) {
        foreach ($resultados_acc) {
          each as $rbt {
            foreach (($rbt.Groups ?? [])) {
              each as $grupo {
                var $chave_tag_bruta { value = ($grupo.Keys|first) }
                conditional {
                  if ($chave_tag_bruta != null && ($chave_tag_bruta|starts_with:$tag_prefixo)) {
                    var.update $tag_dimensao_presente { value = true }
                  }
                }
              }
            }
          }
        }
      }
    }

    // Marca falha de tag inativa somente quando houve resultados mas nenhum
    // deles trouxe a dimensão de tag esperada.
    var $tag_inativa { value = false }
    conditional {
      if ($falhou == false && ($resultados_acc|count) > 0 && $tag_dimensao_presente == false) {
        var.update $tag_inativa { value = true }
        var.update $falhou { value = true }
      }
    }

    // ============================================================
    // F) Normalização + classificação por projeto (Tag Value = projetos.codigo).
    //    Só prossegue quando a coleta de todas as páginas teve sucesso.
    // ============================================================
    var $classificados { value = [] }
    var $nao_alocados { value = 0 }
    var $tags_sem_projeto { value = 0 }
    var $projetos_inativos { value = 0 }

    conditional {
      if ($falhou == false) {
        foreach ($resultados_acc) {
          each as $rbt {
            var $dia { value = $rbt.TimePeriod.Start }
            var $estimado { value = ($rbt.Estimated ?? false) }

            foreach (($rbt.Groups ?? [])) {
              each as $grupo {
                // Keys[0] = "<tag_key>$<valor>" ; Keys[1] = serviço.
                var $chave_tag { value = ($grupo.Keys|first) }
                var $servico { value = ($grupo.Keys[1] ?? "") }
                var $valor { value = ($grupo.Metrics.UnblendedCost.Amount ?? "0") }
                var $moeda { value = ($grupo.Metrics.UnblendedCost.Unit ?? "USD") }

                // Extrai o Value da tag removendo exatamente o prefixo "<tag_key>$".
                // A Key identifica a finalidade; o Value é diretamente o codigo
                // do projeto (sem qualquer prefixo embutido no Value).
                var $tag_value { value = "" }
                conditional {
                  if ($chave_tag != null && ($chave_tag|starts_with:$tag_prefixo)) {
                    var.update $tag_value { value = $chave_tag|substr:$tag_prefixo_len }
                  }
                }

                // Value presente → candidato a projeto; Value vazio → não alocado.
                conditional {
                  if ($tag_value != "") {
                    // Value é diretamente o codigo. Normaliza trim + maiúsculas
                    // para casar com projetos.codigo (filters=trim|upper),
                    // independentemente de espaços/caixa vindos da tag AWS.
                    // Ex.: PRJ$PAGAMENTOS → tag_value "PAGAMENTOS" → codigo "PAGAMENTOS".
                    var $codigo { value = ($tag_value|trim)|to_upper }

                    // Busca o projeto pelo codigo INDEPENDENTEMENTE do status,
                    // para distinguir inexistente (tags_sem_projeto) de
                    // inativo (projetos_inativos). NÃO filtra por status aqui.
                    db.query projetos {
                      where = $db.projetos.codigo == $codigo
                      return = {type: "single"}
                    } as $projeto

                    conditional {
                      if ($projeto == null) {
                        // Não existe projeto com esse codigo: não cria projeto.
                        var.update $tags_sem_projeto { value = $tags_sem_projeto + 1 }
                      }
                      else {
                        conditional {
                          if ($projeto.status == "ativo") {
                            // Projeto ativo: grava normalmente em custos_projeto.
                            var $item {
                              value = {
                                projeto_id: $projeto.id
                                data      : $dia
                                servico   : $servico
                                valor     : $valor
                                moeda     : $moeda
                                estimado  : $estimado
                                metrica   : "unblended"
                              }
                            }
                            var.update $classificados { value = $classificados|push:$item }
                          }
                          else {
                            // Projeto existe porém NÃO está ativo: não grava.
                            var.update $projetos_inativos { value = $projetos_inativos + 1 }
                          }
                        }
                      }
                    }
                  }
                  else {
                    // Value ausente/vazio (ex.: "PRJ$"): custo não alocado (não descartado).
                    var.update $nao_alocados { value = $nao_alocados + 1 }
                  }
                }
              }
            }
          }
        }
      }
    }

    // ============================================================
    // G) Upsert idempotente em custos_projeto.
    //    Chave natural: (provedor_id, projeto_id, data, servico, metrica).
    //    Só persiste quando a classificação completa teve sucesso.
    // ============================================================
    var $registros_gravados { value = 0 }

    conditional {
      if ($falhou == false) {
        foreach ($classificados) {
          each as $item {
            db.query custos_projeto {
              where = $db.custos_projeto.provedor_id == $provedor.id && $db.custos_projeto.projeto_id == $item.projeto_id && $db.custos_projeto.data == $item.data && $db.custos_projeto.servico == $item.servico && $db.custos_projeto.metrica == "unblended"
              return = {type: "single"}
            } as $existente

            conditional {
              if ($existente != null) {
                db.edit custos_projeto {
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
                db.add custos_projeto {
                  data = {
                    provedor_id: $provedor.id
                    projeto_id : $item.projeto_id
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
    // H) Diagnóstico sanitizado, estado em coletas_classificacao e resposta.
    //    Nunca secret/PROV_ENC_KEY/Authorization/signing keys/signature/JWE.
    // ============================================================
    var $diagnostico { value = null }
    var $mensagem { value = "" }

    conditional {
      if ($falhou == true) {
        conditional {
          if ($tag_inativa == true) {
            var.update $mensagem { value = "Tag de alocação de custo inativa ou ainda não propagada na conta AWS" }
          }
          else {
            var.update $mensagem { value = "Falha ao consultar o AWS Cost Explorer" }
            var.update $diagnostico {
              value = {
                http_status: ($ce_result != null) ? $ce_result.response.status : null
                error_code : ($ce_result.response.result.Error.Code ?? null)
                error_msg  : ($ce_result.response.result.Error.Message ?? null)
                request_id : ($ce_result.response.result.RequestId ?? null)
              }
            }
          }
        }
      }
    }

    var $status_classificacao { value = ($falhou == true) ? "erro" : "sucesso" }

    db.add coletas_classificacao {
      data = {
        provedor_id      : $provedor.id
        intervalo_inicio : $inicio
        intervalo_fim    : $fim
        status           : $status_classificacao
        registros_gravados: $registros_gravados
        nao_alocados     : $nao_alocados
        tags_sem_projeto : $tags_sem_projeto
        projetos_inativos: $projetos_inativos
        mensagem         : $mensagem
      }
    } as $registro_classificacao

    var $resposta {
      value = {
        provedor_id      : $provedor.id
        intervalo        : {inicio: $inicio, fim: $fim}
        status           : $status_classificacao
        registros_gravados: $registros_gravados
        nao_alocados     : $nao_alocados
        tags_sem_projeto : $tags_sem_projeto
        projetos_inativos: $projetos_inativos
        mensagem         : $mensagem
        diagnostico      : $diagnostico
      }
    }
  }

  response = $resposta
  guid = "uymc80keb99U1kXi1QXQ6zgrtoA"
}
