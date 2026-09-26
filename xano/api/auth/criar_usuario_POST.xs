query criar_usuario verb=POST {
  api_group = "auth"
  auth = "usuarios"

  input {
    // Dados do novo usuário
    text nome filters=trim
  
    text usuario filters=trim|lower
    email email filters=trim|lower
    text senha filters=trim
    text role?=leitura
    text status?=ativo
  }

  stack {
    // Verifica se o usuário autenticado é admin
    db.get usuarios {
      field_name = "id"
      field_value = $auth.id
    } as $usuario_logado
  
    precondition ($usuario_logado != null) {
      error_type = "unauthorized"
      error = "Token inválido ou expirado"
    }
  
    precondition ($usuario_logado.role == "admin") {
      error_type = "accessdenied"
      error = "Acesso negado"
    }
  
    // Valida: usuario já existe?
    db.get usuarios {
      field_name = "usuario"
      field_value = $input.usuario
    } as $usuario_existe
  
    conditional {
      if ($usuario_existe != null) {
        return {
          value = {status: 400, erro: "Usuário já cadastrado"}
        }
      }
    }
  
    // Valida: email já existe?
    db.get usuarios {
      field_name = "email"
      field_value = $input.email
    } as $email_existe
  
    conditional {
      if ($email_existe != null) {
        return {
          value = {status: 400, erro: "Email já cadastrado"}
        }
      }
    }
  
    // Cria o novo usuário
    db.add usuarios {
      data = {
        nome      : $input.nome
        usuario   : $input.usuario
        email     : $input.email
        senha_hash: $input.senha
        role      : $input.role
        status    : $input.status
      }
    } as $novo_usuario
  
    // Se criou com sucesso, retorna os dados
    conditional {
      if ($novo_usuario != null) {
        return {
          value = {
            status  : 201
            mensagem: "Usuário criado com sucesso"
            usuario : {
              id: $novo_usuario.id
              nome: $novo_usuario.nome
              usuario: $novo_usuario.usuario
              email: $novo_usuario.email
              role: $novo_usuario.role
              status: $novo_usuario.status
              created_at: $novo_usuario.created_at
            }
          }
        }
      }
    
      else {
        return {
          value = {status: 500, erro: "Erro ao criar usuário"}
        }
      }
    }
  }

  response = {}
  guid = "Ro-J9ZK0Be-t6DlkDcQyMWiwQc8"
}