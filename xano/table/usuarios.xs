table usuarios {
  auth = true

  schema {
    int id
    text nome filters=trim
    text usuario filters=trim
    email email filters=trim|lower
    password senha_hash {
      sensitive = true
    }
  
    enum role?=leitura {
      values = ["admin", "leitura"]
    }
  
    enum status?=ativo {
      values = ["ativo", "inativo"]
    }
  
    timestamp created_at?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "created_at", op: "desc"}]}
    {type: "btree|unique", field: [{name: "usuario", op: "asc"}]}
    {type: "btree|unique", field: [{name: "email", op: "asc"}]}
  ]

  guid = "NPxwGZgofTJt2-WpwW-zJVoFN40"
}