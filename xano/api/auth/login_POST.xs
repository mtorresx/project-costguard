query login verb=POST {
  api_group = "auth"

  input {
    text usuario
    text senha
  }

  stack {
    // Busca o usuário no banco
    db.get usuarios {
      field_name = "usuario"
      field_value = $input.usuario
    } as $usuario_encontrado
  
    // Mensagem de erro
    var $erro_login {
      value = {
        status: 401
        erro  : "Usuário ou senha inválidos"
      }
    }
  
    // Valida se existe e qual o status
    conditional {
      if ($usuario_encontrado == null) {
        return {
          value = $erro_login
        }
      }
    
      elseif ($usuario_encontrado.status != "ativo") {
        return {
          value = $erro_login
        }
      }
    }
  
    // Compara a senha
    security.check_password {
      text_password = $input.senha
      hash_password = $usuario_encontrado.senha_hash
    } as $senha_correta
  
    conditional {
      if (!$senha_correta) {
        return {
          value = $erro_login
        }
      }
    }
  
    // Senha correta, Gera JWT
    security.create_auth_token {
      table = "usuarios"
      extras = {
        usuario_id: $usuario_encontrado.id
        usuario   : $usuario_encontrado.usuario
        role      : $usuario_encontrado.role
      }
    
      expiration = 28800
      id = $usuario_encontrado.id
    } as $token
  
    var $sucesso_login {
      value = {
        status  : 200
        token   : $token
        mensagem: "Login realizado com sucesso"
      }
    }
  }

  response = $sucesso_login
  guid = "Z6lI-GZNc1QxP6Ec3n0dnbYwQhY"
}