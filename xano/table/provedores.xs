table provedores {
  auth = false

  schema {
    int id
    text apelido filters=trim
    enum tipo?=aws {
      values = ["aws"]
    }
    text identificador_conta filters=trim
    enum tipo_credencial?=aws_access_key {
      values = ["aws_access_key"]
    }
    // Parte pública da credencial AWS (não é segredo). Mascarada em logs.
    text aws_access_key_id? filters=trim {
      sensitive = true
    }
    // Segredo protegido via JWE (A256KW + A256CBC-HS512). Nunca retornado.
    text aws_secret_cifrado? {
      sensitive = true
      visibility = "private"
    }
    // Reservado (ver design D4). Não usado no caminho JWE, que embute o IV.
    text aws_secret_iv? {
      sensitive = true
      visibility = "private"
    }
    enum status?=pendente {
      values = ["pendente", "ok", "erro", "inativo"]
    }
    timestamp criado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "criado_em", op: "desc"}]}
  ]
  guid = "CLZtq3581sWZwW8L3tEPJDETmz4"
}
