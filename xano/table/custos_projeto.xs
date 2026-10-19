table custos_projeto {
  auth = false

  schema {
    int id
    // Provedor de origem (FK). Todo custo é atribuível a um provedor.
    int provedor_id {
      table = "provedores"
    }
    // Projeto ao qual o custo foi atribuído pela tag de alocação (FK).
    // Tag Key = finalidade (ex.: PRJ); Tag Value = projetos.codigo.
    int projeto_id {
      table = "projetos"
    }
    // Dia do custo (granularidade DAILY) — ResultsByTime[].TimePeriod.Start.
    date data
    // Dimensão SERVICE do Cost Explorer — Groups[].Keys[1].
    text servico filters=trim
    // Métrica coletada no MVP (espelha custos).
    enum metrica?=unblended {
      values = ["unblended"]
    }
    // Montante — Groups[].Metrics.UnblendedCost.Amount.
    decimal valor
    // Unidade/moeda — Groups[].Metrics.UnblendedCost.Unit (USD no MVP).
    text moeda?=USD
    // ResultsByTime[].Estimated.
    bool estimado?=false
    timestamp coletado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree|unique", field: [{name: "provedor_id", op: "asc"}, {name: "projeto_id", op: "asc"}, {name: "data", op: "asc"}, {name: "servico", op: "asc"}, {name: "metrica", op: "asc"}]}
    {type: "btree", field: [{name: "projeto_id", op: "asc"}, {name: "data", op: "desc"}]}
  ]
  guid = "FKRe9Tx6zFwTSmrnz4lLS2N6RAw"
}
