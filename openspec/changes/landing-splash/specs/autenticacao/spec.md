## MODIFIED Requirements

### Requirement: Rotas de login e área autenticada

O frontend SHALL disponibilizar as rotas públicas `/` (landing page) e `/login` (página de login) e a rota `/inicio` como painel autenticado protegido, além das demais páginas autenticadas.

O frontend SHALL proteger a área autenticada, redirecionando para `/login` qualquer acesso sem sessão autenticada. Essa proteção é de navegação e experiência do usuário e MUST NOT ser considerada um mecanismo de segurança; a autorização real permanece no backend.

#### Scenario: Acesso não autenticado à área autenticada

- **WHEN** um usuário sem sessão autenticada tenta acessar `/inicio`
- **THEN** o frontend redireciona o usuário para `/login`

#### Scenario: Acesso autenticado à área autenticada

- **WHEN** um usuário com sessão autenticada válida acessa `/inicio`
- **THEN** o frontend exibe o painel normalmente

#### Scenario: /login é pública

- **WHEN** um usuário sem sessão autenticada acessa `/login`
- **THEN** o frontend exibe a página de login sem redirecionar

### Requirement: Página mínima de login em Reflex

O frontend SHALL disponibilizar em `/login` uma página de login em Reflex que permita informar `username` e `password`, submeter as credenciais ao backend e indicar falha de autenticação com mensagem genérica, sem revelar se a conta existe. A página SHALL oferecer um link de volta para a landing (`/`).

#### Scenario: Login bem-sucedido pela página

- **WHEN** o usuário informa credenciais válidas na página de login e submete
- **THEN** a sessão autenticada é estabelecida e o usuário é encaminhado ao painel `/inicio` pela animação de entrada

#### Scenario: Falha de login exibida na página

- **WHEN** o usuário submete credenciais inválidas na página de login
- **THEN** a página exibe uma mensagem de falha de autenticação genérica, sem revelar se o usuário existe
