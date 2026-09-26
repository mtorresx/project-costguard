table recuperacao_senha {
  auth = false

  schema {
    int id
    int usuarios_id {
      table = "usuarios"
    }
  
    text token_hash filters=trim {
      sensitive = true
      visibility = "internal"
    }
  
    timestamp expira_em
    bool usado
    timestamp created_at?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "created_at", op: "desc"}]}
    {type: "btree", field: [{name: "token_hash", op: "asc"}]}
  ]

  guid = "VE84r34hVXVq6ULK1PK__nVYK4M"
}