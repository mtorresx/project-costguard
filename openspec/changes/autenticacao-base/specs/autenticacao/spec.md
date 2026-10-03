## Purpose

Estabelece a autenticação base do CostGuard: identificação do usuário por `username` e `password` validada exclusivamente no backend Xano, emissão e validação de token, disponibilização de `username` e `role` do usuário autenticado, e a sessão autenticada mínima no frontend Reflex com proteção da área que exige autenticação.

## ADDED Requirements

### Requirement: Nomenclatura padronizada do contrato de autenticação

O contrato de autenticação SHALL utilizar os nomes `username`, `password` e `role`, de forma consistente entre o frontend Reflex e a API Xano.

O corpo da requisição de login SHALL ter a forma:

```json
{ "username": "...", "password": "..." }
```

A resposta de `/me` SHALL ter a forma (podendo conter campos adicionais como `nome`):

```json
{ "username": "...", "role": "..." }
```

A coluna de identificação do usuário na tabela `usuarios` SHALL ser nomeada `username`, de modo que o nome do campo persistido seja consistente com o contrato.

O campo de senha persistido SHALL ser um campo seguro do tipo `password` do Xano (credencial com hash), nomeado `senha_hash`. O contrato externo usa `password` apenas como chave de input; a coluna permanece credencial protegida e não é exposta.

#### Scenario: Login aceita o contrato padronizado

- **WHEN** um cliente envia o corpo de login com as chaves `username` e `password`
- **THEN** o backend interpreta as credenciais a partir dessas chaves

#### Scenario: /me responde com o contrato padronizado

- **WHEN** o usuário autenticado é consultado via `/me` com token válido
- **THEN** a resposta expõe o identificador do usuário sob a chave `username` e o papel sob a chave `role`

### Requirement: Login por username e password

O sistema SHALL autenticar o usuário a partir de um `username` e um `password`, validando as credenciais exclusivamente no backend Xano. O frontend Reflex SHALL apenas coletar e encaminhar as credenciais; ele MUST NOT ser tratado como mecanismo de segurança nem validar credenciais localmente.

O `password` MUST NOT ser armazenado ou trafegado em texto puro no repositório, no frontend ou em documentação versionada, e MUST NOT ser registrado em logs pelo frontend. A comparação do `password` SHALL ocorrer no backend contra a representação segura (hash) armazenada.

#### Scenario: Credenciais válidas

- **WHEN** o usuário submete um `username` e um `password` corretos correspondentes a um usuário ativo
- **THEN** o backend valida as credenciais e responde com sucesso, incluindo um token de autenticação

#### Scenario: Password incorreto

- **WHEN** o usuário submete um `username` existente com `password` incorreto
- **THEN** o backend responde com erro de autenticação e MUST NOT emitir token
- **AND** a mensagem retornada é genérica e não distingue entre usuário inexistente e password incorreto

#### Scenario: Usuário inexistente

- **WHEN** o usuário submete um `username` que não existe
- **THEN** o backend responde com erro de autenticação equivalente ao de password incorreto, sem revelar se a conta existe

#### Scenario: Usuário inativo

- **WHEN** as credenciais correspondem a um usuário cujo status não é ativo
- **THEN** o backend nega a autenticação e MUST NOT emitir token

### Requirement: Emissão de token de autenticação

Ao autenticar com sucesso, o backend Xano SHALL emitir um token de autenticação que o frontend utilizará para identificar as requisições subsequentes do usuário.

#### Scenario: Token emitido no login bem-sucedido

- **WHEN** o login é bem-sucedido
- **THEN** a resposta do backend contém um token de autenticação utilizável nas requisições autenticadas

### Requirement: Identificação do usuário autenticado

O sistema SHALL fornecer um meio de obter o usuário autenticado a partir do token, retornando ao menos o `username` e o `role` do usuário. Essa identificação SHALL ser resolvida no backend a partir do token apresentado.

#### Scenario: Consulta do usuário autenticado com token válido

- **WHEN** o frontend solicita o usuário autenticado apresentando um token válido
- **THEN** o backend responde com os dados do usuário, incluindo `username` e `role`

#### Scenario: Consulta sem token válido

- **WHEN** o frontend solicita o usuário autenticado sem token ou com token inválido/expirado
- **THEN** o backend responde com HTTP 401 e não retorna dados de usuário

### Requirement: Validação de token e tratamento de 401

