table provedores {
  auth = false

  schema {
    int id
    text apelido filters=trim
    enum tipo?=aws {
      values = ["aws"]
    }
  
    text identificador_conta filters=trim
    text tipo_credencial filters=trim
    text credencial {
      sensitive = true
    }
  
    enum status?=inativo {
      values = ["ok", "com_erro", "inativo"]
    }
  
    timestamp criado_em?=now
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "status"}]}
  ]

  guid = "7EIkgae_wiRmAsN3Npxr7lBkB1U"
}