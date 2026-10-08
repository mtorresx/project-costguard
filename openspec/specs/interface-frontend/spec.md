# interface-frontend

## Purpose

Define a interface visual do CostGuard em Reflex: tema, assets e componentes reutilizáveis incorporados do frontend externo, as páginas de apresentação (landing, alertas, projetos, provedores, usuários) e o design do login aplicado ao login funcional existente — preservando integralmente a autenticação do projeto principal.

## Requirements

### Requirement: Tema visual único incorporado

O frontend SHALL adotar o tema visual incorporado (tokens de cor, tipografia e aparência) de forma consistente entre as páginas. O tema SHALL residir no pacote `projetoImpacta` e MUST NOT depender do pacote externo `costguard`.

#### Scenario: Páginas usam o tema incorporado

- **WHEN** qualquer página da interface é renderizada
- **THEN** ela aplica os tokens do tema incorporado (cores, tipografia, aparência) de forma consistente

#### Scenario: Assets visuais disponíveis

- **WHEN** uma página referencia os assets incorporados (CSS, logotipo, vídeo)
- **THEN** os assets são servidos a partir do projeto principal, sem depender do repositório externo

### Requirement: Componentes reutilizáveis incorporados

O frontend SHALL disponibilizar os componentes reutilizáveis incorporados (ex.: layout, elementos de tabela e indicadores visuais) sob o pacote `projetoImpacta`, com todos os imports adaptados de `costguard` para `projetoImpacta`.

#### Scenario: Componente reutilizado por páginas

- **WHEN** uma página usa um componente reutilizável incorporado
- **THEN** o componente renderiza sem erro e sem referência a imports do pacote `costguard`

### Requirement: Páginas de apresentação registradas

O frontend SHALL registrar as páginas visuais incorporadas — landing, alertas, projetos, provedores e usuários — em rotas acessíveis. Páginas cujo backend ainda não existe SHALL ser apresentadas como visual/mock, sem inventar integração de backend.

#### Scenario: Página de apresentação acessível

- **WHEN** o usuário navega para uma das rotas das páginas incorporadas
- **THEN** a página é exibida com seu design, usando dados de apresentação/mock quando não há backend correspondente

#### Scenario: Páginas mock não chamam backend inexistente

- **WHEN** uma página incorporada não possui backend correspondente nesta etapa do projeto
- **THEN** a página permanece como apresentação visual e MUST NOT depender de endpoints inexistentes para renderizar

### Requirement: Design do login aplicado ao login funcional existente

O frontend SHALL aplicar o design visual de login incorporado sobre o fluxo de login funcional já existente, sem substituir a autenticação. O envio de credenciais SHALL continuar usando o contrato atual (`{username, password}`) e o `AuthState` atual; o visual externo baseado no contrato antigo (`usuario`/`senha`) ou em estado de login próprio MUST NOT substituir o fluxo existente.

#### Scenario: Login mantém contrato e fluxo atuais

- **WHEN** o usuário submete o formulário de login redesenhado
- **THEN** as credenciais são enviadas como `{username, password}` ao backend pelo fluxo de autenticação existente, e a sessão resultante usa o `AuthState` atual

#### Scenario: Falha de login exibida com o novo visual

- **WHEN** o login falha
- **THEN** a página exibe a mensagem de falha genérica no visual incorporado, sem revelar se a conta existe

### Requirement: Preservação da autenticação existente

A incorporação do frontend MUST NOT alterar o comportamento de autenticação já especificado e validado: `AuthState`, persistência em `rx.SessionStorage`, rota pública `/login`, validação via `/me`, logout local e tratamento centralizado de HTTP 401 SHALL permanecer conforme a capability `autenticacao`.

#### Scenario: Proteção de rota preservada

- **WHEN** um usuário sem sessão autenticada acessa uma rota que exige autenticação
- **THEN** o comportamento de redirecionamento para `/login` e a validação de sessão permanecem conforme a autenticação existente

#### Scenario: Sessão, logout e 401 inalterados

- **WHEN** ocorrem login, reload, logout ou uma resposta HTTP 401
- **THEN** o comportamento observável é o mesmo já especificado na capability `autenticacao`, sem regressão introduzida pela interface

### Requirement: Independência do pacote e versão do projeto principal

Todo o código visual incorporado SHALL pertencer ao pacote `projetoImpacta` e SHALL ser compatível com a versão de Reflex do projeto principal (`reflex==0.9.12`). A integração MUST NOT introduzir downgrade de Reflex nem dependência residual do pacote `costguard`.

#### Scenario: App compila na versão do projeto

- **WHEN** o app do projeto principal é compilado
- **THEN** a compilação conclui sem erros e sem imports do pacote `costguard`
