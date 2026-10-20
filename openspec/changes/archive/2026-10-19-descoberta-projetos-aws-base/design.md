## Context

Ver `proposal.md` — Why. Estado atual consolidado reaproveitado por esta change:

- `provedores`: entidade com `tipo = aws`, `status`, `identificador_conta`, `aws_access_key_id`,
  `aws_secret_cifrado` (JWE), `tag_alocacao_projeto` (Tag Key, recomendada `PRJ`) e `usar_mock`.
- `integracao-mock`: routing real/Mock por `usar_mock`, `MOCK_BASE_URL` só no backend (barra
  final normalizada), SigV4 coerente ao destino, `GetTags` já usado no teste de conexão Mock.
- `classificacao-custos`: convenção oficial (Tag Key = finalidade; Tag Value = `projetos.codigo`),
  parser do grupo `"<Key>$<Value>"`, normalização e tratamento de valor vazio, paginação.
- `projetos`: entidade com `codigo` único (`trim|upper`), criação admin-only exigindo `nome`,
  `codigo` e `budget >= 0`.

A descoberta é uma leitura de `GetTags` (não `GetCostAndUsage`): `GetTags` retorna valores de uma
Tag Key diretamente (sem o prefixo `"<Key>$"` do agrupamento), o que simplifica o parser — o valor
já é o `codigo` candidato. O endpoint de teste de conexão Mock já exercita `GetTags` com
`TagKey = PRJ`, então o padrão de request/resposta é conhecido e validado.

## Goals / Non-Goals

**Goals:**

- Descobrir os valores da Tag Key de um provedor (real ou Mock) sem gravar nada.
- Permitir importação explícita e seletiva dos projetos inexistentes, sem duplicar.
- Reaproveitar routing real/Mock, SigV4 e `GetTags` existentes (uma só implementação).
- Manter a classificação atual intacta (continua não criando projetos sozinha).

**Non-Goals (nível de design):**

- Não há frontend nesta change (backend-only).
- Não alterar `classificacao-custos`, `custos`, `integracao-mock` nem o Mock.
- Não ativar/desativar cost allocation tags.
- Não definir orçamento na importação (budget = 0; ajuste posterior via CRUD).

## Decisions

### D1 — Descoberta e importação SEPARADAS (preferência do usuário)

Dois endpoints distintos, nunca criação silenciosa:

- `POST provedores/{id}/descobrir-projetos` — **read-only**. Consulta `GetTags`, normaliza/filtra,
  compara com `projetos.codigo` e retorna a lista de descobertos com `existente`/`projeto_id`.
- `POST provedores/{id}/importar-projetos` — **grava**. Recebe uma lista de códigos selecionados
  e cria apenas os inexistentes.

Alternativa descartada (B: descobrir e criar no mesmo endpoint): criaria projetos sem o admin
revisar a lista, contrariando a preferência e o princípio de "nada silencioso". A separação dá
ao admin um passo de revisão/seleção entre descobrir e criar.

Rationale conceitual explícito: `provedores.tag_alocacao_projeto` é a **Tag Key** (finalidade),
não um projeto. Os projetos são os **valores** dessa Key:
```
Provider
  └── Tag Key: PRJ            (provedores.tag_alocacao_projeto)
        ├── PAGAMENTOS        (Tag Value → projetos.codigo)
        ├── MARKETING
        └── INFRAESTRUTURA
```

### D2 — `GetTags` como fonte da descoberta (contrato distinto do GroupBy)

Usar `AWSInsightsIndexService.GetTags` com `TagKey = provedores.tag_alocacao_projeto` e um
`TimePeriod` válido (padrão: últimos 30 dias, como nas demais operações). O contrato de `GetTags`
retorna os valores da Key diretamente em `Tags[]` (cada item é o próprio Value, ex.: `"PAGAMENTOS"`),
**sem** o prefixo `"<Key>$"` que aparece apenas no `GroupBy TAG` de `GetCostAndUsage`. Portanto o
processamento da descoberta é: para cada valor em `Tags[]`, `trim|upper`; descartar vazio;
deduplicar. **MUST NOT** aplicar o parser de `"PRJ$..."`/`substr` sobre a resposta de `GetTags`.
Tratar `NextPageToken` se presente, reassinando cada página.