O backend SHALL validar o token em todas as requisições autenticadas e SHALL responder com HTTP 401 quando o token estiver ausente, inválido ou expirado. O frontend SHALL tratar respostas HTTP 401 de forma consistente, considerando a sessão como não autenticada.

#### Scenario: Requisição autenticada com token ausente

- **WHEN** uma requisição a um recurso que exige autenticação é feita sem token
- **THEN** o backend responde com HTTP 401

#### Scenario: Requisição autenticada com token inválido ou expirado

- **WHEN** uma requisição a um recurso que exige autenticação é feita com token inválido ou expirado
- **THEN** o backend responde com HTTP 401

#### Scenario: Frontend reage a 401

- **WHEN** o frontend recebe uma resposta HTTP 401 em qualquer requisição autenticada
- **THEN** o frontend descarta a sessão local e trata o usuário como não autenticado

### Requirement: Sessão autenticada no frontend Reflex

O frontend Reflex SHALL manter o estado da sessão autenticada necessário para reutilizar o token nas requisições autenticadas e para disponibilizar o `username` e o `role` do usuário autenticado à interface. O token SHALL ser enviado ao backend nas requisições que exigem autenticação.

A sessão SHALL sobreviver ao recarregamento (reload) da página. A sessão MUST NOT ser exigida sobreviver ao fechamento e reabertura do navegador: ao encerrar a sessão do navegador, a sessão autenticada local pode ser descartada.

#### Scenario: Sessão estabelecida após login

- **WHEN** o login é bem-sucedido e o usuário autenticado é identificado
- **THEN** o frontend passa a disponibilizar `username` e `role` do usuário autenticado
- **AND** as requisições autenticadas subsequentes incluem o token

#### Scenario: Sessão persiste após reload

- **WHEN** o usuário autenticado recarrega a página
- **THEN** a sessão autenticada é mantida e o usuário continua autenticado

#### Scenario: Sessão não exigida após fechar o navegador

- **WHEN** o usuário fecha e reabre o navegador
- **THEN** o sistema pode tratar o usuário como não autenticado, exigindo novo login

#### Scenario: Sem sessão autenticada

- **WHEN** não existe sessão autenticada no frontend
- **THEN** o frontend não disponibiliza `username` nem `role` e não realiza requisições autenticadas em nome de um usuário

### Requirement: Logout local

O frontend SHALL permitir o logout local, descartando a sessão autenticada mantida no cliente de modo que o token deixe de ser utilizado em requisições subsequentes.

#### Scenario: Logout descarta a sessão

- **WHEN** o usuário autenticado realiza logout
- **THEN** o frontend descarta o token e os dados da sessão local
- **AND** o usuário passa a ser tratado como não autenticado

### Requirement: Rotas de login e área autenticada

O frontend SHALL disponibilizar a rota pública `/login` para a página de login e a rota `/` como área autenticada mínima protegida. A rota `/` não representa o dashboard definitivo nesta change.

O frontend SHALL proteger a área autenticada, redirecionando para `/login` qualquer acesso sem sessão autenticada. Essa proteção é de navegação e experiência do usuário e MUST NOT ser considerada um mecanismo de segurança; a autorização real permanece no backend.

#### Scenario: Acesso não autenticado à área autenticada

- **WHEN** um usuário sem sessão autenticada tenta acessar `/`
- **THEN** o frontend redireciona o usuário para `/login`

#### Scenario: Acesso autenticado à área autenticada

- **WHEN** um usuário com sessão autenticada válida acessa `/`
- **THEN** o frontend exibe a área autenticada normalmente

#### Scenario: /login é pública

- **WHEN** um usuário sem sessão autenticada acessa `/login`
- **THEN** o frontend exibe a página de login sem redirecionar

### Requirement: Página mínima de login em Reflex

O frontend SHALL disponibilizar em `/login` uma página de login em Reflex que permita informar `username` e `password`, submeter as credenciais ao backend e indicar falha de autenticação com mensagem genérica, sem revelar se a conta existe.

#### Scenario: Login bem-sucedido pela página

- **WHEN** o usuário informa credenciais válidas na página de login e submete
- **THEN** a sessão autenticada é estabelecida e o usuário é encaminhado para a área autenticada `/`

#### Scenario: Falha de login exibida na página

- **WHEN** o usuário submete credenciais inválidas na página de login
- **THEN** a página exibe uma mensagem de falha de autenticação genérica, sem revelar se o usuário existe
