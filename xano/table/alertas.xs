table alertas {
  auth = false

  schema {
    int id
    enum tipo {
      values = ["orcamento", "nao_classificado", "importacao"]
    }
    // atencao (70%), critico (90%, "Aviso"), estourado (100%, "Orçamento excedido"), erro (importação).
    enum nivel {
      values = ["atencao", "critico", "estourado", "erro"]
    }
    text mensagem
    text detalhe?
    // Identificador determinístico da condição. Não é único:
    // episódios encerrados mantêm a chave.
    text chave
    int projeto_id? {
      table = "projetos"
    }
    int provedor_id? {
      table = "provedores"
    }
    // true enquanto a condição que gerou o alerta persiste (episódio ativo).
    bool condicao_ativa?=true
    bool resolvido?=false
    enum resolucao? {
      values = ["manual", "automatica"]
    }
    timestamp resolvido_em?
    int resolvido_por? {
      table = "usuarios"
    }
    timestamp criado_em?=now
    timestamp atualizado_em?=now
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "criado_em", op: "desc"}]}
    {type: "btree", field: [{name: "chave", op: "asc"}]}
    {type: "btree", field: [{name: "condicao_ativa", op: "asc"}]}
  ]
}
