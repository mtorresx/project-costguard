table custos {
  auth = false

  schema {
    int id
    // Provedor de origem (FK). Todo custo é atribuível a um provedor.
    int provedor_id {
      table = "provedores"
    }
    // Dia do custo (granularidade DAILY) — ResultsByTime[].TimePeriod.Start.
    date data
    // Dimensão SERVICE do Cost Explorer — Groups[].Keys[0].
    text servico filters=trim
    // Métrica coletada no MVP.
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
    {type: "btree|unique", field: [{name: "provedor_id", op: "asc"}, {name: "data", op: "asc"}, {name: "servico", op: "asc"}, {name: "metrica", op: "asc"}]}
    {type: "btree", field: [{name: "provedor_id", op: "asc"}, {name: "data", op: "desc"}]}
  ]
  guid = "i7NzpV988EW9P7kST_qrh56iFyA"
}
