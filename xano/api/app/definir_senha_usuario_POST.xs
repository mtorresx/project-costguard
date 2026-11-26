query "usuarios/{id}/senha" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id
    text senha? {
      sensitive = true
    }
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

    precondition ($input.senha != null && ($input.senha|strlen) >= 8) {
      error_type = "inputerror"
      error = "A senha deve ter pelo menos 8 caracteres."
    }

    // Substitui a representação segura anterior (campo password do Xano).
    db.edit usuarios {
      field_name = "id"
      field_value = $input.id
      data = {senha_hash: $input.senha}
    } as $atualizado

    var $resposta {
      value = {id: $atualizado.id, senha_definida: true}
    }
  }

  response = $resposta
}
