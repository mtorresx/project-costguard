query "projetos/{id}/equipes" verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "projetos"
    }
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
  guid = "lmC_mvQPmdBtK_gRI6xnpX502Og"
}
