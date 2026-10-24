query "provedores/{id}/classificar-custos-equipe" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
    // Body opcional. `id` vem apenas do path.
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

    // Tag Key de projeto é obrigatória.
    precondition ($provedor.tag_alocacao_projeto != null && $provedor.tag_alocacao_projeto != "") {
      error_type = "inputerror"
      error = "Tag de alocação de projeto não configurada no provedor"
    }

    // ============================================================
    // A.1) Intervalo (antes de qualquer chamada externa).
    //      Start inclusivo, End exclusivo. Padrão: últimos 30 dias até ontem.
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

    // ============================================================
    // A.2) Tag Keys: projeto (obrigatória) e equipe efetiva (fallback EQP
    //      apenas quando o campo do provedor é nulo/vazio).
    // ============================================================
    var $tag_key_prj { value = $provedor.tag_alocacao_projeto }
    var $tag_key_eqp_raw { value = ($provedor.tag_alocacao_equipe ?? "") }
    var $tag_key_eqp { value = (($tag_key_eqp_raw|trim) != "") ? $tag_key_eqp_raw : "EQP" }

    // Prefixos que o Cost Explorer antepõe ao valor: "<TagKey>$".
    var $prefixo_prj { value = $tag_key_prj ~ "$" }
    var $prefixo_prj_len { value = $prefixo_prj|strlen }
    var $prefixo_eqp { value = $tag_key_eqp ~ "$" }
    var $prefixo_eqp_len { value = $prefixo_eqp|strlen }

    // ============================================================
    // B) Destino (AWS real x AWS Mock) e componentes da assinatura.
    //    Mesmo padrão dos endpoints existentes. usar_mock=false NÃO lê
    //    nem depende de MOCK_BASE_URL.
    // ============================================================
    var $eh_mock { value = ($provedor.usar_mock == true) }

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
    // C) Decifra o secret (SÓ em memória, imediatamente antes de assinar).
    // ============================================================
    var $aws_secret {
      value = $provedor.aws_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"
    }

    var $sig_service { value = "ce" }
    var $sig_region  { value = "us-east-1" }
    var $amz_target  { value = "AWSInsightsIndexService.GetCostAndUsage" }
    var $content_type { value = "application/x-amz-json-1.1" }

    // Identificador único desta execução.
    var $sync_id { value = ""|uuid }

    // ============================================================
    // D) Etapa 1 — Fetch: busca TODAS as páginas antes de persistir.
    //    GroupBy = [ {TAG, projeto}, {TAG, equipe} ] — sem SERVICE.
    // ============================================================
    var $continuar { value = true }
    var $iteracoes { value = 0 }
    var $max_iteracoes { value = 100 }
    var $next_token { value = null }
    var $resultados_acc { value = [] }
    var $falhou { value = false }
    var $limite_paginacao { value = false }
    var $moeda_divergente { value = false }
    var $falha_normalizacao { value = false }
    var $falha_persistencia { value = false }
    var $ce_result { value = null }

    while ($continuar == true && $iteracoes < $max_iteracoes) {
      each {
        var.update $iteracoes { value = $iteracoes + 1 }

        var $corpo_pag {
          value = {
            TimePeriod : {Start: $inicio, End: $fim}
            Granularity: "DAILY"
            Metrics    : ["UnblendedCost"]
            GroupBy    : [{Type: "TAG", Key: $tag_key_prj}, {Type: "TAG", Key: $tag_key_eqp}]
          }
        }
        conditional {
          if ($next_token != null) {
            var.update $corpo_pag {
              value = {
                TimePeriod   : {Start: $inicio, End: $fim}
                Granularity  : "DAILY"
                Metrics      : ["UnblendedCost"]
                GroupBy      : [{Type: "TAG", Key: $tag_key_prj}, {Type: "TAG", Key: $tag_key_eqp}]
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

    // Limite defensivo atingido com NextPageToken pendente: ERRO (nunca
    // sucesso parcial).
    conditional {
      if ($falhou == false && $continuar == true) {
        var.update $falhou { value = true }
        var.update $limite_paginacao { value = true }
      }
    }

    // ============================================================
    // E) Etapa 2 — Normalização + agregação em memória (somente leitura
    //    no banco: nenhuma equipe é criada nesta etapa).
    //    Chave lógica: (projeto_id, codigo_equipe, data, metrica); a moeda
    //    acompanha a linha e não pode divergir dentro da mesma chave.
    // ============================================================
    var $nao_alocados { value = 0 }
    var $tags_sem_projeto { value = 0 }
    var $projetos_inativos { value = 0 }
    // Cache codigo -> {id, status}; status "inexistente" quando não existe.
    var $cache_projetos { value = {} }
    // Agregados: chave -> item; $agg_chaves preserva a ordem de inserção.
    var $agg { value = {} }
    var $agg_chaves { value = [] }
    // DIAGNÓSTICO TEMPORÁRIO (BUG-4): identificador fixo da última operação
    // iniciada na normalização. Nunca contém dados da AWS nem segredos.
    var $etapa { value = "" }

    conditional {
      if ($falhou == false) {
        // Falha em parsing/normalização/agregação/resolução → erro registrado,
        // sem upserts e sem reconciliação.
        try_catch {
          try {
        foreach ($resultados_acc) {
          each as $rbt {
            var $dia { value = $rbt.TimePeriod.Start }
            var $estimado { value = ($rbt.Estimated ?? false) }

            foreach (($rbt.Groups ?? [])) {
              each as $grupo {
                var.update $etapa { value = "inicio_grupo" }
                var.update $etapa { value = "extrair_prj" }
                var $chave_prj { value = ($grupo.Keys|first) }
                var.update $etapa { value = "extrair_eqp" }
                var $chave_eqp { value = ($grupo.Keys[1] ?? "") }
                var.update $etapa { value = "extrair_valor" }
                var $valor_grupo { value = ($grupo.Metrics.UnblendedCost.Amount ?? "0")|to_decimal }
                var.update $etapa { value = "extrair_moeda" }
                var $moeda_grupo { value = ($grupo.Metrics.UnblendedCost.Unit ?? "USD") }

                // Remove exatamente "<Key>$", depois trim + upper.
                var.update $etapa { value = "normalizar_prj" }
                var $valor_prj { value = "" }
                conditional {
                  if ($chave_prj != null && ($chave_prj|starts_with:$prefixo_prj)) {
                    var.update $valor_prj { value = $chave_prj|substr:$prefixo_prj_len }
                  }
                }
                var $codigo_prj { value = ($valor_prj|trim)|to_upper }

                var.update $etapa { value = "normalizar_eqp" }
                var $valor_eqp { value = "" }
                conditional {
                  if ($chave_eqp != null && ($chave_eqp|starts_with:$prefixo_eqp)) {
                    var.update $valor_eqp { value = $chave_eqp|substr:$prefixo_eqp_len }
                  }
                }
                var $codigo_eqp { value = ($valor_eqp|trim)|to_upper }

                conditional {
                  if ($codigo_prj == "") {
                    // Sem projeto (ex.: "PRJ$"): não alocado, mesmo com equipe.
                    var.update $nao_alocados { value = $nao_alocados + 1 }
                  }
                  else {
                    // Resolve o projeto uma vez por código (cache).
                    // Chave interna segura do mapa (o codigo_prj real segue na lógica).
                    var.update $etapa { value = "cache_hash" }
                    var $cache_prj_key { value = "k" ~ ($codigo_prj|sha256) }
                    var.update $etapa { value = "cache_has" }
                    conditional {
                      if (($cache_projetos|has:$cache_prj_key) == false) {
                        var.update $etapa { value = "cache_consulta" }
                        db.query projetos {
                          where = $db.projetos.codigo == $codigo_prj
                          return = {type: "single"}
                        } as $proj_db

                        conditional {
                          if ($proj_db == null) {
                            var.update $etapa { value = "cache_set" }
                            var $cache_item_inexistente {
                              value = {
                                id    : 0
                                status: "inexistente"
                              }
                            }
                            var.update $cache_projetos {
                              value = $cache_projetos|set:$cache_prj_key:$cache_item_inexistente
                            }
                          }
                          else {
                            var.update $etapa { value = "cache_set" }
                            var $cache_item_projeto {
                              value = {
                                id    : $proj_db.id
                                status: $proj_db.status
                              }
                            }
                            var.update $cache_projetos {
                              value = $cache_projetos|set:$cache_prj_key:$cache_item_projeto
                            }
                          }
                        }
                      }
                    }

                    var.update $etapa { value = "cache_get" }
                    var $proj { value = $cache_projetos|get:$cache_prj_key:null }

                    var.update $etapa { value = "resolver_projeto" }
                    conditional {
                      if ($proj.status == "inexistente") {
                        var.update $tags_sem_projeto { value = $tags_sem_projeto + 1 }
                      }
                      elseif ($proj.status != "ativo") {
                        var.update $projetos_inativos { value = $projetos_inativos + 1 }
                      }
                      else {
                        // Projeto ativo: agrega por (projeto, equipe, dia, métrica).
                        var.update $etapa { value = "montar_chave_agg" }
                        var $chave_agg { value = ($proj.id|to_text) ~ "|" ~ $codigo_eqp ~ "|" ~ $dia ~ "|unblended" }

                        // Chave interna segura do mapa; a chave lógica acima não muda.
                        var.update $etapa { value = "agg_hash" }
                        var $agg_key { value = "k" ~ ($chave_agg|sha256) }
                        var.update $etapa { value = "agg_has" }
                        conditional {
                          if (($agg|has:$agg_key) == false) {
                            // Objeto montado em variável própria: objetos
                            // multi-linha não podem ser argumento de filtro.
                            var.update $etapa { value = "agg_montar_item" }
                            var $novo_item {
                              value = {
                                projeto_id   : $proj.id
                                codigo_equipe: $codigo_eqp
                                data         : $dia
                                valor        : $valor_grupo
                                moeda        : $moeda_grupo
                                estimado     : $estimado
                              }
                            }
                            var.update $etapa { value = "agg_set_novo" }
                            var.update $agg {
                              value = $agg|set:$agg_key:$novo_item
                            }
                            var.update $etapa { value = "agg_push" }
                            var.update $agg_chaves { value = $agg_chaves|push:$agg_key }
                          }
                          else {
                            var.update $etapa { value = "agg_get" }
                            var $item_atual { value = $agg|get:$agg_key:null }
                            conditional {
                              if ($item_atual.moeda != $moeda_grupo) {
                                // Nunca somar moedas diferentes: erro controlado.
                                var.update $moeda_divergente { value = true }
                              }
                              else {
                                var.update $etapa { value = "agg_montar_soma" }
                                var $item_somado {
                                  value = {
                                    projeto_id   : $item_atual.projeto_id
                                    codigo_equipe: $item_atual.codigo_equipe
                                    data         : $item_atual.data
                                    valor        : $item_atual.valor + $valor_grupo
                                    moeda        : $item_atual.moeda
                                    estimado     : $item_atual.estimado || $estimado
                                  }
                                }
                                var.update $etapa { value = "agg_set_soma" }
                                var.update $agg {
                                  value = $agg|set:$agg_key:$item_somado
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
                var.update $etapa { value = "fim_grupo" }
              }
            }
          }
        }
          }
          catch {
            var.update $falhou { value = true }
            var.update $falha_normalizacao { value = true }
          }
        }
      }
    }

    conditional {
      if ($moeda_divergente == true) {
        var.update $falhou { value = true }
      }
    }

    // ============================================================
    // F) Etapa 3 — Resolução/criação de equipes + upserts (somente após
    //    fetch e normalização completos). Sem transação global: em falha
    //    parcial a próxima execução converge via upsert.
    // ============================================================
    var $registros_gravados { value = 0 }
    var $sem_responsavel { value = 0 }
    var $equipes_criadas { value = 0 }
    var $linhas_com_equipe { value = 0 }
    // Cache "<projeto_id>|<codigo>" -> equipe_id.
    var $cache_equipes { value = {} }

    conditional {
      if ($falhou == false) {
        try_catch {
          try {
            foreach ($agg_chaves) {
              each as $chave {
                var $item { value = $agg|get:$chave:null }
                var $equipe_id_res { value = null }

                conditional {
                  if ($item.codigo_equipe == "") {
                    // "Sem responsável": equipe_id=null, sem equipe fictícia.
                    var.update $sem_responsavel { value = $sem_responsavel + 1 }
                  }
                  else {
                    var.update $linhas_com_equipe { value = $linhas_com_equipe + 1 }
                    var $chave_eq { value = ($item.projeto_id|to_text) ~ "|" ~ $item.codigo_equipe }
                    var $chave_eq_key { value = "k" ~ ($chave_eq|sha256) }

                    conditional {
                      if ($cache_equipes|has:$chave_eq_key) {
                        var.update $equipe_id_res { value = $cache_equipes|get:$chave_eq_key:null }
                      }
                      else {
                        db.query equipes {
                          where = $db.equipes.projeto_id == $item.projeto_id && $db.equipes.codigo == $item.codigo_equipe
                          return = {type: "single"}
                        } as $eq

                        conditional {
                          if ($eq == null) {
                            try_catch {
                              try {
                                db.add equipes {
                                  data = {
                                    nome       : $item.codigo_equipe
                                    codigo     : $item.codigo_equipe
                                    projeto_id : $item.projeto_id
                                    auto_gerada: true
                                  }
                                } as $eq_novo
                                var.update $equipe_id_res { value = $eq_novo.id }
                                var.update $equipes_criadas { value = $equipes_criadas + 1 }
                              }
                              catch {
                                // Colisão no índice único (projeto_id, codigo), ex.:
                                // inventário criou a mesma equipe ao mesmo tempo.
                                // Rebusca e reutiliza; se ainda não existir, propaga.
                                db.query equipes {
                                  where = $db.equipes.projeto_id == $item.projeto_id && $db.equipes.codigo == $item.codigo_equipe
                                  return = {type: "single"}
                                } as $eq_rebusca
                                precondition ($eq_rebusca != null) {
                                  error_type = "inputerror"
                                  error = "Falha ao criar equipe"
                                }
                                var.update $equipe_id_res { value = $eq_rebusca.id }
                              }
                            }
                          }
                          else {
                            var.update $equipe_id_res { value = $eq.id }
                          }
                        }

                        var.update $cache_equipes { value = $cache_equipes|set:$chave_eq_key:$equipe_id_res }
                      }
                    }
                  }
                }

                // Upsert pela chave única (provedor, projeto, codigo_equipe, data, metrica).
                db.query custos_equipe {
                  where = $db.custos_equipe.provedor_id == $provedor.id && $db.custos_equipe.projeto_id == $item.projeto_id && $db.custos_equipe.codigo_equipe == $item.codigo_equipe && $db.custos_equipe.data == $item.data && $db.custos_equipe.metrica == "unblended"
                  return = {type: "single"}
                } as $existente

                conditional {
                  if ($existente != null) {
                    db.edit custos_equipe {
                      field_name = "id"
                      field_value = $existente.id
                      data = {
                        equipe_id  : $equipe_id_res
                        valor      : $item.valor
                        moeda      : $item.moeda
                        estimado   : $item.estimado
                        sync_id    : $sync_id
                        coletado_em: now
                      }
                    }
                  }
                  else {
                    db.add custos_equipe {
                      data = {
                        provedor_id  : $provedor.id
                        projeto_id   : $item.projeto_id
                        equipe_id    : $equipe_id_res
                        codigo_equipe: $item.codigo_equipe
                        data         : $item.data
                        metrica      : "unblended"
                        valor        : $item.valor
                        moeda        : $item.moeda
                        estimado     : $item.estimado
                        sync_id      : $sync_id
                      }
                    }
                  }
                }

                var.update $registros_gravados { value = $registros_gravados + 1 }
              }
            }
          }
          catch {
            var.update $falhou { value = true }
            var.update $falha_persistencia { value = true }
          }
        }
      }
    }

    // ============================================================
    // G) Etapa 4 — Reconciliação da janela por sync_id. SOMENTE quando
    //    fetch, normalização e TODOS os upserts terminaram com sucesso.
    //    Remove apenas custos_equipe: mesmo provedor; data em [inicio, fim);
    //    projeto atualmente ativo; sync_id diferente do atual ou nulo.
    // ============================================================
    var $registros_removidos { value = 0 }

    conditional {
      if ($falhou == false) {
        try_catch {
          try {
            // Projetos atualmente ativos (lidos no momento da reconciliação).
            db.query projetos {
              where = $db.projetos.status == "ativo"
              return = {type: "list"}
            } as $projetos_ativos

            var $ativos { value = {} }
            foreach ($projetos_ativos) {
              each as $pa {
                var $ativo_key { value = "k" ~ (($pa.id|to_text)|sha256) }
                var.update $ativos { value = $ativos|set:$ativo_key:true }
              }
            }

            db.query custos_equipe {
              where = $db.custos_equipe.provedor_id == $provedor.id && $db.custos_equipe.data >= $inicio && $db.custos_equipe.data < $fim && ($db.custos_equipe.sync_id == null || $db.custos_equipe.sync_id != $sync_id)
              return = {type: "list"}
            } as $candidatos

            foreach ($candidatos) {
              each as $cand {
                var $cand_key { value = "k" ~ (($cand.projeto_id|to_text)|sha256) }
                conditional {
                  if ($ativos|has:$cand_key) {
                    db.del custos_equipe {
                      field_name = "id"
                      field_value = $cand.id
                    }
                    var.update $registros_removidos { value = $registros_removidos + 1 }
                  }
                }
              }
            }
          }
          catch {
            var.update $falhou { value = true }
            var.update $falha_persistencia { value = true }
          }
        }
      }
    }

    // ============================================================
    // H) Aviso não bloqueante, diagnóstico sanitizado, estado e resposta.
    //    Nunca secret/PROV_ENC_KEY/Authorization/signing keys/JWE/sync_id.
    // ============================================================
    var $aviso { value = null }
    conditional {
      if ($falhou == false && ($agg_chaves|count) > 0 && $linhas_com_equipe == 0) {
        var.update $aviso { value = "Nenhum custo com equipe foi encontrado na janela. Confira se a Tag Key de equipe '" ~ $tag_key_eqp ~ "' está ativada como Cost Allocation Tag na conta AWS." }
      }
    }

    var $diagnostico { value = null }
    var $mensagem { value = "" }

    conditional {
      if ($falhou == true) {
        conditional {
          if ($limite_paginacao == true) {
            var.update $mensagem { value = "Limite de paginação atingido com resultados pendentes no AWS Cost Explorer" }
          }
          elseif ($moeda_divergente == true) {
            var.update $mensagem { value = "Custos com moedas diferentes na mesma chave; agregação não suportada" }
          }
          elseif ($falha_normalizacao == true) {
            var.update $mensagem { value = "Falha ao processar a resposta do AWS Cost Explorer (etapa: " ~ $etapa ~ ")" }
          }
          elseif ($falha_persistencia == true) {
            var.update $mensagem { value = "Falha ao persistir custos por equipe; reexecute a classificação" }
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

    var $status_execucao { value = ($falhou == true) ? "erro" : "sucesso" }

    db.add coletas_custos_equipe {
      data = {
        provedor_id        : $provedor.id
        sync_id            : $sync_id
        intervalo_inicio   : $inicio
        intervalo_fim      : $fim
        status             : $status_execucao
        registros_gravados : $registros_gravados
        registros_removidos: $registros_removidos
        nao_alocados       : $nao_alocados
        tags_sem_projeto   : $tags_sem_projeto
        projetos_inativos  : $projetos_inativos
        sem_responsavel    : $sem_responsavel
        equipes_criadas    : $equipes_criadas
        aviso              : $aviso
        mensagem           : $mensagem
      }
    } as $registro_execucao

    var $resposta {
      value = {
        provedor_id        : $provedor.id
        intervalo          : {inicio: $inicio, fim: $fim}
        status             : $status_execucao
        registros_gravados : $registros_gravados
        registros_removidos: $registros_removidos
        nao_alocados       : $nao_alocados
        tags_sem_projeto   : $tags_sem_projeto
        projetos_inativos  : $projetos_inativos
        sem_responsavel    : $sem_responsavel
        equipes_criadas    : $equipes_criadas
        aviso              : $aviso
        mensagem           : $mensagem
        diagnostico        : $diagnostico
      }
    }
  }

  response = $resposta
}
