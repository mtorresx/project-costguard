table projetos {
  auth = false

  schema {
    int id
    text nome filters=trim
    text codigo filters=trim|upper
    decimal budget
    enum status?=ativo {
      values = ["ativo", "inativo"]
    }
    // E-mail de alerta ao DevOps (opcional, aditivo). Validado e normalizado no
    // servidor (function costguard/normalizar_email_devops). Vazio ("") ou nulo =
    // sem destinatário: db.edit ignora null, então para remover grava-se "".
    // Só admin lê e grava: as leituras de projeto montam a resposta campo a campo.
    text email_devops? filters=trim|lower
    // Instante (ms desde a época) do último envio ACEITO pelo provedor de e-mail.
    // Base do limite de 1 envio a cada 5 minutos por projeto. Nulo/0 = nunca enviou.
    // Nunca é devolvido pelas leituras de projeto.
    int devops_ultimo_envio_em?
    // Id do usuário (usuarios.id) que fez o último envio ACEITO: registro de
    // "quem" ao lado do "quando" acima. Gravado junto com ele. Nulo/0 = nunca
    // enviou. Inteiro simples (sem FK) e nunca devolvido pelas leituras.
    int devops_ultimo_envio_por?
    // Idem, para o aviso "recursos sem equipe" (POST /projetos/{id}/notificar-
    // recursos-sem-equipe): limite PRÓPRIO de 1 envio a cada 5 minutos por projeto,
    // independente do de orçamento acima. Aditivo e anulável (nulo/0 = nunca
    // enviou), mesmo padrão das duas colunas anteriores; só o endpoint lê e grava,
    // e nenhuma leitura de projeto devolve estes campos. Tabela publicada ANTES do
    // endpoint.
    int devops_recursos_ultimo_envio_em?
    int devops_recursos_ultimo_envio_por?

    timestamp criado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "criado_em", op: "desc"}]}
    {type: "btree|unique", field: [{name: "codigo", op: "asc"}]}
  ]
  guid = "FKsUn2RpttLw4as7xWHWe3ys-GE"
}
