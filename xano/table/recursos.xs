table recursos {
  auth = false

  schema {
    int id
    // Provedor de origem (FK). Parte da unicidade (provedor_id, arn).
    int provedor_id {
      table = "provedores"
    }
    // ARN completo do recurso — preservado integralmente (nunca truncar).
    text arn
    // Região AWS onde o recurso foi encontrado (GetResources é regional).
    text regiao filters=trim
    // Serviço AWS derivado do ARN (ex.: ec2, rds, s3).
    text servico filters=trim
    // Projeto resolvido (FK, nullable). null = projeto desconhecido.
    int projeto_id? {
      table = "projetos"
    }
    // Equipe resolvida (FK, nullable). null = "Sem responsável".
    int equipe_id? {
      table = "equipes"
    }
    // Valor cru da tag de projeto (auditoria/debug; rastreia projeto desconhecido).
    text codigo_projeto_tag?
    // Valor cru da tag de equipe (auditoria/debug; null/"" quando ausente).
    text codigo_equipe_tag?
    // Identificador da execução de sincronização que viu o recurso por último.
    text sync_id?
    timestamp ultima_vista_em? {
      visibility = "private"
    }
    // Reconciliação: false quando o recurso não apareceu no último sync completo.
    bool ativo?=true
    timestamp criado_em?=now {
      visibility = "private"
    }
    timestamp atualizado_em?=now {
      visibility = "private"
    }
    // Custo mensal do recurso, em USD. Campo OPCIONAL de custo por recurso;
    // preenchido pelo painel do Xano ou por integração futura. Sem
    // coleta automática. ANULÁVEL e SEM padrão:
    // null = recurso sem custo informado (nunca 0). A sincronização de inventário
    // não lê nem grava esta coluna (db.edit/db.add listam só os campos dela).
    // `db.edit` ignora null (e decimal 0 == null), então limpar o valor por uma
    // API exigiria tratamento próprio; hoje a limpeza é feita pelo painel.
    // Não entra em nenhuma soma: o total do projeto vem de custos_equipe.
    decimal custo_mensal?
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree|unique", field: [{name: "provedor_id", op: "asc"}, {name: "arn", op: "asc"}]}
    {type: "btree", field: [{name: "projeto_id", op: "asc"}]}
    {type: "btree", field: [{name: "equipe_id", op: "asc"}]}
  ]
  guid = "bcONi1wyFos3CfA2wG2lFZnR-DE"
}
