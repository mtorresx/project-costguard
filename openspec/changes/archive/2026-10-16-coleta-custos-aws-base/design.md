## Context

Ver `proposal.md` — Why. Esta change adiciona a coleta de custos AWS: duas tabelas e um endpoint administrativo no api_group `app`, reusando o provedor AWS e o padrão SigV4 já implementados.

Estado atual relevante (verificado no repositório):

- **Provedores (`provedores`, implementado e validado em E2E)**: tabela `provedores` com `id`, `apelido`, `tipo` (enum `[aws]`), `identificador_conta`, `tipo_credencial` (enum `[aws_access_key]`), `aws_access_key_id` (sensitive), `aws_secret_cifrado` (sensitive, private — token JWE), `aws_secret_iv` (reservado, não usado no JWE), `status` (enum `[pendente, ok, erro, inativo]`), `criado_em` (private).
- **Credencial**: segredo protegido por **JWE** (`jwe_encode`/`jwe_decode`, `A256KW` + `A256CBC-HS512`), chave em `$env.PROV_ENC_KEY`. Decifrado só no backend: `$provedor.aws_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"`.
- **Padrão SigV4 (em `testar_conexao_provedor_POST.xs`)**: datas `now|format_timestamp:"Ymd\\THis\\Z":"UTC"` (amz-date) e `"Ymd"` (datestamp); signing key em 4 HMAC-SHA256 binários (`hmac_sha256:<key>:true`); assinatura hex (`hmac_sha256:<key>`); header `Authorization: AWS4-HMAC-SHA256 Credential=.../SignedHeaders=.../Signature=...`; chamada por `api.request`. Já comprovado funcionando contra a AWS. **Até aqui o SigV4 foi para GET (STS). O Cost Explorer é POST com corpo JSON** — ver D5.
- **Autorização (padrão de `provedores`/`projetos`)**: `auth = "usuarios"`; escrita exige `db.get usuarios` por `$auth.id` + `precondition` de `role == "admin"`.
- **Documentação AWS Cost Explorer (verificada em docs.aws.amazon.com)**: `GetCostAndUsage` — endpoint único global `https://ce.us-east-1.amazonaws.com/` (POST); header `X-Amz-Target: AWSInsightsIndexService.GetCostAndUsage`; `Content-Type: application/x-amz-json-1.1`; corpo exige `TimePeriod {Start, End}` (Start inclusivo, End exclusivo), `Granularity` (`DAILY`), `Metrics` (ex.: `UnblendedCost`); `GroupBy` opcional (`[{Type:"DIMENSION", Key:"SERVICE"}]`); paginação via `NextPageToken` (no corpo da requisição e da resposta). Resposta: `ResultsByTime[]` com `TimePeriod`, `Total` e `Groups[]` (`Keys`, `Metrics.<metric>.{Amount, Unit}`). Permissão IAM: `ce:GetCostAndUsage` (somente leitura).

## Goals / Non-Goals

**Goals:**
- Criar `custos` e `coletas_custo` e o endpoint `coletar_custos_provedor_POST`, reusando credencial/SigV4/`PROV_ENC_KEY`.
- Coletar custo diário por serviço em USD de um provedor `aws`/`ok`, de forma idempotente por período, com paginação e estado de coleta registrado.
- Não expor nenhum segredo/material de assinatura.

**Non-Goals (design):**
- Sem recursos AWS, tags, equipes, consolidação por projeto, alertas, dashboard.
- Sem agendamento (cron/task) — coleta manual/administrativa.
- Sem frontend nesta change (visualização por `leitura` virá depois).
- Sem multi-cloud: modelagem mínima para AWS, sem abstração genérica prematura (campos não impedem evolução futura).

## Decisions

### D1 — Modelagem: custo por dia **e** por serviço (uma tabela)

Decisão: armazenar **custo por dia por serviço** (uma linha por dia/serviço). O total diário é derivável somando os serviços do dia; a granularidade por serviço é a base para a futura classificação por projeto/tags. Isso responde "por dia, serviço ou ambos": **ambos, numa única tabela** `custos`, sem tabela separada de totais (evita duplicação e divergência).

