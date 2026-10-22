table equipes {
  auth = false

  schema {
    int id
    text nome filters=trim
    // Tag Value da tag de equipe (EQP). Normalizado trim+upper.
    text codigo filters=trim|upper
    // Projeto dono da equipe (FK). Unicidade lógica: (projeto_id, codigo).
    int projeto_id {
      table = "projetos"
    }
    // true quando a equipe foi criada automaticamente a partir do inventário.
    bool auto_gerada?=false
    timestamp criado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree|unique", field: [{name: "projeto_id", op: "asc"}, {name: "codigo", op: "asc"}]}
    {type: "btree", field: [{name: "projeto_id", op: "asc"}]}
  ]
  guid = "USe0_CNZ4zQl6rwV8IlRpUdonhU"
}
