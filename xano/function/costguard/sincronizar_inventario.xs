// Sincronização do inventário de recursos de um provedor. Chamada pelo endpoint manual
// (provedores/{id}/sincronizar-recursos, origem "manual") e pelo ciclo
// automático (sincronizacao/automatica, origem "automatica").
//
// Não lança erro de negócio: devolve {erro_pre, ocupado, resultado} e quem
// chama decide a resposta HTTP. A autorização é de quem chama.
function "costguard/sincronizar_inventario" {
  input {
    int provedor_id
    text origem? filters=trim
  }

  stack {
    var $automatica { value = ($input.origem == "automatica") }
    var $origem { value = ($automatica == true) ? "automatica" : "manual" }

    // Variáveis usadas depois dos blocos condicionais.
    var $erro_pre { value = null }
    var $ocupado { value = false }
    var $executou { value = false }
    var $falhou { value = false }
    var $falha_interna { value = false }
    var $diagnostico { value = null }
    var $regioes { value = [] }
    var $recursos_acc { value = [] }
    var $recursos_encontrados { value = 0 }
    var $recursos_ignorados { value = 0 }
    var $recursos_ativos { value = 0 }
    var $recursos_criados { value = 0 }
    var $recursos_alterados { value = 0 }
    var $recursos_desativados { value = 0 }
    var $equipes_criadas { value = 0 }
    var $sem_responsavel { value = 0 }
    var $projetos_desconhecidos { value = 0 }
    var $projetos_inativos { value = 0 }
    var $trava_id { value = null }

    // ============================================================
    // A) Elegibilidade do provedor (ANTES de decifrar credencial).
    // ============================================================
    db.get provedores {
      field_name = "id"
      field_value = $input.provedor_id
    } as $provedor

    conditional {
      if ($provedor == null) {
        var.update $erro_pre { value = {codigo: "nao_encontrado", mensagem: "Provedor não encontrado"} }
      }
      elseif ($provedor.tipo != "aws") {
        var.update $erro_pre { value = {codigo: "tipo", mensagem: "Tipo de provedor não suportado (apenas 'aws')"} }
      }
      elseif ($provedor.status != "ok") {
        var.update $erro_pre { value = {codigo: "status", mensagem: "Provedor não está conectado (status != ok)"} }
      }
      elseif ($provedor.aws_access_key_id == null || $provedor.aws_access_key_id == "" || $provedor.aws_secret_cifrado == null || $provedor.aws_secret_cifrado == "") {
        var.update $erro_pre { value = {codigo: "credencial", mensagem: "Credencial AWS ausente"} }
      }
    }

    // ============================================================
    // B) Exclusão mútua pela tabela travas. O índice único em
    //    `nome` torna a aquisição atômica. Trava com mais de 15 min é órfã:
    //    é removida e a aquisição é tentada mais uma vez.
    // ============================================================
    var $trava_nome { value = "sinc_inventario_" ~ ($input.provedor_id|to_text) }

    foreach ([1, 2]) {
      each as $tentativa {
        conditional {
          if ($erro_pre == null && $trava_id == null && $ocupado == false) {
            try_catch {
              try {
                var $agora_trava { value = now|to_int }
                db.add travas {
                  data = {nome: $trava_nome, adquirida_em: $agora_trava}
                } as $nova_trava
                var.update $trava_id { value = $nova_trava.id }
              }
              catch {
                db.get travas {
                  field_name = "nome"
                  field_value = $trava_nome
                } as $trava_atual
                conditional {
                  if ($trava_atual != null) {
                    var $agora_cmp { value = now|to_int }
                    var $idade_trava { value = $agora_cmp - $trava_atual.adquirida_em }
                    conditional {
                      if ($idade_trava > 900000 && $tentativa == 1) {
                        db.del travas {
                          field_name = "id"
                          field_value = $trava_atual.id
                        }
                      }
                      else {
                        var.update $ocupado { value = true }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }

    conditional {
      if ($erro_pre == null && $trava_id == null) {
        var.update $ocupado { value = true }
      }
    }

    // ============================================================
    // C) Execução, sob a trava. Qualquer falha não prevista vira erro
    //    registrado; a trava é sempre liberada no finally.
    // ============================================================
    conditional {
      if ($erro_pre == null && $ocupado == false) {
        var.update $executou { value = true }

        try_catch {
          try {
            // Decifra o secret (SÓ em memória, imediatamente antes de assinar).
            var $aws_secret {
              value = $provedor.aws_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"
            }

            var $tag_key_prj_raw { value = ($provedor.tag_alocacao_projeto ?? "") }
            var $tag_key_prj { value = (($tag_key_prj_raw|trim) != "") ? $tag_key_prj_raw : "PRJ" }
            var $tag_key_eqp_raw { value = ($provedor.tag_alocacao_equipe ?? "") }
            var $tag_key_eqp { value = (($tag_key_eqp_raw|trim) != "") ? $tag_key_eqp_raw : "EQP" }

            var $sync_id { value = ""|uuid }

            // ============================================================
            // D) Coleta: AWS Resource Explorer ListResources (REST JSON),
            //    paginado. A região consultada é a do índice agregador
            //    (provedores.regiao_inventario; vazio = us-east-1): uma
            //    consulta cobre todas as regiões, com e sem tag.
            //    https://resource-explorer-2.{região}.amazonaws.com/ListResources
            // ============================================================
            var $regiao_inv_raw { value = (($provedor.regiao_inventario ?? "")|trim) }
            var $regiao_inv { value = ($regiao_inv_raw != "") ? $regiao_inv_raw : "us-east-1" }

            var $rex_ct { value = "application/json" }
            var $rex_host { value = "resource-explorer-2." ~ $regiao_inv ~ ".amazonaws.com" }
            var $rex_uri { value = "/ListResources" }
            var $rex_endpoint { value = "https://resource-explorer-2." ~ $regiao_inv ~ ".amazonaws.com/ListResources" }

            var $mapa_regioes { value = {} }
            var $continuar { value = true }
            var $iteracoes { value = 0 }
            var $max_iteracoes { value = 200 }
            var $next_token { value = null }

            try_catch {
              try {
                while ($continuar == true && $iteracoes < $max_iteracoes && $falhou == false) {
                  each {
                    var.update $iteracoes { value = $iteracoes + 1 }

                    var $corpo_pag { value = {MaxResults: 100} }
                    conditional {
                      if ($next_token != null) {
                        var.update $corpo_pag { value = {MaxResults: 100, NextToken: $next_token} }
                      }
                    }
                    var $corpo_pag_json { value = $corpo_pag|json_encode }

                    var $amz_date_rex  { value = now|format_timestamp:"Ymd\\THis\\Z":"UTC" }
                    var $datestamp_rex { value = now|format_timestamp:"Ymd":"UTC" }
                    var $payload_hash_rex { value = $corpo_pag_json|sha256 }
                    var $canon_headers_rex {
                      value = "content-type:" ~ $rex_ct ~ "\nhost:" ~ $rex_host ~ "\nx-amz-date:" ~ $amz_date_rex ~ "\n"
                    }
                    var $signed_headers_rex { value = "content-type;host;x-amz-date" }
                    var $canon_req_rex {
                      value = "POST" ~ "\n" ~ $rex_uri ~ "\n" ~ "" ~ "\n" ~ $canon_headers_rex ~ "\n" ~ $signed_headers_rex ~ "\n" ~ $payload_hash_rex
                    }
                    var $cred_scope_rex {
                      value = $datestamp_rex ~ "/" ~ $regiao_inv ~ "/resource-explorer-2/aws4_request"
                    }
                    var $sts_rex {
                      value = "AWS4-HMAC-SHA256" ~ "\n" ~ $amz_date_rex ~ "\n" ~ $cred_scope_rex ~ "\n" ~ ($canon_req_rex|sha256)
                    }
                    var $kd_rex { value = $datestamp_rex|hmac_sha256:("AWS4" ~ $aws_secret):true }
                    var $kr_rex { value = $regiao_inv|hmac_sha256:$kd_rex:true }
                    var $ks_rex { value = "resource-explorer-2"|hmac_sha256:$kr_rex:true }
                    var $kg_rex { value = "aws4_request"|hmac_sha256:$ks_rex:true }
                    var $sig_rex { value = $sts_rex|hmac_sha256:$kg_rex }
                    var $auth_rex {
                      value = "AWS4-HMAC-SHA256 Credential=" ~ $provedor.aws_access_key_id ~ "/" ~ $cred_scope_rex ~ ", SignedHeaders=" ~ $signed_headers_rex ~ ", Signature=" ~ $sig_rex
                    }

                    api.request {
                      url = $rex_endpoint
                      method = "POST"
                      params = $corpo_pag
                      headers = [
                        "Content-Type: " ~ $rex_ct,
                        "Host: " ~ $rex_host,
                        "X-Amz-Date: " ~ $amz_date_rex,
                        "Authorization: " ~ $auth_rex
                      ]
                      timeout = 30
                    } as $rex_result

                    conditional {
                      if ($rex_result.response.status == 200) {
                        var $lista_pag { value = ($rex_result.response.result.Resources ?? []) }
                        foreach ($lista_pag) {
                          each as $rx {
                            var $tipo_rx { value = (($rx.ResourceType ?? "")|to_lower) }
                            var $conta_rx { value = ("" ~ ($rx.OwningAccountId ?? "")) }
                            var $tipo_aceito {
                              value = ($tipo_rx == "ec2:instance" || $tipo_rx == "ec2:volume" || $tipo_rx == "rds:db" || $tipo_rx == "s3:bucket" || $tipo_rx == "lambda:function" || $tipo_rx == "dynamodb:table")
                            }
                            conditional {
                              // Só tipos aceitos e só recursos da conta do provedor.
                              // Região, conta e serviço vêm dos campos da resposta,
                              // nunca do ARN (o de bucket S3 não traz região nem conta).
                              if ($tipo_aceito == true && $conta_rx == $provedor.identificador_conta && ($rx.Arn ?? "") != "") {
                                var $tags_rx { value = [] }
                                foreach (($rx.Properties ?? [])) {
                                  each as $prop {
                                    conditional {
                                      if ($prop.Name == "tags") {
                                        var.update $tags_rx { value = ($prop.Data ?? []) }
                                      }
                                    }
                                  }
                                }
                                var $servico_rx { value = (($rx.Service ?? "")|to_lower) }
                                conditional {
                                  if ($servico_rx == "") {
                                    var.update $servico_rx { value = (($tipo_rx|split:":")|first) }
                                  }
                                }
                                var $regiao_rx { value = ($rx.Region ?? "") }
                                var $item_r {
                                  value = {
                                    arn    : $rx.Arn
                                    regiao : $regiao_rx
                                    servico: $servico_rx
                                    tags   : $tags_rx
                                  }
                                }
                                var.update $recursos_acc { value = $recursos_acc|push:$item_r }
                                var $kreg { value = "k" ~ ($regiao_rx|sha256) }
                                conditional {
                                  if (($mapa_regioes|has:$kreg) == false) {
                                    var.update $mapa_regioes { value = $mapa_regioes|set:$kreg:true }
                                    var.update $regioes { value = $regioes|push:$regiao_rx }
                                  }
                                }
                              }
                              else {
                                var.update $recursos_ignorados { value = $recursos_ignorados + 1 }
                              }
                            }
                          }
                        }
                        var $tok { value = ($rex_result.response.result.NextToken ?? "") }
                        conditional {
                          if ($tok != null && $tok != "") {
                            var.update $next_token { value = $tok }
                          }
                          else {
                            var.update $continuar { value = false }
                          }
                        }
                      }
                      else {
                        var.update $falhou { value = true }
                        var.update $continuar { value = false }
                        var $erro_tipo { value = null }
                        var $erro_msg { value = null }
                        // Erro REST JSON: "Message" (com fallback para "message").
                        try_catch {
                          try {
                            var.update $erro_tipo { value = $rex_result.response.result|get:"__type":null }
                            var.update $erro_msg { value = $rex_result.response.result|get:"Message":null }
                            conditional {
                              if ($erro_msg == null) {
                                var.update $erro_msg { value = $rex_result.response.result|get:"message":null }
                              }
                            }
                          }
                          catch {
                            var.update $erro_tipo { value = null }
                          }
                        }
                        var.update $diagnostico {
                          value = {
                            http_status: $rex_result.response.status
                            error_code : ($erro_tipo ?? "ListResourcesFailed")
                            error_msg  : ($erro_msg ?? "Falha ao consultar o Resource Explorer (ListResources)")
                            request_id : null
                          }
                        }
                      }
                    }
                  }
                }

                // Parou pelo limite de páginas com token pendente: coleta
                // incompleta não pode reconciliar (desativaria recursos vivos).
                conditional {
                  if ($falhou == false && $continuar == true) {
                    var.update $falhou { value = true }
                    var.update $diagnostico {
                      value = {
                        http_status: null
                        error_code : "ListResourcesTruncated"
                        error_msg  : "Inventário maior que o limite de páginas; nada foi reconciliado"
                        request_id : null
                      }
                    }
                  }
                }
              }
              catch {
                var.update $falhou { value = true }
                var.update $falha_interna { value = true }
                var.update $diagnostico {
                  value = {
                    http_status: null
                    error_code : "ListResourcesException"
                    error_msg  : "Falha de comunicação ao consultar recursos (ListResources)"
                    request_id : null
                  }
                }
              }
            }

            // ============================================================
            // E) Resolução e gravação. Projetos, equipes e recursos do provedor
            //    são lidos uma vez; só é gravado o recurso que mudou.
            // ============================================================
            var $recursos_atuais { value = [] }
            var $vistos { value = {} }

            conditional {
              if ($falhou == false) {
                try_catch {
                  try {
                    db.query projetos {
                      return = {type: "list"}
                    } as $todos_projetos
                    var $mapa_proj { value = {} }
                    foreach ($todos_projetos) {
                      each as $pj {
                        var $kpj0 { value = "k" ~ ($pj.codigo|sha256) }
                        var $pj_min { value = {id: $pj.id, status: $pj.status} }
                        var.update $mapa_proj { value = $mapa_proj|set:$kpj0:$pj_min }
                      }
                    }

                    db.query equipes {
                      return = {type: "list"}
                    } as $todas_equipes
                    var $mapa_eq { value = {} }
                    foreach ($todas_equipes) {
                      each as $eq0 {
                        var $keq0 { value = "k" ~ ((($eq0.projeto_id|to_text) ~ "_" ~ $eq0.codigo)|sha256) }
                        var.update $mapa_eq { value = $mapa_eq|set:$keq0:$eq0.id }
                      }
                    }

                    db.query recursos {
                      where = $db.recursos.provedor_id == $provedor.id
                      return = {type: "list"}
                    } as $lista_atuais
                    var.update $recursos_atuais { value = $lista_atuais }
                    var $mapa_rec { value = {} }
                    foreach ($lista_atuais) {
                      each as $ra {
                        var $kra { value = "k" ~ ($ra.arn|sha256) }
                        var.update $mapa_rec { value = $mapa_rec|set:$kra:$ra }
                      }
                    }

                    foreach ($recursos_acc) {
                      each as $r {
                        var.update $recursos_encontrados { value = $recursos_encontrados + 1 }

                        var $arn { value = $r.arn }
                        var $regiao_r { value = $r.regiao }
                        var $servico { value = $r.servico }

                        var $val_prj { value = "" }
                        var $val_eqp { value = "" }
                        foreach (($r.tags ?? [])) {
                          each as $tg {
                            conditional {
                              if ($tg.Key == $tag_key_prj) {
                                var.update $val_prj { value = ($tg.Value ?? "") }
                              }
                            }
                            conditional {
                              if ($tag_key_eqp != "" && $tg.Key == $tag_key_eqp) {
                                var.update $val_eqp { value = ($tg.Value ?? "") }
                              }
                            }
                          }
                        }

                        var $codigo_prj { value = ($val_prj|trim)|to_upper }
                        var $codigo_eqp { value = ($val_eqp|trim)|to_upper }

                        var $projeto_id_res { value = null }
                        var $equipe_id_res { value = null }
                        var $proj { value = null }

                        conditional {
                          if ($codigo_prj != "") {
                            var $kpj { value = "k" ~ ($codigo_prj|sha256) }
                            var.update $proj { value = $mapa_proj|get:$kpj:null }
                          }
                        }

                        conditional {
                          if ($proj == null) {
                            // Sem tag de projeto ou projeto desconhecido: "Não classificado".
                            var.update $projetos_desconhecidos { value = $projetos_desconhecidos + 1 }
                          }
                          elseif ($proj.status != "ativo") {
                            // Projeto inativo: persiste com projeto_id, sem equipe.
                            var.update $projeto_id_res { value = $proj.id }
                            var.update $projetos_inativos { value = $projetos_inativos + 1 }
                          }
                          elseif ($codigo_eqp == "") {
                            // Projeto ativo sem EQP: "Sem responsável".
                            var.update $projeto_id_res { value = $proj.id }
                            var.update $sem_responsavel { value = $sem_responsavel + 1 }
                          }
                          else {
                            var.update $projeto_id_res { value = $proj.id }
                            var $keq { value = "k" ~ ((($proj.id|to_text) ~ "_" ~ $codigo_eqp)|sha256) }
                            var $eq_id { value = $mapa_eq|get:$keq:null }
                            conditional {
                              if ($eq_id == null) {
                                db.add equipes {
                                  data = {
                                    nome       : $codigo_eqp
                                    codigo     : $codigo_eqp
                                    projeto_id : $proj.id
                                    auto_gerada: true
                                  }
                                } as $eq_novo
                                var.update $eq_id { value = $eq_novo.id }
                                var.update $mapa_eq { value = $mapa_eq|set:$keq:$eq_novo.id }
                                var.update $equipes_criadas { value = $equipes_criadas + 1 }
                              }
                            }
                            var.update $equipe_id_res { value = $eq_id }
                          }
                        }

                        // Upsert por (provedor_id, arn). ARN repetido na mesma
                        // coleta é tratado uma única vez.
                        var $kr { value = "k" ~ ($arn|sha256) }
                        conditional {
                          if (($vistos|has:$kr) == false) {
                            var $existente { value = $mapa_rec|get:$kr:null }
                            conditional {
                              if ($existente != null) {
                                var $igual {
                                  value = ($existente.ativo == true && $existente.regiao == $regiao_r && $existente.servico == $servico && (($existente.projeto_id ?? 0) == ($projeto_id_res ?? 0)) && (($existente.equipe_id ?? 0) == ($equipe_id_res ?? 0)) && (($existente.codigo_projeto_tag ?? "") == $val_prj) && (($existente.codigo_equipe_tag ?? "") == $val_eqp))
                                }
                                conditional {
                                  if ($igual == false) {
                                    // db.edit ignora valor nulo: para limpar projeto ou
                                    // equipe grava-se 0, que é como o Xano guarda a chave
                                    // estrangeira vazia (as leituras aceitam null ou 0).
                                    db.edit recursos {
                                      field_name = "id"
                                      field_value = $existente.id
                                      data = {
                                        regiao            : $regiao_r
                                        servico           : $servico
                                        projeto_id        : ($projeto_id_res ?? 0)
                                        equipe_id         : ($equipe_id_res ?? 0)
                                        codigo_projeto_tag: $val_prj
                                        codigo_equipe_tag : $val_eqp
                                        sync_id           : $sync_id
                                        ultima_vista_em   : now
                                        ativo             : true
                                        atualizado_em     : now
                                      }
                                    }
                                    var.update $recursos_alterados { value = $recursos_alterados + 1 }
                                  }
                                }
                              }
                              else {
                                db.add recursos {
                                  data = {
                                    provedor_id       : $provedor.id
                                    arn               : $arn
                                    regiao            : $regiao_r
                                    servico           : $servico
                                    projeto_id        : $projeto_id_res
                                    equipe_id         : $equipe_id_res
                                    codigo_projeto_tag: $val_prj
                                    codigo_equipe_tag : $val_eqp
                                    sync_id           : $sync_id
                                    ultima_vista_em   : now
                                    ativo             : true
                                  }
                                }
                                var.update $recursos_criados { value = $recursos_criados + 1 }
                              }
                            }
                            var.update $vistos { value = $vistos|set:$kr:true }
                            var.update $recursos_ativos { value = $recursos_ativos + 1 }
                          }
                        }
                      }
                    }
                  }
                  catch {
                    var.update $falhou { value = true }
                    var.update $falha_interna { value = true }
                    var.update $diagnostico {
                      value = {
                        http_status: null
                        error_code : "PersistenciaException"
                        error_msg  : "Falha ao gravar recursos; nada foi reconciliado"
                        request_id : null
                      }
                    }
                  }
                }
              }
            }

            // ============================================================
            // F) Reconciliação — SOMENTE após sucesso completo. Recurso ativo
            //    do provedor que não veio nesta coleta → ativo=false.
            // ============================================================
            conditional {
              if ($falhou == false) {
                try_catch {
                  try {
                    foreach ($recursos_atuais) {
                      each as $o {
                        var $ko { value = "k" ~ ($o.arn|sha256) }
                        conditional {
                          if ($o.ativo == true && ($vistos|has:$ko) == false) {
                            db.edit recursos {
                              field_name = "id"
                              field_value = $o.id
                              data = {
                                ativo        : false
                                atualizado_em: now
                              }
                            }
                            var.update $recursos_desativados { value = $recursos_desativados + 1 }
                          }
                        }
                      }
                    }
                  }
                  catch {
                    var.update $falhou { value = true }
                    var.update $falha_interna { value = true }
                    var.update $diagnostico {
                      value = {
                        http_status: null
                        error_code : "ReconciliacaoException"
                        error_msg  : "Falha ao reconciliar recursos ausentes"
                        request_id : null
                      }
                    }
                  }
                }
              }
            }
          }
          catch {
            var.update $falhou { value = true }
            var.update $falha_interna { value = true }
            var.update $diagnostico {
              value = {
                http_status: null
                error_code : "SincronizacaoException"
                error_msg  : "Falha inesperada durante a sincronização"
                request_id : null
              }
            }
          }
          finally {
            db.del travas {
              field_name = "id"
              field_value = $trava_id
            }
          }
        }
      }
    }

    // ============================================================
    // G) Estado por provedor e registro da execução.
    //    Falha de pré-condição só é registrada no modo automático; no manual
    //    quem chama responde o erro, como sempre.
    // ============================================================
    var $mudou { value = (($recursos_criados + $recursos_alterados + $recursos_desativados + $equipes_criadas) > 0) }
    var $status_sync { value = ($falhou == true) ? "erro" : "sucesso" }
    var $mensagem { value = ($falhou == true) ? "Falha na sincronização de recursos" : "" }
    conditional {
      if ($falhou == true && $diagnostico != null && $diagnostico.error_msg != null) {
        var.update $mensagem { value = "Falha na sincronização de recursos: " ~ $diagnostico.error_msg }
      }
    }
    conditional {
      if ($erro_pre != null) {
        var.update $status_sync { value = "erro" }
        var.update $mensagem { value = "Falha na sincronização de recursos: " ~ $erro_pre.mensagem }
      }
    }

    var $registrar { value = ($provedor != null && ($executou == true || ($erro_pre != null && $automatica == true))) }

    conditional {
      if ($registrar == true) {
        var $status_anterior { value = ($provedor.inventario_ultimo_status ?? "") }
        var $mensagem_anterior { value = ($provedor.inventario_ultima_mensagem ?? "") }
        var $status_mudou { value = ($status_anterior != $status_sync) }
        var $novo_sucesso { value = $provedor.inventario_ultimo_sucesso }
        var $nova_mudanca { value = $provedor.inventario_ultima_mudanca }
        conditional {
          if ($status_sync == "sucesso") {
            var.update $novo_sucesso { value = now }
          }
        }
        conditional {
          if ($mudou == true) {
            var.update $nova_mudanca { value = now }
          }
        }

        db.edit provedores {
          field_name = "id"
          field_value = $provedor.id
          data = {
            inventario_ultima_tentativa: now
            inventario_ultimo_sucesso  : $novo_sucesso
            inventario_ultimo_status   : $status_sync
            inventario_ultima_mensagem : $mensagem
            inventario_ultima_origem   : $origem
            inventario_ultima_mudanca  : $nova_mudanca
          }
        }

        // coletas_inventario alimenta o alerta de falha de importação. No modo
        // manual há sempre uma linha; no automático só quando algo mudou
        // (720 ciclos por dia por provedor estourariam o limite do plano).
        conditional {
          if ($automatica == false || $mudou == true || $status_mudou == true || $mensagem_anterior != $mensagem) {
            db.add coletas_inventario {
              data = {
                provedor_id           : $provedor.id
                status                : $status_sync
                recursos_encontrados  : $recursos_encontrados
                projetos_desconhecidos: $projetos_desconhecidos
                mensagem              : $mensagem
              }
            } as $registro_execucao
          }
        }

        // Alertas: só no ciclo automático, quando o inventário
        // ou o status mudou. Falha na avaliação não desfaz a sincronização.
        conditional {
          if ($automatica == true && ($mudou == true || $status_mudou == true)) {
            try_catch {
              try {
                function.run "costguard/avaliar_alertas" {
                  input = {simular: false}
                } as $alertas_avaliados
              }
              catch {
                var $alertas_avaliados { value = null }
              }
            }
          }
        }
      }
    }

    var $resultado {
      value = {
        provedor_id           : $input.provedor_id
        status                : $status_sync
        origem                : $origem
        mudou                 : $mudou
        regioes_consultadas   : ($regioes|count)
        recursos_encontrados  : $recursos_encontrados
        recursos_ignorados    : $recursos_ignorados
        recursos_ativos       : $recursos_ativos
        recursos_criados      : $recursos_criados
        recursos_alterados    : $recursos_alterados
        recursos_desativados  : $recursos_desativados
        equipes_criadas       : $equipes_criadas
        sem_responsavel       : $sem_responsavel
        projetos_desconhecidos: $projetos_desconhecidos
        projetos_inativos     : $projetos_inativos
        mensagem              : $mensagem
        diagnostico           : $diagnostico
      }
    }

    var $saida {
      value = {
        erro_pre : $erro_pre
        ocupado  : $ocupado
        resultado: $resultado
      }
    }
  }

  response = $saida
}