```xs
table custos {
  auth = false
  schema {
    int id
    int provedor_id { table = "provedores" }   // provedor de origem
    date data                                   // dia do custo (granularidade DAILY)
    text servico filters=trim                   // dimensão SERVICE do Cost Explorer
    enum metrica?=unblended { values = ["unblended"] }  // métrica coletada no MVP
    decimal valor                               // montante
    text moeda?=USD                             // unidade (USD no MVP)
    bool estimado?=false                        // ResultsByTime[].Estimated
    timestamp coletado_em?=now { visibility = "private" }
  }
  index = [
    {type: "primary", field: [{name: "id"}]}
    // Idempotência (D4): uma linha por provedor+data+serviço+métrica.
    {type: "btree|unique", field: [
      {name: "provedor_id", op: "asc"},
      {name: "data", op: "asc"},
      {name: "servico", op: "asc"},
      {name: "metrica", op: "asc"}
    ]}
    {type: "btree", field: [{name: "provedor_id", op: "asc"}, {name: "data", op: "desc"}]}
  ]
}
```

- `metrica` é enum de um valor (`unblended`) nesta fase; previsto para evoluir sem quebrar o índice único.
- `moeda` default `USD`; o Cost Explorer devolve `Unit` por métrica (esperado `USD` para `UnblendedCost`).
- `servico` guarda o nome do serviço vindo de `Groups[].Keys[0]`.
- `estimado` reflete `ResultsByTime[].Estimated` (dias recentes costumam vir estimados); default `false`.

### D2 — Estado da coleta: tabela `coletas_custo`

```xs
table coletas_custo {
  auth = false
  schema {
    int id
    int provedor_id { table = "provedores" }
    date intervalo_inicio
    date intervalo_fim                           // exclusivo (semântica AWS)
    enum status?=sucesso { values = ["sucesso", "erro"] }
    int dias_processados?=0
    int registros_gravados?=0
    text mensagem?                               // sanitizada; vazia em sucesso
    timestamp executado_em?=now
  }
  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "provedor_id", op: "asc"}, {name: "executado_em", op: "desc"}]}
  ]
}
```

- "Momento da última coleta" = `executado_em` da linha mais recente por `provedor_id`.
- `mensagem` nunca contém segredo/material de assinatura (D6).

### D3 — Endpoint e contrato

| Método | Rota | Auth | Autorização | Entrada | Saída (sucesso) |
|---|---|---|---|---|---|
| POST | `/provedores/{id}/coletar-custos` | sim | admin | path: `id`; body opcional: `{ data_inicio?, data_fim? }` | `{provedor_id, intervalo:{inicio,fim}, status, dias_processados, registros_gravados, mensagem}` |

- `id` vem **apenas do path**; o body contém somente `data_inicio?`/`data_fim?` (o `id` não é duplicado no corpo).
- Rota aninhada em `provedores/{id}` deixa claro o provedor de origem (identificação do provedor = D7).
- Nomes de arquivo seguindo a convenção: `xano/api/app/coletar_custos_provedor_POST.xs`.
- A resposta nunca inclui segredo, Authorization, signing keys nem JWE decifrado; diagnóstico de erro limitado a status HTTP / `Error.Code` / `Error.Message` sanitizada / `RequestId` (D6).

### D4 — Idempotência (upsert por chave natural)

Chave natural: `(provedor_id, data, servico, metrica)` com índice `btree|unique` (D1). Os upserts só executam **após** todas as páginas da AWS terem sido obtidas com sucesso (ver D10 — coleta atômica). Fluxo por item do lote completo acumulado:
1. `db.get custos` pela chave natural;
2. se existir → `db.edit` atualizando `valor`/`moeda`/`estimado`/`coletado_em`;
3. senão → `db.add`.

Responde "como será feita a idempotência": upsert sobre o índice único, garantindo no máximo uma linha por combinação; reexecução para o mesmo período atualiza valores em vez de duplicar.

### D5 — Requisição Cost Explorer e SigV4 para POST com corpo

**Requisição explícita do MVP:**

```
POST https://ce.us-east-1.amazonaws.com/
Content-Type: application/x-amz-json-1.1
X-Amz-Target: AWSInsightsIndexService.GetCostAndUsage

{
  "TimePeriod": { "Start": "<YYYY-MM-DD>", "End": "<YYYY-MM-DD>" },
  "Granularity": "DAILY",
  "Metrics": ["UnblendedCost"],
  "GroupBy": [ { "Type": "DIMENSION", "Key": "SERVICE" } ]
}
```

