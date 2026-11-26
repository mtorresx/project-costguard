// Limpeza de dados de TESTE. Apaga um provedor cujo apelido começa com
// "TESTE_" (comparação exata, sensível a maiúsculas) e somente as linhas
// ligadas a ele: recursos, custos, coletas e alertas. Nunca apaga projetos,
// equipes nem usuários. Exige admin ativo, apelido TESTE_ e identificador de
// conta fictício de teste (12 zeros). Qualquer outro provedor é recusado.
query "provedores/{id}/excluir-teste" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
  }

  stack {
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

    db.get provedores {
      field_name = "id"
      field_value = $input.id
    } as $provedor_alvo

    precondition ($provedor_alvo != null) {
      error_type = "notfound"
      error = "Provedor não encontrado"
    }

    var $apelido_alvo { value = ($provedor_alvo.apelido ?? "") }

    precondition ($apelido_alvo|starts_with:"TESTE_") {
      error_type = "accessdenied"
      error = "Somente provedores de teste (apelido iniciado por TESTE_) podem ser excluídos"
    }

    // Segunda barreira: provedor de teste usa sempre o identificador de conta
    // fictício (12 zeros, mesmo valor de CONTA_TESTE em tests/integracao/cliente.py).
    // Um provedor com conta real nunca é excluído por este endpoint, mesmo que o
    // apelido comece com TESTE_.
    var $conta_alvo { value = ($provedor_alvo.identificador_conta ?? "") }

    precondition ($conta_alvo == "000000000000") {
      error_type = "accessdenied"
      error = "Somente provedores de teste com a conta fictícia de teste podem ser excluídos"
    }

    db.query recursos {
      where = $db.recursos.provedor_id == $provedor_alvo.id
      return = {type: "list"}
    } as $linhas_recursos

    foreach ($linhas_recursos) {
      each as $linha {
        db.del recursos {
          field_name = "id"
          field_value = $linha.id
        }
      }
    }

    db.query custos_equipe {
      where = $db.custos_equipe.provedor_id == $provedor_alvo.id
      return = {type: "list"}
    } as $linhas_custos_equipe

    foreach ($linhas_custos_equipe) {
      each as $linha {
        db.del custos_equipe {
          field_name = "id"
          field_value = $linha.id
        }
      }
    }

    db.query custos_projeto {
      where = $db.custos_projeto.provedor_id == $provedor_alvo.id
      return = {type: "list"}
    } as $linhas_custos_projeto

    foreach ($linhas_custos_projeto) {
      each as $linha {
        db.del custos_projeto {
          field_name = "id"
          field_value = $linha.id
        }
      }
    }

    db.query custos {
      where = $db.custos.provedor_id == $provedor_alvo.id
      return = {type: "list"}
    } as $linhas_custos

    foreach ($linhas_custos) {
      each as $linha {
        db.del custos {
          field_name = "id"
          field_value = $linha.id
        }
      }
    }

    db.query coletas_inventario {
      where = $db.coletas_inventario.provedor_id == $provedor_alvo.id
      return = {type: "list"}
    } as $linhas_coletas_inventario

    foreach ($linhas_coletas_inventario) {
      each as $linha {
        db.del coletas_inventario {
          field_name = "id"
          field_value = $linha.id
        }
      }
    }

    db.query coletas_custos_equipe {
      where = $db.coletas_custos_equipe.provedor_id == $provedor_alvo.id
      return = {type: "list"}
    } as $linhas_coletas_custos_equipe

    foreach ($linhas_coletas_custos_equipe) {
      each as $linha {
        db.del coletas_custos_equipe {
          field_name = "id"
          field_value = $linha.id
        }
      }
    }

    db.query coletas_custo {
      where = $db.coletas_custo.provedor_id == $provedor_alvo.id
      return = {type: "list"}
    } as $linhas_coletas_custo

    foreach ($linhas_coletas_custo) {
      each as $linha {
        db.del coletas_custo {
          field_name = "id"
          field_value = $linha.id
        }
      }
    }

    db.query coletas_classificacao {
      where = $db.coletas_classificacao.provedor_id == $provedor_alvo.id
      return = {type: "list"}
    } as $linhas_coletas_classificacao

    foreach ($linhas_coletas_classificacao) {
      each as $linha {
        db.del coletas_classificacao {
          field_name = "id"
          field_value = $linha.id
        }
      }
    }

    db.query alertas {
      where = $db.alertas.provedor_id == $provedor_alvo.id
      return = {type: "list"}
    } as $linhas_alertas

    foreach ($linhas_alertas) {
      each as $linha {
        db.del alertas {
          field_name = "id"
          field_value = $linha.id
        }
      }
    }

    db.del provedores {
      field_name = "id"
      field_value = $provedor_alvo.id
    }

    var $resposta {
      value = {
        provedor_id           : $provedor_alvo.id
        apelido               : $apelido_alvo
        recursos              : ($linhas_recursos|count)
        custos_equipe         : ($linhas_custos_equipe|count)
        custos_projeto        : ($linhas_custos_projeto|count)
        custos                : ($linhas_custos|count)
        coletas_inventario    : ($linhas_coletas_inventario|count)
        coletas_custos_equipe : ($linhas_coletas_custos_equipe|count)
        coletas_custo         : ($linhas_coletas_custo|count)
        coletas_classificacao : ($linhas_coletas_classificacao|count)
        alertas               : ($linhas_alertas|count)
      }
    }
  }

  response = $resposta
}
