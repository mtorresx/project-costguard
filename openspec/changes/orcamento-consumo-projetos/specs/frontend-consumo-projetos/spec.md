## Purpose

Exibir nos cards da listagem `/projetos` o consumo real do orçamento mensal no mês corrente, com faixas de consumo e estados explícitos, preservando o visual do frontend de referência e usando somente os dados calculados pelo backend.

## ADDED Requirements

### Requirement: Carregamento da listagem com consumo

Ao abrir `/projetos`, o frontend SHALL obter os projetos e o consumo em uma única chamada a `GET /projetos/resumo-consumo-mtd`, com o token da sessão. O frontend MUST NOT chamar `GET /projetos/{id}/custos-equipe` por projeto na listagem. Em HTTP 401, o frontend SHALL aplicar o tratamento central de sessão já existente. O frontend MUST NOT recalcular percentual nem faixa: SHALL usar `percentual_usado` e `faixa` retornados pelo backend.

#### Scenario: Uma chamada para a listagem

- **WHEN** um usuário autenticado abre `/projetos`
- **THEN** o frontend faz uma única chamada a `GET /projetos/resumo-consumo-mtd` para montar os cards
- **AND** não faz chamadas a `custos-equipe` por projeto

#### Scenario: Sessão expirada

- **WHEN** a chamada recebe HTTP 401
- **THEN** o frontend limpa a sessão e redireciona ao login, conforme o tratamento existente

### Requirement: Card com consumo MTD

Cada card SHALL manter nome, `PRJ_<codigo>`, status e ação "Ver detalhamento", e SHALL exibir, no layout do card do frontend de referência:

- o rótulo "Custo classificado (MTD)" e o valor de `custo_mtd`, com prefixo "US$" quando `moeda = "USD"`, duas casas decimais, separador de milhar e sinal negativo preservado;
- "Último custo classificado: DD/MM/AAAA", a partir de `ultima_data_com_custo`, apenas quando o campo não for nulo;
- o orçamento mensal (`budget`) em US$;
- o percentual utilizado com uma casa decimal e uma barra de progresso, quando `percentual_usado` não for nulo.

O card MUST NOT exibir textos como "Dados atualizados até" ou "Classificado até".

#### Scenario: Card com consumo normal

- **WHEN** o item tem `custo_status = "ok"`, `custo_mtd = 620.0`, `budget = 1000`, `percentual_usado = 62.0`, `faixa = "normal"` e `ultima_data_com_custo = "2026-10-19"`
- **THEN** o card mostra "Custo classificado (MTD)" com "US$ 620.00", "Último custo classificado: 19/10/2026", orçamento "US$ 1,000.00", "62.0%" e a barra preenchida em 62% na cor da faixa normal

#### Scenario: Sem afirmação de completude

- **WHEN** qualquer card é exibido
- **THEN** o card não contém "Dados atualizados até" nem "Classificado até"

### Requirement: Cores e indicação das faixas

A barra e o percentual SHALL usar a cor da `faixa`: `normal` verde, `atencao` amarelo, `critico` laranja e `estourado` vermelho. A faixa SHALL ser indicada também por texto ("Normal", "Atenção", "Crítico", "Estourado"), para não depender apenas da cor. A largura da barra SHALL ser limitada ao intervalo de 0% a 100%, enquanto o texto mostra o percentual real.

#### Scenario: Faixa atenção

- **WHEN** o item tem `faixa = "atencao"` e `percentual_usado = 75.0`
- **THEN** a barra fica amarela em 75% e o card indica "Atenção"

#### Scenario: Faixa crítico

- **WHEN** o item tem `faixa = "critico"` e `percentual_usado = 95.0`
- **THEN** a barra fica laranja em 95% e o card indica "Crítico"

#### Scenario: Orçamento estourado

- **WHEN** o item tem `faixa = "estourado"` e `percentual_usado = 150.0`
- **THEN** a barra fica vermelha e preenchida em 100%, o texto mostra "150.0%" e o card indica "Estourado"

### Requirement: Orçamento não definido

Quando `budget` não for maior que zero, o card SHALL mostrar "Sem orçamento definido" no lugar do percentual e da barra. O card MUST NOT mostrar "0%" nem barra vazia como se o consumo fosse zero. O custo SHALL continuar sendo exibido conforme `custo_status`.

#### Scenario: Projeto com budget zero e custo

- **WHEN** o item tem `budget = 0`, `custo_status = "ok"` e `custo_mtd = 873.64`
- **THEN** o card mostra "US$ 873.64" e "Sem orçamento definido", sem percentual e sem barra

### Requirement: Estados de custo sem valor fabricado

O card SHALL tratar cada `custo_status` sem fabricar valores:

