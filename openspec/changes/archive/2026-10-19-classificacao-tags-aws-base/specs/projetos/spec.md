## MODIFIED Requirements

### Requirement: Entidade Projeto

O sistema SHALL persistir projetos com os campos: `id`, `nome`, `codigo`, `budget` e `status`. O `codigo` SHALL representar o **Tag Value** da tag de alocação de custo do projeto, isto é, diretamente o valor comparado com a tag AWS (ex.: Tag Key `PRJ`, Tag Value `PAGAMENTOS` → `codigo` = `PAGAMENTOS`). A Tag Key que identifica a finalidade da tag é configurada por provedor (`provedores.tag_alocacao_projeto`, Key recomendada `PRJ`) e NÃO faz parte do `codigo`. O `budget` SHALL representar o orçamento mensal em USD, aceitando valor decimal maior ou igual a zero. O `status` SHALL distinguir projeto `ativo` de `inativo`.

#### Scenario: Projeto persistido com os campos do contrato

- **WHEN** um projeto é criado com sucesso
- **THEN** ele passa a existir com `id`, `nome`, `codigo`, `budget` e `status`

#### Scenario: Código corresponde ao Tag Value da tag de alocação

- **WHEN** um projeto tem `codigo = PAGAMENTOS` e o provedor tem `tag_alocacao_projeto = PRJ`
- **THEN** a tag AWS esperada é `PRJ = PAGAMENTOS` (Cost Explorer retorna `PRJ$PAGAMENTOS`), e o `codigo` é diretamente o Tag Value, sem qualquer prefixo embutido
