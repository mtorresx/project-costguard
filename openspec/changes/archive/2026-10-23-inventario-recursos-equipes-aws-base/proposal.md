## Why

Hoje o CostGuard sabe quais projetos existem (via descoberta/importação por tag `PRJ`) e associa
custos a projetos (`classificacao-custos`), mas **não conhece os recursos individuais** nem as
**equipes** donas deles. Sem isso, não é possível responder perguntas de inventário/propriedade:
quantos e quais recursos um projeto tem, qual equipe é dona de cada recurso, quantos recursos
cada equipe possui, e quais recursos do projeto estão "Sem responsável".

Esta change adiciona o **inventário de recursos AWS por tag** e a **entidade Equipe** (com
criação automática a partir da tag `EQP`), resolvendo projeto → equipe → recurso e o estado "Sem
responsável", com persistência e reconciliação. **Não** calcula custo por equipe — isso é escopo
da change futura `custos-equipes-aws-base` (1 change funcional = 1 branch).

## What Changes

- Nova entidade **`equipes`**: `id`, `nome`, `codigo`, `projeto_id`, `auto_gerada` (+ `status` só
  se justificado). Unicidade lógica **`(projeto_id, codigo)`** — o mesmo `codigo` pode existir em
  projetos diferentes. Equipe não tem orçamento.
- Nova entidade **`recursos`**: inventário por provedor, com ARN, região, serviço/tipo,
  `projeto_id` e `equipe_id` (ambos nullable), os valores de tag crus de projeto/equipe,
  rastreio de presença no último inventário (`ultima_vista_em`/`sync_id`) e `ativo`.
- Nova operação administrativa **`POST /provedores/{id}/sincronizar-recursos`**: consulta o
  inventário AWS (Resource Groups Tagging API `GetResources`, filtrando por Tag Key de projeto),
  resolve projeto e equipe por recurso, cria equipes automaticamente quando necessário, faz
  upsert dos recursos e **reconcilia** (desativa os que sumiram) apenas após sincronização
  completa e bem-sucedida.
- Novo campo opcional no provedor para a **Tag Key de equipe** (`tag_alocacao_equipe`, recomendada
  `EQP`), análogo ao `tag_alocacao_projeto` já existente (configurável, não hardcoded).
- Estratégia regional explícita (ver design): MVP consulta **as regiões habilitadas da conta**
  (enumeradas via EC2 `DescribeRegions`), pois `GetResources` é regional.
- Estado "Sem responsável" como estado **real** do recurso (`equipe_id = null`), nunca uma equipe
  fictícia `SEM_RESPONSAVEL`.
- Endpoints read-only de leitura do inventário (`GET /projetos/{id}/recursos`,
  `GET /projetos/{id}/equipes`) incluídos nesta capability (backend only) para habilitar o
  consumo futuro, sem frontend.
- **BREAKING**: nenhum. Não altera classificação, coleta, Mock, auth nem os schemas existentes
  (apenas adiciona um campo opcional ao provedor e duas tabelas novas).

Fora do escopo (próximas changes): custo por equipe / Cost Explorer PRJ+EQP, percentual de
orçamento, dashboard, telas de recurso/equipe/detalhe de projeto, alertas, recursos totalmente
sem tag (Resource Explorer `tag:none`), custo por recurso, rateio de recurso entre equipes,
edição manual de projeto/equipe do recurso. Também fora: alterar o AWS Mock (dependência externa
registrada no design).

## Capabilities

### New Capabilities

- `equipes`: entidade Equipe pertencente a um projeto, com unicidade `(projeto_id, codigo)`,
  criação automática (`auto_gerada = true`) a partir da tag `EQP` durante o inventário, sem
  orçamento. Operações de leitura (por projeto) e a semântica de equipe gerada automaticamente.
- `inventario-recursos`: inventário de recursos AWS por tag (Resource Groups Tagging API
  `GetResources`, por região habilitada, paginado), resolução projeto→equipe por recurso, estado
  "Sem responsável", upsert e reconciliação (desativa recursos ausentes só após sync completa),
  admin-only, read-only na AWS, segredos nunca expostos; inclui a entidade `recursos`, o endpoint
  de sincronização e os endpoints read-only de leitura do inventário.

### Modified Capabilities

- `provedores`: adicionar o campo opcional `tag_alocacao_equipe` (Tag Key de equipe, recomendada
  `EQP`) à entidade e aos fluxos de criação/edição/leitura, análogo a `tag_alocacao_projeto`. Sem
  esse valor, o inventário resolve apenas projeto e trata todos os recursos como "Sem
  responsável". Segredo nunca exposto; demais regras inalteradas.

## Impact

- **Backend Xano**:
  - Tabelas novas `equipes` e `recursos`.
  - Campo `tag_alocacao_equipe` em `provedores`; `criar/editar/listar/detalhe` passam a aceitá-lo/
    retorná-lo.
  - Endpoint `POST /provedores/{id}/sincronizar-recursos` (admin), reaproveitando JWE/SigV4/
    paginação já consolidados, agora contra `tagging.{region}.amazonaws.com`.
  - Endpoints read-only `GET /projetos/{id}/recursos` e `GET /projetos/{id}/equipes`.
- **AWS**: read-only. Novas permissões IAM: `tag:GetResources` e `ec2:DescribeRegions` (ver
  design). Nenhuma escrita.
- **AWS Mock**: **dependência externa** — o Mock atual não simula a Tagging API nem a enumeração
  de regiões; o E2E do inventário fica bloqueado até evolução do Mock (contrato especificado no
  design). Não alterado nesta branch.
- **Frontend/classificação/coleta/custos**: nenhuma alteração.
