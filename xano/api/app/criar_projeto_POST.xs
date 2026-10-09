query projetos verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    text nome filters=trim
    text codigo filters=trim|upper
    decimal budget
  }

  stack {
    // Autorização: operação de escrita exige admin (validada no backend).
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

    // Campos obrigatórios.
    precondition ($input.nome != null && $input.nome != "") {
      error_type = "inputerror"
      error = "Campo 'nome' é obrigatório"
    }

    precondition ($input.codigo != null && $input.codigo != "") {
      error_type = "inputerror"
      error = "Campo 'codigo' é obrigatório"
    }

    // Budget decimal >= 0.
    precondition ($input.budget != null && $input.budget >= 0) {
      error_type = "inputerror"
      error = "Campo 'budget' deve ser maior ou igual a zero"
    }

    // Código único (o índice único é a garantia final).
    db.get projetos {
      field_name = "codigo"
      field_value = $input.codigo
    } as $projeto_existe

    precondition ($projeto_existe == null) {
      error_type = "inputerror"
      error = "Código de projeto já existe"
    }

    db.add projetos {
      data = {
        nome  : $input.nome
        codigo: $input.codigo
        budget: $input.budget
        status: "ativo"
      }
    } as $novo_projeto

    var $resposta {
      value = {
        id    : $novo_projeto.id
        nome  : $novo_projeto.nome
        codigo: $novo_projeto.codigo
        budget: $novo_projeto.budget
        status: $novo_projeto.status
      }
    }
  }

  response = $resposta
  guid = "lLkOuUSti56d8aa2yvyy-GUvtBM"
}
