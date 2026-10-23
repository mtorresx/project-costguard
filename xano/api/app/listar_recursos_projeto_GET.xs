query "projetos/{id}/recursos" verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "projetos"
    }
  }

  stack {
    // Qualquer usuário autenticado pode ler (auth garante 401 sem token).
    db.get projetos {
      field_name = "id"
      field_value = $input.id
    } as $projeto

    precondition ($projeto != null) {
      error_type = "notfound"
      error = "Projeto não encontrado"
    }

    db.query recursos {
      where = $db.recursos.projeto_id == $input.id
      sort = {atualizado_em: "desc"}
      return = {type: "list"}
    } as $lista

    // Metadados de inventário (sem custos). equipe_id=null → "Sem responsável".
    var $resposta {
      value = $lista|map:{
        id               : $$.id,
        provedor_id      : $$.provedor_id,
        arn              : $$.arn,
        regiao           : $$.regiao,
        servico          : $$.servico,
        projeto_id       : $$.projeto_id,
        equipe_id        : $$.equipe_id,
        codigo_projeto_tag: $$.codigo_projeto_tag,
        codigo_equipe_tag: $$.codigo_equipe_tag,
        sem_responsavel  : ($$.equipe_id == null),
        ativo            : $$.ativo
      }
    }
  }

  response = $resposta
  guid = "M-TZpHN9iUKqY-8ovjYJ9ZkcYKU"
}
