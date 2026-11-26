## ADDED Requirements

### Requirement: Dashboard com dados reais

A home autenticada (`/`) SHALL exibir somente dados reais obtidos do backend: custo classificado no mês (soma dos projetos com custo em USD, com o período), quantidade de projetos ativos, quantidade de alertas abertos e quantidade de recursos não classificados. A página MUST NOT exibir valores fictícios ou ilustrativos.

#### Scenario: Indicadores reais

- **WHEN** um usuário autenticado acessa `/`
- **THEN** os indicadores correspondem às respostas de `GET /projetos-resumo-consumo-mtd`, `GET /alertas` e `GET /recursos-nao-classificados`

#### Scenario: Sem custo classificado

- **WHEN** nenhum projeto possui custo classificado em USD no mês
- **THEN** o card de custo informa a ausência de custos, sem exibir "US$ 0.00"

#### Scenario: Projetos fora da soma

- **WHEN** há projetos com custo em moeda diferente de USD ou em moedas mistas
- **THEN** eles não entram na soma e o card informa quantos ficaram de fora

### Requirement: Maiores consumos e alertas recentes

A home SHALL listar até 5 projetos ativos com maior percentual de consumo do orçamento (somente com percentual calculado pelo backend), com barra colorida pela faixa, e até 5 alertas abertos mais recentes, com link para `/alertas`. Cada projeto SHALL levar ao seu detalhamento.

#### Scenario: Lista de consumo

- **WHEN** existem projetos ativos com orçamento e custo no mês
- **THEN** eles aparecem do maior para o menor percentual, com a faixa do backend

### Requirement: Falhas independentes por bloco

Uma falha em uma das fontes SHALL ser exibida no bloco correspondente sem impedir os demais. HTTP 401 SHALL seguir o tratamento central de sessão.

#### Scenario: Alertas indisponíveis

- **WHEN** `GET /alertas` falha
- **THEN** o bloco de alertas e o indicador de alertas mostram indisponibilidade, e os blocos de custo e projetos continuam exibidos
