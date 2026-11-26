query "projetos/{id}" verb=PATCH {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "projetos"
    }
  
    text nome? filters=trim
    // Texto: no XanoScript um decimal opcional ausente chega como 0 e 0 == null,
    // então não seria possível gravar orçamento zero.
    text budget? filters=trim
    // E-mail do DevOps (opcional, só admin: este endpoint já exige admin).
    // Ausente ou "" = mantém o atual; valor = valida e substitui; só espaços =
    // erro (nunca apaga em silêncio); remover = SOMENTE com remover_email_devops=true.
    // Sem `filters=trim` de propósito: o servidor precisa ver os espaços para
    // distinguir "só espaços" de ausente (a normalização aparada fica na function).
    text email_devops?
    // Remoção explícita: a ÚNICA forma de apagar o e-mail (não depende de como o
    // Xano entrega texto vazio em entrada opcional). Ausente = false.
    bool remover_email_devops?=false
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

    precondition ($usuario_logado.status == "ativo" && $usuario_logado.role == "admin") {
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

    // budget: "" (ausente) mantém o atual; caso contrário converte e valida >= 0.
    // codigo é imutável (não editável).
    var $budget_enviado { value = (($input.budget ?? "")|strlen) > 0 }
    var $budget_novo { value = $projeto_alvo.budget }

    conditional {
      if ($budget_enviado) {
        // Representação decimal completa (sem expoente, letras ou espaços).
        // Sintaxe do filtro no XanoScript: padrão|regex_matches:valor.
        precondition ("/^-?[0-9]+([.][0-9]+)?$/"|regex_matches:$input.budget) {
          error_type = "inputerror"
          error = "Campo 'budget' deve ser numérico"
        }

        var.update $budget_novo { value = $input.budget|to_decimal }

        precondition ($budget_novo >= 0) {
          error_type = "inputerror"
          error = "Campo 'budget' deve ser maior ou igual a zero"
        }
      }
    }

    // email_devops: db.edit ignora valor nulo, então a remoção grava "" (texto
    // vazio, não nulo). Ausente/"" repete o valor atual. Só a flag explícita remove.
    var $email_devops_novo { value = ($projeto_alvo.email_devops ?? "") }
    var $email_enviado_bruto { value = ($input.email_devops ?? "") }
    var $email_enviado_aparado { value = ($email_enviado_bruto|trim) }

    conditional {
      if ($input.remover_email_devops == true) {
        precondition ($email_enviado_aparado == "") {
          error_type = "inputerror"
          error = "Informe o e-mail do DevOps ou peça a remoção, não os dois."
        }

        var.update $email_devops_novo { value = "" }
      }
      elseif ($email_enviado_bruto != "") {
        // E-mail enviado só com espaços: erro claro, nunca remoção silenciosa.
        precondition ($email_enviado_aparado != "") {
          error_type = "inputerror"
          error = "O e-mail do DevOps está em branco. Informe um e-mail válido; para remover, envie remover_email_devops=true."
        }

        function.run "costguard/normalizar_email_devops" {
          input = {email: $email_enviado_bruto}
        } as $email_check

        precondition ($email_check.valido == true) {
          error_type = "inputerror"
          error = "Informe um e-mail válido para o DevOps."
        }

        var.update $email_devops_novo { value = $email_check.email }
      }
    }

    db.edit projetos {
      field_name = "id"
      field_value = $input.id
      data = {
        nome        : ($input.nome != null) ? $input.nome : $projeto_alvo.nome
        budget      : $budget_novo
        email_devops: $email_devops_novo
      }
    } as $projeto_atualizado

    // Orçamento alterado muda a faixa do alerta: reavalia.
    // Falha aqui não desfaz a edição.
    conditional {
      if ($budget_enviado && $budget_novo != $projeto_alvo.budget) {
        try_catch {
          try {
            function.run "costguard/avaliar_alertas" {
              input = {simular: false}
            } as $alertas_avaliados
          }
          catch {
            var $alertas_avaliados { value = null }
          }
        }
      }
    }

    // Resposta de endpoint de admin: devolve o e-mail do DevOps (nulo se vazio).
    var $resposta {
      value = {
        id              : $projeto_atualizado.id
        nome            : $projeto_atualizado.nome
        codigo          : $projeto_atualizado.codigo
        budget          : $projeto_atualizado.budget
        status          : $projeto_atualizado.status
        tem_email_devops: (($projeto_atualizado.email_devops ?? "") != "")
        email_devops    : (($projeto_atualizado.email_devops ?? "") == "") ? null : $projeto_atualizado.email_devops
      }
    }
  }

  response = $resposta
  guid = "51QA9-dOmAo9MWrR5fUPeHiZ31I"
}
