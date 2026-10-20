## Why

Hoje a classificação de custos (`classificacao-custos`) associa custos a projetos apenas quando
o projeto já existe no CostGuard (match por `projetos.codigo`), e **não cria projetos
automaticamente**. No E2E isso revelou um atrito de UX: um provedor AWS pode ter várias tags
`PRJ` válidas (ex.: `PRJ$PAGAMENTOS`, `PRJ$MARKETING`, `PRJ$INFRAESTRUTURA`), mas o admin precisa
cadastrar manualmente cada projeto antes que a classificação consiga associá-lo — sem uma forma
de descobrir quais valores de tag existem naquele provedor.

Esta change adiciona uma etapa de **descoberta** dos valores da Tag Key do provedor e uma
operação **explícita de importação** dos que ainda não existem, reaproveitando o routing AWS
real/Mock, o SigV4 e o `GetTags` já consolidados — sem criar projetos silenciosamente.

## What Changes

- Nova operação administrativa de **descoberta** de projetos a partir das tags do provedor:
  consulta o Cost Explorer (`GetTags`) para a Tag Key `provedores.tag_alocacao_projeto`,
  extrai os valores distintos (ignorando valor vazio), e os compara com `projetos.codigo`
  existentes, retornando para cada valor se já existe projeto e qual é. **Não grava nada.**
- Nova operação administrativa de **importação** explícita: recebe uma lista de códigos
  selecionados e cria os projetos **inexistentes** com `nome = codigo`, `codigo = <valor
  normalizado trim+upper>`, `budget = 0`, `status = ativo`. Não cria duplicados nem reativa
  projetos existentes. É a única que grava. **Não reconsulta a AWS** — trabalha apenas com a
  lista enviada pelo admin (normaliza `trim+upper`, remove vazios, deduplica).
- Reaproveitamento do mecanismo já consolidado: routing real/Mock por `usar_mock`, `MOCK_BASE_URL`
  só no backend, SigV4 coerente ao destino, `GetTags` com a Tag Key do provedor, e a convenção
  oficial (Tag Key = finalidade, Tag Value = `projetos.codigo`).
- Tratamento de paginação de `GetTags` (se houver), ignorar valor vazio, normalização
  `trim+upper`, admin-only, autenticação no backend, segredos nunca expostos.
- **BREAKING**: nenhum. A classificação (`classificacao-custos`), a coleta (`custos`) e o Mock
  (`integracao-mock`) permanecem inalterados.

Fora do escopo:

- Alterar a classificação de custos existente (continua sem criar projetos automaticamente).
- Alterar o AWS Mock Simulator.
- Equipes (`EQP`), alertas, dashboard, budget consumption.
- Criação automática/silenciosa de projetos na descoberta (a criação é só na importação explícita).
- Edição de orçamento na importação (budget nasce 0; o admin ajusta depois pelo CRUD existente).
- Frontend Reflex (fica para uma change de UI posterior; esta é backend-only).

## Capabilities

### New Capabilities

- `descoberta-projetos`: descoberta read-only dos valores da Tag Key de um provedor AWS
  (real ou Mock) via `GetTags`, comparação com `projetos.codigo` existentes, e importação
  explícita (admin-only) que cria apenas os projetos inexistentes a partir dos códigos
  selecionados, sem duplicar, com normalização `trim+upper` e valor vazio ignorado. Inclui os
  dois endpoints administrativos e as regras de isolamento/segurança reaproveitadas.

### Modified Capabilities

(nenhuma — a descoberta não altera o contrato de `projetos`, `provedores`, `custos`,
`classificacao-custos` nem `integracao-mock`; apenas os consome.)

## Impact

- **Backend Xano**:
  - Novo endpoint `POST provedores/{id}/descobrir-projetos` (admin, read-only).
  - Novo endpoint `POST provedores/{id}/importar-projetos` (admin, grava projetos inexistentes).
  - Reuso do padrão `GetTags` + routing real/Mock + SigV4 (como em `testar-conexao` Mock e
    `classificar-custos`). Nenhuma tabela nova.
  - Criação de projetos reutiliza a entidade `projetos` e sua regra de `codigo` único.
- **AWS/Mock**: continua read-only (`ce:GetTags`); Mock inalterado.
- **Frontend Reflex**: nenhuma alteração nesta change.
- **Segurança**: admin-only, segredos nunca expostos, `MOCK_BASE_URL` só no backend,
  `usar_mock` define o destino.
