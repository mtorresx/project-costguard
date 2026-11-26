// Remove o cadastro da conexão do Azure feito PELA TELA (tabela `azure_conexao`).
// Só admin ativo. SEM input e SEM chamada ao Azure.
//
// Depois disto, o sistema volta a usar as variáveis AZURE_* do Xano como reserva,
// se existirem (senão o GET devolve "nao_configurado" e origem null). A leitura
// guardada em `provedor_externo_leitura` (provedor "azure", todos os meses) é
// APAGADA junto, pois pertencia à credencial removida; o GET volta a "sem_leitura"
// (reserva do servidor presente) ou a "nao_configurado". A leitura é apagada ANTES
// do cadastro: se a segunda etapa falhar, nunca sobra uma leitura antiga associada
// a outra credencial.
//
// IDEMPOTENTE: sem cadastro, responde 200 do mesmo jeito e NÃO mexe na leitura
// guardada (ela pertence às variáveis do servidor). Resposta: {"conectado": false},
// que diz só que NÃO há conexão cadastrada pela tela (o estado real, inclusive o das
// variáveis do servidor, vem do GET /azure/custo).
//
// Exclusão mútua: a MESMA trava do sincronizar e do cadastro (tabela travas, nome
// azure_custo_sincronizar); trava ocupada = HTTP 429. Nenhum segredo é lido,
// decifrado, registrado ou devolvido.
// NÃO VERIFICADO: `verb=DELETE` (sem
// precedente neste repositório); se o dry-run recusar, publicar como
// POST azure/conexao/remover.
query "azure/conexao" verb=DELETE {
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
    var $trava_id { value = null }
    var $trava_ocupada { value = false }

    // ============================================================
    // Trava de exclusão mútua (tabela travas, índice único em `nome`), a MESMA do
    // sincronizar e do cadastro. Removida no finally; trava órfã (> 2 min) é
    // removida na primeira tentativa seguinte.
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

        conditional {
          if ($estado == "") {
            db.get azure_conexao {
              field_name = "chave"
              field_value = "azure"
            } as $cadastro

            // Sem cadastro: nada a fazer (idempotente; a leitura guardada não é tocada).
            conditional {
              if ($cadastro != null) {
                // 1) Apaga a leitura guardada do Azure (todos os meses).
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

                // 2) Apaga o cadastro (única linha).
                db.del azure_conexao {
                  field_name = "id"
                  field_value = $cadastro.id
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
      error = "Não foi possível remover a conexão do Azure agora. Tente novamente em instantes."
    }

    precondition ($estado != "negado") {
      error_type = "accessdenied"
      error = "Acesso negado"
    }

    var $resposta {
      value = {conectado: false}
    }
  }

  response = $resposta
}
