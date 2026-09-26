query desativar_projeto verb=POST {
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
  
    db.edit projetos {
      field_name = "id"
      field_value = $input.id
      data = {status: "inativo"}
    } as $projeto_desativado
  
    var $resposta {
      value = {
        id    : $projeto_desativado.id
        nome  : $projeto_desativado.nome
        codigo: $projeto_desativado.codigo
        budget: $projeto_desativado.budget
        status: $projeto_desativado.status
      }
    }
  }

  response = $resposta
  guid = "2Wmyar0EPch-E2SVhmqa7_5ljhg"
}