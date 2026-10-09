query projetos verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
  }

  stack {
    // Qualquer usuário autenticado pode listar (auth = "usuarios" garante 401 sem token).
    db.query projetos {
      sort = {criado_em: "desc"}
      return = {type: "list"}
    } as $lista_projetos
  }

  response = $lista_projetos
  guid = "zIdTmocAQrjIb7f_KXOsjvk0bps"
}
