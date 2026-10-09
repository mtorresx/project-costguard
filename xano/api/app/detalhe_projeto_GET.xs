query "projetos/{id}" verb=GET {
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
  }

  response = $projeto
  guid = "E43u2kQEUQLH7c2DFDhj3ySY2mU"
}
