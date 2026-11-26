## Context

Ver `proposal.md` — Why. Estado atual relevante (lido na implementação existente):

- `provedores` (`xano/table/provedores.xs`): campos `id`, `apelido`, `tipo` (enum `aws`),
  `identificador_conta`, `tipo_credencial`, `aws_access_key_id` (sensível), `aws_secret_cifrado`
  (JWE, private), `status` (enum `pendente|ok|erro|inativo`), `tag_alocacao_projeto` (da change
  `classificacao-tags-aws-base`, ainda não arquivada).
- `testar_conexao_provedor_POST.xs`: assina SigV4 para STS (`service=sts`,
  `host=sts.amazonaws.com`) e chama `GET https://sts.amazonaws.com/?Action=GetCallerIdentity`.
- `coletar_custos_provedor_POST.xs`: constantes SigV4 do Cost Explorer (`$sig_service="ce"`,
  `$sig_region="us-east-1"`, `$sig_host="ce.us-east-1.amazonaws.com"`,
  `$sig_endpoint="https://ce.us-east-1.amazonaws.com/"`), payload `GetCostAndUsage`, paginação
  `NextPageToken`, upsert idempotente. O `api.request.url` usa `$sig_endpoint`.
- `classificar_custos_provedor_POST.xs` (change aberta): mesmo padrão de SigV4/destino para
  Cost Explorer, com `GroupBy [TAG, SERVICE]`.

Fato-chave sobre SigV4 e o Mock: a assinatura SigV4 inclui o `Host` e o canonical URI no
canonical request. Embora o Mock **não valide SigV4** hoje, a assinatura enviada deve ser
**tecnicamente coerente com o destino efetivo** — ou seja, assinada com o host e o canonical
URI do Mock quando a requisição vai ao Mock — para possibilitar validação futura sem redesenho.
Portanto, a estratégia é usar **uma única implementação SigV4** e parametrizar os componentes
que compõem a assinatura (`host`, canonical URI/path) e o destino (`url`), de modo que
assinatura e requisição fiquem sempre consistentes.

## Goals / Non-Goals

**Goals:**

- Adicionar `usar_mock` ao provedor sem alterar o fluxo AWS real (default `false`).
- Reutilizar uma única implementação de SigV4, coleta e teste, parametrizando só o destino.
- Suportar N provedores Mock, cada um com sua conta/credencial, sem nada global/hardcoded.
- Isolar completamente o Mock do caminho real.
- Habilitar (posteriormente) o E2E de `classificacao-tags-aws-base` via Mock.

**Non-Goals (nível de design):**

- Não modificar o AWS Mock Simulator.
- Não implementar STS no Mock, nem validação criptográfica de credenciais Mock.
- Não arquivar `classificacao-tags-aws-base` nesta change.
- Não implementar nada nesta etapa — apenas planejamento.

## Decisions

### D1 — `usar_mock` como boolean no provedor (não novo tipo)

Adicionar `bool usar_mock?=false` em `provedores`. Mock é uma característica do provedor AWS,
não um novo `tipo`. Default `false` é obrigatório para preservar todos os provedores e fluxos
existentes. Alternativa descartada: novo `tipo = mock` — quebraria as pré-condições
`tipo == "aws"` espalhadas (teste, coleta, classificação) e exigiria tratamento paralelo.

### D2 — Base URL do Mock em variável de ambiente

`MOCK_BASE_URL` (ex.: `https://<URL-DO-SIMULADOR>`) como env var do workspace Xano, lida
**apenas no backend** — nunca enviada ao frontend Reflex. Não hardcodar no XanoScript (o ambiente
Mock pode mudar) e não criar `MOCK_ACCOUNT_ID` global (o Account ID vem sempre de
`provedor.identificador_conta`).

**Montagem segura da URL (normalização obrigatória):** antes de concatenar, remover eventual
barra final de `MOCK_BASE_URL`, de modo que tanto `https://<URL-DO-SIMULADOR>` quanto
`https://<URL-DO-SIMULADOR>/` (erro de config) produzam a mesma URL correta, sem barra
dupla. Esquema conceitual:

```
base_normalizada = MOCK_BASE_URL sem barra final      // rstrip "/"
url_mock          = base_normalizada ~ "/aws/" ~ identificador_conta ~ "/ce/"
```

Resultado: sempre `https://<URL-DO-SIMULADOR>/aws/{conta}/ce/`, nunca
`https://<URL-DO-SIMULADOR>//aws/{conta}/ce/`. O caminho `usar_mock = false` MUST NOT ler
`MOCK_BASE_URL` nem depender dela.

### D3 — Uma única implementação SigV4, assinando coerentemente o destino efetivo

Nos endpoints de coleta (e, futuramente, classificação), reutilizar a mesma implementação SigV4
e **parametrizar os componentes da assinatura que dependem do destino**, de modo que a assinatura
corresponda sempre ao host/URI efetivamente usados. Não criar uma segunda implementação.

Parametrizar três componentes a partir de `usar_mock` (o restante — `service=ce`,
`region=us-east-1`, geração de canonical request, string to sign, signing key — permanece único e
inalterado):

1. `$sig_host` (vai ao header `Host` e à linha `host:` do canonical headers):
   - `usar_mock = false` → `ce.us-east-1.amazonaws.com`;
   - `usar_mock = true`  → `<URL-DO-SIMULADOR>` (derivado de `MOCK_BASE_URL`).
2. `$canonical_uri` (o path usado no canonical request; hoje é implicitamente `/`):
   - `usar_mock = false` → `/`;
   - `usar_mock = true`  → `/aws/{identificador_conta}/ce/`.
3. `$sig_endpoint` / `api.request.url` (destino efetivo):
   - `usar_mock = false` → `https://ce.us-east-1.amazonaws.com/`;
   - `usar_mock = true`  → `{base_normalizada}/aws/{identificador_conta}/ce/` (ver D2).

Assim, a assinatura enviada é **tecnicamente coerente** com o destino: no Mock, assina-se com
`host = <URL-DO-SIMULADOR>` e `canonical URI = /aws/{conta}/ce/`, e a requisição vai
exatamente para esse host/URI. O Mock ainda não valida a assinatura, mas ela fica correta para
validação futura, sem redesenho. O `service`/`region` permanecem `ce`/`us-east-1` (reuso da mesma
derivação de signing key; o Mock emula o contrato do Cost Explorer).

Nota de implementação: o canonical request atual usa `"/"` fixo como URI. A parametrização
introduz `$canonical_uri` substituindo esse literal, e ajusta o header/linha `host` para
`$sig_host`. É a menor alteração que mantém assinatura e destino consistentes, sem duplicação.

### D4 — Teste de conexão condicional ao `usar_mock`

Em `testar_conexao_provedor_POST.xs`, ramificar por `usar_mock`:

- `false` → fluxo STS atual **inalterado**.
- `true`  → NÃO assinar/chamar STS. Fazer uma chamada ao Cost Explorer do Mock em
  `{base_normalizada}/aws/{identificador_conta}/ce/` com
  `X-Amz-Target: AWSInsightsIndexService.GetTags`, corpo com `TagKey = PRJ` e um `TimePeriod`
  válido, **assinada com SigV4 coerente ao destino do Mock** (host `<URL-DO-SIMULADOR>`,
  canonical URI `/aws/{conta}/ce/`, conforme D3) — exercitando a execução da assinatura pelo
  CostGuard. O secret Mock é decifrado via JWE só em memória, como no real. Critério de sucesso:
  resposta HTTP 2xx no contrato AWS JSON do Cost Explorer (GetTags), **mesmo que a lista de Tags
  venha vazia** ⇒ `status = ok`. O teste MUST NOT ser condicionado à existência de custos nem de
  um projeto específico. Account ID inexistente, resposta incompatível com o contrato, ou Mock
  offline/inacessível ⇒ `status = erro` sanitizado (não silencioso).

