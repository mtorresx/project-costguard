## MODIFIED Requirements

### Requirement: Entidade Equipe

O sistema SHALL persistir equipes com, no mínimo: `id`, `nome`, `codigo`, `projeto_id` (referência
ao projeto dono) e `auto_gerada` (booleano que indica se a equipe foi criada automaticamente a
partir de uma tag de equipe, seja pelo inventário de recursos ou pela classificação de custos por
equipe). O `codigo` SHALL representar o Tag Value da tag de equipe (ex.: Tag Key `EQP`, Value
`BACKEND` → `codigo = BACKEND`), normalizado em `trim`+maiúsculas. Uma equipe SHALL pertencer a
exatamente um projeto. A entidade Equipe MUST NOT possuir orçamento (não há `budget` de equipe).

#### Scenario: Equipe persistida com os campos do contrato

- **WHEN** uma equipe é criada com sucesso
- **THEN** ela passa a existir com `id`, `nome`, `codigo`, `projeto_id` e `auto_gerada`

#### Scenario: Equipe não tem orçamento

- **WHEN** uma equipe é criada
- **THEN** nenhum orçamento é atribuído a ela (o orçamento pertence apenas ao projeto)

## ADDED Requirements

### Requirement: Criação automática de equipe pela classificação de custos por equipe

O sistema SHALL criar uma equipe automaticamente quando a classificação de custos por equipe
encontrar um valor de tag de equipe não vazio, sob um projeto resolvido e ativo, para o qual ainda
não exista equipe com aquele `(projeto_id, codigo)`. A equipe criada SHALL ter `codigo = <valor
normalizado trim+upper>`, `nome = codigo`, `projeto_id = <projeto resolvido>` e
`auto_gerada = true`, com as mesmas regras da criação a partir do inventário. Quando a equipe já
existir, SHALL ser reutilizada, sem duplicata. O sistema MUST NOT criar equipe para projeto
inexistente ou inativo, MUST NOT criar equipe para valor de equipe vazio ("Sem responsável") e
MUST NOT atribuir orçamento à equipe.

#### Scenario: Equipe criada pela classificação de custos

- **WHEN** a classificação de custos por equipe encontra `EQP = SRE` sob o projeto ativo `PAGAMENTOS` e não existe equipe `(PAGAMENTOS, SRE)`
- **THEN** o sistema cria a equipe com `nome = SRE`, `codigo = SRE`, `projeto_id` de `PAGAMENTOS` e `auto_gerada = true`

#### Scenario: Equipe existente reutilizada pela classificação

- **WHEN** a classificação de custos por equipe encontra `EQP = BACKEND` e já existe equipe `(PAGAMENTOS, BACKEND)`, criada pelo inventário ou manualmente
- **THEN** o sistema reutiliza a equipe existente e não cria duplicata

#### Scenario: Sem equipe para projeto inativo ou sem responsável

- **WHEN** a classificação de custos por equipe encontra um valor de equipe sob um projeto inativo, ou um valor de equipe vazio sob projeto ativo
- **THEN** nenhuma equipe é criada
