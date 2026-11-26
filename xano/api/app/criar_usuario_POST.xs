query usuarios verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    text nome? filters=trim
    text username? filters=trim
    text email? filters=trim|lower
    text role? filters=trim
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

    precondition ($input.nome != null && $input.nome != "") {
      error_type = "inputerror"
      error = "Informe o nome."
    }

    precondition ($input.username != null && $input.username != "") {
      error_type = "inputerror"
      error = "Informe o nome de usuário."
    }

    precondition (($input.username|split:" "|count) == 1) {
      error_type = "inputerror"
      error = "O nome de usuário não pode conter espaços."
    }

    precondition ($input.email != null && $input.email != "") {
      error_type = "inputerror"
      error = "Informe o e-mail."
    }

    var $email_partes {
      value = $input.email|split:"@"
    }

    precondition (($email_partes|count) == 2 && ($email_partes|first) != "" && (($email_partes|last)|split:"."|count) >= 2 && ($input.email|split:" "|count) == 1) {
      error_type = "inputerror"
      error = "Informe um e-mail válido."
    }

    precondition ($input.role == "admin" || $input.role == "leitura") {
      error_type = "inputerror"
      error = "Papel inválido. Use admin ou leitura."
    }

    precondition ($input.senha != null && ($input.senha|strlen) >= 8) {
      error_type = "inputerror"
      error = "A senha deve ter pelo menos 8 caracteres."
    }

    db.get usuarios {
      field_name = "username"
      field_value = $input.username
    } as $mesmo_username

    precondition ($mesmo_username == null) {
      error_type = "inputerror"
      error = "Nome de usuário já está em uso."
    }

    db.get usuarios {
      field_name = "email"
      field_value = $input.email
    } as $mesmo_email

    precondition ($mesmo_email == null) {
      error_type = "inputerror"
      error = "E-mail já está em uso."
    }

    // senha_hash é do tipo password: o Xano nunca grava texto puro.
    db.add usuarios {
      data = {
        nome      : $input.nome
        username  : $input.username
        email     : $input.email
        role      : $input.role
        status    : "ativo"
        senha_hash: $input.senha
      }
    } as $novo

    var $resposta {
      value = {
        id      : $novo.id
        nome    : $novo.nome
        username: $novo.username
        email   : $novo.email
        role    : $novo.role
        status  : $novo.status
      }
    }
  }

  response = $resposta
}
