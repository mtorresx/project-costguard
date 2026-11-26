// Painel do projeto: projeto, recursos
// e equipes numa única leitura. O custo por equipe continua em
// projetos/{id}/custos-equipe (janela informada pelo frontend).
query "projetos/{id}/painel" verb=GET {
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

    function.run "costguard/recursos_projeto" {
      input = {id: $input.id}
    } as $recursos

    function.run "costguard/equipes_projeto" {
      input = {id: $input.id}
    } as $equipes

    var $resposta {
      value = {
        projeto : {
          id    : $projeto.id
          nome  : $projeto.nome
          codigo: $projeto.codigo
          budget: $projeto.budget
          status: $projeto.status
        }
        recursos: $recursos
        equipes : $equipes
      }
    }
  }

  response = $resposta
  guid = "dnu-8nag9jz9m9dY198i-trBmks"
}
