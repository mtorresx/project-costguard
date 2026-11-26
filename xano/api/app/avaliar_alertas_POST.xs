// Avaliação de alertas: lê o estado atual e reconcilia a tabela alertas
// Com simular=true devolve as ações previstas e não grava nada.
query "alertas/avaliar" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    bool simular?=false
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

    // Lógica em function "costguard/avaliar_alertas" (mesmo contrato).
    function.run "costguard/avaliar_alertas" {
      input = {simular: ($input.simular == true)}
    } as $resposta
  }

  response = $resposta
}
