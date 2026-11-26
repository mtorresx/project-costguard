query alertas verb=GET {
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

    // Lógica em function "costguard/lista_alertas" (mesmo contrato).
    function.run "costguard/lista_alertas" {
      input = {}
    } as $resultado
  }

  response = $resultado
  guid = "nuykCofZfpoUCFaxCCYlcaZOLRc"
}
