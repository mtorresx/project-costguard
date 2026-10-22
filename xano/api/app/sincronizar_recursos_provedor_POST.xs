query "provedores/{id}/sincronizar-recursos" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
  }

  stack {
    // ============================================================
    // 1) Autorização: sincronização é operação administrativa.
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

    var $tag_key_prj { value = $provedor.tag_alocacao_projeto }
    // Fallback "EQP" para provedores legados (campo null/blank após ADD_FIELD):
    // a convenção padrão é EQP, então não transformar tudo em "Sem responsável".
    var $tag_key_eqp_raw { value = ($provedor.tag_alocacao_equipe ?? "") }
    var $tag_key_eqp { value = (($tag_key_eqp_raw|trim) != "") ? $tag_key_eqp_raw : "EQP" }
    var $eh_mock { value = ($provedor.usar_mock == true) }

    // Base do Mock normalizada (só quando usar_mock). MOCK_BASE_URL só no backend.
    var $mock_base_norm { value = "" }
    conditional {
      if ($eh_mock == true) {
        precondition ($env.MOCK_BASE_URL != null && $env.MOCK_BASE_URL != "") {
          error_type = "inputerror"
          error = "Ambiente Mock não configurado (MOCK_BASE_URL ausente)"
        }
        var $mb_raw { value = $env.MOCK_BASE_URL }
        var $mb_len { value = $mb_raw|strlen }
        var $mb_ult { value = $mb_raw|substr:($mb_len - 1) }
        var.update $mock_base_norm { value = $mb_raw }
        conditional {
          if ($mb_ult == "/") {
            var.update $mock_base_norm { value = $mb_raw|substr:0:($mb_len - 1) }
          }
        }
      }
    }

    // sync_id ÚNICO por execução (UUID). Identifica uma execução específica,
    // para a reconciliação distinguir recursos vistos nesta sync dos ausentes.
    // Não depender de timestamp+provedor_id (duas execuções próximas colidiriam).
    var $sync_id { value = ""|uuid }

    // ============================================================
    // B.2) Proteção best-effort contra duplo disparo (NÃO é lock atômico).
    //      Ver design (LIMITAÇÃO MVP): evita execução concorrente acidental na
    //      operação normal; endpoint admin-only. Recuperação de marca órfã por
    //      janela de tempo. Há uma janela read-then-write não atômica, aceita
    //      no MVP — não tratar como mutex transacional distribuído.
    // ============================================================
    // Janela máxima de uma sincronização (ms). Marca mais antiga = órfã/expirada.
    var $sinc_janela_ms { value = 900000 }
    var $agora_ms { value = now|to_int }

    var $em_andamento { value = ($provedor.sincronizacao_recursos_em_andamento == true) }
    var $marca_inicio_ms {
      value = ($provedor.sincronizacao_recursos_inicio != null) ? ($provedor.sincronizacao_recursos_inicio|to_int) : 0
    }
    var $marca_expirada { value = (($agora_ms - $marca_inicio_ms) > $sinc_janela_ms) }

    // Rejeita somente se há marca ativa E ainda dentro da janela (não órfã).
    precondition (!($em_andamento == true && $marca_expirada == false)) {
      error_type = "inputerror"
      error = "Já existe uma sincronização de recursos em andamento para este provedor."
    }

    // Adquire a marca (best-effort). Marca órfã/expirada é sobrescrita.
    db.edit provedores {
      field_name = "id"
      field_value = $provedor.id
      data = {
        sincronizacao_recursos_em_andamento: true
        sincronizacao_recursos_inicio      : now
        sincronizacao_recursos_id          : $sync_id
      }
    }

    var $content_type_json { value = "application/x-amz-json-1.1" }
    var $sig_region_default { value = "us-east-1" }

    var $falhou { value = false }
    var $diagnostico { value = null }

    // ============================================================
    // C) DescribeRegions (EC2 Query API). service=ec2.
    //    Real: https://ec2.us-east-1.amazonaws.com/
    //    Mock: {base}/aws/{conta}/ec2/
    // ============================================================
    var $ec2_host { value = "ec2.us-east-1.amazonaws.com" }
    var $ec2_canonical_uri { value = "/" }
    var $ec2_endpoint { value = "https://ec2.us-east-1.amazonaws.com/" }
    conditional {
      if ($eh_mock == true) {
        var $ec2_host_mock { value = $mock_base_norm }
        conditional {
          if ($mock_base_norm|starts_with:"https://") {
            var.update $ec2_host_mock { value = $mock_base_norm|substr:8 }
          }
          else {
            conditional {
              if ($mock_base_norm|starts_with:"http://") {
                var.update $ec2_host_mock { value = $mock_base_norm|substr:7 }
              }
            }
          }
        }
        var.update $ec2_host { value = $ec2_host_mock }
        var.update $ec2_canonical_uri { value = "/aws/" ~ $provedor.identificador_conta ~ "/ec2/" }
        var.update $ec2_endpoint { value = $mock_base_norm ~ "/aws/" ~ $provedor.identificador_conta ~ "/ec2/" }
      }
    }

    // Corpo form-urlencoded do DescribeRegions (Query API).
    var $ec2_body { value = "Action=DescribeRegions&Version=2016-11-15" }
    var $ec2_ct { value = "application/x-www-form-urlencoded" }

    var $amz_date_ec2  { value = now|format_timestamp:"Ymd\\THis\\Z":"UTC" }
    var $datestamp_ec2 { value = now|format_timestamp:"Ymd":"UTC" }
    var $payload_hash_ec2 { value = $ec2_body|sha256 }
    var $canon_headers_ec2 {
      value = "content-type:" ~ $ec2_ct ~ "\nhost:" ~ $ec2_host ~ "\nx-amz-date:" ~ $amz_date_ec2 ~ "\n"
    }
    var $signed_headers_ec2 { value = "content-type;host;x-amz-date" }
    var $canon_req_ec2 {
      value = "POST" ~ "\n" ~ $ec2_canonical_uri ~ "\n" ~ "" ~ "\n" ~ $canon_headers_ec2 ~ "\n" ~ $signed_headers_ec2 ~ "\n" ~ $payload_hash_ec2
    }
    var $cred_scope_ec2 {
      value = $datestamp_ec2 ~ "/" ~ $sig_region_default ~ "/ec2/aws4_request"
    }
    var $sts_ec2 {
      value = "AWS4-HMAC-SHA256" ~ "\n" ~ $amz_date_ec2 ~ "\n" ~ $cred_scope_ec2 ~ "\n" ~ ($canon_req_ec2|sha256)
    }
    var $kd_ec2 { value = $datestamp_ec2|hmac_sha256:("AWS4" ~ $aws_secret):true }
    var $kr_ec2 { value = $sig_region_default|hmac_sha256:$kd_ec2:true }
    var $ks_ec2 { value = "ec2"|hmac_sha256:$kr_ec2:true }
    var $kg_ec2 { value = "aws4_request"|hmac_sha256:$ks_ec2:true }
    var $sig_ec2 { value = $sts_ec2|hmac_sha256:$kg_ec2 }
    var $auth_ec2 {
      value = "AWS4-HMAC-SHA256 Credential=" ~ $provedor.aws_access_key_id ~ "/" ~ $cred_scope_ec2 ~ ", SignedHeaders=" ~ $signed_headers_ec2 ~ ", Signature=" ~ $sig_ec2
    }

    api.request {
      url = $ec2_endpoint
      method = "POST"
      params = $ec2_body
      headers = [
        "Content-Type: " ~ $ec2_ct,
        "Host: " ~ $ec2_host,
        "X-Amz-Date: " ~ $amz_date_ec2,
        "Authorization: " ~ $auth_ec2
      ]
      timeout = 30
    } as $ec2_result

    // Parse das regiões a partir do XML (<regionName>...</regionName>).
    var $regioes { value = [] }
    conditional {
      if ($ec2_result.response.status == 200) {
        var $xml_regioes { value = ("" ~ $ec2_result.response.result) }
        var $matches_reg { value = "/<regionName>([^<]+)<\\/regionName>/"|regex_get_all_matches:$xml_regioes }
        foreach ($matches_reg) {
          each as $m {
            var $rn { value = ($m[1] ?? "") }
            conditional {
              if ($rn != "") {
                var.update $regioes { value = $regioes|push:$rn }
              }
            }
          }
        }
      }
      else {
        var.update $falhou { value = true }
        var.update $diagnostico {
          value = {
            http_status: $ec2_result.response.status
            error_code : "DescribeRegionsFailed"
            error_msg  : "Falha ao enumerar regiões (DescribeRegions)"
            request_id : null
          }
        }
      }
    }

    conditional {
      if ($falhou == false && ($regioes|count) == 0) {
        var.update $falhou { value = true }
        var.update $diagnostico {
          value = {
            http_status: ($ec2_result.response.status ?? null)
            error_code : "NoRegions"
            error_msg  : "Nenhuma região habilitada retornada por DescribeRegions"
            request_id : null
          }
        }
      }
    }

    // ============================================================
    // D) Para cada região: GetResources (Tagging API), paginado.
    //    Acumula todos os recursos em memória (sem reconciliar ainda).
    // ============================================================
    var $recursos_acc { value = [] }
    var $amz_target_tag { value = "ResourceGroupsTaggingAPI_20170126.GetResources" }

    conditional {
      if ($falhou == false) {
        foreach ($regioes) {
          each as $regiao {
            // Destino/host/URI por região (real x mock).
            var $tag_host { value = "tagging." ~ $regiao ~ ".amazonaws.com" }
            var $tag_uri { value = "/" }
            var $tag_endpoint { value = "https://tagging." ~ $regiao ~ ".amazonaws.com/" }
            conditional {
              if ($eh_mock == true) {
                var $tag_host_mock { value = $mock_base_norm }
                conditional {
                  if ($mock_base_norm|starts_with:"https://") {
                    var.update $tag_host_mock { value = $mock_base_norm|substr:8 }
                  }
                  else {
                    conditional {
                      if ($mock_base_norm|starts_with:"http://") {
                        var.update $tag_host_mock { value = $mock_base_norm|substr:7 }
                      }
                    }
                  }
                }
                var.update $tag_host { value = $tag_host_mock }
                var.update $tag_uri { value = "/aws/" ~ $provedor.identificador_conta ~ "/tagging/" ~ $regiao ~ "/" }
                var.update $tag_endpoint { value = $mock_base_norm ~ "/aws/" ~ $provedor.identificador_conta ~ "/tagging/" ~ $regiao ~ "/" }
              }
            }

            // Paginação GetResources desta região.
            var $continuar { value = true }
            var $iteracoes { value = 0 }
            var $max_iteracoes { value = 200 }
            var $next_token { value = null }

            while ($continuar == true && $iteracoes < $max_iteracoes && $falhou == false) {
              each {
                var.update $iteracoes { value = $iteracoes + 1 }

                var $corpo_pag {
                  value = {
                    TagFilters: [{Key: $tag_key_prj}]
                  }
                }
                conditional {
                  if ($next_token != null) {
                    var.update $corpo_pag {
                      value = {
                        TagFilters   : [{Key: $tag_key_prj}]
                        PaginationToken: $next_token
                      }
                    }
                  }
                }
                var $corpo_pag_json { value = $corpo_pag|json_encode }

                var $amz_date_tag  { value = now|format_timestamp:"Ymd\\THis\\Z":"UTC" }
                var $datestamp_tag { value = now|format_timestamp:"Ymd":"UTC" }
                var $payload_hash_tag { value = $corpo_pag_json|sha256 }
                var $canon_headers_tag {
                  value = "content-type:" ~ $content_type_json ~ "\nhost:" ~ $tag_host ~ "\nx-amz-date:" ~ $amz_date_tag ~ "\nx-amz-target:" ~ $amz_target_tag ~ "\n"
                }
                var $signed_headers_tag { value = "content-type;host;x-amz-date;x-amz-target" }
                var $canon_req_tag {
                  value = "POST" ~ "\n" ~ $tag_uri ~ "\n" ~ "" ~ "\n" ~ $canon_headers_tag ~ "\n" ~ $signed_headers_tag ~ "\n" ~ $payload_hash_tag
                }
                var $cred_scope_tag {
                  value = $datestamp_tag ~ "/" ~ $regiao ~ "/tagging/aws4_request"
                }
                var $sts_tag {
                  value = "AWS4-HMAC-SHA256" ~ "\n" ~ $amz_date_tag ~ "\n" ~ $cred_scope_tag ~ "\n" ~ ($canon_req_tag|sha256)
                }
                var $kd_tag { value = $datestamp_tag|hmac_sha256:("AWS4" ~ $aws_secret):true }
                var $kr_tag { value = $regiao|hmac_sha256:$kd_tag:true }
                var $ks_tag { value = "tagging"|hmac_sha256:$kr_tag:true }
                var $kg_tag { value = "aws4_request"|hmac_sha256:$ks_tag:true }
                var $sig_tag { value = $sts_tag|hmac_sha256:$kg_tag }
                var $auth_tag {
                  value = "AWS4-HMAC-SHA256 Credential=" ~ $provedor.aws_access_key_id ~ "/" ~ $cred_scope_tag ~ ", SignedHeaders=" ~ $signed_headers_tag ~ ", Signature=" ~ $sig_tag
                }

                api.request {
                  url = $tag_endpoint
                  method = "POST"
                  params = $corpo_pag
                  headers = [
                    "Content-Type: " ~ $content_type_json,
                    "X-Amz-Target: " ~ $amz_target_tag,
                    "Host: " ~ $tag_host,
                    "X-Amz-Date: " ~ $amz_date_tag,
                    "Authorization: " ~ $auth_tag
                  ]
                  timeout = 30
                } as $tag_result

                conditional {
                  if ($tag_result.response.status == 200) {
                    var $lista_pag { value = ($tag_result.response.result.ResourceTagMappingList ?? []) }
                    // Anexa a região a cada item desta página.
                    foreach ($lista_pag) {
                      each as $rtm {
                        var $item_r {
                          value = {
                            arn   : ($rtm.ResourceARN ?? "")
                            regiao: $regiao
                            tags  : ($rtm.Tags ?? [])
                          }
                        }
                        var.update $recursos_acc { value = $recursos_acc|push:$item_r }
                      }
                    }
                    var $tok { value = ($tag_result.response.result.PaginationToken ?? "") }
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
                    var.update $diagnostico {
                      value = {
                        http_status: $tag_result.response.status
                        error_code : ($tag_result.response.result.Error.Code ?? "GetResourcesFailed")
                        error_msg  : ($tag_result.response.result.Error.Message ?? "Falha ao consultar GetResources")
                        request_id : ($tag_result.response.result.RequestId ?? null)
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

    // ============================================================
    // E) Resolução + upsert (só em sucesso). Contadores do resultado.
    // ============================================================
    var $recursos_encontrados { value = 0 }
    var $recursos_ativos { value = 0 }
    var $equipes_criadas { value = 0 }
    var $sem_responsavel { value = 0 }
    var $projetos_desconhecidos { value = 0 }
    var $projetos_inativos { value = 0 }
    var $recursos_desativados { value = 0 }

    conditional {
      if ($falhou == false) {
        foreach ($recursos_acc) {
          each as $r {
            var.update $recursos_encontrados { value = $recursos_encontrados + 1 }

            var $arn { value = $r.arn }
            var $regiao_r { value = $r.regiao }
            // Serviço derivado do ARN: arn:partition:service:region:acct:...
            var $arn_partes { value = $arn|split:":" }
            var $servico { value = ($arn_partes[2] ?? "") }

            // Extrai valores crus das tags PRJ/EQP.
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

            conditional {
              if ($codigo_prj != "") {
                db.query projetos {
                  where = $db.projetos.codigo == $codigo_prj
                  return = {type: "single"}
                } as $proj

                conditional {
                  if ($proj == null) {
                    // Projeto desconhecido: não cria nada.
                    var.update $projetos_desconhecidos { value = $projetos_desconhecidos + 1 }
                  }
                  else {
                    var.update $projeto_id_res { value = $proj.id }
                    conditional {
                      if ($proj.status != "ativo") {
                        // Projeto inativo: persiste com projeto_id, sem equipe.
                        var.update $projetos_inativos { value = $projetos_inativos + 1 }
                      }
                      else {
                        // Projeto ativo: resolve/cria equipe quando houver EQP.
                        conditional {
                          if ($codigo_eqp != "") {
                            db.query equipes {
                              where = $db.equipes.projeto_id == $proj.id && $db.equipes.codigo == $codigo_eqp
                              return = {type: "single"}
                            } as $eq

                            conditional {
                              if ($eq == null) {
                                db.add equipes {
                                  data = {
                                    nome       : $codigo_eqp
                                    codigo     : $codigo_eqp
                                    projeto_id : $proj.id
                                    auto_gerada: true
                                  }
                                } as $eq_novo
                                var.update $equipe_id_res { value = $eq_novo.id }
                                var.update $equipes_criadas { value = $equipes_criadas + 1 }
                              }
                              else {
                                var.update $equipe_id_res { value = $eq.id }
                              }
                            }
                          }
                          else {
                            // Projeto ativo sem EQP: "Sem responsável".
                            var.update $sem_responsavel { value = $sem_responsavel + 1 }
                          }
                        }
                      }
                    }
                  }
                }
              }
              else {
                // Sem PRJ (não deveria ocorrer com o filtro, mas é defensivo).
                var.update $projetos_desconhecidos { value = $projetos_desconhecidos + 1 }
              }
            }

            // Upsert por (provedor_id, arn).
            db.query recursos {
              where = $db.recursos.provedor_id == $provedor.id && $db.recursos.arn == $arn
              return = {type: "single"}
            } as $existente

            conditional {
              if ($existente != null) {
                db.edit recursos {
                  field_name = "id"
                  field_value = $existente.id
                  data = {
                    regiao            : $regiao_r
                    servico           : $servico
                    projeto_id        : $projeto_id_res
                    equipe_id         : $equipe_id_res
                    codigo_projeto_tag: $val_prj
                    codigo_equipe_tag : $val_eqp
                    sync_id           : $sync_id
                    ultima_vista_em   : now
                    ativo             : true
                    atualizado_em     : now
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
              }
            }

            var.update $recursos_ativos { value = $recursos_ativos + 1 }
          }
        }
      }
    }

    // ============================================================
    // F) Reconciliação — SOMENTE após sucesso completo.
    //    Recursos do provedor não vistos neste sync → ativo=false.
    // ============================================================
    conditional {
      if ($falhou == false) {
        db.query recursos {
          where = $db.recursos.provedor_id == $provedor.id && $db.recursos.ativo == true && ($db.recursos.sync_id == null || $db.recursos.sync_id != $sync_id)
          return = {type: "list"}
        } as $orfaos

        foreach ($orfaos) {
          each as $o {
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

    // ============================================================
    // F.1) Liberação da marca best-effort (sucesso E erro controlado).
    //      Libera apenas se a marca ainda pertence a ESTA execução (mesmo
    //      sync_id), para não apagar a marca de uma execução que tomou o lugar
    //      de uma marca órfã. Caminhos de erro controlado chegam aqui com
    //      $falhou=true; em crash não-controlado, a janela de expiração cobre.
    // ============================================================
    db.get provedores {
      field_name = "id"
      field_value = $provedor.id
    } as $provedor_atual

    conditional {
      if ($provedor_atual != null && $provedor_atual.sincronizacao_recursos_id == $sync_id) {
        db.edit provedores {
          field_name = "id"
          field_value = $provedor.id
          data = {
            sincronizacao_recursos_em_andamento: false
            sincronizacao_recursos_id          : null
          }
        }
      }
    }

    // ============================================================
    // G) Resposta sanitizada.
    // ============================================================
    var $status_sync { value = ($falhou == true) ? "erro" : "sucesso" }
    var $mensagem { value = ($falhou == true) ? "Falha na sincronização de recursos" : "" }

    var $resposta {
      value = {
        provedor_id           : $provedor.id
        status                : $status_sync
        regioes_consultadas   : ($regioes|count)
        recursos_encontrados  : $recursos_encontrados
        recursos_ativos       : $recursos_ativos
        recursos_desativados  : $recursos_desativados
        equipes_criadas       : $equipes_criadas
        sem_responsavel       : $sem_responsavel
        projetos_desconhecidos: $projetos_desconhecidos
        projetos_inativos     : $projetos_inativos
        mensagem              : $mensagem
        diagnostico           : $diagnostico
      }
    }
  }

  response = $resposta
  guid = "rPpVEUwelIk9YgWq0JsnqA5CDZU"
}
