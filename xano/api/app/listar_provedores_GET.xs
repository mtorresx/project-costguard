query provedores verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
  }

  stack {
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
        usar_mock          : $$.usar_mock,
        status             : $$.status
      }
    }
  }

  response = $resposta
  guid = "wfGAR7qlY6Bwykfcty0jZnkVtDM"
}
