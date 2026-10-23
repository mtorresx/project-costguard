# documentacao-api Specification

## Purpose
Define a política de exposição da documentação automática (Swagger/OpenAPI) dos api_groups do
backend Xano do CostGuard: a documentação permanece desabilitada, sem afetar a disponibilidade nem
o contrato dos endpoints.

## Requirements

### Requirement: Documentação Swagger/OpenAPI desabilitada nos api_groups

O sistema SHALL manter a documentação Swagger/OpenAPI gerada automaticamente **desabilitada** em
todos os api_groups do CostGuard (`auth` e `app`). A documentação MUST NOT estar disponível nem de
forma pública nem de forma privada protegida por token. A configuração dos api_groups MUST NOT
depender da ausência da opção de documentação (que resulta em documentação pública por padrão):
a desabilitação SHALL ser declarada explicitamente.

#### Scenario: Documentação do grupo auth indisponível

- **WHEN** alguém tenta acessar a documentação Swagger/OpenAPI do api_group `auth`, com ou sem token
- **THEN** a documentação não está disponível

#### Scenario: Documentação do grupo app indisponível

- **WHEN** alguém tenta acessar a documentação Swagger/OpenAPI do api_group `app`, com ou sem token
- **THEN** a documentação não está disponível

### Requirement: Endpoints permanecem disponíveis e com contrato inalterado

A desabilitação da documentação MUST NOT desabilitar os api_groups nem qualquer endpoint. Os
endpoints dos grupos `auth` e `app` SHALL continuar aceitando requisições externas com as mesmas
rotas, inputs, respostas, autenticação e autorização já especificadas nas demais capabilities.

#### Scenario: Login e /me continuam funcionando

- **WHEN** um usuário ativo envia credenciais válidas a `POST /login` e usa o token em `GET /me`
- **THEN** o login emite o token e `/me` responde com `username` e `role`, como antes da mudança

#### Scenario: Endpoints de negócio continuam funcionando

- **WHEN** um usuário autenticado chama um endpoint de leitura do grupo `app` (ex.: `GET /projetos`)
- **THEN** o backend responde normalmente, e sem token válido continua respondendo HTTP 401

### Requirement: Token de documentação não versionado

O repositório MUST NOT conter token de acesso à documentação Swagger/OpenAPI dos api_groups. Após a
desabilitação, o token anteriormente usado pelo grupo `auth` SHALL deixar de conceder acesso a
qualquer documentação.

#### Scenario: Arquivos de api_group sem token

- **WHEN** os arquivos de definição dos api_groups são inspecionados
- **THEN** nenhum deles contém token de documentação Swagger

#### Scenario: Token antigo sem utilidade

- **WHEN** o token antigo do grupo `auth` é usado para acessar a documentação após a publicação
- **THEN** nenhuma documentação é disponibilizada
