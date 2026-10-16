table coletas_custo {
  auth = false

  schema {
    int id
    // Provedor de origem (FK).
    int provedor_id {
      table = "provedores"
    }
    // Intervalo consultado: início inclusivo, fim exclusivo (semântica AWS).
    date intervalo_inicio
    date intervalo_fim
    enum status?=sucesso {
      values = ["sucesso", "erro"]
    }
    int dias_processados?=0
    int registros_gravados?=0
    // Sanitizada; vazia em sucesso. Nunca contém segredo/material de assinatura.
    text mensagem?
    timestamp executado_em?=now
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "provedor_id", op: "asc"}, {name: "executado_em", op: "desc"}]}
  ]
  guid = "SpoelVRdO41guJa_hEpzJewH8LE"
}
