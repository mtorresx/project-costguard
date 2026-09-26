query detalhe_projeto verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
    int id
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
  
    db.get projetos {
      field_name = "id"
      field_value = $input.id
    } as $projeto
  
    precondition ($projeto != null) {
      error_type = "notfound"
      error = "Projeto não encontrado"
    }
  
    var $resposta {
      value = {
        id    : $projeto.id
        nome  : $projeto.nome
        codigo: $projeto.codigo
        budget: $projeto.budget
        status: $projeto.status
      }
    }
  }

  response = $resposta
  guid = "yr7ZSp08dbZW-7osSQWQ8yOsGds"
}