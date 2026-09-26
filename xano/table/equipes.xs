table equipes {
  auth = false

  schema {
    int id
    text nome filters=trim
    text codigo filters=trim|upper
    int projetos_id {
      table = "projetos"
    }
  
    bool auto_gerada?
    timestamp criado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "projetos_id", op: "asc"}]}
    {
      type : "btree|unique"
      field: [
        {name: "projetos_id", op: "asc"}
        {name: "codigo", op: "asc"}
      ]
    }
  ]

  guid = "V-VoaWJvGMz7H8hexy-nog1XGV8"
}