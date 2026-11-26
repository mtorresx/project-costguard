query projetos verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
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

    // Qualquer usuário autenticado pode listar (auth = "usuarios" garante 401 sem token).
    db.query projetos {
      sort = {criado_em: "desc"}
      return = {type: "list"}
    } as $lista_projetos

    // Resposta montada campo a campo: nunca devolve o registro cru. O e-mail do
    // DevOps só vai para admin ativo; para leitura o campo é OMITIDO (nem nulo).
    // `tem_email_devops` (booleano) vai para TODOS os perfis: habilita o botão
    // "Notificar DevOps" sem revelar o endereço. devops_ultimo_envio_em e
    // devops_ultimo_envio_por nunca são devolvidos.
    var $eh_admin { value = ($usuario_sessao.role == "admin") }
    var $lista_saida { value = [] }

    foreach ($lista_projetos) {
      each as $p {
        var $item {
          value = {
            id              : $p.id
            nome            : $p.nome
            codigo          : $p.codigo
            budget          : $p.budget
            status          : $p.status
            tem_email_devops: (($p.email_devops ?? "") != "")
          }
        }

        conditional {
          if ($eh_admin) {
            var.update $item {
              value = {
                id              : $p.id
                nome            : $p.nome
                codigo          : $p.codigo
                budget          : $p.budget
                status          : $p.status
                tem_email_devops: (($p.email_devops ?? "") != "")
                email_devops    : (($p.email_devops ?? "") == "") ? null : $p.email_devops
              }
            }
          }
        }

        var.update $lista_saida { value = $lista_saida|push:$item }
      }
    }
  }

  response = $lista_saida
  guid = "zIdTmocAQrjIb7f_KXOsjvk0bps"
}
