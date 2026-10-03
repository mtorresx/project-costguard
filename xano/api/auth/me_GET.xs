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
  
    conditional {
      if ($usuario_atual == null) {
        return {
          value = {erro: "Token inválido ou expirado"}
        }
      }
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