- `sem_registros`: mostrar "Sem custos classificados no mês até a data atual." no lugar do valor, sem "US$ 0.00", sem percentual e sem barra;
- `moeda_incompativel`: mostrar o valor com o código da moeda retornada e "Comparação com o orçamento em US$ não é feita.", sem percentual e sem barra;
- `moedas_mistas`: mostrar "Custos em moedas diferentes; não é possível somar.", sem valor, sem percentual e sem barra;
- `ok` com `custo_mtd = 0`: mostrar "US$ 0.00" como valor real e, havendo orçamento, "0.0%" com barra vazia na faixa normal.

#### Scenario: Sem registros no mês

- **WHEN** o item tem `custo_status = "sem_registros"`
- **THEN** o card mostra "Sem custos classificados no mês até a data atual." e não exibe "US$ 0.00", percentual nem barra

#### Scenario: Moeda incompatível

- **WHEN** o item tem `custo_status = "moeda_incompativel"`, `moeda = "EUR"` e `custo_mtd = 120.5`
- **THEN** o card mostra "EUR 120.50" e "Comparação com o orçamento em US$ não é feita.", sem percentual nem barra

#### Scenario: Moedas misturadas

- **WHEN** o item tem `custo_status = "moedas_mistas"`
- **THEN** o card mostra "Custos em moedas diferentes; não é possível somar.", sem valor, percentual nem barra

#### Scenario: Custo zero real

- **WHEN** o item tem `custo_status = "ok"`, `custo_mtd = 0`, `budget = 1000`, `percentual_usado = 0.0` e `faixa = "normal"`
- **THEN** o card mostra "US$ 0.00", "0.0%" e a barra vazia na cor da faixa normal

#### Scenario: Crédito

- **WHEN** o item tem `custo_mtd = -15`, `percentual_usado = -1.5` e `faixa = "normal"`
- **THEN** o card mostra "-US$ 15.00" e "-1.5%", com a barra em 0%, sem alterar o valor exibido

### Requirement: Projetos inativos com histórico

Projetos inativos SHALL continuar na listagem, com indicação de status inativo e com o custo classificado existente, seguindo os mesmos estados dos projetos ativos. O frontend MUST NOT ocultar o histórico de custo de projetos inativos.

#### Scenario: Projeto inativo com custo

- **WHEN** o item tem `status = "inativo"`, `custo_status = "ok"` e `custo_mtd = 50`
- **THEN** o card aparece na listagem com status inativo e "US$ 50.00"

### Requirement: Endpoint de consumo indisponível

Quando `GET /projetos/resumo-consumo-mtd` falhar por erro de rede ou status diferente de 200 e 401, o frontend SHALL exibir a mensagem "Não foi possível carregar o consumo dos projetos." e SHALL carregar a listagem por `GET /projetos`. Nesse modo, cada card SHALL mostrar "Consumo indisponível" no lugar do custo, sem valor, percentual nem barra, e os controles de criar, editar e desativar e a navegação ao detalhamento SHALL continuar funcionando. Se `GET /projetos` também falhar, o frontend SHALL exibir a mensagem de erro de carregamento de projetos já existente. O frontend MUST NOT exibir zero como substituto do consumo indisponível.

#### Scenario: Consumo indisponível com listagem disponível

- **WHEN** `GET /projetos/resumo-consumo-mtd` responde HTTP 500 e `GET /projetos` responde HTTP 200
- **THEN** a página mostra "Não foi possível carregar o consumo dos projetos." e os cards com "Consumo indisponível"
- **AND** os controles de admin e a navegação ao detalhamento continuam disponíveis

#### Scenario: Ambos indisponíveis

- **WHEN** `GET /projetos/resumo-consumo-mtd` e `GET /projetos` falham
- **THEN** a página mostra "Não foi possível carregar os projetos." e nenhum card

### Requirement: Preservação da listagem existente

A change MUST preservar o comportamento atual de `/projetos`: controles de criar, editar e desativar apenas para admin (ocultação como UX; autorização no backend), navegação ao detalhamento pelo card, recarga da listagem após salvar ou desativar e o estado vazio "Nenhum projeto cadastrado ainda.". A tela de detalhamento `/projetos/[projeto_id]` MUST NOT ser alterada.

#### Scenario: Usuário leitura

- **WHEN** um usuário com role leitura abre `/projetos`
- **THEN** os cards mostram o consumo sem controles de criar, editar ou desativar

#### Scenario: Recarga após edição

- **WHEN** um admin salva a edição de um projeto
- **THEN** a listagem é recarregada com o consumo atualizado pelo endpoint de resumo

#### Scenario: Card igual ao detalhe

- **WHEN** o usuário abre o detalhamento a partir de um card no mesmo dia
- **THEN** o "Custo classificado (MTD)" do detalhe é igual ao valor do card