Na paginação, o mesmo corpo é reenviado acrescido de `"NextPageToken": "<token>"` (D10).

**Mapeamento da resposta → tabela `custos`:**

| Campo `custos` | Origem na resposta AWS |
|---|---|
| `data` | `ResultsByTime[].TimePeriod.Start` |
| `estimado` | `ResultsByTime[].Estimated` |
| `servico` | `Groups[].Keys[0]` |
| `valor` | `Groups[].Metrics.UnblendedCost.Amount` |
| `moeda` | `Groups[].Metrics.UnblendedCost.Unit` |

**SigV4 (reusa o padrão de `testar_conexao_provedor_POST.xs`)**, com as diferenças obrigatórias de uma requisição **POST com corpo JSON** e header `x-amz-target`:
- `service = "ce"`, `region = "us-east-1"`, `host = "ce.us-east-1.amazonaws.com"`, `endpoint = "https://ce.us-east-1.amazonaws.com/"`.
- `payload_hash = $corpo_json|sha256` (hash do corpo real, não vazio).
- Signed headers (ordem alfabética): `content-type;host;x-amz-date;x-amz-target`.
- Canonical headers correspondentes:
  `content-type:application/x-amz-json-1.1\nhost:<host>\nx-amz-date:<amz_date>\nx-amz-target:AWSInsightsIndexService.GetCostAndUsage\n`.
- Canonical request com método `POST`, URI `/`, query vazia, o payload hash do corpo.
- Signing key / string-to-sign / Authorization: idênticos ao padrão existente (scope `<datestamp>/us-east-1/ce/aws4_request`).
- Chamada: `api.request { method = "POST", params = $corpo, headers = [Host, X-Amz-Date, X-Amz-Target, Content-Type, Authorization] }`. (`params` = corpo da requisição no XanoScript.)
- O corpo JSON assinado deve ser **exatamente** o enviado (serialização estável) para a assinatura bater.

Responde: endpoint correto (`ce.us-east-1.amazonaws.com`), service/region (`ce`/`us-east-1`), request `GetCostAndUsage`.

### D6 — Segurança (reuso das regras aprovadas)

- Segredo decifrado via `jwe_decode` só em memória, imediatamente antes de assinar; nunca logado, nunca na resposta.
- Nunca retornar/logar: Secret Access Key, `PROV_ENC_KEY`, Authorization, signing keys (`$k_*`), assinatura, JWE decifrado.
- Diagnóstico de erro: no máximo `{ http_status, error_code, error_msg, request_id }` (mesmo padrão de `testar-conexao`).

### D7 — Identificação do provedor de origem

A rota é `provedores/{id}/coletar-custos`; cada `custos`/`coletas_custo` referencia `provedor_id` (FK para `provedores`). Assim todo custo é atribuível ao provedor de origem e múltiplos provedores não se misturam.

### D8 — Granularidade e intervalo (padrão do MVP)

- Granularidade: `DAILY` (um registro por dia/serviço).
- Intervalo: `Start` (`data_inicio`) **inclusivo**, `End` (`data_fim`) **exclusivo** (semântica AWS). Quando omitidos, padrão determinístico do MVP = **últimos 30 dias completos até ontem**: `Start = hoje (UTC) − 30 dias` e `End = hoje (UTC)`. Como `End` é exclusivo, o último dia coletado é ontem. (30 dias é o default fixo do MVP, documentado.)
- Validação: `data_inicio < data_fim`; datas no formato `YYYY-MM-DD`.

### D9 — Permissões IAM mínimas e pré-condições operacionais

- Permissão IAM mínima do MVP: **`ce:GetCostAndUsage`** (somente leitura). Nenhuma permissão de escrita. Alinha com o privilégio mínimo da credencial IAM dedicada do provedor.
- Pré-condições operacionais, **fora do controle do CostGuard** (não provisionadas por ele):
  - o AWS Cost Explorer deve estar **habilitado previamente** na conta;
  - após a habilitação, os dados de custo podem levar **~24h** para começar a aparecer;
  - **cada requisição paginada** da Cost Explorer API possui **cobrança** da AWS;
  - em **AWS Organizations**, políticas/configurações da **management account** podem impedir o acesso mesmo com a credencial IAM local adequada.
