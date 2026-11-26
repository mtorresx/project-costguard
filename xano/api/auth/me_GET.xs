query me verb=GET {
  api_group = "auth"
  auth = "usuarios"

  input {
  }

  stack {
    db.get usuarios {
      field_name = "id"
      field_value = $auth.id
    } as $usuario_atual
  
    // Usuário inexistente ou desativado: sessão inválida (HTTP 401).
    precondition ($usuario_atual != null && $usuario_atual.status == "ativo") {
      error_type = "unauthorized"
      error = "Token inválido ou expirado"
    }
  
    // Monta a resposta com os dados atuais do banco
    var $dados_usuario {
      value = {
        username: $usuario_atual.username
        nome    : $usuario_atual.nome
        role    : $usuario_atual.role
      }
    }
  }

  response = $dados_usuario
  guid = "cH6naWTcuIwyJ_QoGqFEulojCDw"
}