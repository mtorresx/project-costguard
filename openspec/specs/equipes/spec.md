# equipes Specification

## Purpose
Entidade Equipe do CostGuard: um grupo responsável por recursos dentro de um projeto,
identificado pela tag `EQP` (Tag Value = `equipes.codigo`). Define a persistência da equipe, sua
unicidade por projeto (`(projeto_id, codigo)`, pois o mesmo código pode existir em projetos
distintos), a criação automática a partir do inventário (`auto_gerada = true`) e a leitura das
equipes de um projeto. Equipe não possui orçamento. A autorização é validada no backend.

## Requirements

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

### Requirement: Unicidade de equipe por projeto

O sistema SHALL garantir que o `codigo` de equipe seja único **dentro de um projeto**, isto é, a
unicidade lógica é a combinação `(projeto_id, codigo)`. O sistema MUST NOT exigir unicidade global
de `codigo`: o mesmo `codigo` (ex.: `BACKEND`) SHALL poder existir em projetos diferentes.

#### Scenario: Mesmo código em projetos diferentes é permitido

- **WHEN** existe a equipe `BACKEND` no projeto `PAGAMENTOS` e cria-se `BACKEND` no projeto `PORTAL`
- **THEN** ambas coexistem, pois a unicidade é por `(projeto_id, codigo)`

#### Scenario: Código duplicado no mesmo projeto é rejeitado

- **WHEN** já existe a equipe `BACKEND` no projeto `PAGAMENTOS` e tenta-se criar outra `BACKEND` no mesmo projeto
- **THEN** o backend não cria a duplicata, preservando a unicidade `(projeto_id, codigo)`

### Requirement: Criação automática de equipe a partir do inventário

O sistema SHALL criar uma equipe automaticamente quando o inventário encontrar um valor de tag de
equipe (`EQP`) válido, sob um projeto resolvido e ativo, para o qual ainda não exista equipe com
aquele `(projeto_id, codigo)`. A equipe criada automaticamente SHALL ter `codigo = <valor
normalizado trim+upper>`, `nome = codigo`, `projeto_id = <projeto resolvido>` e `auto_gerada =
true`. O sistema MUST NOT inventar orçamento. Equipes criadas automaticamente SHALL ser
distinguíveis das demais pelo indicador `auto_gerada`.

#### Scenario: Equipe nova é criada automaticamente

- **WHEN** o inventário encontra `EQP = BACKEND` sob um projeto ativo e não existe equipe `(projeto, BACKEND)`
- **THEN** o sistema cria a equipe com `nome = BACKEND`, `codigo = BACKEND`, `projeto_id` do projeto e `auto_gerada = true`

#### Scenario: Equipe existente é reutilizada, não duplicada

- **WHEN** o inventário encontra `EQP = BACKEND` e já existe equipe `(projeto, BACKEND)`
- **THEN** o sistema reutiliza a equipe existente e não cria duplicata

### Requirement: Leitura de equipes de um projeto

O sistema SHALL permitir que um usuário autenticado liste as equipes de um projeto. A leitura MUST
NOT exigir role admin. A resposta SHALL incluir, no mínimo, `id`, `nome`, `codigo`, `projeto_id` e
`auto_gerada`.

#### Scenario: Listar equipes de um projeto

- **WHEN** um usuário autenticado solicita as equipes de um projeto existente
- **THEN** o backend responde com as equipes daquele projeto e seus metadados

#### Scenario: Leitura sem autenticação

- **WHEN** uma requisição de leitura de equipes é feita sem token válido
- **THEN** o backend responde com HTTP 401

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
