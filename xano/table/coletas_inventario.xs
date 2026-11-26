table coletas_inventario {
  auth = false

  schema {
    int id
    // Provedor de origem (FK).
    int provedor_id {
      table = "provedores"
    }
    enum status?=sucesso {
      values = ["sucesso", "erro"]
    }
    int recursos_encontrados?=0
    int projetos_desconhecidos?=0
    // Sanitizada; vazia em sucesso. Nunca contém segredo/material de assinatura.
    text mensagem?
    timestamp executado_em?=now
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "provedor_id", op: "asc"}, {name: "executado_em", op: "desc"}]}
  ]
}
