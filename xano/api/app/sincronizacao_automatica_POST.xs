// Ciclo automático do inventário.
// Não usa token de usuário: exige o segredo do gatilho no cabeçalho
// X-Sync-Key, comparado com a variável de ambiente SYNC_AGENT_KEY. Sem
// parâmetros: o backend escolhe o provedor. Devolve só contadores.
query "sincronizacao/automatica" verb=POST {
  api_group = "app"

  input {
  }

  stack {
    var $chave_esperada { value = ($env.SYNC_AGENT_KEY ?? "") }
    var $chave_recebida { value = "" }
    try_catch {
      try {
        var.update $chave_recebida { value = $env.$http_headers|get:"X-Sync-Key":"" }
      }
      catch {
        var.update $chave_recebida { value = "" }
      }
    }

    // Segredo não configurado, ausente ou diferente: 401 sem detalhar.
    precondition ($chave_esperada != "" && $chave_recebida != null && $chave_recebida == $chave_esperada) {
      error_type = "unauthorized"
      error = "Não autorizado"
    }

    // No máximo um provedor por chamada: o elegível (status ok) com a
    // tentativa mais antiga. Intervalo mínimo de 90 s por provedor.
    db.query provedores {
      where = $db.provedores.status == "ok" && $db.provedores.tipo == "aws"
      sort = {id: "asc"}
      return = {type: "list"}
    } as $elegiveis

    var $agora_ms { value = now|to_int }
    var $intervalo_min_ms { value = 90000 }
    var $escolhido_id { value = 0 }
    var $escolhido_tentativa { value = 0 }

    foreach ($elegiveis) {
      each as $pv {
        var $tent { value = ($pv.inventario_ultima_tentativa != null) ? ($pv.inventario_ultima_tentativa|to_int) : 0 }
        conditional {
          if ($escolhido_id == 0 || $tent < $escolhido_tentativa) {
            var.update $escolhido_id { value = $pv.id }
            var.update $escolhido_tentativa { value = $tent }
          }
        }
      }
    }

    var $resposta {
      value = {
        executou            : false
        motivo              : "sem_provedor"
        status              : null
        recursos_criados    : 0
        recursos_alterados  : 0
        recursos_desativados: 0
      }
    }

    conditional {
      if ($escolhido_id != 0 && ($agora_ms - $escolhido_tentativa) < $intervalo_min_ms) {
        var.update $resposta {
          value = {
            executou            : false
            motivo              : "intervalo_minimo"
            status              : null
            recursos_criados    : 0
            recursos_alterados  : 0
            recursos_desativados: 0
          }
        }
      }
      elseif ($escolhido_id != 0) {
        function.run "costguard/sincronizar_inventario" {
          input = {provedor_id: $escolhido_id, origem: "automatica"}
        } as $saida

        conditional {
          if ($saida.ocupado == true) {
            var.update $resposta {
              value = {
                executou            : false
                motivo              : "em_andamento"
                status              : null
                recursos_criados    : 0
                recursos_alterados  : 0
                recursos_desativados: 0
              }
            }
          }
          else {
            var.update $resposta {
              value = {
                executou            : true
                motivo              : ""
                status              : $saida.resultado.status
                recursos_criados    : $saida.resultado.recursos_criados
                recursos_alterados  : $saida.resultado.recursos_alterados
                recursos_desativados: $saida.resultado.recursos_desativados
              }
            }
          }
        }
      }
    }
  }

  response = $resposta
}
