query editar_usuario verb=PATCH {
  api_group = "auth"
  auth = "usuarios"

  input {
    int id
    text nome? filters=trim
    text role?
    text status?
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
  
    // Busca o usuário que vai ser editado
    db.get usuarios {
      field_name = "id"
      field_value = $input.id
    } as $usuario_alvo
  
    conditional {
      if ($usuario_alvo == null) {
        return {
          value = {status: 404, erro: "Usuário não encontrado"}
        }
      }
    }
  
    // Atualiza os campos que vieram preenchidos
    db.edit usuarios {
      field_name = "id"
      field_value = $input.id
      data = {
        nome  : ($input.nome != null) ? $input.nome : $usuario_alvo.nome
        role  : ($input.role != null) ? $input.role : $usuario_alvo.role
        status: ($input.status != null) ? $input.status : $usuario_alvo.status
      }
    } as $usuario_atualizado
  
    var $sucesso {
      value = {
        status  : 200
        mensagem: "Usuário atualizado com sucesso"
        usuario : {
          id: $usuario_atualizado.id
          nome: $usuario_atualizado.nome
          usuario: $usuario_atualizado.usuario
          role: $usuario_atualizado.role
          status: $usuario_atualizado.status
        }
      }
    }
  }

  response = $sucesso
  guid = "_nCUOXEj4dQiZM0lmX9rkv_N8XI"
}