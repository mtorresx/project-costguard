## Purpose

Fornecer, em uma única leitura, o consumo do orçamento mensal de todos os projetos no mês corrente (MTD), calculado no backend a partir de `custos_equipe`, para alimentar a listagem de projetos sem cálculo de regra de negócio no frontend.

## ADDED Requirements

### Requirement: Endpoint de resumo de consumo MTD

O sistema SHALL oferecer `GET /projetos-resumo-consumo-mtd` a qualquer usuário autenticado, sem exigir role admin. A leitura MUST NOT gravar, alterar ou remover registros e MUST NOT disparar coleta ou classificação. Sem token válido, o sistema SHALL responder HTTP 401. O endpoint MUST NOT aceitar parâmetros de intervalo nesta versão. Os endpoints existentes, incluindo `GET /projetos`, MUST NOT ter seu contrato alterado.

#### Scenario: Usuário admin consulta

- **WHEN** um usuário autenticado com role admin chama `GET /projetos-resumo-consumo-mtd`
- **THEN** o backend responde HTTP 200 com o resumo de consumo de todos os projetos

#### Scenario: Usuário leitura consulta

- **WHEN** um usuário autenticado com role leitura chama o endpoint
- **THEN** o backend responde HTTP 200 com o mesmo conteúdo, sem gravar nada

#### Scenario: Sem autenticação

- **WHEN** o endpoint é chamado sem token válido
- **THEN** o backend responde HTTP 401

#### Scenario: Leitura sem efeitos colaterais

- **WHEN** o endpoint é chamado
- **THEN** nenhum registro de `custos_equipe`, `custos_projeto`, `custos`, `projetos` ou das tabelas de execução é criado, alterado ou removido

### Requirement: Janela MTD calculada no backend

O backend SHALL calcular a janela do mês corrente no fuso `America/Sao_Paulo`: `data_inicio` é o primeiro dia do mês corrente e `data_fim` é o dia seguinte à data atual, exclusivo. A resposta SHALL conter `data_inicio` e `data_fim` no formato `YYYY-MM-DD` no nível superior. Apenas registros com `data >= data_inicio` e `data < data_fim` SHALL ser considerados.

#### Scenario: Janela no meio do mês

- **WHEN** o endpoint é chamado em 2026-10-26 às 16h em `America/Sao_Paulo`
- **THEN** a resposta contém `data_inicio = "2026-10-01"` e `data_fim = "2026-10-27"`

#### Scenario: Virada de dia em UTC antes de São Paulo

- **WHEN** o endpoint é chamado em 2026-10-31 às 22h em `America/Sao_Paulo` (já 2026-11-01 em UTC)
- **THEN** a resposta contém `data_inicio = "2026-10-01"` e `data_fim = "2026-11-01"`

#### Scenario: Primeiro dia do mês

- **WHEN** o endpoint é chamado em 2026-11-01 às 10h em `America/Sao_Paulo`
- **THEN** a resposta contém `data_inicio = "2026-11-01"` e `data_fim = "2026-11-02"`

### Requirement: Conteúdo da resposta por projeto

A resposta SHALL conter `projetos`, uma lista com todos os projetos cadastrados, ativos e inativos, na mesma ordem de `GET /projetos` (mais recentes primeiro). Cada item SHALL conter exatamente: `id`, `nome`, `codigo`, `status`, `budget`, `custo_status`, `custo_mtd`, `moeda`, `ultima_data_com_custo`, `percentual_usado` e `faixa`. A resposta MUST NOT expor `sync_id`, credenciais, campos internos de execução nem detalhamento por equipe, provedor, serviço ou dia.

#### Scenario: Projetos ativos e inativos

- **WHEN** existem projetos ativos e inativos
- **THEN** todos aparecem em `projetos`, cada um com seu `status`

#### Scenario: Campos internos ausentes

- **WHEN** a resposta é gerada
- **THEN** nenhum item contém `sync_id`, `coletado_em`, `provedor_id` ou dados de credencial

### Requirement: Fonte do custo MTD

O custo de cada projeto SHALL ser a soma de `valor` dos registros de `custos_equipe` do projeto na janela, de todos os provedores, incluindo todas as equipes e "Sem responsável" (`codigo_equipe = ""`). Esse valor bruto SHALL ser igual ao `total_projeto` retornado por `GET /projetos/{id}/custos-equipe` com o mesmo `data_inicio` e `data_fim`. O sistema MUST NOT usar `custos_projeto`, `custos` ou valores estimados de outra fonte para esse cálculo.

#### Scenario: Equipes e Sem responsável somados

- **WHEN** o projeto tem registros de `BACKEND`, `QA` e "Sem responsável" na janela
- **THEN** o custo do projeto é a soma de todos esses registros

#### Scenario: Consistência com o detalhe

- **WHEN** o endpoint e `GET /projetos/{id}/custos-equipe` são consultados com a mesma janela
- **THEN** o custo bruto do projeto é igual ao `total_projeto` do detalhe, a menos de arredondamento de ponto flutuante

### Requirement: Estado do custo

Cada projeto SHALL ter `custo_status` com um dos valores abaixo, definidos pelos registros do projeto na janela:

