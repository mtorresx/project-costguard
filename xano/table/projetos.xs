table projetos {
  auth = false

  schema {
    int id
    text nome filters=trim
    text codigo filters=trim|upper
    decimal budget
    enum status?=ativo {
      values = ["ativo", "inativo"]
    }
  
    timestamp criado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "criado_em", op: "desc"}]}
    {type: "btree|unique", field: [{name: "codigo", op: "asc"}]}
  ]

  guid = "C4ikDhXF1OmzYjxDTTHyKDyzvic"
}