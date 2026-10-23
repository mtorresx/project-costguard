## Why

Hoje o CostGuard atribui custos AWS a projetos (`classificacao-custos`, tabela `custos_projeto`)
e conhece o inventário atual de recursos e equipes (`inventario-recursos`, `equipes`), mas **não
consegue responder "quanto cada equipe de um projeto consumiu na AWS?"**.

O inventário não serve para isso: ele representa a atribuição **atual** de cada recurso, e um
recurso que hoje pertence a `BACKEND` pode ter pertencido a outra equipe no passado. Usar o
inventário atual para atribuir custo histórico reescreveria o passado. A fonte correta é a
dimensão de tag que o próprio AWS Cost Explorer associa a cada custo no período consultado.

Exemplo conceitual do resultado esperado:

```text
Projeto PAGAMENTOS
  BACKEND           US$ 300
  QA                US$ 120
  DEVOPS            US$  80
  Sem responsável   US$  25
  Total do projeto  US$ 525
```

## What Changes

- Nova operação administrativa **`POST /provedores/{id}/classificar-custos-equipe`**: consulta o
  AWS Cost Explorer (`GetCostAndUsage`, `DAILY`, `UnblendedCost`) agrupando por **duas tags**, a
  Tag Key de projeto (`tag_alocacao_projeto`, obrigatória) e a Tag Key de equipe
  (`tag_alocacao_equipe`, com fallback `EQP` quando nula/vazia), sem a dimensão `SERVICE`.
  Reaproveita o fluxo existente de JWE, SigV4, destino real/Mock e paginação.
- Resolução **projeto → equipe** por dia: projeto desconhecido ou inativo não recebe custo;
  projeto ativo sem equipe gera **"Sem responsável"** (`equipe_id = null`, `codigo_equipe = ""`),
  sem equipe fictícia; equipe desconhecida em projeto ativo é criada ou reutilizada por
  `(projeto_id, codigo)` com `auto_gerada = true`.
- Nova entidade **`custos_equipe`** (custo diário por provedor/projeto/equipe), com chave única
  `(provedor_id, projeto_id, codigo_equipe, data, metrica)` e identificador privado de execução
  `sync_id`.
- Nova entidade **`coletas_custos_equipe`** (estado de cada execução, contadores dos casos de
  borda e aviso não bloqueante).
- **Reconciliação da janela por `sync_id`**: só depois de todas as páginas obtidas, todos os dados
  normalizados/agregados e todos os upserts concluídos, remove as linhas antigas da janela
  consultada (mesmo provedor, projetos atualmente ativos) que não foram vistas na execução atual.
  Projetos atualmente inativos não têm histórico apagado.
- **Aviso não bloqueante** quando nenhuma alocação de equipe aparece na janela, orientando a
  conferir se a Tag Key de equipe está ativada como Cost Allocation Tag na AWS.
- Novo endpoint de leitura **`GET /projetos/{id}/custos-equipe?data_inicio&data_fim`**: total por
  equipe, total "Sem responsável" e total do projeto, agregados entre provedores e no intervalo.
- Ajuste em `docs/domain-model.md` (durante o Apply) para distinguir a atribuição **atual**
  (inventário) da atribuição **histórica** de custo (Cost Explorer).
- **BREAKING**: nenhum. Não altera `custos`, `custos_projeto`, `recursos`, os endpoints existentes
  nem o AWS Mock.

Fora do escopo (changes futuras):

- frontend Reflex;
- custo por serviço dentro da equipe (`SERVICE` por equipe);
- custo por recurso (`GetCostAndUsageWithResources`);
- orçamento, dashboard e alertas;
- agendamento automático;
- `ce:ListCostAllocationTags` ou qualquer nova permissão IAM;
- alterações no AWS Mock;
- trava contra execução concorrente;
- série diária e filtro por provedor no endpoint de leitura;
- correção dos bugs latentes já identificados na classificação por projeto (registrados como
  follow-up no design).

## Capabilities

### New Capabilities

- `custos-equipe`: coleta e persistência do custo AWS diário por provedor/projeto/equipe a partir
  das Tag Keys de projeto e de equipe do provedor, consultando o Cost Explorer agrupado por duas
  tags, com o estado "Sem responsável", tratamento não silencioso dos casos de borda, upsert
  idempotente, reconciliação da janela por `sync_id`, registro de cada execução e endpoint de
  leitura agregado por projeto.

### Modified Capabilities

- `equipes`: a criação automática de equipe (`auto_gerada = true`) passa a ocorrer também pela
  classificação de custos por equipe, e não apenas pelo inventário. A unicidade
  `(projeto_id, codigo)` e a ausência de orçamento permanecem.

## Impact

- **Backend Xano**:
  - Tabelas novas `custos_equipe` e `coletas_custos_equipe`.
  - Endpoints novos `POST /provedores/{id}/classificar-custos-equipe` (admin) e
    `GET /projetos/{id}/custos-equipe` (autenticado).
  - Sem alteração de schema em `provedores`, `projetos`, `equipes`, `recursos`, `custos`,
    `custos_projeto`.
- **AWS**: read-only; usa apenas `ce:GetCostAndUsage`, já exigida. Pré-condição operacional na
  AWS real: as Tag Keys de projeto **e de equipe** precisam estar ativadas como Cost Allocation
  Tags.
- **AWS Mock**: nenhuma alteração. O Mock atual já suporta `GroupBy [TAG PRJ, TAG EQP]` e será
  usado no E2E.
- **Frontend**: nenhuma alteração.
- **Documentação**: `docs/domain-model.md` (seções de Equipe/Recurso/Registro de Custo), ajustado
  durante o Apply.
