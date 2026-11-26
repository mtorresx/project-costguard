## MODIFIED Requirements

### Requirement: Edição de projeto restrita a admin

O sistema SHALL permitir a edição de projeto apenas a admin, validando a autorização no backend. A edição SHALL preservar a unicidade de `codigo` e a regra de `budget` decimal maior ou igual a zero. Um `budget` igual a zero enviado na edição SHALL ser gravado como zero; um `budget` ausente SHALL manter o valor atual; um `budget` negativo ou não numérico SHALL ser recusado com HTTP 400 sem gravar.

#### Scenario: Admin edita projeto

- **WHEN** um admin edita um projeto existente com dados válidos
- **THEN** o backend aplica as alterações e retorna o projeto atualizado

#### Scenario: Usuário leitura não edita projeto

- **WHEN** um usuário com role leitura tenta editar um projeto
- **THEN** o backend nega a operação com erro de autorização

#### Scenario: Orçamento zerado

- **WHEN** um admin edita um projeto com orçamento 1000 enviando `budget = 0`
- **THEN** o projeto passa a ter `budget = 0`

#### Scenario: Orçamento ausente

- **WHEN** um admin edita apenas o nome de um projeto, sem enviar `budget`
- **THEN** o orçamento atual é mantido

#### Scenario: Orçamento inválido

- **WHEN** um admin envia `budget` negativo ou não numérico
- **THEN** o backend responde HTTP 400 e não grava

### Requirement: Criação de projeto restrita a admin

O sistema SHALL permitir a criação de projeto apenas a usuários autenticados com `role = admin`. A autorização SHALL ser validada no backend. A criação SHALL exigir `nome` e `codigo` não vazios e `budget` decimal maior ou igual a zero; `budget = 0` SHALL ser aceito; `budget` ausente, não numérico ou negativo SHALL ser recusado com HTTP 400 sem gravar.

#### Scenario: Admin cria projeto válido

- **WHEN** um admin envia `nome`, `codigo` e `budget` válidos para um `codigo` inédito
- **THEN** o backend cria o projeto com `status` ativo e o retorna

#### Scenario: Usuário leitura não cria projeto

- **WHEN** um usuário com role leitura tenta criar um projeto
- **THEN** o backend nega a operação com erro de autorização e não cria o projeto

#### Scenario: Campos obrigatórios ausentes

- **WHEN** um admin tenta criar um projeto sem `nome` ou sem `codigo`
- **THEN** o backend rejeita a operação com erro de validação

#### Scenario: Budget inválido

- **WHEN** um admin tenta criar um projeto com `budget` ausente, não numérico ou menor que zero
- **THEN** o backend rejeita a operação com erro de validação

#### Scenario: Orçamento zero na criação

- **WHEN** um admin cria um projeto com `budget = 0`
- **THEN** o projeto é criado com `budget = 0`
