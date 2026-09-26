query editar_projeto verb=PATCH {
  api_group = "app"
  auth = "usuarios"

  input {
    int id
    text nome? filters=trim
    decimal budget?
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
  
    precondition ($usuario_logado.role == "admin") {
      error_type = "accessdenied"
      error = "Acesso negado"
    }
  
    db.get projetos {
      field_name = "id"
      field_value = $input.id
    } as $projeto_alvo
  
    precondition ($projeto_alvo != null) {
      error_type = "notfound"
      error = "Projeto não encontrado"
    }
  
    conditional {
      if ($input.budget != null) {
        precondition ($input.budget > 0) {
          error_type = "badrequest"
          error = "Campo 'budget' deve ser maior que zero"
        }
      }
    }
  
    db.edit projetos {
      field_name = "id"
      field_value = $input.id
      data = {
        nome  : ($input.nome != null) ? $input.nome : $projeto_alvo.nome
        budget: ($input.budget != null) ? $input.budget : $projeto_alvo.budget
      }
    } as $projeto_atualizado
  
    var $resposta {
      value = {
        id    : $projeto_atualizado.id
        nome  : $projeto_atualizado.nome
        codigo: $projeto_atualizado.codigo
        budget: $projeto_atualizado.budget
        status: $projeto_atualizado.status
      }
    }
  }

  response = $resposta
  guid = "AZrGYBG4n8vpVdWqGwPwKHuEPrM"
}