- `sem_registros`: nenhum registro. `custo_mtd = null`, `moeda = null`, `ultima_data_com_custo = null`.
- `moedas_mistas`: registros com mais de uma moeda. O sistema MUST NOT somar nem converter os valores. `custo_mtd = null`, `moeda = null` e `ultima_data_com_custo` é a maior data dos registros.
- `moeda_incompativel`: registros em uma única moeda diferente de `USD`. `custo_mtd` é a soma, `moeda` é essa moeda e `ultima_data_com_custo` é a maior data dos registros. O sistema MUST NOT converter a moeda.
- `ok`: registros em `USD`. `custo_mtd` é a soma, `moeda = "USD"` e `ultima_data_com_custo` é a maior data dos registros.

A situação de um projeto MUST NOT impedir a resposta dos demais: moedas mistas em um projeto não geram erro para a lista inteira.

#### Scenario: Projeto sem registros

- **WHEN** o projeto não tem registros na janela
- **THEN** o item contém `custo_status = "sem_registros"`, `custo_mtd = null`, `moeda = null`, `ultima_data_com_custo = null`, `percentual_usado = null` e `faixa = null`

#### Scenario: Custo zero real

- **WHEN** o projeto tem registros em `USD` cuja soma é exatamente zero
- **THEN** o item contém `custo_status = "ok"` e `custo_mtd = 0`, e não `null`

#### Scenario: Moeda diferente de USD

- **WHEN** todos os registros do projeto na janela estão em uma moeda diferente de `USD`
- **THEN** o item contém `custo_status = "moeda_incompativel"`, `custo_mtd` com a soma, `moeda` com essa moeda, `percentual_usado = null` e `faixa = null`

#### Scenario: Moedas misturadas em um projeto

- **WHEN** os registros de um projeto na janela têm mais de uma moeda
- **THEN** esse item contém `custo_status = "moedas_mistas"`, `custo_mtd = null`, `moeda = null`, `percentual_usado = null` e `faixa = null`
- **AND** o endpoint responde HTTP 200 com os demais projetos calculados normalmente

#### Scenario: Projeto inativo com histórico

- **WHEN** um projeto inativo tem registros em `custos_equipe` na janela
- **THEN** o item mostra o custo desses registros, com `status = "inativo"`

### Requirement: Última data com custo

`ultima_data_com_custo` SHALL ser a maior `data` existente em `custos_equipe` para o projeto dentro da janela consultada, no formato `YYYY-MM-DD`, ou `null` quando não houver registros. O campo MUST NOT ser interpretado nem documentado como data até a qual a classificação está completa.

#### Scenario: Registros até antes de hoje

- **WHEN** a janela vai de 2026-10-01 a 2026-10-27 e o projeto tem registros até 2026-10-19
- **THEN** o item contém `ultima_data_com_custo = "2026-10-19"`

#### Scenario: Sem registros

- **WHEN** o projeto não tem registros na janela
- **THEN** o item contém `ultima_data_com_custo = null`

### Requirement: Arredondamento

`custo_mtd` SHALL ser retornado arredondado para 2 casas decimais. `percentual_usado` SHALL ser retornado arredondado para 1 casa decimal. A faixa MUST ser determinada a partir do custo bruto e do percentual bruto, nunca a partir dos valores arredondados.

#### Scenario: Custo com muitas casas

- **WHEN** a soma bruta do projeto é `873.6381400000001`
- **THEN** o item contém `custo_mtd = 873.64`

#### Scenario: Faixa não depende do arredondamento

- **WHEN** o custo bruto é `69.96` e o `budget` é `100`
- **THEN** o item contém `percentual_usado = 70.0` e `faixa = "normal"`

### Requirement: Percentual e faixa de consumo

Quando `custo_status = "ok"` e `budget > 0`, o sistema SHALL calcular `percentual_usado = custo bruto / budget × 100` e a `faixa`, sobre o percentual bruto `p`:

- `p < 70` → `normal`
- `70 <= p < 90` → `atencao`
- `90 <= p < 100` → `critico`
- `p >= 100` → `estourado`

Quando `budget` não for maior que zero, ou quando `custo_status` for diferente de `ok`, o sistema SHALL retornar `percentual_usado = null` e `faixa = null`. Custo negativo (crédito) SHALL ser preservado: o percentual pode ser negativo e a faixa é `normal`.

#### Scenario: Faixa normal

- **WHEN** o custo é `500` e o `budget` é `1000`
- **THEN** o item contém `percentual_usado = 50.0` e `faixa = "normal"`

#### Scenario: Limite exato de atenção

- **WHEN** o custo é `700` e o `budget` é `1000`
- **THEN** o item contém `percentual_usado = 70.0` e `faixa = "atencao"`

#### Scenario: Limite exato de crítico

- **WHEN** o custo é `900` e o `budget` é `1000`
- **THEN** o item contém `percentual_usado = 90.0` e `faixa = "critico"`

#### Scenario: Limite exato de estouro

- **WHEN** o custo é `1000` e o `budget` é `1000`
- **THEN** o item contém `percentual_usado = 100.0` e `faixa = "estourado"`

#### Scenario: Acima do orçamento

- **WHEN** o custo é `1500` e o `budget` é `1000`
- **THEN** o item contém `percentual_usado = 150.0` e `faixa = "estourado"`

#### Scenario: Orçamento não definido

- **WHEN** o projeto tem `budget = 0` e `custo_status = "ok"`
- **THEN** o item contém `custo_mtd` com o valor real, `percentual_usado = null` e `faixa = null`

#### Scenario: Crédito

- **WHEN** a soma do projeto é `-15` em `USD` e o `budget` é `1000`
- **THEN** o item contém `custo_mtd = -15`, `percentual_usado = -1.5` e `faixa = "normal"`
