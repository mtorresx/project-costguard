query deletar_usuario verb=DELETE {
  api_group = "auth"
  auth = "usuarios"

  input {
    int id
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
  
    precondition ($input.id != $auth.id) {
      error_type = "inputerror"
      error = "Você não pode desativar sua própria conta"
    }
  
    // Busca o usuário
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
  
    // Soft delete: marca status = inativo
    db.edit usuarios {
      field_name = "id"
      field_value = $input.id
      data = {status: "inativo"}
    } as $usuario_desativado
  
    var $sucesso {
      value = {
        status  : 200
        mensagem: "Usuário desativado com sucesso"
      }
    }
  }

  response = $sucesso
  guid = "TrlkxQvvIx4VtHVAO7eZTT7KCRw"
}