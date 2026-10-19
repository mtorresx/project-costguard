table coletas_classificacao {
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
    // Registros efetivamente gravados em custos_projeto.
    int registros_gravados?=0
    // Casos de borda, rastreáveis e não silenciosos:
    // custo cujo Value da tag de alocação está ausente/vazio.
    int nao_alocados?=0
    // Value (codigo candidato) sem projeto correspondente no CostGuard.
    int tags_sem_projeto?=0
    // Value que corresponde a projeto inativo.
    int projetos_inativos?=0
    // Sanitizada; vazia em sucesso. Nunca contém segredo/material de assinatura.
    text mensagem?
    timestamp executado_em?=now
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "provedor_id", op: "asc"}, {name: "executado_em", op: "desc"}]}
  ]
  guid = "KSKPPOJuadagv7xZSa6rvCMzRaw"
}
