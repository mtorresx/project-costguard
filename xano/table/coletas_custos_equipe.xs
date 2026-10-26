table coletas_custos_equipe {
  auth = false

  schema {
    int id
    // Provedor de origem (FK).
    int provedor_id {
      table = "provedores"
    }
    // Identificador da execução (nunca exposto pela API).
    text sync_id? {
      visibility = "private"
    }
    // Intervalo consultado: início inclusivo, fim exclusivo (semântica AWS).
    date intervalo_inicio
    date intervalo_fim
    enum status?=sucesso {
      values = ["sucesso", "erro"]
    }
    // Linhas agregadas gravadas (upsert) em custos_equipe.
    int registros_gravados?=0
    // Linhas removidas pela reconciliação da janela desta execução.
    int registros_removidos?=0
    // Grupos AWS com valor de projeto vazio.
    int nao_alocados?=0
    // Grupos AWS cujo valor de projeto não corresponde a projeto do CostGuard.
    int tags_sem_projeto?=0
    // Grupos AWS de projeto inativo (não gravados).
    int projetos_inativos?=0
    // Linhas agregadas gravadas como "Sem responsável".
    int sem_responsavel?=0
    int equipes_criadas?=0
    // Aviso não bloqueante (ex.: nenhuma equipe encontrada na janela).
    text aviso?
    // Sanitizada; vazia em sucesso. Nunca contém segredo/material de assinatura.
    text mensagem?
    timestamp executado_em?=now
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "provedor_id", op: "asc"}, {name: "executado_em", op: "desc"}]}
  ]
}
