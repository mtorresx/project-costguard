## Purpose

Gestão base de Projetos do CostGuard: a entidade `projetos` e suas operações de leitura (qualquer usuário autenticado) e de escrita (restritas a admin), com autenticação e autorização validadas no backend Xano, e a página `/projetos` em Reflex consumindo esses dados reais.

## ADDED Requirements

### Requirement: Entidade Projeto

O sistema SHALL persistir projetos com os campos: `id`, `nome`, `codigo`, `budget` e `status`. O `codigo` SHALL representar apenas a parte variável da tag de projeto (ex.: tag `PRJ_PAGAMENTOS` → `codigo` = `PAGAMENTOS`). O `budget` SHALL representar o orçamento mensal em USD, aceitando valor decimal maior ou igual a zero. O `status` SHALL distinguir projeto `ativo` de `inativo`.

#### Scenario: Projeto persistido com os campos do contrato

- **WHEN** um projeto é criado com sucesso
- **THEN** ele passa a existir com `id`, `nome`, `codigo`, `budget` e `status`

### Requirement: Código de projeto único

O sistema SHALL impedir a existência de dois projetos com o mesmo `codigo`. A unicidade SHALL ser garantida no backend.

#### Scenario: Código duplicado é rejeitado

- **WHEN** um admin tenta criar um projeto com um `codigo` que já existe
- **THEN** o backend rejeita a operação com erro de validação e não cria o projeto

### Requirement: Leitura de projetos por usuário autenticado

O sistema SHALL permitir que qualquer usuário autenticado liste os projetos e consulte o detalhe de um projeto. A leitura MUST NOT exigir role admin.

#### Scenario: Listar projetos autenticado

- **WHEN** um usuário autenticado (admin ou leitura) solicita a lista de projetos
- **THEN** o backend responde com os projetos existentes

#### Scenario: Detalhe de projeto autenticado

- **WHEN** um usuário autenticado solicita o detalhe de um projeto existente
- **THEN** o backend responde com os dados do projeto

#### Scenario: Detalhe de projeto inexistente

- **WHEN** um usuário autenticado solicita o detalhe de um `id` que não existe
- **THEN** o backend responde com erro de recurso não encontrado

#### Scenario: Leitura sem autenticação

- **WHEN** uma requisição de leitura de projetos é feita sem token válido
- **THEN** o backend responde com HTTP 401

### Requirement: Criação de projeto restrita a admin

O sistema SHALL permitir a criação de projeto apenas a usuários autenticados com `role = admin`. A autorização SHALL ser validada no backend. A criação SHALL exigir `nome` e `codigo` não vazios e `budget` decimal maior ou igual a zero.

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

- **WHEN** um admin tenta criar um projeto com `budget` ausente ou menor que zero
- **THEN** o backend rejeita a operação com erro de validação

### Requirement: Edição de projeto restrita a admin

O sistema SHALL permitir a edição de projeto apenas a admin, validando a autorização no backend. A edição SHALL preservar a unicidade de `codigo` e a regra de `budget` decimal maior ou igual a zero.

#### Scenario: Admin edita projeto

- **WHEN** um admin edita um projeto existente com dados válidos
- **THEN** o backend aplica as alterações e retorna o projeto atualizado

#### Scenario: Usuário leitura não edita projeto

- **WHEN** um usuário com role leitura tenta editar um projeto
- **THEN** o backend nega a operação com erro de autorização

### Requirement: Desativação de projeto restrita a admin

O sistema SHALL permitir desativar um projeto apenas a admin, alterando seu `status` para `inativo`. O sistema MUST NOT excluir fisicamente o projeto nesta operação.

#### Scenario: Admin desativa projeto

- **WHEN** um admin desativa um projeto ativo
- **THEN** o `status` do projeto passa a `inativo` e o registro continua existindo

#### Scenario: Usuário leitura não desativa projeto

- **WHEN** um usuário com role leitura tenta desativar um projeto
- **THEN** o backend nega a operação com erro de autorização

### Requirement: Página /projetos com dados reais

O frontend SHALL exibir em `/projetos` os projetos reais obtidos do backend, substituindo os dados mock. As requisições SHALL incluir o token da sessão e reagir a HTTP 401 conforme o tratamento central já existente (limpando a sessão e redirecionando ao login). O design incorporado SHALL ser preservado.

#### Scenario: Lista real exibida

- **WHEN** um usuário autenticado acessa `/projetos`
- **THEN** a página exibe os projetos obtidos do backend, sem dados mock

#### Scenario: Admin vê controles de escrita

- **WHEN** um admin acessa `/projetos`
- **THEN** a página oferece ações de criar, editar e desativar projeto

#### Scenario: Usuário leitura sem controles de escrita

- **WHEN** um usuário com role leitura acessa `/projetos`
- **THEN** a página exibe os projetos sem os controles de criar, editar ou desativar
- **AND** essa ocultação é apenas UX; a autorização real permanece no backend

#### Scenario: 401 na página de projetos

- **WHEN** uma requisição de `/projetos` recebe HTTP 401
- **THEN** o frontend limpa a sessão e redireciona ao login, conforme o tratamento existente
