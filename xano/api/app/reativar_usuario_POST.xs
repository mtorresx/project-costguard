query "usuarios/{id}/reativar" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id
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

    db.get usuarios {
      field_name = "id"
      field_value = $input.id
    } as $alvo

    precondition ($alvo != null) {
      error_type = "notfound"
      error = "Usuário não encontrado."
    }

    db.edit usuarios {
      field_name = "id"
      field_value = $input.id
      data = {status: "ativo"}
    } as $atualizado

    var $resposta {
      value = {
        id      : $atualizado.id
        nome    : $atualizado.nome
        username: $atualizado.username
        email   : $atualizado.email
        role    : $atualizado.role
        status  : $atualizado.status
      }
    }
  }

  response = $resposta
}
