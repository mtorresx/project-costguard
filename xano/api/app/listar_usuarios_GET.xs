query usuarios verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
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

    db.query usuarios {
      sort = {id: "asc"}
      return = {type: "list"}
    } as $lista

    // Nunca expõe senha_hash.
    var $resposta {
      value = $lista|map:{
        id      : $$.id,
        nome    : $$.nome,
        username: $$.username,
        email   : $$.email,
        role    : $$.role,
        status  : $$.status
      }
    }
  }

  response = $resposta
}
