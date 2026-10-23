table provedores {
  auth = false

  schema {
    int id
    text apelido filters=trim
    enum tipo?=aws {
      values = ["aws"]
    }
    text identificador_conta filters=trim
    enum tipo_credencial?=aws_access_key {
      values = ["aws_access_key"]
    }
    // Parte pública da credencial AWS (não é segredo). Mascarada em logs.
    text aws_access_key_id? filters=trim {
      sensitive = true
    }
    // Segredo protegido via JWE (A256KW + A256CBC-HS512). Nunca retornado.
    text aws_secret_cifrado? {
      sensitive = true
      visibility = "private"
    }
    // Reservado (ver design D4). Não usado no caminho JWE, que embute o IV.
    text aws_secret_iv? {
      sensitive = true
      visibility = "private"
    }
    enum status?=pendente {
      values = ["pendente", "ok", "erro", "inativo"]
    }
    // AWS Tag Key da cost allocation tag usada no GroupBy do Cost Explorer
    // (ex.: "Projeto"). Não é segredo. Opcional: sem ela a classificação
    // de custos por projeto não pode ser executada.
    text tag_alocacao_projeto? filters=trim
    // AWS Tag Key usada para identificar a equipe dona de um recurso no
    // inventário. Default/recomendado: "EQP". Não é segredo. Provedores novos
    // nascem com "EQP"; a sincronização também aplica fallback "EQP" para
    // registros legados null/blank (ver endpoint de sincronização).
    text tag_alocacao_equipe?=EQP filters=trim
    // Característica opcional: quando true, as chamadas ao Cost Explorer deste
    // provedor usam o AWS Mock Simulator ({MOCK_BASE_URL}/aws/{conta}/ce/) em vez
    // do endpoint AWS real. Default false preserva o fluxo AWS real. Não é segredo.
    bool usar_mock?=false
    // Proteção best-effort contra duplo disparo da sincronização de recursos.
    // NÃO é um lock atômico/distribuído (ver design): apenas evita execução
    // concorrente acidental na operação normal (endpoint admin-only).
    bool sincronizacao_recursos_em_andamento?=false {
      visibility = "private"
    }
    timestamp sincronizacao_recursos_inicio? {
      visibility = "private"
    }
    text sincronizacao_recursos_id? {
      visibility = "private"
    }
    timestamp criado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "criado_em", op: "desc"}]}
  ]
  guid = "CLZtq3581sWZwW8L3tEPJDETmz4"
}
