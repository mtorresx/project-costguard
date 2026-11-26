// Estado da sincronização do inventário por provedor. Somente leitura; qualquer usuário
// autenticado. `versao` muda quando algum inventário muda: a tela só recarrega
// os dados quando ela muda.
query "sincronizacao/estado" verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
  }

  stack {
    // P2-10: usuário desativado (ou removido) perde também o acesso às leituras.
    db.get usuarios {
      field_name = "id"
      field_value = $auth.id
    } as $usuario_sessao

    precondition ($usuario_sessao != null && $usuario_sessao.status == "ativo") {
      error_type = "unauthorized"
      error = "Token inválido ou expirado"
    }

    db.query provedores {
      sort = {id: "asc"}
      return = {type: "list"}
    } as $lista_provedores

    var $itens { value = [] }
    var $versao { value = 0 }

    foreach ($lista_provedores) {
      each as $pv {
        conditional {
          if ($pv.status != "inativo") {
            var $mud { value = ($pv.inventario_ultima_mudanca != null) ? ($pv.inventario_ultima_mudanca|to_int) : 0 }
            conditional {
              if ($mud > $versao) {
                var.update $versao { value = $mud }
              }
            }
            var $item {
              value = {
                provedor_id     : $pv.id
                apelido         : $pv.apelido
                status_provedor : $pv.status
                ultima_tentativa: $pv.inventario_ultima_tentativa
                ultimo_sucesso  : $pv.inventario_ultimo_sucesso
                ultimo_status   : $pv.inventario_ultimo_status
                ultima_mensagem : $pv.inventario_ultima_mensagem
                ultima_origem   : $pv.inventario_ultima_origem
              }
            }
            var.update $itens { value = $itens|push:$item }
          }
        }
      }
    }

    var $agora_ms { value = now|to_int }
    var $resposta {
      value = {
        versao    : $versao
        agora     : $agora_ms
        provedores: $itens
      }
    }
  }

  response = $resposta
  guid = "0TC53kKBDBdDyEDcmkAnX2-hz3Q"
}