- Quando qualquer pré-condição impedir a coleta, o backend trata como erro sanitizado e registra o estado (não silencioso).

### D10 — Coleta atômica, falha parcial e paginação

- **Atomicidade (sem persistência parcial):** o backend NÃO grava nada na tabela `custos` durante a paginação. Fluxo: (1) consultar e **acumular/normalizar em memória** todas as páginas; (2) **somente após todas** retornarem sucesso, executar os upserts (D4) do lote completo.
- **Paginação:** enquanto a resposta trouxer `NextPageToken`, repetir `GetCostAndUsage` com esse token **no corpo** (reassinando cada requisição, pois o corpo muda), acumulando resultados.
- **Falha parcial:** se qualquer página falhar (HTTP != 200 ou erro de rede), a coleta é abortada **antes de qualquer upsert**: a tabela `custos` **não é alterada** com um lote incompleto; registra-se `coletas_custo` com `status = erro` e mensagem sanitizada; os dados de coletas anteriores permanecem intactos. O estado de erro é sempre registrado (não silencioso).
- **Limite de páginas:** teto defensivo de iterações (ex.: `while` com contador máximo) evita loop infinito caso a AWS devolva token repetidamente; atingir o teto conta como `erro` sanitizado (sem persistir o lote).

### D11 — Provedor não elegível

Antes de qualquer chamada AWS: validar provedor existe, `tipo = aws`, `status = ok`. Caso contrário, rejeitar (`notfound` para inexistente; `inputerror`/`accessdenied` conforme o caso para não-AWS ou status != ok) sem decifrar credencial nem chamar a AWS.

## Risks / Trade-offs

- **SigV4 POST com corpo** → mais sensível que o GET do STS (hash do corpo, header `x-amz-target`, serialização estável do JSON). Mitigação: reusar o padrão comprovado e isolar a montagem; verificação funcional real só no E2E (como ocorreu em `provedor-aws-base`).
- **Serialização estável do corpo** → a assinatura exige que o corpo assinado seja idêntico ao enviado. Mitigação: montar o JSON uma vez (uma variável) e usar a mesma variável no hash e no `params`.
- **Loop de paginação sem fim** → mitigado pelo teto de iterações (D10).
- **Acúmulo em memória antes do upsert** → a coleta atômica (D10) guarda o lote completo em memória antes de persistir; para os volumes do MVP (poucos serviços × ~30 dias) é aceitável. Intervalos muito grandes poderiam crescer o lote; mitigável limitando o intervalo numa evolução futura.
- **`UnblendedCost` vs outras métricas** → MVP coleta só `UnblendedCost` (custo real faturado, em USD). Decisão registrada; `metrica` enum permite evoluir.
- **Pré-condições operacionais do Cost Explorer (D9)** → habilitação prévia na conta, ~24h de atraso dos dados, cobrança por request paginado e restrições de AWS Organizations estão fora do controle do CostGuard; qualquer impedimento é tratado como `status = erro` sanitizado. Responsabilidade do operador AWS.
- **Fuso/limite de datas** → datas em UTC, `End` exclusivo; divergência de fuso pode incluir/excluir um dia de borda. Aceitável no MVP.

## Migration Plan

- Mudança aditiva: duas tabelas novas e um endpoint novo no api_group `app`; nenhuma alteração em `provedores`/`projetos`/`usuarios`/autenticação. Rollback = remover as tabelas/endpoint. Nenhuma nova variável de ambiente (reusa `PROV_ENC_KEY`).

## Open Questions

- **Q1 — Default do intervalo (30 dias):** o padrão de 30 dias atende o MVP acadêmico? Não bloqueia o contrato; o valor pode ser ajustado na implementação sem mudar specs. Proposta atual: 30 dias até ontem.
- **Q2 — Métrica única (`UnblendedCost`):** suficiente para o MVP? Decisão atual: sim. O schema (`metrica` enum) acomoda métricas adicionais depois sem quebrar a idempotência.
- **Q3 — Teto de páginas na paginação:** valor do limite defensivo (ex.: 100 iterações) a confirmar na implementação; é detalhe de robustez, não altera specs.
