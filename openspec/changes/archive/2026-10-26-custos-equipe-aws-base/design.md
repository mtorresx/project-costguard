## Context

Ver `proposal.md` — Why. Estado atual relevante, lido na implementação existente:

- `classificar_custos_provedor_POST.xs` (`POST /provedores/{id}/classificar-custos`): admin-only;
  pré-condições (`tipo = aws`, `status = ok`, credencial presente, `tag_alocacao_projeto`
  definido); decifra o JWE só em memória; resolve o destino real/Mock por `usar_mock` (host,
  canonical URI e URL coerentes); `GetCostAndUsage` `DAILY` + `UnblendedCost` com
  `GroupBy [TAG <tag_alocacao_projeto>, DIMENSION SERVICE]`; paginação por `NextPageToken`
  (máximo de 100 iterações), reassinando cada página; resolução `trim|upper` do Value contra
  `projetos.codigo`; upsert em `custos_projeto`; registro em `coletas_classificacao`; diagnóstico
  sanitizado (`http_status`, `error_code`, `error_msg`, `request_id`).
- `sincronizar_recursos_provedor_POST.xs`: Tag Key de equipe efetiva = `tag_alocacao_equipe`, com
  fallback `EQP` quando nula/vazia; criação/reutilização de equipe por `(projeto_id, codigo)` com
  `auto_gerada = true`; `sync_id` único por execução (`""|uuid`) e reconciliação por
  `sync_id != atual` somente após sucesso completo.
- Tabelas existentes: `custos`, `custos_projeto`, `coletas_custo`, `coletas_classificacao`,
  `equipes` (índice único `(projeto_id, codigo)`), `recursos`, `provedores` (já contém
  `tag_alocacao_projeto` e `tag_alocacao_equipe`), `projetos`.

Fatos da AWS confirmados na documentação oficial (`API_GetCostAndUsage`, cost allocation tags):

