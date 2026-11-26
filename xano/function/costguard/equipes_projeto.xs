// Lógica compartilhada: usada pelo
// endpoint listar_equipes_projeto_GET e pelos painéis agregados.
function "costguard/equipes_projeto" {
  input {
    int id
  }

  stack {
    db.get projetos {
      field_name = "id"
      field_value = $input.id
    } as $projeto

    precondition ($projeto != null) {
      error_type = "notfound"
      error = "Projeto não encontrado"
    }

    db.query equipes {
      where = $db.equipes.projeto_id == $input.id
      sort = {codigo: "asc"}
      return = {type: "list"}
    } as $lista

    var $resposta {
      value = $lista|map:{
        id         : $$.id,
        nome       : $$.nome,
        codigo     : $$.codigo,
        projeto_id : $$.projeto_id,
        auto_gerada: $$.auto_gerada
      }
    }
  }

  response = $resposta
}
