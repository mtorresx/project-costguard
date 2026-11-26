query projetos verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    text nome filters=trim
    text codigo filters=trim|upper
    // Texto: no XanoScript um decimal 0 é igual a null, o que impedia criar
    // projeto com orçamento zero.
    text budget? filters=trim
    // E-mail do DevOps (opcional). Endpoint só de admin; validado no servidor.
    text email_devops? filters=trim
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

    precondition ($usuario_logado.status == "ativo" && $usuario_logado.role == "admin") {
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
    precondition ((($input.budget ?? "")|strlen) > 0) {
      error_type = "inputerror"
      error = "Campo 'budget' é obrigatório"
    }

    precondition ("/^-?[0-9]+([.][0-9]+)?$/"|regex_matches:$input.budget) {
      error_type = "inputerror"
      error = "Campo 'budget' deve ser numérico"
    }

    var $budget_valor { value = $input.budget|to_decimal }

    precondition ($budget_valor >= 0) {
      error_type = "inputerror"
      error = "Campo 'budget' deve ser maior ou igual a zero"
    }

    // E-mail do DevOps: vazio/ausente = sem destinatário (gravado como "").
    function.run "costguard/normalizar_email_devops" {
      input = {email: $input.email_devops}
    } as $email_check

    precondition ($email_check.valido == true) {
      error_type = "inputerror"
      error = "Informe um e-mail válido para o DevOps."
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
        budget: $budget_valor
        status: "ativo"
        email_devops: $email_check.email
      }
    } as $novo_projeto

    // Resposta de endpoint de admin: devolve o e-mail do DevOps (nulo se vazio).
    var $resposta {
      value = {
        id              : $novo_projeto.id
        nome            : $novo_projeto.nome
        codigo          : $novo_projeto.codigo
        budget          : $novo_projeto.budget
        status          : $novo_projeto.status
        tem_email_devops: (($novo_projeto.email_devops ?? "") != "")
        email_devops    : (($novo_projeto.email_devops ?? "") == "") ? null : $novo_projeto.email_devops
      }
    }
  }

  response = $resposta
  guid = "lLkOuUSti56d8aa2yvyy-GUvtBM"
}
