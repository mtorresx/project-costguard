## Context

Ver `proposal.md` — Why. Estado atual verificado no repositório:

- Tabelas Xano existentes: `usuarios`, `provedores`, `projetos`, `custos`, `custos_projeto`,
  `coletas_custo`, `coletas_classificacao`. **NÃO existem `equipes` nem `recursos`** (confirmado
  por inspeção de `xano/table/`).
- `provedores` já tem `tag_alocacao_projeto` (Tag Key de projeto, recomendada `PRJ`), `usar_mock`,
  credencial JWE e SigV4 consolidado.
- Padrões reaproveitáveis dos endpoints existentes: autorização admin + pré-condições de provedor;
  decifragem JWE do secret só em memória; SigV4 parametrizado por destino (host/canonical URI/URL,
  real vs Mock); paginação com reassinatura por página; diagnóstico sanitizado; routing real/Mock
  por `usar_mock`.
- Convenção oficial atual: projeto `PRJ=<codigo>`, equipe `EQP=<codigo>` (Tag Key = finalidade,
  Tag Value = código). As convenções históricas `PRJ_PAGAMENTOS`/`EQP_BACKEND` NÃO são o contrato
  atual (ver "Inconsistência documental").

Fatos técnicos da AWS confirmados por documentação oficial (Resource Groups Tagging API /
Resource Explorer):

- `GetResources` (serviço `resourcegroupstaggingapi`, prefixo IAM `tag`) retorna recursos
  tagueados **de uma Região específica** — é **regional**. Suporta `TagFilters` e paginação por
  `PaginationToken` (repetir até `null`).
- `GetResources` **não retorna recursos sem nenhuma tag**; para esses, só via **Resource Explorer**
  com query `tag:none` (fora do escopo desta change).
- Permissão mínima: `tag:GetResources`. Para enumerar regiões habilitadas: EC2 `DescribeRegions`
  (`ec2:DescribeRegions`).
- Resource Explorer permite busca cross-region, mas **exige provisionamento** (índice local por
  região + aggregator index + view) — pré-condição fora do controle do CostGuard.

## Goals / Non-Goals

**Goals:** inventariar recursos que participam do tagging de projeto; resolver projeto→equipe por
recurso; criar equipes automaticamente; representar "Sem responsável" como estado real; persistir
e reconciliar recursos; endpoints read-only para consumo futuro.

**Non-Goals (nível de design):** custo por equipe/recurso, Cost Explorer PRJ+EQP, orçamento/
percentual, dashboard, telas, alertas, recursos totalmente sem tag (Resource Explorer `tag:none`),
rateio, edição manual de atribuição, alterar o Mock.

## Decisions

### D1 — API de inventário: Resource Groups Tagging API `GetResources`

Adotar `GetResources` filtrando **apenas pela Tag Key de projeto** (`TagFilters: [{ Key: <PRJ> }]`).
Ler, em cada `ResourceTagMappingList[]`, o `ResourceARN` e as `Tags[]`; extrair a tag de projeto e,
se houver, a de equipe. **Não** filtrar por equipe junto — isso excluiria os "Sem responsável"
(projeto sem EQP). Alternativa descartada: enumerar via APIs por serviço (EC2/RDS/S3...) — inviável
e não uniforme. `GetResources` dá ARN + tags de forma homogênea.

### D2 — Estratégia regional: enumerar regiões habilitadas e varrer (MVP)

Opções comparadas:

- **A) Região única configurada no provedor** — simples (1 chamada), poucas permissões, mas
  **cobertura incorreta**: perde recursos fora da região. Rejeitada como MVP (fere o requisito de
  não assumir região única). Pode existir como *override* opcional de performance no futuro.
- **B) Enumerar regiões habilitadas (EC2 `DescribeRegions`) e `GetResources` por região** —
  cobertura correta da conta; custo = 1 `DescribeRegions` + N `GetResources` (N = regiões
  habilitadas, ~17 por padrão); permissões `ec2:DescribeRegions` + `tag:GetResources`;
  implementação média (loop de regiões × paginação); **testável no Mock** (o Mock pode simular
  `DescribeRegions` e `GetResources` por região). **Escolhida para o MVP.**
