## ADDED Requirements

### Requirement: Painel agregado de leitura

O backend SHALL oferecer `GET /painel` (qualquer usuário autenticado; HTTP 401 sem token), com o parâmetro opcional `mes` (`AAAA-MM`, mesmas regras de `GET /projetos-resumo-consumo-mtd`), que devolve numa única resposta `resumo`, `alertas` e `recursos_nao_classificados`, com conteúdo idêntico ao de `GET /projetos-resumo-consumo-mtd`, `GET /alertas` e `GET /recursos-nao-classificados`. A lógica SHALL ser compartilhada (funções Xano), de modo que os endpoints individuais e o painel não divirjam. Os endpoints individuais MUST manter seus contratos.

#### Scenario: Conteúdo idêntico

- **WHEN** um usuário autenticado chama `GET /painel?mes=2026-10`
- **THEN** `resumo` é igual à resposta de `GET /projetos-resumo-consumo-mtd?mes=2026-10`, `alertas` igual a `GET /alertas` e `recursos_nao_classificados` igual a `GET /recursos-nao-classificados`

#### Scenario: Mês inválido

- **WHEN** `mes` é futuro ou está fora do formato
- **THEN** o backend responde HTTP 400

### Requirement: Painel do projeto

O backend SHALL oferecer `GET /projetos/{id}/painel` (qualquer usuário autenticado), que devolve `projeto` (`id`, `nome`, `codigo`, `budget`, `status`), `recursos` e `equipes`, com conteúdo idêntico ao de `GET /projetos/{id}/recursos` e `GET /projetos/{id}/equipes`. Projeto inexistente SHALL resultar em HTTP 404.

#### Scenario: Projeto existente

- **WHEN** um usuário autenticado chama `GET /projetos/10/painel`
- **THEN** recebe o projeto e as mesmas listas de recursos e equipes dos endpoints individuais

### Requirement: Leituras do frontend dentro do limite do plano

O frontend SHALL usar `GET /painel` no Início, em Projetos e em Alertas, e `GET /projetos/{id}/painel` mais `GET /projetos/{id}/custos-equipe` no detalhe, executando leituras independentes em paralelo. As respostas de leitura bem-sucedidas SHALL ser reaproveitadas por até 60 segundos (por token e URL), e qualquer escrita SHALL descartar todas as respostas guardadas. O frontend SHALL controlar a vazão para não ultrapassar o limite de requisições do plano (10 a cada 20 segundos), aguardando apenas o necessário. O botão "Atualizar" do Início SHALL ignorar as respostas guardadas. Se `GET /painel` falhar (exceto HTTP 401), o frontend SHALL recorrer às leituras individuais, preservando os erros independentes por bloco.

#### Scenario: Navegação sem fila

- **WHEN** o usuário entra e navega por Início, Projetos, detalhe, Alertas, Provedores e Usuários e volta a três delas
- **THEN** nenhuma requisição espera na fila do limite do plano e as páginas revisitadas carregam sem nova chamada ao backend

#### Scenario: Escrita invalida o reaproveitamento

- **WHEN** o usuário resolve um alerta ou sincroniza um provedor
- **THEN** a leitura seguinte vai ao backend e reflete a alteração