O teste Mock valida: endpoint, Account ID, comunicação HTTPS, contrato AWS JSON e a execução da
assinatura SigV4 pelo CostGuard. Limitação documentada: como o Mock não valida SigV4, o teste
**não** autentica criptograficamente as credenciais — credencial fictícia incorreta ainda pode
dar `ok`. Isso não é ocultado.

### D5 — Classificação reaproveita o mesmo mecanismo de destino

`classificar_custos_provedor_POST.xs` (change `classificacao-tags-aws-base`, aberta) receberá a
mesma parametrização de destino (D3) quando aquela change for retomada/arquivada, habilitando o
E2E via Mock. Esta change **não** altera aquele endpoint agora (para não interferir numa change
aberta); o delta formal de `custos` cobre a coleta base. A convenção de tag permanece a oficial:
Key = `tag_alocacao_projeto` (recomendada `PRJ`), Value = `projetos.codigo` (ex.: `PRJ$PAGAMENTOS`
→ `PAGAMENTOS`; `PRJ$` → não alocado). NÃO reintroduzir `PRJ_PAGAMENTOS`.

### D6 — Tag de projeto para contas Mock

Não criar regra especial de tag para Mock. Um provedor Mock usa o mesmo
`tag_alocacao_projeto`; para as contas do Mock Simulator, configurar `PRJ` normalmente. Sem
hardcode espalhado.

### D7 — Frontend: um único checkbox

No modal de provedor, adicionar logo após o Account ID um checkbox "Usar ambiente AWS Mock"
ligado a `usar_mock`. Sem redesenho, sem nova página. Access Key e Secret permanecem visíveis
com Mock marcado; Account ID continua obrigatório. Na listagem, exibir uma indicação discreta de
Mock apenas se ajudar operacionalmente (ex.: um selo), evitando poluição.

## Risks / Trade-offs

- **Mock não valida SigV4** → o teste Mock e a coleta Mock podem "passar" com credenciais
  fictícias incorretas. Mitigação: documentar explicitamente (specs + UI/doc); o teste Mock é
  declarado como validação de endpoint/Account ID/contrato, não de credenciais.
- **Acoplamento ao host/URI real na assinatura** → hoje `$sig_host` e o canonical URI (`/`) são
  fixos. Mitigação: parametrizar `$sig_host`, `$canonical_uri` e o destino numa resolução
  condicional única (D3); `usar_mock = false` usa exatamente os valores atuais (host
  `ce.us-east-1.amazonaws.com`, URI `/`, endpoint real), sem regressão; `usar_mock = true` assina
  coerentemente com o host/URI do Mock.
- **Dependência de env var `MOCK_BASE_URL`** → se ausente, provedores Mock não funcionam.
  Mitigação: só afeta `usar_mock = true`; o caminho real não lê a var. Validar presença antes de
  montar a URL Mock e retornar erro sanitizado se faltar.
- **Interferência com `classificacao-tags-aws-base` (aberta)** → ambas tocam provedores.
  Mitigação: esta change usa ADDED (`usar_mock`) + MODIFIED em "Teste de conexão" e "Consulta ao
  Cost Explorer", requisitos NÃO modificados pela outra change (que modifica "Entidade Provedor"
  e a capability `classificacao-custos`). Deltas disjuntos evitam conflito no archive.
- **Credenciais cruzando ambientes** → risco de usar credencial Mock em endpoint real ou vice-
  versa. Mitigação: o destino é derivado do mesmo provedor que fornece a credencial; nunca se
  mistura provedor e destino de provedores diferentes.

## Permissões / Configuração

- Nenhuma permissão IAM nova para o Mock (ele não valida credenciais).
- Nova configuração: env var `MOCK_BASE_URL` no workspace Xano.
- AWS real: permissões inalteradas (`sts:GetCallerIdentity` no teste, `ce:GetCostAndUsage` na
  coleta).

## Open Questions

- Nenhuma. As decisões de SigV4 (assinar com host/URI do destino efetivo), montagem segura da
  URL (normalização de barra final, `MOCK_BASE_URL` só no backend) e teste de conexão Mock
  (`GetTags` com `TagKey = PRJ`, tags vazias = sucesso) estão definidas pelo usuário e refletidas
  nas specs.
