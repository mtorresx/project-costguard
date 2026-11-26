query "usuarios/{id}/desativar" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id
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

    db.get usuarios {
      field_name = "id"
      field_value = $input.id
    } as $alvo

    precondition ($alvo != null) {
      error_type = "notfound"
      error = "Usuário não encontrado."
    }

    precondition ($alvo.id != $usuario_logado.id) {
      error_type = "inputerror"
      error = "Você não pode desativar o próprio usuário."
    }

    // ============================================================
    // Trava de exclusão mútua (tabela travas, índice único em `nome`).
    // Toda operação que pode reduzir os administradores ativos roda sob a
    // trava; a releitura, a contagem e a única gravação acontecem com ela.
    // A trava não expira: só é removida pelo finally da própria requisição.
    // ============================================================
    var $trava_id { value = null }
    var $erro_aquisicao { value = false }

    foreach ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]) {
      each as $tentativa {
        conditional {
          if ($trava_id == null && $erro_aquisicao == false) {
            var $agora_ms { value = now|to_int }
            try_catch {
              try {
                db.add travas {
                  data = {nome: "admins", adquirida_em: $agora_ms}
                } as $nova_trava
                var.update $trava_id { value = $nova_trava.id }
              }
              catch {
                // Só um conflito com trava existente é "ocupado"; qualquer
                // outra falha de banco interrompe a aquisição.
                db.get travas {
                  field_name = "nome"
                  field_value = "admins"
                } as $trava_atual
                conditional {
                  if ($trava_atual == null) {
                    var.update $erro_aquisicao { value = true }
                  }
                  else {
                    util.sleep {
                      value = 0.5
                    }
                  }
                }
              }
            }
          }
        }
      }
    }

    precondition ($erro_aquisicao == false) {
      error_type = "standard"
      error = "Não foi possível iniciar a operação. Tente novamente."
    }

    precondition ($trava_id != null) {
      error_type = "inputerror"
      error = "Outra operação de administração está em andamento. Tente novamente em instantes. Se persistir, uma trava pendente pode precisar ser removida da tabela travas no Xano."
    }

    // Seção crítica: não lança erro; registra recusa/falha, libera a trava
    // no finally e só depois responde (try/finally sem catch engole erros).
    var $recusa { value = null }
    var $falha { value = false }
    var $negado { value = false }
    var $atualizado { value = null }

    try_catch {
      try {
        // Autorização refeita com a trava: o solicitante pode ter sido
        // desativado ou rebaixado enquanto aguardava.
        db.get usuarios {
          field_name = "id"
          field_value = $auth.id
        } as $solicitante_atual

        conditional {
          if ($solicitante_atual == null || $solicitante_atual.status != "ativo" || $solicitante_atual.role != "admin") {
            var.update $negado { value = true }
          }
        }

        // Releitura com a trava: estado atual do alvo e dos administradores.
        db.get usuarios {
          field_name = "id"
          field_value = $input.id
        } as $alvo_atual

        conditional {
          if ($alvo_atual.role == "admin" && $alvo_atual.status == "ativo") {
            db.query usuarios {
              where = $db.usuarios.role == "admin" && $db.usuarios.status == "ativo"
              return = {type: "list"}
            } as $admins_ativos

            conditional {
              if (($admins_ativos|count) <= 1) {
                var.update $recusa { value = "Não é possível desativar o único administrador ativo." }
              }
            }
          }
        }

        conditional {
          if ($recusa == null && $negado == false) {
            // Única gravação de negócio: somente o status (desativação lógica).
            db.edit usuarios {
              field_name = "id"
              field_value = $input.id
              data = {status: "inativo"}
            } as $editado
            var.update $atualizado { value = $editado }
          }
        }
      }
      catch {
        var.update $falha { value = true }
      }
      finally {
        db.del travas {
          field_name = "id"
          field_value = $trava_id
        }
      }
    }

    precondition ($falha == false) {
      error_type = "standard"
      error = "Não foi possível concluir a operação. Tente novamente."
    }

    precondition ($negado == false) {
      error_type = "accessdenied"
      error = "Acesso negado"
    }

    precondition ($recusa == null) {
      error_type = "inputerror"
      error = $recusa
    }

    var $resposta {
      value = {
        id      : $atualizado.id
        nome    : $atualizado.nome
        username: $atualizado.username
        email   : $atualizado.email
        role    : $atualizado.role
        status  : $atualizado.status
      }
    }
  }

  response = $resposta
}
