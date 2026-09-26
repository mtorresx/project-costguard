query criar_projeto verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    text nome filters=trim
    text codigo filters=trim|upper
    decimal budget
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
  
    // nome e codigo
    precondition ($input.nome != null && $input.nome != "") {
      error_type = "badrequest"
      error = "Campo 'nome' é obrigatório"
    }
  
    precondition ($input.codigo != null && $input.codigo != "") {
      error_type = "badrequest"
      error = "Campo 'codigo' é obrigatório"
    }
  
    // budget obrigatório e nunca 0
    precondition ($input.budget != null && $input.budget > 0) {
      error_type = "badrequest"
      error = "Campo 'budget' deve ser maior que zero"
    }
  
    // codigo precisa ser único
    db.get projetos {
      field_name = "codigo"
      field_value = $input.codigo
    } as $projeto_existe
  
    precondition ($projeto_existe == null) {
      error_type = "badrequest"
      error = "Código de projeto já existe"
    }
  
    // Cria o projeto
    db.add projetos {
      data = {
        nome  : $input.nome
        codigo: $input.codigo
        budget: $input.budget
        status: "ativo"
      }
    } as $novo_projeto
  
    var $sucesso {
      value = {
        id    : $novo_projeto.id
        nome  : $novo_projeto.nome
        codigo: $novo_projeto.codigo
        budget: $novo_projeto.budget
        status: $novo_projeto.status
      }
    }
  }

  response = $sucesso
  guid = "PyuUr0s9mQR1dbgqdA2lmfd5GaU"
}