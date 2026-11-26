query "provedores/{id}" verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
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
        status             : $provedor.status
      }
    }
  }

  response = $resposta
  guid = "07Jk2boMLlQj5Ui0pa3_fMVulXo"
}
