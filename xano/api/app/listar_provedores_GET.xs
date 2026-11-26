query provedores verb=GET {
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

    // Qualquer usuário autenticado pode listar (auth = "usuarios" garante 401 sem token).
    db.query provedores {
      sort = {criado_em: "desc"}
      return = {type: "list"}
    } as $lista_provedores

    // Monta a resposta sem expor segredo nem IV (apenas metadados).
    var $resposta {
      value = $lista_provedores|map:{
        id                 : $$.id,
        apelido            : $$.apelido,
        tipo               : $$.tipo,
        identificador_conta: $$.identificador_conta,
        tipo_credencial    : $$.tipo_credencial,
        tag_alocacao_projeto: $$.tag_alocacao_projeto,
        tag_alocacao_equipe: $$.tag_alocacao_equipe,
        status             : $$.status
      }
    }
  }

  response = $resposta
  guid = "wfGAR7qlY6Bwykfcty0jZnkVtDM"
}
