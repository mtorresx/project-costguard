## MODIFIED Requirements

### Requirement: Identificação do usuário autenticado

O sistema SHALL fornecer um meio de obter o usuário autenticado a partir do token, retornando ao menos o `username` e o `role` do usuário. Essa identificação SHALL ser resolvida no backend a partir do token apresentado. Quando o usuário do token não existir ou estiver com `status = inativo`, o backend SHALL responder HTTP 401 e MUST NOT retornar dados de usuário.

#### Scenario: Consulta do usuário autenticado com token válido

- **WHEN** o frontend solicita o usuário autenticado apresentando um token válido de um usuário ativo
- **THEN** o backend responde com os dados do usuário, incluindo `username` e `role`

#### Scenario: Consulta sem token válido

- **WHEN** o frontend solicita o usuário autenticado sem token ou com token inválido/expirado
- **THEN** o backend responde com HTTP 401 e não retorna dados de usuário

#### Scenario: Usuário desativado após o login

- **WHEN** o frontend solicita o usuário autenticado com um token válido de um usuário que foi desativado
- **THEN** o backend responde com HTTP 401 e o frontend encerra a sessão

## ADDED Requirements

### Requirement: Usuário desativado não executa escritas

Todo endpoint de escrita do api_group `app` SHALL exigir que o usuário do token esteja com `status = ativo`, além de `role = admin`, respondendo HTTP 403 caso contrário, mesmo que o token ainda não tenha expirado.

#### Scenario: Admin desativado com token anterior

- **WHEN** um admin desativado usa um token emitido antes da desativação para criar um projeto
- **THEN** o backend responde HTTP 403 e não grava
