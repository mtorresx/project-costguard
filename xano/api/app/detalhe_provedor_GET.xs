query "provedores/{id}" verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
  }

  stack {
    db.get provedores {
      field_name = "id"
      field_value = $input.id
    } as $provedor

    precondition ($provedor != null) {
      error_type = "notfound"
      error = "Provedor não encontrado"
    }

    // Resposta apenas com metadados — segredo e IV nunca são retornados.
    var $resposta {
      value = {
        id                 : $provedor.id
        apelido            : $provedor.apelido
        tipo               : $provedor.tipo
        identificador_conta: $provedor.identificador_conta
        tipo_credencial    : $provedor.tipo_credencial
        tag_alocacao_projeto: $provedor.tag_alocacao_projeto
        tag_alocacao_equipe: $provedor.tag_alocacao_equipe
        usar_mock          : $provedor.usar_mock
        status             : $provedor.status
      }
    }
  }

  response = $resposta
  guid = "07Jk2boMLlQj5Ui0pa3_fMVulXo"
}
