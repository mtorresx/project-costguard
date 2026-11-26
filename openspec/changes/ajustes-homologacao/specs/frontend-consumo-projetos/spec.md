## MODIFIED Requirements

### Requirement: Carregamento da listagem com consumo

Ao abrir `/projetos`, o frontend SHALL obter os projetos e o consumo em uma única chamada a `GET /painel` (cujo `resumo` é idêntico a `GET /projetos-resumo-consumo-mtd`), com o token da sessão e com o parâmetro `mes` quando um mês anterior estiver selecionado. O frontend MUST NOT chamar `GET /projetos/{id}/custos-equipe` por projeto na listagem. Em HTTP 401, o frontend SHALL aplicar o tratamento central de sessão já existente. O frontend MUST NOT recalcular percentual nem faixa: SHALL usar `percentual_usado` e `faixa` retornados pelo backend. Os cards SHALL ser ordenados com os ativos antes dos inativos, pelo maior `percentual_usado` (itens sem percentual depois), depois pelo maior custo e depois pelo nome.

#### Scenario: Uma chamada para a listagem

- **WHEN** um usuário autenticado abre `/projetos`
- **THEN** o frontend faz uma única chamada a `GET /painel` para montar os cards
- **AND** não faz chamadas a `custos-equipe` por projeto

#### Scenario: Sessão expirada

- **WHEN** a chamada recebe HTTP 401
- **THEN** o frontend limpa a sessão e redireciona ao login, conforme o tratamento existente

#### Scenario: Ordenação por consumo

- **WHEN** há projetos ativos com 92%, 15% e sem percentual, e um projeto inativo
- **THEN** os cards aparecem nessa ordem: 92%, 15%, sem percentual, inativo

### Requirement: Card com consumo MTD

Cada card SHALL manter nome, `PRJ_<codigo>`, status e ação "Ver detalhamento", e SHALL exibir, no layout do card do frontend de referência:

- o rótulo "Custo classificado no mês" e o valor de `custo_mtd`, com prefixo "US$" quando `moeda = "USD"`, duas casas decimais, separador de milhar e sinal negativo preservado;
- "Último custo classificado: DD/MM/AAAA", a partir de `ultima_data_com_custo`, apenas quando o campo não for nulo;
- o orçamento mensal (`budget`) em US$;
- o percentual utilizado com uma casa decimal e uma barra de progresso, quando `percentual_usado` não for nulo.

A página SHALL oferecer um seletor de mês (mês atual e os 5 anteriores); para mês fechado, a ausência de custo SHALL ser informada como "Sem custos classificados neste mês." O card MUST NOT exibir textos como "Dados atualizados até" ou "Classificado até".

#### Scenario: Card com consumo normal

- **WHEN** o item tem `custo_status = "ok"`, `custo_mtd = 620.0`, `budget = 1000`, `percentual_usado = 62.0`, `faixa = "normal"` e `ultima_data_com_custo = "2026-10-19"`
- **THEN** o card mostra "Custo classificado no mês" com "US$ 620.00", "Último custo classificado: 19/10/2026", orçamento "US$ 1,000.00", "62.0%" e a barra preenchida em 62% na cor da faixa normal

#### Scenario: Sem afirmação de completude

- **WHEN** qualquer card é exibido
- **THEN** o card não contém "Dados atualizados até" nem "Classificado até"

#### Scenario: Mês anterior selecionado

- **WHEN** o usuário seleciona outubro de 2026 em novembro
- **THEN** os cards mostram o custo de outubro inteiro, com `mes = "2026-10"` enviado ao backend em `GET /painel`