- **C) Resource Explorer com aggregator index (cross-region numa região)** — 1 consulta cobre a
  conta, mas **exige provisionamento** (índice por região + aggregator + view) fora do controle do
  CostGuard; permissão `resource-explorer-2:Search`; difícil de simular no Mock; pré-condição
  operacional frágil. Rejeitada para o MVP; registrada como evolução futura.
- **D) Outra** — não identificada como melhor que B para o MVP.

**Decisão:** B. Justificativa: é a única com cobertura correta sem depender de provisionamento
prévio na conta, usa apenas permissões read-only simples, e é simulável no Mock. O custo de N
chamadas é aceitável para uma operação administrativa manual. A `regiao` de cada recurso é gravada.

Robustez: a enumeração de regiões é parte da sincronização; se `DescribeRegions` falhar, a
sincronização falha como um todo (sem reconciliar). Opcionalmente, o provedor pode no futuro ter
uma lista de regiões-alvo para reduzir chamadas — não no MVP.

### D3 — Tag Key de equipe por provedor (`tag_alocacao_equipe`), com default EQP seguro

Análogo a `tag_alocacao_projeto`: campo no provedor, recomendado `EQP`, não hardcoded na lógica
(o valor vem sempre do provedor). Para evitar que um provedor sem o campo transforme todos os
recursos em "Sem responsável", a estratégia é em camadas (sem migration destrutiva):

1. **Default do schema = `"EQP"`**: `text tag_alocacao_equipe?=EQP` — provedores novos nascem com
   `EQP` mesmo que o insert não envie o campo.
2. **Create com fallback `EQP`**: `criar_provedor_POST` grava `EQP` quando o campo não é informado
   (nunca `null`).
3. **PATCH preserva**: edição sem enviar o campo mantém o valor atual (não apaga).
4. **Runtime da sincronização com fallback `EQP`**: ao resolver a Tag Key de equipe, se o valor do
   provedor for `null`/vazio (provedor **legado** cujo ADD_FIELD deixou `null`), usa-se `EQP`. Isso
   garante que provedores legados continuem resolvendo equipes pela convenção padrão, em vez de
   marcarem tudo como "Sem responsável" silenciosamente.

Se o admin informar explicitamente outra Key válida, ela é preservada em todos os caminhos. A
ausência de equipe só resulta em "Sem responsável" quando o recurso realmente não tem a tag de
equipe (não por o provedor estar sem a Key configurada).

### D4 — Modelo `equipes`

Campos do MVP: `id`, `nome`, `codigo` (`trim|upper`), `projeto_id` (FK `projetos`), `auto_gerada`
(bool, default conforme origem). **Sem `budget`.** Sobre `status`: **não incluir** no MVP — não há
requisito de domínio atual que dependa de ativar/desativar equipe (diferente de projeto, que já
tinha `status`); o ciclo de vida da equipe é derivado da nuvem (reatribuição automática). Se
necessário no futuro (ex.: equipe órfã), tratar em change própria. Unicidade: índice
`(projeto_id, codigo)` único. `codigo` NÃO é globalmente único.

### D5 — Modelo `recursos` (campos realmente necessários no MVP)

Campos adotados e justificativa (dos candidatos propostos, mantidos os necessários):

