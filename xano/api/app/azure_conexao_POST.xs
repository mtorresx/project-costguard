// Cadastra (ou substitui) PELA TELA a conexão do Azure usada na leitura do custo
// do mês (somente leitura). Só admin ativo. UMA única conexão: o POST sempre
// substitui a anterior. Sem o cadastro, o sistema continua usando as variáveis
// AZURE_* do Xano como reserva (o cadastro da tela vem primeiro).
//
// Entrada (todas com trim): tenant_id, client_id, subscription_id (GUID) e
// client_secret (ASCII visível, sem espaço, 8 a 256 caracteres: a MESMA regra que o
// sincronizar REVALIDA depois de decifrar, senão o cadastro salvo viraria
// "configuracao_invalida"; o GET decifra só o tenant). Dado inválido = HTTP 400 com mensagem fixa que cita só
// o NOME do campo ("Dados de conexão inválidos. Verifique o campo tenant_id."),
// NUNCA o valor.
//
// `apelido` (OPCIONAL, texto simples, NÃO é segredo): passa por
// costguard/limpar_texto_linha (CR/LF/tab viram espaço, trim, corte em 120) e o
// tamanho é medido no texto JÁ LIMPO, sem novo trim e sem truncar: mais de 60
// caracteres => HTTP 400 "Apelido inválido: use de 1 a 60 caracteres." (sem ecoar o
// valor). O corte em 120 da limpeza nunca esconde excesso: um texto maior que 120
// sai com mais de 60 e é recusado, em vez de ser cortado em silêncio. Vazio, ausente
// ou só espaços = sem apelido (grava ""; o GET mostra o padrão "Azure"). Validado na
// mesma etapa das demais entradas, ANTES da trava e da chamada ao Azure.
// `tenant_final`: os ÚLTIMOS 4 caracteres do tenant_id (já validado como GUID de 36
// caracteres), calculados aqui e guardados em texto simples; nunca o ID inteiro.
// Substituição: o POST sobrescreve apelido e tenant_final; sem `apelido` no novo POST,
// o apelido anterior NÃO é mantido (a conexão inteira é substituída).
//
// ANTES de gravar, pede um token ao Azure (o mesmo pedido do sincronizar: POST
// https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token, client_credentials,
// escopo https://management.azure.com/.default). Qualquer falha (erro, timeout,
// resposta sem token) => HTTP 400 "Não foi possível autenticar no Azure com os dados
// informados." e NADA é gravado; a mensagem não ecoa entrada nem corpo do Azure
// (mensagens AADSTS trazem tenant/client ids). 429 do Azure no token => HTTP 429 com
// os segundos (1 a 3600, maior valor entre os cabeçalhos que CONTÊM "retry-after";
// sem nenhum, 60), sem gravar. O token só valida tenant/client/segredo: NÃO valida o
// subscription_id (a assinatura só é confirmada na primeira leitura, que devolve
// sem_permissao se estiver errada). NENHUMA chamada extra ao Azure; nenhuma
// sincronização é disparada.
//
// Sucesso: grava (upsert da linha única `chave = "azure"` em `azure_conexao`) os
// QUATRO dados CIFRADOS com JWE (`jwe_encode` + `$env.PROV_ENC_KEY`, A256KW +
// A256CBC-HS512, o mesmo mecanismo da credencial AWS), atualizado_em e
// atualizado_por (id do admin), e responde exatamente {"conectado": true}.
// A leitura guardada em `provedor_externo_leitura` (provedor "azure", todos os meses)
// é APAGADA antes de gravar: pertencia a outra credencial/assinatura, e o GET volta a
// "sem_leitura". Se a gravação falhar depois, a conexão antiga permanece e só se perde
// a leitura guardada (basta sincronizar de novo).
//
// Exclusão mútua: usa a MESMA trava do sincronizar (tabela travas, nome
// azure_custo_sincronizar): dois POST/DELETE simultâneos, ou um POST durante uma
// sincronização, não correm juntos. Trava ocupada = HTTP 429; órfã > 2 min é removida.
//
// SEGREDOS: nada (nem o segredo, nem os IDs, nem os valores cifrados, nem o token) é
// devolvido, registrado ou ecoado em mensagem de erro. Sem function.run com segredo
// como input (o histórico de requisições do Xano guarda input e resposta de funções).
// HISTÓRICO DO XANO (NÃO VERIFICADO no painel): o histórico de requisições guarda o
// corpo/entrada de APIs por 24 h quando está habilitado, ou seja, o client_secret
// enviado a este endpoint ficaria no histórico. Este arquivo NÃO define o atributo de
// histórico (sem precedente no repositório nem sintaxe comprovada): desligar o
// histórico da BRANCH inteira (recomendado enquanto o Azure estiver em uso) e, no
// mínimo, deste endpoint é uma ação MANUAL no painel do Xano.
// O cabeçalho Authorization (JWT do admin) também
// entra no histórico de todo endpoint. Se o corpo da chamada externa (api.request) ao
// Azure entra no histórico: NÃO VERIFICADO.
query "azure/conexao" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    text tenant_id? filters=trim
    text client_id? filters=trim
    text client_secret? filters=trim {
      sensitive = true
    }
    text subscription_id? filters=trim
    text apelido? filters=trim
  }

  stack {
    // Autorização: admin ativo (validada no backend).
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

    // Entrada normalizada (trim) e validada ANTES de qualquer trava, URL ou gravação.
    var $tenant { value = (($input.tenant_id ?? "")|trim) }
    var $client { value = (($input.client_id ?? "")|trim) }
    var $segredo { value = (($input.client_secret ?? "")|trim) }
    var $assinatura { value = (($input.subscription_id ?? "")|trim) }

    // GUID: 36 caracteres e formato 8-4-4-4-12 em hexadecimal. O tamanho é
    // conferido à parte porque o `$` do regex aceita uma quebra de linha final.
    var $tenant_ok { value = (($tenant|strlen) == 36 && ("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$tenant)) }
    var $client_ok { value = (($client|strlen) == 36 && ("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$client)) }
    var $assinatura_ok { value = (($assinatura|strlen) == 36 && ("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$assinatura)) }

    // Segredo: ASCII visível, sem espaço nem controle; 8 a 256 caracteres.
    var $segredo_ok { value = (($segredo|strlen) >= 8 && ($segredo|strlen) <= 256 && ("/^[!-~]+$/"|regex_matches:$segredo)) }

    precondition ($tenant_ok == true) {
      error_type = "inputerror"
      error = "Dados de conexão inválidos. Verifique o campo tenant_id."
    }

    precondition ($client_ok == true) {
      error_type = "inputerror"
      error = "Dados de conexão inválidos. Verifique o campo client_id."
    }

    precondition ($assinatura_ok == true) {
      error_type = "inputerror"
      error = "Dados de conexão inválidos. Verifique o campo subscription_id."
    }

    precondition ($segredo_ok == true) {
      error_type = "inputerror"
      error = "Dados de conexão inválidos. Verifique o campo client_secret."
    }

    // Apelido (opcional): limpeza e depois o tamanho do texto JÁ LIMPO (sem novo trim:
    // um texto cortado em 120 por limpar_texto_linha continua > 60 e é recusado).
    function.run "costguard/limpar_texto_linha" {
      input = {texto: ($input.apelido ?? "")}
    } as $apelido

    var $apelido_ok { value = (($apelido|strlen) <= 60) }

    precondition ($apelido_ok == true) {
      error_type = "inputerror"
      error = "Apelido inválido: use de 1 a 60 caracteres."
    }

    // Últimos 4 caracteres do tenant (36 caracteres já validados acima). Nunca o ID inteiro.
    var $tenant_corte { value = ($tenant|strlen) - 4 }
    var $tenant_final { value = $tenant|substr:$tenant_corte }

    var $estado { value = "" }
    var $falha { value = false }
    var $segundos_restantes { value = 0 }
    var $trava_id { value = null }
    var $trava_ocupada { value = false }

    // ============================================================
    // Trava de exclusão mútua (tabela travas, índice único em `nome`), a MESMA do
    // sincronizar. Removida no finally; trava órfã (> 2 min, acima do timeout do
    // token) é removida na primeira tentativa seguinte.
    // ============================================================
    var $trava_nome { value = "azure_custo_sincronizar" }

    foreach ([1, 2]) {
      each as $tentativa {
        conditional {
          if ($trava_id == null && $trava_ocupada == false) {
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
                      if ($idade_trava > 120000 && $tentativa == 1) {
                        db.del travas {
                          field_name = "id"
                          field_value = $trava_atual.id
                        }
                      }
                      else {
                        var.update $trava_ocupada { value = true }
                      }
                    }
                  }
                  else {
                    var.update $trava_ocupada { value = true }
                  }
                }
              }
            }
          }
        }
      }
    }

    precondition ($trava_id != null) {
      error_type = "toomanyrequests"
      error = "Já existe uma operação de conexão ou sincronização do Azure em andamento. Tente novamente em instantes."
    }

    // Seção crítica: não lança erro; registra o desfecho em variáveis, libera a
    // trava no finally e só depois responde.
    var $t_status { value = 0 }
    var $t_token { value = "" }
    var $t_cabecalhos { value = [] }

    try_catch {
      try {
        // Releitura com a trava: autorização atual.
        db.get usuarios {
          field_name = "id"
          field_value = $auth.id
        } as $solicitante_atual

        conditional {
          if ($solicitante_atual == null || $solicitante_atual.status != "ativo" || $solicitante_atual.role != "admin") {
            var.update $estado { value = "negado" }
          }
        }

        // ---- Token (client credentials): prova tenant, client id e segredo ----
        // NÃO VERIFICADO: params + Content-Type form-urlencoded em api.request.
        conditional {
          if ($estado == "") {
            try_catch {
              try {
                api.request {
                  url = "https://login.microsoftonline.com/" ~ $tenant ~ "/oauth2/v2.0/token"
                  method = "POST"
                  params = {client_id: $client, client_secret: $segredo, scope: "https://management.azure.com/.default", grant_type: "client_credentials"}
                  headers = [
                    "Content-Type: application/x-www-form-urlencoded",
                    "User-Agent: costguard-xano/1.0"
                  ]
                  timeout = 10
                } as $resp_token
                var.update $t_status { value = ($resp_token.response.status ?? 0) }
                var.update $t_cabecalhos { value = ($resp_token.response.headers ?? []) }
                conditional {
                  if ($t_status == 200) {
                    var.update $t_token { value = (($resp_token.response.result.access_token ?? "")|to_text) }
                  }
                }
              }
              catch {
                var.update $t_status { value = 0 }
              }
            }

            // Token: só caracteres de JWT (base64url e pontos), tamanho limitado e
            // sem espaço/quebra (o `$` do regex aceita um "\n" final; o tamanho fecha a brecha).
            var $token_ok { value = ($t_status == 200 && ($t_token|strlen) >= 20 && ($t_token|strlen) <= 8192 && (($t_token|trim)|strlen) == ($t_token|strlen) && ("/^[A-Za-z0-9._~-]+$/"|regex_matches:$t_token)) }

            conditional {
              if ($t_status == 429) {
                var.update $estado { value = "limite" }
              }
              elseif ($token_ok == false) {
                var.update $estado { value = "recusado" }
              }
            }
          }
        }

        // ---- 429 do token: segundos de espera ----
        // MAIOR valor entre TODOS os cabeçalhos cujo nome CONTÉM "retry-after" (sem
        // diferenciar maiúsculas); sem nenhum, 60 s; limitado a 1..3600.
        // NÃO VERIFICADO: formato de response.headers no Xano (lista de textos
        // "Nome: valor" é a suposição) e o filtro contains.
        conditional {
          if ($estado == "limite") {
            var $seg_max { value = -1 }
            try_catch {
              try {
                foreach ($t_cabecalhos) {
                  each as $cabecalho {
                    var $cab_baixo { value = (($cabecalho|to_text)|to_lower) }
                    var $cab_nome { value = (($cab_baixo|split:":")|first)|trim }
                    var $cab_valor { value = (($cab_baixo|split:":")|last)|trim }
                    // Só inteiro simples (uma data HTTP em Retry-After é ignorada).
                    conditional {
                      if (($cab_nome|contains:"retry-after") && ("/^[0-9]{1,9}$/"|regex_matches:$cab_valor)) {
                        conditional {
                          if (($cab_valor|to_int) > $seg_max) {
                            var.update $seg_max { value = $cab_valor|to_int }
                          }
                        }
                      }
                    }
                  }
                }
              }
              catch {
                var.update $seg_max { value = -1 }
              }
            }

            var.update $segundos_restantes { value = 60 }
            conditional {
              if ($seg_max >= 0) {
                var.update $segundos_restantes { value = $seg_max }
              }
            }
            conditional {
              if ($segundos_restantes < 1) {
                var.update $segundos_restantes { value = 1 }
              }
              elseif ($segundos_restantes > 3600) {
                var.update $segundos_restantes { value = 3600 }
              }
            }
          }
        }

        // ---- Gravação (só com o token obtido) ----
        conditional {
          if ($estado == "") {
            // 1) Cifra os QUATRO dados ANTES de apagar qualquer coisa: se a chave
            //    (PROV_ENC_KEY) faltar ou falhar, nada foi alterado.
            var $tenant_cifrado { value = $tenant|jwe_encode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512" }
            var $client_cifrado { value = $client|jwe_encode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512" }
            var $segredo_cifrado { value = $segredo|jwe_encode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512" }
            var $assinatura_cifrada { value = $assinatura|jwe_encode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512" }

            // 2) Invalida a leitura guardada do Azure (todos os meses): pertencia a
            //    outra credencial/assinatura. Antes de gravar a conexão nova: se a
            //    gravação falhar, a conexão antiga fica e só se perde a leitura.
            db.query provedor_externo_leitura {
              where = $db.provedor_externo_leitura.provedor == "azure"
              return = {type: "list"}
            } as $leituras_antigas

            foreach ($leituras_antigas) {
              each as $leitura_antiga {
                db.del provedor_externo_leitura {
                  field_name = "id"
                  field_value = $leitura_antiga.id
                }
              }
            }

            // 3) Upsert da linha única (chave "azure"), sob a trava.
            var $agora_ms { value = now|to_int }

            db.get azure_conexao {
              field_name = "chave"
              field_value = "azure"
            } as $existente

            conditional {
              if ($existente == null) {
                db.add azure_conexao {
                  data = {
                    chave                  : "azure"
                    tenant_id_cifrado      : $tenant_cifrado
                    client_id_cifrado      : $client_cifrado
                    client_secret_cifrado  : $segredo_cifrado
                    subscription_id_cifrado: $assinatura_cifrada
                    apelido                : $apelido
                    tenant_final           : $tenant_final
                    atualizado_em          : $agora_ms
                    atualizado_por         : $solicitante_atual.id
                  }
                }
              }
              else {
                db.edit azure_conexao {
                  field_name = "id"
                  field_value = $existente.id
                  data = {
                    tenant_id_cifrado      : $tenant_cifrado
                    client_id_cifrado      : $client_cifrado
                    client_secret_cifrado  : $segredo_cifrado
                    subscription_id_cifrado: $assinatura_cifrada
                    apelido                : $apelido
                    tenant_final           : $tenant_final
                    atualizado_em          : $agora_ms
                    atualizado_por         : $solicitante_atual.id
                  }
                }
              }
            }

            var.update $estado { value = "salvo" }
          }
        }
      }
      catch {
        var.update $falha { value = true }
      }
      finally {
        conditional {
          if ($trava_id != null) {
            db.del travas {
              field_name = "id"
              field_value = $trava_id
            }
          }
        }
      }
    }

    precondition ($falha == false) {
      error_type = "standard"
      error = "Não foi possível salvar a conexão do Azure agora. Tente novamente em instantes."
    }

    precondition ($estado != "negado") {
      error_type = "accessdenied"
      error = "Acesso negado"
    }

    var $msg_limite {
      value = "O Azure limitou as requisições. Aguarde " ~ ($segundos_restantes|to_text) ~ " segundos para tentar de novo."
    }

    precondition ($estado != "limite") {
      error_type = "toomanyrequests"
      error = $msg_limite
    }

    precondition ($estado != "recusado") {
      error_type = "inputerror"
      error = "Não foi possível autenticar no Azure com os dados informados."
    }

    precondition ($estado == "salvo") {
      error_type = "standard"
      error = "Não foi possível salvar a conexão do Azure agora. Tente novamente em instantes."
    }

    var $resposta {
      value = {conectado: true}
    }
  }

  response = $resposta
}
