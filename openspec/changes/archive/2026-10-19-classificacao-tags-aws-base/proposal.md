## Why

Hoje o CostGuard coleta custos AWS reais (DAILY, por SERVICE, em USD) e os persiste
na tabela `custos` vinculados ao provedor de origem, mas **não há relação entre esses
custos e os projetos cadastrados**. Não é possível responder à pergunta central do
produto: "Quanto o projeto X consumiu em determinado dia/período?".

A convenção de domínio (`docs/domain-model.md`): a tag de projeto usa uma **Tag Key**
que identifica a finalidade (Key padrão/recomendada = `PRJ`) e um **Tag Value** que é
diretamente o `codigo` do projeto (ex.: Key `PRJ`, Value `PAGAMENTOS` ↔
`projetos.codigo = PAGAMENTOS`). A Key é configurável por provedor
(`provedores.tag_alocacao_projeto`), permitindo outras convenções (ex.: Key `Project`).
Esta change usa essa convenção para associar os custos AWS aos projetos, aproveitando o
`GroupBy` por tag do AWS Cost Explorer.

## What Changes

- Nova operação administrativa de **coleta de custos por projeto**: consulta o AWS Cost
  Explorer (`GetCostAndUsage`) agrupando por uma **tag de alocação de custo** (`GroupBy`
  com `Type = TAG`), de forma read-only, reaproveitando toda a infraestrutura de SigV4,
  JWE e paginação já validada na coleta base.
- Nova entidade **`custos_projeto`** para persistir o custo por projeto/dia/serviço,
  **sem alterar a semântica da tabela `custos` já validada** (que permanece como custo
  por provedor/dia/serviço).
- O resultado da classificação relaciona o **Tag Value** retornado pela AWS — que é
  diretamente o código do projeto (ex.: `PAGAMENTOS`) — ao `projetos.codigo` correspondente.
- Novo campo no provedor para armazenar a **Key da tag de alocação de custo** usada no
  `GroupBy` (a AWS exige uma Key específica para agrupar por tag; Key recomendada = `PRJ`).
- Tratamento explícito dos casos de borda: Tag Value ausente/vazio (não alocado), Value
  sem projeto correspondente no CostGuard, projeto inativo, e tag de alocação ainda não
  ativada/propagada na conta AWS.
- Registro do estado de cada execução de classificação (sucesso/erro sanitizado, sem
  segredos), de forma não silenciosa.
- **BREAKING**: nenhum. A coleta base `custos`/`coletas_custo` permanece inalterada.

Fora do escopo (explicitamente adiado para changes futuras):

- Equipes e a convenção de tag de equipe (conceitualmente Key `EQP`, Value = código da equipe).
- Alertas, consumo de orçamento (budget x custo) e dashboard.
- Inventário completo de recursos.
- Agendamento automático da coleta/classificação.
- Outros provedores cloud.
- Ativação/desativação automática de cost allocation tags na AWS.
- Criação automática de projetos a partir de tags desconhecidas.

## Capabilities

### New Capabilities

- `classificacao-custos`: coleta e persistência de custos AWS atribuídos a projetos a
  partir da convenção em que a **Tag Key** identifica a finalidade (recomendada `PRJ`) e o
  **Tag Value** é diretamente o `projetos.codigo`, consultando o Cost Explorer agrupado por
  tag, de forma idempotente e read-only, com os casos de borda tratados de modo não
  silencioso. Inclui a entidade `custos_projeto`, a entidade de estado de execução e a
  operação administrativa de classificação.

### Modified Capabilities

- `provedores`: adicionar ao provedor AWS o campo opcional que identifica a **Key da tag
  de alocação de custo** (recomendada `PRJ`) usada no agrupamento do Cost Explorer. Sem esse
  valor, a classificação por projeto não pode ser executada. O segredo da credencial e as
  regras de leitura/escrita existentes permanecem inalterados.
- `projetos`: ajustar o contrato da entidade Projeto para refletir a convenção oficial — o
  `codigo` é o **Tag Value** da tag de alocação (ex.: Key `PRJ`, Value `PAGAMENTOS`), e não
  mais "a parte variável da tag `PRJ_PAGAMENTOS`". Apenas a descrição/contrato muda; a
  estrutura da entidade (`id`, `nome`, `codigo`, `budget`, `status`) permanece.

## Impact

- **Backend Xano**:
  - Nova tabela `custos_projeto` e nova tabela de estado de execução da classificação.
  - Novo campo `tag_alocacao_projeto` (Key recomendada `PRJ`) na tabela `provedores`.
  - Novo endpoint administrativo de classificação (ex.: `POST provedores/{id}/classificar-custos`).
  - Reaproveitamento do fluxo SigV4/JWE/paginação já existente em
    `coletar_custos_provedor_POST.xs`.
- **AWS**: continua read-only. Permissão IAM adicional possível: `ce:ListCostAllocationTags`
  (e/ou `ce:GetTags`) para detecção de tag de alocação ausente/inativa; `ce:GetCostAndUsage`
  já é usada.
- **Frontend Reflex**: nenhuma alteração nesta change (exibição de custo por projeto fica
  para change futura de dashboard/consumo).
- **Documentação**: formaliza a convenção oficial de que a **Tag Key** identifica a
  finalidade (recomendada `PRJ`) e o **Tag Value** é diretamente o `projetos.codigo` (ex.:
  Key `PRJ`, Value `PAGAMENTOS`; Cost Explorer retorna `PRJ$PAGAMENTOS`). Atualiza
  `docs/domain-model.md` e `docs/project-overview.md` e o delta de `projetos` (ver design —
  D1). A Key é configurável por provedor (`provedores.tag_alocacao_projeto`).
