// Sincronização MANUAL do custo do mês corrente da assinatura Azure (provedor
// somente leitura; custo NÃO ALOCADO). Só admin ativo. SEM input: nada do corpo
// é lido. Não entra no ciclo automático (sincronizacao_automatica_POST) nem em
// nenhum outro fluxo; não se mistura aos custos AWS/projetos/painel.
//
// Nada é criado, alterado ou apagado no Azure: duas chamadas de leitura no
// máximo por requisição (1 token + 1 consulta), sem laço, sem paginação, sem
// retentativa.
//
// CREDENCIAIS (ordem): 1) cadastro feito pela tela (tabela `azure_conexao`,
// cifrado com JWE e `$env.PROV_ENC_KEY`), 2) como RESERVA, as variáveis de
// ambiente do Xano (AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
// AZURE_SUBSCRIPTION_ID; opcional AZURE_COST_API_VERSION, padrão 2023-11-01,
// versão testada no Azure real). Cadastro que existe mas não decifra =
// configuracao_invalida, sem cair nas variáveis. O formato das variáveis do servidor
// e o tenant do cadastro são validados em costguard/azure_config_estado ANTES de montar
// qualquer URL, já COM a trava tomada (a função devolve só estado/origem/versão; do
// cadastro ela decifra apenas o tenant). Os QUATRO campos do cadastro são decifrados
// AQUI, dentro do endpoint, nunca devolvidos por função nem passados como input de
// função (o histórico de requisições do Xano guarda input e resposta de funções), e
// REVALIDADOS aqui (GUIDs e a mesma regra do segredo do POST /azure/conexao). Cadastro
// que não decifra ou está fora do formato NÃO vira 200 silencioso: nada é chamado no
// Azure, grava-se o desfecho genérico (status "indisponivel" com erro_resumo FIXO "O
// cadastro do Azure guardado no servidor não pôde ser lido. Cadastre a conexão
// novamente.", sem eco de valores; a coluna `status` é um enum fechado e a tabela não
// é republicada) e costguard/azure_custo_estado devolve esse par como status
// "configuracao_invalida" (origem "tela", sem custo). Sem credenciais: responde 200 com status
// "nao_configurado" e custo null (nunca 0), sem chamar o Azure. Tenant, client
// id, segredo, assinatura, token e o corpo da resposta do Azure NUNCA são
// gravados em tabela de leitura, registrados nem devolvidos.
//
// Regras:
//   - SEM cache de 4 h: cada clique de admin que passa pelas travas abaixo faz
//     leitura real no Azure. O estado guardado continua sendo devolvido pelo GET
//     e quando o POST não consulta (cooldown ou 429 vigente);
//   - trava anti-concorrência (tabela travas, órfã > 2 min) para dois cliques
//     simultâneos não gerarem duas chamadas. É A MESMA trava do cadastro
//     (POST/DELETE /azure/conexao): trocar a conexão e sincronizar nunca correm
//     juntos, então uma leitura feita com a credencial antiga não é gravada depois
//     de a leitura guardada ser apagada;
//   - cooldown de 60 s: se a última TENTATIVA (tentativa_em, sucesso OU falha)
//     tem menos de 60 s, não chama o Azure e devolve o estado guardado
//     (origem "cooldown", HTTP 200);
//   - tentativa_em é gravado ANTES de chamar o Azure (a linha do mês é criada
//     sem valor se não existir): uma exceção posterior não perde o cooldown nem
//     o bloqueio. O parse da resposta fica em try_catch próprio: qualquer falha
//     vira "indisponivel" (mantém o último valor), nunca 500;
//   - 429 do Azure (na consulta OU no token): NÃO repete; guarda o bloqueio
//     (bloqueado_ate) e responde HTTP 429 com os segundos (1 a 3600) na mensagem;
//     chamadas seguintes dentro do bloqueio respondem 429 sem chamar o Azure.
//     Segundos = MAIOR valor entre TODOS os cabeçalhos cujo nome CONTÉM
//     "retry-after" (sem diferenciar maiúsculas; ex.: Retry-After,
//     ...clienttype-retry-after, ...qpu-retry-after); sem nenhum, 60;
//   - 401/403 => status "sem_permissao"; 5xx/timeout => "indisponivel" mantendo
//     o último valor; 204 ou sem linhas (HTTP 200 com rows vazia: caso real de
//     um mês sem consumo, sem a coluna de moeda) => "sem_dados": NÃO é erro; é
//     uma leitura BEM-SUCEDIDA (atualizado_em = agora, configurado, custo null,
//     NÃO zero, moeda null; descarta o último valor conhecido do mês, decisão de
//     produto);
//     nextLink presente ou mais de uma linha => "resposta_incompleta" (não
//     pagina, não guarda valor).
// Resposta: os campos do GET + `origem` (como foi esta resposta: "azure" =
// consultou agora, "cooldown" = devolveu o estado guardado sem chamar o Azure,
// null = sem credenciais) + `origem_credencial` ("tela" | "servidor" | null: de
// onde vêm as credenciais; é a `origem` do GET, renomeada aqui para não colidir).
// O valor antigo "cache" NÃO existe mais.
query "azure/custo/sincronizar" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
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

    var $estado { value = "" }
    var $falha { value = false }
    var $segundos_restantes { value = 0 }
    var $trava_id { value = null }
    var $trava_ocupada { value = false }

    // ============================================================
    // Trava de exclusão mútua (tabela travas, índice único em `nome`): só uma
    // sincronização por vez, e a MESMA trava do cadastro da conexão (POST/DELETE
    // /azure/conexao). Removida no finally; trava órfã (> 2 min, acima dos
    // timeouts das duas chamadas) é removida na primeira tentativa seguinte.
    // A configuração é conferida DENTRO da trava (ver adiante).
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
      error = "Já existe uma sincronização do custo do Azure em andamento. Tente novamente em instantes."
    }

    // Seção crítica: não lança erro; registra o desfecho em variáveis, libera a
    // trava no finally e só depois responde.
    var $desfecho { value = "" }
    var $erro_texto { value = "" }
    var $q_status { value = 0 }
    var $q_colunas { value = [] }
    var $q_linhas { value = [] }
    var $q_proximo { value = "" }
    var $q_cabecalhos { value = [] }
    var $t_cabecalhos { value = [] }
    var $l_cabecalhos { value = [] }
    var $novo_custo { value = 0 }
    var $nova_moeda { value = "" }

    // Credenciais em uso: preenchidas DENTRO da seção crítica (cadastro da tela
    // decifrado aqui, ou variáveis do servidor), nunca devolvidas nem gravadas.
    var $origem_cred { value = null }
    var $versao_api { value = "" }
    var $c_tenant { value = "" }
    var $c_client { value = "" }
    var $c_segredo { value = "" }
    var $c_assinatura { value = "" }

    try_catch {
      try {
        conditional {
          if ($estado == "") {
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
          }
        }

        // Configuração (com a trava tomada): formato validado antes de qualquer
        // URL; a função devolve só estado, origem ("tela" | "servidor") e versão.
        conditional {
          if ($estado == "") {
            function.run "costguard/azure_config_estado" {
              input = {}
            } as $config

            var.update $origem_cred { value = $config.origem }
            var.update $versao_api { value = $config.versao_api }

            conditional {
              if ($config.estado != "ok") {
                var.update $estado { value = "sem_config" }
              }
            }
          }
        }

        // Credenciais: cadastro da tela primeiro (decifrado AQUI, no endpoint);
        // variáveis do servidor só como reserva (origem "servidor", já validadas
        // pela função de configuração). Falha ao decifrar ou formato inválido = sem
        // chamar o Azure ("cadastro_invalido", gravado adiante).
        conditional {
          if ($estado == "") {
            conditional {
              if ($origem_cred == "tela") {
                db.get azure_conexao {
                  field_name = "chave"
                  field_value = "azure"
                } as $cadastro

                // Decifra e REVALIDA o formato (mesmas regras do POST /azure/conexao:
                // GUIDs de 36 caracteres e segredo ASCII visível de 8 a 256 caracteres).
                // Qualquer falha (decifragem ou formato) = "cadastro_invalido": nada é
                // chamado no Azure e nada é ecoado; o desfecho é gravado adiante.
                try_catch {
                  try {
                    var.update $c_tenant { value = (($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }
                    var.update $c_client { value = (($cadastro.client_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }
                    var.update $c_segredo { value = (($cadastro.client_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }
                    var.update $c_assinatura { value = (($cadastro.subscription_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }

                    var $c_tenant_ok { value = (($c_tenant|strlen) == 36 && ("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$c_tenant)) }
                    var $c_client_ok { value = (($c_client|strlen) == 36 && ("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$c_client)) }
                    var $c_assinatura_ok { value = (($c_assinatura|strlen) == 36 && ("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$c_assinatura)) }
                    var $c_segredo_ok { value = (($c_segredo|strlen) >= 8 && ($c_segredo|strlen) <= 256 && ("/^[!-~]+$/"|regex_matches:$c_segredo)) }

                    conditional {
                      if ($c_tenant_ok == false || $c_client_ok == false || $c_assinatura_ok == false || $c_segredo_ok == false) {
                        var.update $estado { value = "cadastro_invalido" }
                      }
                    }
                  }
                  catch {
                    var.update $estado { value = "cadastro_invalido" }
                  }
                }
              }
              else {
                var.update $c_tenant { value = (($env.AZURE_TENANT_ID ?? "")|trim) }
                var.update $c_client { value = (($env.AZURE_CLIENT_ID ?? "")|trim) }
                var.update $c_segredo { value = (($env.AZURE_CLIENT_SECRET ?? "")|trim) }
                var.update $c_assinatura { value = (($env.AZURE_SUBSCRIPTION_ID ?? "")|trim) }
              }
            }
          }
        }

        conditional {
          if ($estado == "") {
            var $agora_ms { value = now|to_int }
            var $mes_atual { value = $agora_ms|format_timestamp:"Y-m":"UTC" }
            var $cooldown_ms { value = 60000 }

            db.query provedor_externo_leitura {
              where = $db.provedor_externo_leitura.provedor == "azure" && $db.provedor_externo_leitura.mes_referencia == $mes_atual
              return = {type: "list"}
            } as $linhas_mes
            var $linha { value = (($linhas_mes|count) > 0) ? ($linhas_mes|first) : null }

            // Valores a gravar: por padrão, mantêm o que já está guardado.
            // custo_mes_total é anulável: sem valor = null (nunca 0). `db.edit`
            // IGNORA null, então numa linha já existente o custo antigo permanece
            // na coluna; quem manda é `tem_valor` (o GET só devolve o custo com
            // tem_valor = true). Em linha NOVA (db.add) o null é gravado de fato.
            var $n_custo { value = ($linha != null) ? $linha.custo_mes_total : null }
            var $n_moeda { value = ($linha != null) ? ($linha.moeda ?? "") : "" }
            var $n_atualizado { value = ($linha != null) ? ($linha.atualizado_em ?? 0) : 0 }
            var $n_tem_valor { value = ($linha != null) ? ($linha.tem_valor ?? false) : false }
            var $n_status { value = ($linha != null) ? $linha.status : "sem_leitura" }
            var $n_erro { value = ($linha != null) ? ($linha.erro_resumo ?? "") : "" }
            var $n_bloqueio { value = ($linha != null) ? ($linha.bloqueado_ate ?? 0) : 0 }
            var $n_tentativa { value = ($linha != null) ? ($linha.tentativa_em ?? 0) : 0 }

            // SEM cache de 4 h: cada clique faz leitura real, salvo:
            // 1) Bloqueio por 429 anterior: não chama o Azure (responde 429).
            // 2) Cooldown de 60 s após qualquer tentativa (sucesso OU falha):
            //    não chama o Azure e devolve o estado guardado (200).
            conditional {
              if ($linha != null && $linha.bloqueado_ate > $agora_ms) {
                var $resto_bloqueio { value = ((($linha.bloqueado_ate - $agora_ms) / 1000)|round:0)|to_int }
                var.update $segundos_restantes { value = $resto_bloqueio }
                conditional {
                  if ($segundos_restantes < 1) {
                    var.update $segundos_restantes { value = 1 }
                  }
                  elseif ($segundos_restantes > 3600) {
                    var.update $segundos_restantes { value = 3600 }
                  }
                }
                var.update $estado { value = "limite" }
              }
              elseif ($linha != null && ($linha.tentativa_em ?? 0) > 0 && ($agora_ms - $linha.tentativa_em) < $cooldown_ms) {
                var.update $estado { value = "cooldown" }
              }
            }

            conditional {
              if ($estado == "") {
                var.update $n_tentativa { value = $agora_ms }

                // Grava a tentativa ANTES de chamar o Azure (cria a linha do mês
                // sem valor, se preciso). Assim uma exceção depois da chamada não
                // perde o cooldown nem, nos demais caminhos, o bloqueio.
                conditional {
                  if ($linha == null) {
                    db.add provedor_externo_leitura {
                      data = {
                        provedor      : "azure"
                        mes_referencia: $mes_atual
                        custo_mes_total: null
                        moeda         : ""
                        atualizado_em : 0
                        tem_valor     : false
                        status        : "sem_leitura"
                        erro_resumo   : ""
                        tentativa_em  : $agora_ms
                        bloqueado_ate : 0
                      }
                    } as $linha_nova
                    var.update $linha { value = $linha_nova }
                  }
                  else {
                    db.edit provedor_externo_leitura {
                      field_name = "id"
                      field_value = $linha.id
                      data = {tentativa_em: $agora_ms}
                    }
                  }
                }

                // ---- (1) Token (client credentials) ----
                // NÃO VERIFICADO: params + Content-Type form-urlencoded em api.request.
                var $t_status { value = 0 }
                var $t_token { value = "" }
                try_catch {
                  try {
                    api.request {
                      url = "https://login.microsoftonline.com/" ~ $c_tenant ~ "/oauth2/v2.0/token"
                      method = "POST"
                      params = {client_id: $c_client, client_secret: $c_segredo, scope: "https://management.azure.com/.default", grant_type: "client_credentials"}
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

                // Token: só caracteres de JWT (base64url e pontos), tamanho limitado:
                // vai num cabeçalho, então nada com espaço ou quebra de linha. O `$`
                // do regex aceita um "\n" final; por isso o tamanho do token sem
                // espaços/quebras (trim) tem de ser igual ao tamanho original.
                var $token_ok { value = ($t_status == 200 && ($t_token|strlen) >= 20 && ($t_token|strlen) <= 8192 && (($t_token|trim)|strlen) == ($t_token|strlen) && ("/^[A-Za-z0-9._~-]+$/"|regex_matches:$t_token)) }

                conditional {
                  if ($t_status == 429) {
                    // Limite no endpoint do TOKEN: tratado como o 429 da consulta
                    // (sem repetir, bloqueio guardado, HTTP 429 com os segundos).
                    var.update $l_cabecalhos { value = $t_cabecalhos }
                    var.update $desfecho { value = "limite" }
                  }
                  elseif ($token_ok == false && ($t_status == 400 || $t_status == 401 || $t_status == 403)) {
                    var.update $desfecho { value = "sem_permissao" }
                    var.update $erro_texto { value = "O Azure recusou as credenciais." }
                  }
                  elseif ($token_ok == false && $t_status == 200) {
                    var.update $desfecho { value = "indisponivel" }
                    var.update $erro_texto { value = "A resposta do Azure veio em formato inesperado." }
                  }
                  elseif ($token_ok == false) {
                    var.update $desfecho { value = "indisponivel" }
                    var.update $erro_texto { value = "O Azure não respondeu agora. Tente novamente mais tarde." }
                  }
                }

                // ---- (2) Consulta de custo do mês corrente (uma única chamada) ----
                conditional {
                  if ($desfecho == "") {
                    var $corpo_consulta {
                      value = "{\"type\":\"ActualCost\",\"timeframe\":\"MonthToDate\",\"dataset\":{\"granularity\":\"None\",\"aggregation\":{\"totalCost\":{\"name\":\"Cost\",\"function\":\"Sum\"}}}}"|json_decode
                    }

                    try_catch {
                      try {
                        api.request {
                          url = "https://management.azure.com/subscriptions/" ~ $c_assinatura ~ "/providers/Microsoft.CostManagement/query?api-version=" ~ $versao_api
                          method = "POST"
                          params = $corpo_consulta
                          headers = [
                            "Content-Type: application/json",
                            "Authorization: Bearer " ~ $t_token,
                            "User-Agent: costguard-xano/1.0"
                          ]
                          timeout = 15
                        } as $resp_custo
                        var.update $q_status { value = ($resp_custo.response.status ?? 0) }
                        var.update $q_cabecalhos { value = ($resp_custo.response.headers ?? []) }
                        var.update $q_colunas { value = ($resp_custo.response.result.properties.columns ?? []) }
                        var.update $q_linhas { value = ($resp_custo.response.result.properties.rows ?? []) }
                        var.update $q_proximo { value = (($resp_custo.response.result.properties.nextLink ?? "")|to_text) }
                      }
                      catch {
                        var.update $q_status { value = 0 }
                      }
                    }

                    conditional {
                      if ($q_status == 200) {
                        // Parse da resposta em try_catch próprio: qualquer exceção (get por índice,
                        // to_decimal, count em tipo inesperado...) vira "indisponivel" (mantém o
                        // último valor) em vez de 500.
                        try_catch {
                          try {
                              conditional {
                                if ($q_proximo != "") {
                                  // Agregação única não deve paginar: NÃO segue o nextLink.
                                  var.update $desfecho { value = "resposta_incompleta" }
                                  var.update $erro_texto { value = "A resposta do Azure veio paginada; o valor não foi guardado." }
                                }
                                elseif (($q_linhas|count) == 0) {
                                  // HTTP 200 com rows = []: mês sem consumo (a moeda não vem).
                                  var.update $desfecho { value = "sem_dados" }
                                }
                                elseif (($q_linhas|count) > 1) {
                                  var.update $desfecho { value = "resposta_incompleta" }
                                  var.update $erro_texto { value = "A resposta do Azure trouxe mais de uma linha (moedas diferentes?); o valor não foi guardado." }
                                }
                                else {
                                  // Colunas localizadas pelo NOME (Cost e Currency, sem diferenciar
                                  // maiúsculas), nunca pela posição. Com linhas mas sem uma delas,
                                  // ou com valor inválido: "indisponivel" (moeda nunca é adivinhada).
                                  var $idx_custo { value = -1 }
                                  var $idx_moeda { value = -1 }
                                  var $idx_atual { value = 0 }
                                  foreach ($q_colunas) {
                                    each as $coluna {
                                      var $nome_coluna { value = (($coluna.name ?? "")|to_lower) }
                                      conditional {
                                        if ($nome_coluna == "cost") {
                                          var.update $idx_custo { value = $idx_atual }
                                        }
                                        elseif ($nome_coluna == "currency") {
                                          var.update $idx_moeda { value = $idx_atual }
                                        }
                                      }
                                      var.update $idx_atual { value = $idx_atual + 1 }
                                    }
                                  }

                                  var $linha_azure { value = ($q_linhas|first) }
                                  var $valor_txt { value = "" }
                                  var $moeda_txt { value = "" }
                                  conditional {
                                    if ($idx_custo >= 0 && $idx_moeda >= 0) {
                                      var.update $valor_txt { value = (($linha_azure|get:$idx_custo:"")|to_text) }
                                      var.update $moeda_txt { value = (($linha_azure|get:$idx_moeda:"")|to_text) }
                                    }
                                  }

                                  // O `$` dos regex aceita quebra de linha final: o tamanho fecha a
                                  // brecha (moeda com exatamente 3 caracteres; valor sem espaços/quebras).
                                  conditional {
                                    if (($moeda_txt|strlen) == 3 && ($valor_txt|strlen) <= 40 && (($valor_txt|trim)|strlen) == ($valor_txt|strlen) && ("/^-?[0-9]+([.][0-9]+)?([eE][-+]?[0-9]+)?$/"|regex_matches:$valor_txt) && ("/^[A-Za-z]{3}$/"|regex_matches:$moeda_txt)) {
                                      var.update $novo_custo { value = $valor_txt|to_decimal }
                                      var.update $nova_moeda { value = $moeda_txt|to_upper }
                                      var.update $desfecho { value = "ok" }
                                    }
                                    else {
                                      var.update $desfecho { value = "indisponivel" }
                                      var.update $erro_texto { value = "A resposta do Azure veio em formato inesperado." }
                                    }
                                  }
                                }
                              }
                          }
                          catch {
                            var.update $desfecho { value = "indisponivel" }
                            var.update $erro_texto { value = "A resposta do Azure veio em formato inesperado." }
                          }
                        }
                      }
                      elseif ($q_status == 204) {
                        var.update $desfecho { value = "sem_dados" }
                      }
                      elseif ($q_status == 401 || $q_status == 403) {
                        var.update $desfecho { value = "sem_permissao" }
                        var.update $erro_texto { value = "O Azure recusou o acesso. Confira o papel Cost Management Reader do aplicativo na assinatura." }
                      }
                      elseif ($q_status == 429) {
                        // NÃO repete a chamada. Os segundos são calculados adiante,
                        // uma única vez para o 429 do token e o da consulta.
                        var.update $l_cabecalhos { value = $q_cabecalhos }
                        var.update $desfecho { value = "limite" }
                      }
                      else {
                        // 5xx, timeout/exceção (status 0) e demais códigos.
                        var.update $desfecho { value = "indisponivel" }
                        var.update $erro_texto { value = "O Azure não respondeu agora. Mostrando o último valor guardado, se houver." }
                      }
                    }
                  }
                }

                // ---- 429 (token ou consulta): segundos de espera ----
                // MAIOR valor entre TODOS os cabeçalhos cujo nome CONTÉM "retry-after"
                // (sem diferenciar maiúsculas: Retry-After e os "...clienttype-retry-after"
                // / "...qpu-retry-after" do Cost Management; "...-remaining" não conta);
                // sem nenhum, 60 s; limitado a 1..3600. Provado no Azure real: o 429 traz
                // x-ms-ratelimit-microsoft.costmanagement-clienttype-retry-after em segundos.
                // NÃO VERIFICADO: formato de response.headers no Xano (lista de
                // textos "Nome: valor" é a suposição) e o filtro contains.
                conditional {
                  if ($desfecho == "limite") {
                    var $seg_max { value = -1 }
                    try_catch {
                      try {
                        foreach ($l_cabecalhos) {
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

                // ---- (3) Valores a gravar conforme o desfecho ----
                conditional {
                  if ($desfecho == "ok") {
                    var.update $n_custo { value = $novo_custo }
                    var.update $n_moeda { value = $nova_moeda }
                    var.update $n_atualizado { value = $agora_ms }
                    var.update $n_tem_valor { value = true }
                    var.update $n_status { value = "ok" }
                    var.update $n_erro { value = "" }
                    var.update $n_bloqueio { value = 0 }
                  }
                  elseif ($desfecho == "sem_dados") {
                    // NÃO é erro: leitura bem-sucedida sem consumo no mês. Guarda o instante
                    // da leitura e descarta o valor anterior; custo null, não 0.
                    var.update $n_atualizado { value = $agora_ms }
                    var.update $n_moeda { value = "" }
                    var.update $n_tem_valor { value = false }
                    var.update $n_status { value = "sem_dados" }
                    var.update $n_erro { value = "" }
                    var.update $n_bloqueio { value = 0 }
                    var.update $n_custo { value = null }
                  }
                  elseif ($desfecho == "sem_permissao" || $desfecho == "resposta_incompleta") {
                    // Nenhuma leitura bem-sucedida vale mais: zera atualizado_em (o GET não
                    // mostra hora de leitura quando a última tentativa foi uma falha).
                    var.update $n_atualizado { value = 0 }
                    var.update $n_tem_valor { value = false }
                    var.update $n_status { value = $desfecho }
                    var.update $n_erro { value = $erro_texto }
                    var.update $n_custo { value = null }
                  }
                  elseif ($desfecho == "indisponivel") {
                    // Mantém a última leitura bem-sucedida (valor, tem_valor e atualizado_em intactos).
                    var.update $n_status { value = "indisponivel" }
                    var.update $n_erro { value = $erro_texto }
                  }
                  elseif ($desfecho == "limite") {
                    // Mantém status e valor; só registra o bloqueio.
                    var.update $n_bloqueio { value = $agora_ms + ($segundos_restantes * 1000) }
                  }
                }

                // Guarda o último valor: SOMENTE estes campos, nunca credenciais,
                // token ou corpo da resposta do Azure. A linha do mês já existe
                // (criada/atualizada antes da chamada), então aqui é sempre db.edit.
                db.edit provedor_externo_leitura {
                  field_name = "id"
                  field_value = $linha.id
                  data = {
                    custo_mes_total: $n_custo
                    moeda         : $n_moeda
                    atualizado_em : $n_atualizado
                    tem_valor     : $n_tem_valor
                    status        : $n_status
                    erro_resumo   : $n_erro
                    tentativa_em  : $n_tentativa
                    bloqueado_ate : $n_bloqueio
                  }
                }

                conditional {
                  if ($desfecho == "limite") {
                    var.update $estado { value = "limite" }
                  }
                  else {
                    var.update $estado { value = "consultado" }
                  }
                }
              }
            }
          }
        }

        // Cadastro da tela que não decifra ou está fora do formato (detectado AQUI):
        // nada foi chamado no Azure. Grava o desfecho genérico na linha do mês (status
        // "indisponivel" + erro_resumo FIXO, igual ao texto de configuracao_invalida/tela
        // em costguard/azure_custo_estado, que o devolve como "configuracao_invalida"):
        // sem 200 silencioso e sem eco de valores. Não mexe em tentativa_em nem no
        // bloqueio do 429 de uma linha existente.
        conditional {
          if ($estado == "cadastro_invalido") {
            var $agora_inv { value = now|to_int }
            var $mes_inv { value = $agora_inv|format_timestamp:"Y-m":"UTC" }

            db.query provedor_externo_leitura {
              where = $db.provedor_externo_leitura.provedor == "azure" && $db.provedor_externo_leitura.mes_referencia == $mes_inv
              return = {type: "list"}
            } as $linhas_inv

            conditional {
              if (($linhas_inv|count) > 0) {
                var $linha_inv { value = ($linhas_inv|first) }
                db.edit provedor_externo_leitura {
                  field_name = "id"
                  field_value = $linha_inv.id
                  data = {
                    status     : "indisponivel"
                    erro_resumo: "O cadastro do Azure guardado no servidor não pôde ser lido. Cadastre a conexão novamente."
                  }
                }
              }
              else {
                db.add provedor_externo_leitura {
                  data = {
                    provedor      : "azure"
                    mes_referencia: $mes_inv
                    custo_mes_total: null
                    moeda         : ""
                    atualizado_em : 0
                    tem_valor     : false
                    status        : "indisponivel"
                    erro_resumo   : "O cadastro do Azure guardado no servidor não pôde ser lido. Cadastre a conexão novamente."
                    tentativa_em  : 0
                    bloqueado_ate : 0
                  }
                }
              }
            }
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
      error = "Não foi possível sincronizar o custo do Azure agora. Tente novamente em instantes."
    }

    precondition ($estado != "negado") {
      error_type = "accessdenied"
      error = "Acesso negado"
    }

    var $msg_limite {
      value = "O Azure limitou as consultas de custo. Aguarde " ~ ($segundos_restantes|to_text) ~ " segundos para tentar de novo."
    }

    precondition ($estado != "limite") {
      error_type = "toomanyrequests"
      error = $msg_limite
    }

    // Estado guardado (já com o resultado desta sincronização).
    function.run "costguard/azure_custo_estado" {
      input = {}
    } as $guardado

    // `origem` = como foi ESTA resposta: "azure" (consultou agora), "cooldown"
    // (estado guardado, sem chamar o Azure) ou null (sem credenciais). O antigo
    // "cache" não existe mais. `origem_credencial` = de onde vêm as credenciais
    // ("tela" | "servidor" | null), a `origem` do GET com outro nome para não colidir.
    var $origem { value = ($estado == "cooldown") ? "cooldown" : (($estado == "consultado") ? "azure" : null) }

    var $resposta {
      value = {
        provedor          : $guardado.provedor
        configurado       : $guardado.configurado
        status            : $guardado.status
        nao_alocado       : true
        custo_mes_total   : $guardado.custo_mes_total
        moeda             : $guardado.moeda
        atualizado_em     : $guardado.atualizado_em
        mes_referencia    : $guardado.mes_referencia
        erro_resumo       : $guardado.erro_resumo
        proxima_leitura_em: $guardado.proxima_leitura_em
        origem            : $origem
        origem_credencial : $guardado.origem
      }
    }
  }

  response = $resposta
}