- `GroupBy` aceita no máximo **dois** agrupamentos ("up to two different groups, either
  dimensions, tag keys, cost categories…"). Duas Tag Keys diferentes são permitidas.
- No agrupamento por TAG, cada grupo vem no formato `key$value`; custos sem valor para a Key ficam
  em `key$` ("you get all tag values, including empty strings").
- Tag Keys são case-sensitive. Agrupar por uma Key inexistente ou não ativada coloca todo o custo
  em `Key$`.
- `Filter.Tags` aceita apenas `EQUALS | ABSENT | CASE_SENSITIVE` (padrão case-sensitive).
- Tags precisam ser ativadas como Cost Allocation Tags; isso pode levar até 24h para aparecer e
  mais até 24h para ativar. O backfill (management account) pode retroagir até 12 meses e só
  disponibiliza valores de tag que estavam historicamente atribuídos ao recurso.

Fatos do AWS Mock (repositório `api-mock-aws`, `SUPPORT_MATRIX.md` e `cost_explorer_engine.py`):

- Suporta `GroupBy` com até dois elementos, incluindo `TAG PRJ` + `TAG EQP`, com a ordem das
  `Keys` preservada; ausência de tag produz `PRJ$`/`EQP$`.
- Aceita apenas as Tag Keys configuradas no `.env` do Mock (`PRJ`, `EQP`).
- Pagina por blocos de 60 dias (`ResultsByTime`).
- Não implementa `ListCostAllocationTags`.
- Editar uma tag no Mock reclassifica retroativamente todo o histórico do recurso (simplificação
  do Mock, diferente da AWS real).

## Goals / Non-Goals

**Goals:**

- Responder "quanto cada equipe de um projeto consumiu no período?" a partir da dimensão de tag
  histórica do Cost Explorer.
- Reaproveitar o fluxo validado (JWE, SigV4, destino real/Mock, paginação, diagnóstico
  sanitizado) sem regressão nos endpoints existentes.
- Representar "Sem responsável" sem equipe fictícia.
- Manter a persistência diária, idempotente e convergente em reexecuções, inclusive quando a AWS
  reprocessa o histórico.
- Tratar todos os casos de borda de forma rastreável e não silenciosa.

**Non-Goals:**

- Frontend, dashboard, orçamento, alertas, agendamento.
- Custo por serviço dentro da equipe; custo por recurso.
- `ListCostAllocationTags` ou nova permissão IAM.
- Alterar o AWS Mock.
- Trava contra execução concorrente.
- Corrigir os bugs latentes da classificação por projeto (ver Follow-ups).

## Decisions

### D1 — Consulta: `GroupBy [TAG projeto, TAG equipe]`, sem SERVICE (aprovada)

Uma única consulta por execução e por provedor:

```json
{
  "TimePeriod": { "Start": "<inicio>", "End": "<fim>" },
  "Granularity": "DAILY",
  "Metrics": ["UnblendedCost"],
  "GroupBy": [
    { "Type": "TAG", "Key": "<tag_alocacao_projeto>" },
    { "Type": "TAG", "Key": "<tag_equipe_efetiva>" }
  ]
}
```

- `Keys[0]` = `"<Key projeto>$<valor>"`, `Keys[1]` = `"<Key equipe>$<valor>"`.
- `tag_alocacao_projeto` é obrigatória (sem ela, rejeita antes de chamar a AWS).
- `tag_equipe_efetiva` = `tag_alocacao_equipe` quando preenchida após `trim`; caso contrário,
  `EQP` (mesma regra do inventário).

Alternativa descartada nesta change: uma chamada por projeto com
`Filter.Tags = {Key: projeto, Values: [codigo]}` e `GroupBy [TAG equipe, SERVICE]`. Ela multiplica
chamadas cobradas e, como o filtro é case-sensitive, perderia silenciosamente valores com caixa
ou espaços diferentes (ex.: `pagamentos`, `" PAGAMENTOS"`), violando "nenhum custo é descartado".
O detalhamento por serviço dentro da equipe fica para uma change futura.

### D2 — Entidade `custos_equipe` e representação de "Sem responsável" (aprovada)

| campo | tipo | observação |
|---|---|---|
| `id` | int | |
| `provedor_id` | FK `provedores` | |
| `projeto_id` | FK `projetos` | projeto ativo no momento da gravação |
| `equipe_id` | FK `equipes`, nullable | `null` = "Sem responsável" |
| `codigo_equipe` | text, `trim\|upper` | código normalizado da equipe; `""` = "Sem responsável" |
| `data` | date | dia do custo (`ResultsByTime[].TimePeriod.Start`) |
| `metrica` | enum `unblended` | espelha `custos`/`custos_projeto` |
| `valor` | decimal | soma dos grupos agregados |
| `moeda` | text, default `USD` | `Metrics.UnblendedCost.Unit` |
| `estimado` | bool | `ResultsByTime[].Estimated` |
| `sync_id` | text, private | identificador da execução que gravou/atualizou a linha por último |
| `coletado_em` | timestamp, private | |

Índices:

- único `(provedor_id, projeto_id, codigo_equipe, data, metrica)`;
- btree `(projeto_id, data desc)` para a leitura;
- btree `(provedor_id, data)` para a reconciliação da janela.

`codigo_equipe` entra na chave em vez de `equipe_id` porque, num índice único do Postgres (base do
Xano), `NULL` não colide com `NULL`; uma chave com `equipe_id` nulo não impediria duplicatas de
"Sem responsável". Com `codigo_equipe = ""` a unicidade é garantida pelo banco e nenhuma linha é
criada em `equipes`. A semântica exata de `NULL` em índice único do Xano deve ser confirmada via
Xano Developer MCP no Apply (inferência, não comprovada nesta sessão).

Invariante: `codigo_equipe = ""` ⇔ `equipe_id = null`.

### D3 — Normalização e agregação antes de persistir

Para cada `ResultsByTime` (dia) e cada grupo:

1. Valor de projeto = `Keys[0]` sem o prefixo exato `"<Key projeto>$"`, depois `trim|upper`.
2. Valor de equipe = `Keys[1]` sem o prefixo exato `"<Key equipe>$"`, depois `trim|upper`.
3. A checagem de vazio é feita **após** o `trim` (valor só com espaços = vazio).
4. Os grupos são agregados em memória pela chave `(projeto_id, codigo_equipe, data)`, somando
   `valor`; `estimado` da linha agregada = `Estimated` do dia.

A agregação é necessária porque valores distintos na AWS (`PAGAMENTOS`, `pagamentos`,
`" PAGAMENTOS"`) colapsam na mesma chave após a normalização; sem ela, um upsert sobrescreveria o
outro em vez de somar.

Valores `0` e negativos (ex.: créditos) são persistidos como vierem, como em `custos`.

A agregação nunca soma unidades diferentes: se dois grupos da mesma chave vierem com `Unit`
diferentes, a execução termina como `erro` sanitizado antes de qualquer persistência (ver D12).

### D4 — Resolução projeto → equipe (aprovada)

Na ordem do domínio (projeto antes de equipe):

| situação | ação | contador |
|---|---|---|
| valor de projeto vazio (`PRJ$`), com ou sem equipe | não grava | `nao_alocados` |
| projeto inexistente | não grava, não cria projeto | `tags_sem_projeto` |
| projeto inativo | não grava, não cria equipe | `projetos_inativos` |
| projeto ativo, equipe vazia | grava com `equipe_id = null`, `codigo_equipe = ""` | `sem_responsavel` (linhas) |
| projeto ativo, equipe existente | reutiliza `(projeto_id, codigo)` | — |
| projeto ativo, equipe inexistente | cria `nome = codigo`, `auto_gerada = true` | `equipes_criadas` |

Os contadores `nao_alocados`, `tags_sem_projeto` e `projetos_inativos` contam grupos da resposta
da AWS (mesma semântica de `coletas_classificacao`). O custo não gravado permanece na coleta base
`custos` e na AWS: nada é descartado na origem.

O status do projeto é lido uma vez por código durante a execução. Equipes são resolvidas uma vez
por `(projeto_id, codigo)` e reaproveitadas em memória. Se a criação colidir com o índice único
(ex.: inventário rodando ao mesmo tempo), a equipe é buscada novamente e reutilizada.

Equipes criadas antes de uma falha posterior permanecem: são equipes reais indicadas por tags
válidas da AWS.

### D5 — Semântica temporal: Cost Explorer como fonte histórica, inventário como estado atual

- A equipe de cada linha de `custos_equipe` vem **exclusivamente** da dimensão de tag que o Cost
  Explorer retorna para aquele dia.
- A tabela `recursos` (inventário) MUST NOT ser usada para atribuir ou reclassificar custo.
- Reatribuição: quando a tag muda na AWS, os dias futuros passam a vir com a nova equipe; os dias
  passados só mudam se a AWS reprocessar o histórico (ex.: backfill), e a reconciliação (D7)
  reflete essa mudança na próxima execução sobre a janela.
- Diferença conhecida do Mock: editar a tag no Mock reescreve todo o histórico. No E2E isso é útil
  para exercitar a reconciliação, mas não reproduz a semântica temporal da AWS real.

### D6 — Upsert idempotente com `sync_id`

- Cada execução gera um `sync_id` único (`""|uuid`, como no inventário).
- Para cada linha agregada: busca pela chave única; se existe, `db.edit` (`valor`, `moeda`,
  `estimado`, `equipe_id`, `sync_id`, `coletado_em`); senão, `db.add` com todos os campos e o
  `sync_id` atual.
- Reexecutar a mesma janela sem mudanças na AWS não cria duplicatas e mantém os mesmos valores.

### D7 — Reconciliação da janela por `sync_id` (aprovada, com a arquitetura ajustada)

**Identificador.** O `sync_id` identifica uma execução específica: é gerado uma única vez no início
da execução (`""|uuid`), é único entre execuções e é gravado em toda linha de `custos_equipe`
inserida ou atualizada por ela (D6).

**Quando ocorre.** Somente se a execução concluir completamente, nesta ordem:

1. obtenção de todas as páginas da AWS (fetch);
2. normalização e agregação de todos os dados;
3. todos os upserts.

Se qualquer etapa falhar ou não terminar, a reconciliação **não** é executada e
`registros_removidos = 0`.

**O que remove.** Apenas linhas da tabela `custos_equipe` que satisfazem **todas** as condições:

- `provedor_id` = provedor da execução;
- `data >= data_inicio` e `data < data_fim`, onde `[data_inicio, data_fim)` é exatamente a janela
  consultada nessa execução (`data_fim` exclusivo);
- `projeto_id` pertence a um projeto com `status = ativo` no momento da reconciliação;
- `sync_id` diferente do `sync_id` da execução atual, ou nulo.

**O que nunca remove.** Linhas de outros provedores; linhas com `data` fora de
`[data_inicio, data_fim)`; linhas de projetos atualmente inativos; linhas com o `sync_id` da
execução atual; registros de qualquer outra tabela.

**Contador.** `registros_removidos` conta somente as linhas removidas por essa reconciliação.

Consequências:

- uma combinação que sumiu completamente da resposta (ex.: após backfill, o custo saiu de
  `EQP$` para `EQP$BACKEND`) é removida, evitando contagem dupla;
- um projeto ativo cujo custo inteiro sumiu da janela também tem as linhas antigas removidas;
- linhas de projetos atualmente **inativos** nunca são removidas: o histórico deles é preservado;
- linhas fora da janela e de outros provedores nunca são tocadas.

A remoção é física: `custos_equipe` é um retrato derivado da AWS para a janela, e as linhas
removidas foram substituídas pelo retrato mais recente. O custo de origem continua na AWS e na
coleta base `custos`.

Em qualquer falha antes do término dos upserts, a reconciliação **não** é executada.

### D8 — Garantias em falha parcial (sem transação global)

Não há transação global comprovada no Xano para o lote. Portanto, esta change **não** se descreve
como "gravação atômica". As garantias são:

- **fetch completo antes da persistência**: nenhuma escrita em `custos_equipe` antes de todas as
  páginas;
- **upsert idempotente** pela chave única;
- **reconciliação apenas após sucesso completo** (D7);
- **convergência**: se a execução falhar no meio dos upserts, parte das linhas pode ter o
  `sync_id` novo e parte o antigo; nenhuma linha é removida; reexecutar a mesma janela leva ao
  estado correto.

Para registrar a falha durante a persistência como `erro` (e não abortar sem registro), o trecho
de upserts e reconciliação deve ser protegido por tratamento de erro do XanoScript (ex.:
`try_catch`), com sintaxe a confirmar via Xano Developer MCP no Apply.

Paginação: se o limite de iterações (100) for atingido com `NextPageToken` ainda presente, a
execução é tratada como **erro** (não como sucesso parcial).

### D9 — Aviso de tag de equipe possivelmente não ativada (aprovada)

Se houver ao menos uma linha agregada de projeto ativo na janela e **nenhuma** delas tiver equipe
(todas com `codigo_equipe = ""`), a execução termina com `status = sucesso` e um `aviso`
não bloqueante:

> "Nenhum custo com equipe foi encontrado na janela. Confira se a Tag Key de equipe
> `<tag_equipe_efetiva>` está ativada como Cost Allocation Tag na conta AWS."

Não é erro: todos os custos podem legitimamente estar sem responsável. Não usa
`ListCostAllocationTags`. A ativação das Tag Keys de projeto e de equipe é documentada como
pré-condição operacional na AWS real.

### D10 — Estado da execução em `coletas_custos_equipe`

Espelha `coletas_classificacao`, com campos adicionais:

`id`, `provedor_id`, `sync_id` (private), `intervalo_inicio`, `intervalo_fim`, `status`
(`sucesso`/`erro`), `registros_gravados`, `registros_removidos`, `nao_alocados`,
`tags_sem_projeto`, `projetos_inativos`, `sem_responsavel`, `equipes_criadas`, `aviso`,
`mensagem` (sanitizada), `executado_em`.

Tabela nova (em vez de reaproveitar `coletas_classificacao`) para não alterar a semântica da
tabela existente.

### D11 — Endpoints (aprovados)

**`POST /provedores/{id}/classificar-custos-equipe`** (admin)

- Entrada: `id` (path); `data_inicio?`, `data_fim?` (body, `YYYY-MM-DD`). Mesma semântica de
  intervalo da classificação atual: `Start` inclusivo, `End` exclusivo; padrão
  `Start = hoje (UTC) − 30 dias`, `End = hoje (UTC)`; `data_inicio < data_fim`.
- Saída:

```json
{
  "provedor_id": 2,
  "intervalo": { "inicio": "2026-09-23", "fim": "2026-10-23" },
  "status": "sucesso",
  "registros_gravados": 150,
  "registros_removidos": 0,
  "nao_alocados": 30,
  "tags_sem_projeto": 30,
  "projetos_inativos": 30,
  "sem_responsavel": 30,
  "equipes_criadas": 4,
  "aviso": null,
  "mensagem": "",
  "diagnostico": null
}
```

- Em erro: `status = "erro"`, `mensagem` sanitizada e `diagnostico` no padrão atual
  (`http_status`, `error_code`, `error_msg`, `request_id`), mesmo padrão HTTP dos endpoints
  atuais. Erros de autorização/pré-condição usam `error_type` (`unauthorized`, `accessdenied`,
  `notfound`, `inputerror`).

**`GET /projetos/{id}/custos-equipe?data_inicio&data_fim`** (qualquer usuário autenticado)

- Mesmo intervalo padrão e mesma semântica (`data_fim` exclusivo). Somente leitura; nunca dispara
  coleta nem escrita.
- Agrega todas as linhas de `custos_equipe` do projeto no intervalo, entre todos os provedores.
- Saída:

```json
{
  "projeto_id": 4,
  "intervalo": { "inicio": "2026-09-23", "fim": "2026-10-23" },
  "moeda": "USD",
  "equipes": [
    { "equipe_id": 6, "codigo": "BACKEND", "nome": "BACKEND", "total": 300.00 }
  ],
  "sem_responsavel": { "total": 25.00 },
  "total_projeto": 525.00
}
```

- `equipes` contém apenas equipes com linhas no intervalo, ordenadas por `codigo`; "Sem
  responsável" nunca aparece dentro de `equipes`.
- `total_projeto` = Σ `equipes[].total` + `sem_responsavel.total`.
- Projeto inexistente → `notfound`; projeto inativo → retorna o histórico preservado.
- Sem série diária, sem filtro por provedor, sem detalhamento por serviço.
- `moeda`: moeda única dos registros agregados. Sem registros → `moeda = null`, totais zero e
  `equipes` vazia. Mais de uma moeda no intervalo → erro controlado `inputerror` ("Os custos do
  intervalo estão em moedas diferentes e não podem ser agregados."), sem somar e sem converter
  (D12).

### D12 — Moeda: premissa USD, sem conversão e sem soma de moedas distintas

Evidência no código atual:

- `coletar_custos_provedor_POST.xs:341` e `classificar_custos_provedor_POST.xs:335` gravam
  `moeda = Metrics.UnblendedCost.Unit`, com fallback `"USD"` só quando a AWS não informa a unidade.
  Nenhum dos dois valida nem converte a unidade.
- `custos.xs` e `custos_projeto.xs` declaram `text moeda?=USD` com o comentário "USD no MVP".
- As specs `custos` e `classificacao-custos` exigem valor "expresso em USD".
- `docs/domain-model.md` e `docs/project-overview.md`: moeda inicial USD e conversão de moeda fora
  do escopo.
- O AWS Mock sempre responde `Unit = "USD"`.

Inferência: o Cost Explorer reporta `UnblendedCost` em USD nas contas atendidas hoje, mas o código
não garante isso, e a leitura agrega vários provedores, então uma unidade diferente não pode ser
descartada.

Decisão:

- **Premissa desta change:** os custos são em USD.
- `custos_equipe.moeda` grava a unidade retornada pela AWS (fallback `USD` só quando ausente),
  igual às tabelas existentes.
- Nenhuma agregação soma moedas distintas: na classificação, a mesma chave com `Unit` diferentes
  gera `erro` (D3); na leitura, mais de uma moeda no intervalo gera erro controlado (D11).
- Conversão cambial está fora do escopo.

## Risks / Trade-offs

- **Tag Key de equipe não ativada na AWS real** → todo custo aparece como "Sem responsável".
  Mitigação: aviso não bloqueante (D9) e pré-condição operacional documentada.
- **Sem transação global** → falha no meio dos upserts deixa a janela mista. Mitigação: D8 —
  nenhuma reconciliação em falha, reexecução converge.
- **Execuções concorrentes na mesma janela** → uma pode reconciliar (remover) linhas gravadas pela
  outra. Mitigação: endpoint admin-only, disparo manual; reexecução converge. Trava concorrente
  está fora do escopo.
- **Divergência temporária com `custos_projeto`** → as duas classificações são executadas
  separadamente; os totais por projeto só coincidem quando ambas rodam sobre o mesmo dado da AWS.
- **Mock reescreve histórico ao editar tag** → o E2E não comprova a semântica temporal real;
  comprova a reconciliação.
- **Mock aceita apenas `PRJ`/`EQP`** → a configurabilidade das Keys não é testável via Mock; é
  verificada por revisão de código (nenhum literal `PRJ`/`EQP` fora do fallback de equipe).
- **AWS real não testável nesta change** → paginação real com dois agrupamentos por TAG não é
  comprovada; risco registrado.
- **Custo da API** → uma consulta paginada por execução, igual à classificação atual.

## Permissões IAM

- `ce:GetCostAndUsage` (já exigida). Nenhuma permissão nova.

## Follow-ups (fora desta change, não corrigidos agora)

Bugs latentes identificados em `classificar_custos_provedor_POST.xs` durante a análise:

1. Variantes de caixa/espaço do mesmo código no mesmo dia/serviço (`PRJ$PAGAMENTOS` e
   `PRJ$pagamentos`) fazem o segundo upsert **sobrescrever** o primeiro em vez de somar.
2. Ao atingir `max_iteracoes` com `NextPageToken` pendente, a execução termina como sucesso
   parcial silencioso.
3. A heurística de "tag de alocação inativa" (nenhum grupo com prefixo `Key$`) provavelmente nunca
   dispara na AWS real, que sempre devolve `Key$` mesmo para Key inexistente.
4. Valor de projeto só com espaços é contado como `tags_sem_projeto` em vez de `nao_alocados`.
5. Os upserts não são protegidos por tratamento de erro; uma falha de banco no meio aborta sem
   registrar `erro` em `coletas_classificacao`.

Proposta: uma change de correção dedicada, em branch própria.

## Open Questions

Nenhuma bloqueante. Itens a confirmar no Apply via Xano Developer MCP, sem impacto nas specs:

- semântica de `NULL` em índice único (justifica `codigo_equipe` na chave);
- sintaxe de tratamento de erro (`try_catch`) e de remoção em lote (`db.del` por consulta) no
  XanoScript.
