## Why

Hoje o CostGuard coleta custos AWS reais (DAILY, por SERVICE, em USD) e os persiste
na tabela `custos` vinculados ao provedor de origem, mas **não há relação entre esses
custos e os projetos cadastrados**. Não é possível responder à pergunta central do
produto: "Quanto o projeto X consumiu em determinado dia/período?".

A convenção de domínio já existe (`docs/domain-model.md`): a tag de projeto usa o
prefixo `PRJ_` e o `codigo` do projeto é a parte variável (ex.: tag `PRJ_PAGAMENTOS`
→ `projetos.codigo = PAGAMENTOS`). Esta change usa essa convenção para associar os
custos AWS aos projetos, aproveitando o `GroupBy` por tag do AWS Cost Explorer.

## What Changes

- Nova operação administrativa de **coleta de custos por projeto**: consulta o AWS Cost
  Explorer (`GetCostAndUsage`) agrupando por uma **tag de alocação de custo** (`GroupBy`
  com `Type = TAG`), de forma read-only, reaproveitando toda a infraestrutura de SigV4,
  JWE e paginação já validada na coleta base.
- Nova entidade **`custos_projeto`** para persistir o custo por projeto/dia/serviço,
  **sem alterar a semântica da tabela `custos` já validada** (que permanece como custo
  por provedor/dia/serviço).
- O resultado da classificação relaciona o **tag value** retornado pela AWS (ex.:
  `PRJ_PAGAMENTOS`) ao `projetos.codigo` correspondente (ex.: `PAGAMENTOS`).
- Novo campo no provedor para armazenar a **Key da tag de alocação de custo** usada no
  `GroupBy` (a AWS exige uma Key específica para agrupar por tag).
- Tratamento explícito dos casos de borda: custo sem tag `PRJ_` (não alocado), tag
  `PRJ_` sem projeto correspondente no CostGuard, projeto inativo, e tag de alocação
  ainda não ativada/propagada na conta AWS.
- Registro do estado de cada execução de classificação (sucesso/erro sanitizado, sem
  segredos), de forma não silenciosa.
- **BREAKING**: nenhum. A coleta base `custos`/`coletas_custo` permanece inalterada.

Fora do escopo (explicitamente adiado para changes futuras):

- Equipes e a convenção `EQP_`.
- Alertas, consumo de orçamento (budget x custo) e dashboard.
- Inventário completo de recursos.
- Agendamento automático da coleta/classificação.
- Outros provedores cloud.
- Ativação/desativação automática de cost allocation tags na AWS.
- Criação automática de projetos a partir de tags desconhecidas.

## Capabilities

### New Capabilities

- `classificacao-custos`: coleta e persistência de custos AWS atribuídos a projetos a
  partir da convenção de tag `PRJ_<codigo>`, consultando o Cost Explorer agrupado por
  tag, de forma idempotente e read-only, com os casos de borda tratados de modo não
  silencioso. Inclui a entidade `custos_projeto`, a entidade de estado de execução e a
  operação administrativa de classificação.

### Modified Capabilities

- `provedores`: adicionar ao provedor AWS o campo opcional que identifica a **Key da tag
  de alocação de custo** (ex.: `Projeto`) usada no agrupamento do Cost Explorer. Sem esse
  valor, a classificação por projeto não pode ser executada. O segredo da credencial e as
  regras de leitura/escrita existentes permanecem inalterados.

## Impact

- **Backend Xano**:
  - Nova tabela `custos_projeto` e nova tabela de estado de execução da classificação.
  - Novo campo (ex.: `tag_alocacao_projeto`) na tabela `provedores`.
  - Novo endpoint administrativo de classificação (ex.: `POST provedores/{id}/classificar-custos`).
  - Reaproveitamento do fluxo SigV4/JWE/paginação já existente em
    `coletar_custos_provedor_POST.xs`.
- **AWS**: continua read-only. Permissão IAM adicional possível: `ce:ListCostAllocationTags`
  (e/ou `ce:GetTags`) para detecção de tag de alocação ausente/inativa; `ce:GetCostAndUsage`
  já é usada.
- **Frontend Reflex**: nenhuma alteração nesta change (exibição de custo por projeto fica
  para change futura de dashboard/consumo).
- **Documentação**: formaliza a decisão (confirmada) de que `PRJ_<codigo>` é um tag **value**
  (ex.: `PRJ_PAGAMENTOS`) sob uma Key de alocação padronizada por provedor
  (`provedores.tag_alocacao_projeto`, ex.: `Projeto`), usada como Tag Key no `GroupBy` do
  Cost Explorer (ver design — D1).
