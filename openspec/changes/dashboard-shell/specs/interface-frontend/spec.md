## MODIFIED Requirements

### Requirement: Páginas de apresentação registradas

O frontend SHALL registrar as páginas incorporadas — login, home, projetos, detalhamento de projeto, provedores, alertas e usuários — em rotas acessíveis. Todas as páginas autenticadas SHALL exibir dados reais do backend e MUST NOT exibir dados fictícios, selos de demonstração ou preferências que não são persistidas.

#### Scenario: Página de apresentação acessível

- **WHEN** o usuário autenticado navega para uma das rotas registradas
- **THEN** a página é exibida com seu design e com dados obtidos do backend

#### Scenario: Páginas mock não chamam backend inexistente

- **WHEN** uma página autenticada é renderizada
- **THEN** ela depende apenas de endpoints existentes no backend e não exibe dados de apresentação no lugar de dados reais

#### Scenario: Shell sem itens de demonstração

- **WHEN** qualquer página autenticada é exibida
- **THEN** o topo e o menu não mostram selos de demonstração nem campos de preferência não persistidos, e o indicador de alertas reflete a última leitura real de `GET /alertas`

## ADDED Requirements

### Requirement: Limite de requisições do backend

O frontend SHALL repetir automaticamente, com espera crescente e número limitado de tentativas, as requisições recusadas pelo backend com HTTP 429 (limite de requisições). Um HTTP 429 na validação de sessão MUST NOT encerrar a sessão; somente HTTP 401 ou falha de validação do token encerram a sessão. Se o limite persistir, a página SHALL exibir a indisponibilidade do bloco afetado.

#### Scenario: 429 transitório

- **WHEN** uma leitura recebe HTTP 429 e a nova tentativa recebe HTTP 200
- **THEN** a página exibe os dados normalmente

#### Scenario: 429 na validação de sessão

- **WHEN** a validação da sessão recebe HTTP 429 em todas as tentativas
- **THEN** o usuário permanece logado e a página exibe um aviso de que a sessão não pôde ser validada
