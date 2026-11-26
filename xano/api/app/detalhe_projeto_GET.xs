query "projetos/{id}" verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "projetos"
    }
  }

  stack {
    // P2-10: usuário desativado (ou removido) perde também o acesso às leituras.
    db.get usuarios {
      field_name = "id"
      field_value = $auth.id
    } as $usuario_sessao

    precondition ($usuario_sessao != null && $usuario_sessao.status == "ativo") {
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

    // Resposta montada campo a campo: nunca devolve o registro cru. O e-mail do
    // DevOps só vai para admin ativo; para leitura o campo é OMITIDO (nem nulo).
    // `tem_email_devops` (booleano) vai para TODOS os perfis: habilita o botão
    // "Notificar DevOps" sem revelar o endereço. devops_ultimo_envio_em e
    // devops_ultimo_envio_por nunca são devolvidos.
    var $resposta {
      value = {
        id              : $projeto.id
        nome            : $projeto.nome
        codigo          : $projeto.codigo
        budget          : $projeto.budget
        status          : $projeto.status
        tem_email_devops: (($projeto.email_devops ?? "") != "")
      }
    }

    conditional {
      if ($usuario_sessao.role == "admin") {
        var.update $resposta {
          value = {
            id              : $projeto.id
            nome            : $projeto.nome
            codigo          : $projeto.codigo
            budget          : $projeto.budget
            status          : $projeto.status
            tem_email_devops: (($projeto.email_devops ?? "") != "")
            email_devops    : (($projeto.email_devops ?? "") == "") ? null : $projeto.email_devops
          }
        }
      }
    }
  }

  response = $resposta
  guid = "E43u2kQEUQLH7c2DFDhj3ySY2mU"
}