- `id` — PK.
- `provedor_id` (FK) — origem; parte da unicidade.
- `arn` (text, íntegro) — identificador único do recurso; **preservado integralmente**.
- `regiao` (text) — necessária (recurso é regional; usada em auditoria e futura coleta).
- `servico` (text) — derivado do ARN (ex.: `ec2`, `rds`, `s3`); útil para inventário/auditoria.
- `projeto_id` (FK nullable) — projeto resolvido.
- `equipe_id` (FK nullable) — equipe resolvida; `null` = "Sem responsável".
- `codigo_projeto_tag` (text) — valor cru da tag de projeto (auditoria/debug e rastreio de "projeto
  desconhecido").
- `codigo_equipe_tag` (text, nullable) — valor cru da tag de equipe.
- `sync_id` (text) e `ultima_vista_em` (timestamp) — presença no último inventário (reconciliação).
- `ativo` (bool) — estado de reconciliação (recurso ainda presente).
- `criado_em`/`atualizado_em` (timestamps) — auditoria.

Descartado no MVP: `tipo_recurso` separado (derivável do ARN quando necessário; evita campo de
baixo uso) e `tags_raw/json` completo (guardar o JSON cru de todas as tags é útil para debug, mas
não essencial ao MVP e depende de suporte adequado a JSON na tabela; manter apenas os valores crus
de PRJ/EQP cobre auditoria da classificação). Se o debug exigir o JSON completo depois, adiciona-se
em change incremental.

**Unicidade:** `(provedor_id, arn)`. Embora o ARN seja globalmente único na AWS, a chave inclui
`provedor_id` para manter o isolamento por provedor já adotado no projeto e evitar colisões caso o
mesmo recurso seja (indevidamente) cadastrado sob dois provedores. `nome/identificador` separado
não é essencial — o ARN já identifica; um "nome amigável" pode ser derivado do ARN na leitura.

### D6 — Resolução projeto→equipe (ordem canônica)

Para cada recurso: (1) extrair valor da Tag Key de projeto; (2) `trim|upper`; (3) buscar
`projetos.codigo`; (4) sem projeto ⇒ `projeto_id=null`, `equipe_id=null`, não cria nada,
contabiliza "projeto desconhecido"; (5) projeto inativo ⇒ persiste com `projeto_id` do inativo,
`equipe_id=null`, **não cria equipe**, contabiliza; (6) projeto ativo ⇒ ler Tag Key de equipe;
(7) equipe ausente/vazia ⇒ `equipe_id=null` ("Sem responsável"); (8) equipe presente ⇒ `trim|upper`,
buscar `(projeto_id, codigo)`; (9) existe ⇒ atribui; (10) não existe ⇒ cria `auto_gerada=true` e
atribui. Nunca cria equipe fictícia `SEM_RESPONSAVEL`. A nuvem é a fonte da verdade: mudança de tag
reatribui na próxima sincronização.

**Projeto inativo (decisão):** persistir o recurso vinculado ao projeto inativo com
`equipe_id=null` e contabilizar `projetos_inativos`, **sem criar equipe**. Alternativa (ignorar o
recurso) foi descartada: perder a visibilidade do recurso seria pior; mantê-lo visível e sem
equipe é coerente com "custos/recursos não são descartados por problema de classificação".

### D7 — Upsert idempotente + reconciliação segura

- Gerar um `sync_id` **único por execução via UUID** (`""|uuid`) no início. Um UUID identifica
  uma execução específica; NÃO usar timestamp+provedor_id (duas execuções próximas/paralelas do
  mesmo provedor poderiam colidir e deixar um recurso ausente incorretamente `ativo`).
- Buscar todas as páginas de todas as regiões, acumulando em memória (sem persistir parcial que
  dispare reconciliação).
- Upsert por `(provedor_id, arn)`: atualiza campos resolvidos + `sync_id`/`ultima_vista_em`/
  `ativo=true`; insere quando novo.
- **Somente após sucesso completo** (todas as páginas de todas as regiões): reconciliar — marcar
  `ativo=false` os recursos do provedor cujo `sync_id` != o atual (não vistos nesta execução).
  Desativação lógica (nunca exclusão física).
- Falha em qualquer etapa ⇒ não reconciliar; inventário anterior intacto; `status=erro` sanitizado.

Nota de implementação: o upsert em si pode persistir página a página (idempotente); o passo que
**NÃO** pode rodar em falha parcial é a **reconciliação** (desativação dos ausentes). A segurança
está em condicionar a reconciliação ao sucesso completo e usar o `sync_id` para distinguir vistos
de ausentes.

### D8 — Endpoints

- `POST /provedores/{id}/sincronizar-recursos` (admin): executa o inventário completo (regiões →
  GetResources paginado → resolução → upsert → reconciliação) e responde com `status` + contadores
  (`recursos_encontrados`, `recursos_ativos`, `recursos_desativados`, `equipes_criadas`,
  `sem_responsavel`, `projetos_desconhecidos`, `projetos_inativos`) + `mensagem`/`diagnostico`
  sanitizados.
- `GET /projetos/{id}/recursos` e `GET /projetos/{id}/equipes` (autenticado, read-only): pertencem
  a esta capability para habilitar consumo do inventário sem depender de outra change. Sem
  frontend. Decisão: **incluir** nesta change (são leitura simples do que esta change cria; deixá-los
  para depois atrasaria o uso do inventário).

### D9 — Reaproveitar JWE/SigV4; novo destino regional

Reutilizar a mesma implementação SigV4, parametrizando `service = "tagging"`, `region = <região
corrente>`, `host = tagging.<região>.amazonaws.com`, canonical URI `/`, `X-Amz-Target` da Tagging
API (`ResourceGroupsTaggingAPI_20170126.GetResources`) e corpo JSON. Para `DescribeRegions`, EC2
Query API (`ec2.<região>.amazonaws.com` ou `ec2.amazonaws.com`) também assinada por SigV4. **Não**
duplicar o algoritmo de assinatura. Routing real/Mock por `usar_mock` como nas demais operações
(no Mock, host/base derivados de `MOCK_BASE_URL`).

### D10 — Proteção best-effort contra duplo disparo (NÃO é lock atômico)

**Decisão do usuário / LIMITAÇÃO MVP:** evitar duplo disparo acidental da sincronização na operação
normal, sem introduzir uma abstração de lock que dependa de comportamento não confirmado do Xano
(captura de violação de unique no `db.add`, try/catch, etc.). Foi descartada, para o MVP, a tabela
`locks_sincronizacao` com `provedor_id UNIQUE`.

Mecanismo adotado — estado no próprio provedor (campos `private`):
`sincronizacao_recursos_em_andamento` (bool), `sincronizacao_recursos_inicio` (timestamp),
`sincronizacao_recursos_id` (text = `sync_id` da execução).

Fluxo: após as pré-condições e **antes** de qualquer chamada externa, reler o provedor; se
`em_andamento == true` **e** a marca ainda está dentro da janela (`agora − inicio ≤ 15 min`),
rejeitar com erro controlado sanitizado ("Já existe uma sincronização de recursos em andamento
para este provedor."). Caso contrário (sem marca, ou marca órfã/expirada), adquirir a marca
(`em_andamento=true`, `inicio=now`, `id=sync_id`). Ao final — **sucesso e todo caminho de erro
controlado** (que chega ao fim com `$falhou=true`) — liberar a marca **apenas se**
`sincronizacao_recursos_id` ainda for o `sync_id` desta execução (para não apagar a marca de uma
execução que tomou o lugar de uma marca órfã).

**LIMITAÇÃO MVP (explícita):** esta proteção é **operacional/best-effort**, com uma janela
read-then-write **não atômica** entre a verificação e a aquisição; **não** deve ser tratada como
mutex transacional distribuído. Duas chamadas verdadeiramente simultâneas ainda poderiam, em
teoria, passar ambas. O objetivo é impedir o duplo disparo acidental da operação normal; o endpoint
é **admin-only**. A recuperação de marca órfã é por **janela de tempo** (15 min > soma plausível
dos timeouts de rede), também best-effort. Um lock atômico (ex.: tabela com `provedor_id UNIQUE`)
poderá ser implementado futuramente quando o mecanismo atômico suportado pelo Xano estiver
confirmado documentalmente.

## Dependência exata do AWS Mock (externa, não alterar aqui)

O Mock atual simula apenas Cost Explorer (`GetCostAndUsage`, `GetTags`). Esta change exige, para o
E2E, que o Mock passe a simular:

1. **Resource Groups Tagging API `GetResources`**, por região:
   - `POST {MOCK_BASE_URL}/aws/{account_id}/tagging/{region}/` (ou esquema equivalente que o Mock
     definir para endpoints regionais de tagging);
   - Header `X-Amz-Target: ResourceGroupsTaggingAPI_20170126.GetResources`,
     `Content-Type: application/x-amz-json-1.1`;
   - Body: `{ "TagFilters": [ { "Key": "<PRJ>" } ], "PaginationToken": "<opcional>" }`;
   - Resposta: `{ "ResourceTagMappingList": [ { "ResourceARN": "...", "Tags": [ {"Key":"PRJ","Value":"PAGAMENTOS"}, {"Key":"EQP","Value":"BACKEND"} ] }, ... ], "PaginationToken": "<ou vazio>" }`;
   - Deve suportar paginação (retornar `PaginationToken` não-vazio para simular múltiplas páginas).
2. **Enumeração de regiões (DescribeRegions) — obrigatório** (decisão do usuário): o Mock SHALL
   simular EC2 `DescribeRegions` (`POST`/Query em `{MOCK_BASE_URL}/aws/{account_id}/ec2/{region}/`
   com `Action=DescribeRegions`), retornando uma lista de regiões fictícias habilitadas. **Não**
   usar uma única região fictícia hardcoded: o Mock deve reproduzir a arquitetura real
   `DescribeRegions → GetResources por região → consolidação`. O dataset de E2E idealmente terá
   recursos em **pelo menos 2 regiões**, para exercitar a varredura multi-região e a consolidação.

**E2E bloqueado até o Mock evoluir:** a sincronização de recursos ponta a ponta (descobrir recursos,
resolver equipe, "Sem responsável", reconciliação) **não pode ser testada** sem esse suporte. As
partes testáveis antes disso: schema (equipes/recursos), pré-condições/autorização, validação de
`tag_alocacao_equipe`, e o comportamento de erro quando o destino não suporta a Tagging API. A
evolução do Mock será feita em branch/change separada no repositório do Mock (não aqui).

## Permissões IAM necessárias (novas)

- `tag:GetResources` — inventário por região (read-only).
- `ec2:DescribeRegions` — enumerar regiões habilitadas (read-only).

Ambas read-only, coerentes com a credencial de privilégio mínimo. Nenhuma permissão de escrita. As
permissões anteriores (`sts:GetCallerIdentity`, `ce:GetCostAndUsage`, `ce:GetTags`) permanecem.

## Inconsistência documental identificada

`docs/domain-model.md` (seção 8 "Convenção de Tags") descreve a tag de equipe no formato histórico
`EQP_BACKEND` (prefixo embutido no valor), que **não** é a convenção oficial atual (`EQP=BACKEND`,
Tag Key = `EQP`, Tag Value = `codigo`). O mesmo documento, porém, afirma corretamente que "o mesmo
código de equipe pode existir em projetos diferentes" (coerente com a unicidade `(projeto_id,
codigo)` desta change). **Recomendação:** atualizar `docs/domain-model.md` para a convenção oficial
`EQP=<codigo>` (como foi feito para `PRJ` em change anterior). Não altero a doc nesta etapa de
planejamento; registro para decisão do usuário (pode ser corrigida no archive desta change ou em
ajuste doc à parte).

## Risks / Trade-offs

- **Dependência do Mock** → E2E do inventário bloqueado até o Mock simular Tagging API +
  (opcionalmente) DescribeRegions. Mitigação: contrato especificado acima; partes não dependentes
  do Mock são testáveis antes.
- **N chamadas por região** → custo/tempo de uma sincronização cresce com o número de regiões
  habilitadas. Mitigação: operação administrativa manual; futuro override de regiões-alvo.
- **Projeto inativo / desconhecido** → recursos preservados e contabilizados, sem criar
  projeto/equipe; coerente com "nada é descartado por classificação".
- **Reconciliação x falha parcial** → desativação só após sucesso completo, via `sync_id`.
- **ARN muito longo** → campo `text` íntegro; não truncar.

## Decisões confirmadas pelo usuário

- **Endpoints read-only incluídos** (D8): `GET /projetos/{id}/recursos` e `GET /projetos/{id}/equipes`
  pertencem a esta change (usados por E2E e pelo futuro frontend). **Sem custos** nesses endpoints
  nesta change.
- **Projeto inativo** (D6): persistir o recurso com `projeto_id` do projeto inativo encontrado,
  `equipe_id = null`, **sem criar equipe**, incrementando `projetos_inativos`; **não** tratar como
  projeto desconhecido. Objetivo: preservar a rastreabilidade da tag e do recurso sem transformá-lo
  numa associação operacional válida.
- **Mock / regiões** (dependência): o Mock deverá **simular `DescribeRegions`** (não usar uma única
  região fictícia hardcoded), reproduzindo a arquitetura real `DescribeRegions → GetResources por
  região → consolidação`. O dataset de E2E idealmente terá recursos em **pelo menos 2 regiões**.
  Implementação em branch/change separada no repositório do AWS Mock.
- **Documentação** (decisão 4): corrigir nesta change, em `docs/domain-model.md`, as descrições da
  convenção atual que ainda usam o formato histórico `PRJ_PAGAMENTOS`/`EQP_BACKEND`, para
  `PRJ=PAGAMENTOS`/`EQP=BACKEND`, deixando claro que `PRJ$...`/`EQP$...` é a representação do Cost
  Explorer (GroupBy), não o formato da tag gravada no recurso.

Nenhuma questão em aberto permanece para esta change.
