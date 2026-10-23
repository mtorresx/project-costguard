table custos_equipe {
  auth = false

  schema {
    int id
    // Provedor de origem (FK).
    int provedor_id {
      table = "provedores"
    }
    // Projeto (FK). Sempre um projeto ativo no momento da gravação.
    int projeto_id {
      table = "projetos"
    }
    // Equipe (FK, nullable). null = "Sem responsável" (nunca uma equipe fictícia).
    int equipe_id? {
      table = "equipes"
    }
    // Código normalizado (trim+upper) da tag de equipe. "" = "Sem responsável".
    // Opcional e NÃO nulo: participa da chave única sem depender de NULL.
    text codigo_equipe? filters=trim|upper
    // Dia do custo (DAILY) — ResultsByTime[].TimePeriod.Start.
    date data
    // Métrica coletada no MVP (espelha custos/custos_projeto).
    enum metrica?=unblended {
      values = ["unblended"]
    }
    // Soma dos grupos agregados após normalização.
    decimal valor
    // Unidade retornada pela AWS (Metrics.UnblendedCost.Unit). Sem conversão.
    text moeda?=USD
    // ResultsByTime[].Estimated.
    bool estimado?=false
    // Identificador da execução que gravou/atualizou a linha por último.
    text sync_id? {
      visibility = "private"
    }
    timestamp coletado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree|unique", field: [{name: "provedor_id", op: "asc"}, {name: "projeto_id", op: "asc"}, {name: "codigo_equipe", op: "asc"}, {name: "data", op: "asc"}, {name: "metrica", op: "asc"}]}
    {type: "btree", field: [{name: "projeto_id", op: "asc"}, {name: "data", op: "desc"}]}
    {type: "btree", field: [{name: "provedor_id", op: "asc"}, {name: "data", op: "asc"}]}
  ]
}
