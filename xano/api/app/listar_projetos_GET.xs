query listar_projetos verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
  }

  stack {
    db.get usuarios {
      field_name = "id"
      field_value = $auth.id
    } as $usuario_logado
  
    precondition ($usuario_logado != null) {
      error_type = "unauthorized"
      error = "Token inválido ou expirado"
    }
  
    // Busca todos os projetos
    db.query projetos {
      return = {type: "list"}
    } as $lista_projetos
  }

  response = $lista_projetos
  guid = "Rq67Yh5IxHHQTFT06ErrUC8nktc"
}