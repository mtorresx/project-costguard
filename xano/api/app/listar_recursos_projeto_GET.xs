query "projetos/{id}/recursos" verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "projetos"
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

    // Lógica em function "costguard/recursos_projeto" (mesmo contrato).
    function.run "costguard/recursos_projeto" {
      input = {id: $input.id}
    } as $resultado
  }

  response = $resultado
  guid = "M-TZpHN9iUKqY-8ovjYJ9ZkcYKU"
}