Alternativa considerada: derivar os valores de um `GetCostAndUsage` agrupado por tag. Descartada
— `GetTags` é mais direto, mais barato e já validado no teste de conexão Mock.

### D3 — Routing real/Mock e SigV4 reaproveitados (sem duplicar)

Reutilizar exatamente o mecanismo de `integracao-mock`/`classificacao-custos`: resolver
`$eh_mock`, `$sig_host`, `$canonical_uri`, `$sig_endpoint` a partir de `usar_mock` (com
normalização de `MOCK_BASE_URL` e validação de presença no ramo Mock), e assinar `GetTags` com a
única implementação SigV4 existente, coerente ao destino. O segredo é decifrado só em memória.
Não criar nova implementação de assinatura.

### D4 — Importação cria projeto mínimo, sem duplicar nem reativar

Para cada `codigo` da lista (normalizado `trim|upper`, ignorando vazio): consultar
`projetos.codigo`; se existe → ignorar (não altera, não reativa, conta como "ignorado"); se não
existe → `db.add` com `nome = codigo`, `codigo`, `budget = 0`, `status = ativo`. A unicidade de
`codigo` (índice único existente em `projetos`) é a salvaguarda final contra duplicatas, mesmo em
corrida. Não inventar orçamento (budget = 0). O resultado distingue `criados` de `ignorados`.

Observação de robustez: a importação valida os códigos recebidos independentemente de terem
vindo da descoberta (o admin pode montar a lista). A verificação de existência é feita no momento
da importação (não confia num `existente` possivelmente obsoleto da descoberta).

### D5 — Sem novas tabelas; sem estado persistido de descoberta

A descoberta é efêmera (read-only, resultado na resposta). A importação usa a tabela `projetos`
existente. Nenhuma tabela nova é necessária no MVP. (Registro de histórico de descoberta/
importação pode ser avaliado numa change futura, se desejado.)

## Risks / Trade-offs

- **`GetTags` no Mock vs AWS real** → o Mock já suporta `GetTags` (validado no teste de conexão);
  na AWS real, `GetTags` exige `ce:GetTags`. Mitigação: documentar a permissão IAM; o routing é o
  mesmo, só o destino muda.
- **Valores de tag que não seguem a convenção de `codigo`** (ex.: espaços, caixa) → mitigado por
  `trim|upper`; valores vazios ignorados. Se um valor normalizado colidir com `codigo` existente,
  é tratado como "já existe" (correto).
- **`existente` da descoberta pode ficar obsoleto** entre descobrir e importar → mitigado: a
  importação reavalia a existência no momento de gravar; o índice único de `codigo` é a barreira
  final.
- **Importar código não presente na AWS** → o endpoint de importação aceita a lista do admin sem
  reconsultar a AWS (D4), para manter a operação simples e previsível. Trade-off aceito: o admin é
  responsável pela lista; a descoberta é a fonte recomendada para montá-la.
- **Paginação de `GetTags`** → tratada como a de `GetCostAndUsage`; falha de página vira erro
  sanitizado, sem lista parcial.

## Permissões / Configuração

- `ce:GetTags` (AWS real) — read-only. `ce:GetCostAndUsage` já usado pela classificação permanece.
- `MOCK_BASE_URL` (já existente) — só backend, usada no ramo Mock.
- Nenhuma nova env var, nenhuma nova tabela.

## Decisões confirmadas pelo usuário

- **Importação NÃO reconsulta a AWS** (D4): `importar-projetos` trabalha somente com a lista
  explícita enviada pelo admin; não chama `GetTags`. A existência é verificada contra
  `projetos.codigo` no momento da gravação.
- **Sem histórico/auditoria nesta change** (D5): nenhuma tabela de descoberta/importação;
  não persistir execução, usuário, timestamp nem snapshot das tags. Auditoria fica para change
  futura.
- **Backend-only**: sem UI Reflex nesta change (listar descobertos, selecionar e acionar
  importação serão tratados numa change de frontend posterior).
- **GetTags ≠ GroupBy**: a descoberta usa `GetTags`, cujo contrato retorna os valores da Tag Key
  diretamente em `Tags[]` — NÃO aplicar o parser de `"<Key>$<Value>"` (que é exclusivo do
  `GroupBy` de `GetCostAndUsage`). Os valores de `GetTags` já são o `codigo` candidato; apenas
  `trim|upper`, descartar vazio e deduplicar.
