// Lógica compartilhada: usada pelo
// endpoint listar_recursos_projeto_GET e pelos painéis agregados.
function "costguard/recursos_projeto" {
  input {
    int id
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

    // Metadados de inventário. equipe_id=null → "Sem responsável".
    // custo_mensal: USD por recurso (campo opcional, sem coleta automática); devolvido
    // como está na tabela — null quando não informado, nunca 0 no lugar de null.
    // Informativo: o total do projeto continua vindo de custos_equipe.
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
        ativo            : $$.ativo,
        descoberto_em    : $$.criado_em,
        custo_mensal     : $$.custo_mensal
      }
    }
  }

  response = $resposta
}
