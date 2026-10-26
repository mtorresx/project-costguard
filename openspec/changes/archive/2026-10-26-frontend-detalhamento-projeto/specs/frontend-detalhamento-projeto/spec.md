## ADDED Requirements

### Requirement: Rota dinâmica de detalhamento

O frontend SHALL disponibilizar a rota `/projetos/[projeto_id]`, protegida pela mesma validação de sessão das demais áreas autenticadas. O parâmetro `projeto_id` SHALL ser usado para consultar o projeto no backend. Quando o parâmetro não for um inteiro positivo, a página MUST NOT chamar o backend e SHALL exibir "Projeto não encontrado".

#### Scenario: Acesso autenticado ao detalhamento

- **WHEN** um usuário autenticado acessa `/projetos/4`
- **THEN** a página consulta `GET /projetos/4` e exibe o detalhamento do projeto retornado

#### Scenario: Acesso sem sessão

- **WHEN** um usuário sem sessão autenticada acessa `/projetos/4`
- **THEN** o frontend redireciona para `/login`, conforme a proteção de rota existente

#### Scenario: Parâmetro inválido

- **WHEN** um usuário acessa `/projetos/abc` ou `/projetos/0`
- **THEN** a página exibe "Projeto não encontrado" com link de volta para `/projetos`, sem chamar o backend

### Requirement: Navegação a partir da listagem de projetos

A página `/projetos` SHALL permitir abrir o detalhamento de um projeto pelo card, com a ação "Ver detalhamento", levando à rota `/projetos/{id}`. Os controles de editar e desativar, visíveis apenas para admin, MUST NOT disparar a navegação para o detalhamento.

#### Scenario: Clique no card abre o detalhamento

- **WHEN** um usuário clica no card de um projeto em `/projetos`
- **THEN** o frontend navega para `/projetos/{id}` daquele projeto

#### Scenario: Botão de editar não navega

- **WHEN** um admin clica em "Editar" dentro do card
- **THEN** o formulário de edição abre e o frontend não navega para o detalhamento

### Requirement: Carregamento do projeto e tratamento de erros

O frontend SHALL consultar `GET /projetos/{id}` com o token da sessão (`Authorization: Bearer`). Uma resposta HTTP 401 SHALL ser tratada pelo mecanismo central de sessão (limpar a sessão e redirecionar ao login). Uma resposta HTTP 404 SHALL mostrar "Projeto não encontrado". Falhas de rede ou respostas inesperadas SHALL mostrar uma mensagem genérica, sem travar a página e sem exibir corpo técnico, status HTTP ou `RequestId`.

#### Scenario: Projeto inexistente

- **WHEN** `GET /projetos/{id}` responde 404
- **THEN** a página exibe "Projeto não encontrado" com link de volta para `/projetos`

#### Scenario: Sessão expirada

- **WHEN** qualquer consulta da página recebe HTTP 401
- **THEN** o frontend limpa a sessão e redireciona ao login

#### Scenario: Falha de rede

- **WHEN** a consulta do projeto falha por erro de rede
- **THEN** a página exibe uma mensagem genérica e permanece utilizável

#### Scenario: Projeto inativo continua acessível

- **WHEN** `GET /projetos/{id}` retorna um projeto com `status = inativo`
- **THEN** a página exibe o detalhamento normalmente e mostra o status "Inativo" no cabeçalho, sem bloquear nem esconder o conteúdo

### Requirement: Janela de custos do mês corrente

A página SHALL calcular automaticamente a janela de custos como o mês corrente até a data atual, usando o fuso `America/Sao_Paulo` para determinar o mês e a data atual: `data_inicio` é o primeiro dia do mês e `data_fim` é o dia seguinte à data atual, porque o endpoint trata `data_fim` como exclusivo. A semântica do backend não muda. A página MUST NOT oferecer seletor de intervalo nesta versão. A página SHALL exibir o período usado como texto, com início e a data atual. A página MUST NOT comparar o orçamento mensal com um intervalo diferente do mês corrente.

#### Scenario: Janela em meio ao mês

- **WHEN** a data atual em `America/Sao_Paulo` é 26/10/2026 e a página é carregada
- **THEN** a consulta usa `data_inicio = 2026-10-01` e `data_fim = 2026-10-27`, e a tela exibe o período "01/10/2026 a 26/10/2026"

#### Scenario: Primeiro dia do mês

- **WHEN** a data atual em `America/Sao_Paulo` é 01/11/2026
- **THEN** a consulta usa `data_inicio = 2026-11-01` e `data_fim = 2026-11-02`

#### Scenario: Virada de mês em UTC não altera a janela

- **WHEN** são 02:00 UTC de 01/11/2026, o que equivale a 31/10/2026 23:00 em `America/Sao_Paulo`
- **THEN** a consulta usa `data_inicio = 2026-10-01` e `data_fim = 2026-11-01`, porque o mês é o de São Paulo

### Requirement: Métricas financeiras com dados reais

A página SHALL exibir exatamente duas métricas financeiras, em grade de duas colunas com o estilo visual da referência: **Custo classificado (MTD)** e **Orçamento restante**, com o percentual utilizado do orçamento mensal (texto "X% utilizado de US$ Y" e barra de progresso). O rótulo "Custo classificado" indica que o valor é o custo já classificado e MUST NOT afirmar que ele está atualizado até o momento da consulta. A página MUST NOT exibir projeção do fim do mês, variação percentual, tendência, custo por provedor nem um terceiro card para preencher espaço.

Quando `moeda` for `USD` e `budget` for maior que zero:

- orçamento restante = `budget − custo_atual`, com o sinal preservado quando negativo;
- percentual utilizado = `custo_atual / budget × 100`, com uma casa decimal;
- a barra de progresso é limitada a 100%, mas o texto mostra o percentual real.

#### Scenario: Métricas com custo e orçamento

- **WHEN** `custos-equipe` retorna `moeda = "USD"` e `total_projeto = 1239.73` e o projeto tem `budget = 2000.00`
- **THEN** a página exibe "US$ 1,239.73" como "Custo classificado (MTD)", "US$ 760.27" como orçamento restante e "62.0% utilizado de US$ 2,000.00"

#### Scenario: Estouro de orçamento

- **WHEN** o custo atual é maior que o orçamento
- **THEN** o orçamento restante aparece negativo com sinal, a barra fica em 100% e o texto mostra o percentual real acima de 100%

#### Scenario: Ausência de métricas extras

- **WHEN** a página é carregada
- **THEN** não há card de projeção, de variação percentual, de tendência nem de custo por provedor

### Requirement: Sem valores fictícios quando o custo é desconhecido

A página MUST NOT usar valor fictício, zero como substituto de custo desconhecido, nem tendência inventada. Quando `custos-equipe` retornar `moeda = null` (sem registros no período), a página SHALL mostrar "Sem custos classificados no mês até a data atual." no lugar dos valores de custo e de orçamento restante, sem calcular o restante a partir de zero.

O orçamento restante e o percentual SHALL ser calculados somente quando a moeda do custo for compatível com a moeda do orçamento (USD). Quando `moeda` for diferente de `USD`, a página SHALL mostrar o custo com a moeda retornada e MUST NOT calcular orçamento restante nem percentual, informando que a comparação com o orçamento em USD não é feita. A página MUST NOT converter valores entre moedas.

Quando `budget` for zero, a página SHALL mostrar "Sem orçamento definido" no lugar do percentual e do orçamento restante.

#### Scenario: Mês sem custos classificados

- **WHEN** `custos-equipe` retorna `moeda = null`, `total_projeto = 0` e `equipes` vazia
- **THEN** a página mostra "Sem custos classificados no mês até a data atual." e não exibe "US$ 0.00" como custo nem orçamento restante calculado

#### Scenario: Moeda diferente de USD

- **WHEN** `custos-equipe` retorna `moeda = "EUR"`
- **THEN** a página mostra o custo em "EUR" e não calcula orçamento restante nem percentual

#### Scenario: Projeto sem orçamento

- **WHEN** o projeto tem `budget = 0` e `custos-equipe` retorna `moeda = "USD"`
- **THEN** a página mostra o custo e "Sem orçamento definido" no lugar do restante e do percentual

### Requirement: Custo por equipe

A página SHALL exibir, a partir de `custos-equipe.equipes`, somente as equipes com custo no período, na ordem retornada pelo backend (`codigo`). Cada item SHALL mostrar o nome da equipe, o número de recursos ativos da equipe, o total e uma barra proporcional ao `total_projeto`. A página MUST NOT exibir variação por equipe. Sem equipes com custo, a página SHALL mostrar "Nenhum custo por equipe no mês até a data atual."

#### Scenario: Equipes com custo

- **WHEN** `custos-equipe` retorna `BACKEND` com total 384.80 e `DEVOPS` com total 417.01 num total de 1239.73
- **THEN** a página lista `BACKEND` e `DEVOPS` com esses totais, e as barras representam suas frações do total do projeto

#### Scenario: Sem equipes com custo

- **WHEN** `custos-equipe.equipes` está vazia
- **THEN** a página mostra "Nenhum custo por equipe no mês até a data atual."

### Requirement: Recursos detalhados por equipe

A página SHALL exibir o inventário de recursos do projeto agrupado por equipe, a partir de `GET /projetos/{id}/recursos` e `GET /projetos/{id}/equipes`. A página MUST consider somente os recursos com `ativo = true`. Cada grupo SHALL usar o nome da equipe obtido de `equipes` pelo `equipe_id`. Os recursos com `equipe_id = null` SHALL aparecer em um grupo "Sem responsável", exibido por último. Cada grupo SHALL ser recolhível e mostrar o número de recursos.

A tabela de recursos SHALL conter as colunas **Recurso**, **Serviço** e **Região**. A página MUST NOT exibir coluna de valor, de custo ou de tendência por recurso.

O nome exibido do recurso SHALL ser o último segmento do ARN (após o último `/` ou `:`). O ARN completo SHALL ser exibido como dica de ferramenta (`title`) da célula. Se o ARN não tiver separadores, a página exibe o ARN inteiro.

Sem recursos ativos, a página SHALL mostrar "Nenhum recurso registrado ainda."

#### Scenario: Agrupamento por equipe

- **WHEN** o projeto tem recursos ativos com `equipe_id` de `BACKEND` e de `QA`, e recursos com `equipe_id = null` e tag de equipe vazia
- **THEN** a página mostra um grupo para cada equipe com seu nome, e um grupo "Sem responsável" por último

#### Scenario: Equipe_id 0 com tag preenchida não é equipe real

- **WHEN** há recursos ativos com `equipe_id = 0` e `codigo_equipe_tag` igual a `BACKEND`, `WEB` e `MARKETING`
- **THEN** a página cria um grupo "Equipe não vinculada — BACKEND", um "Equipe não vinculada — WEB" e um "Equipe não vinculada — MARKETING", sem misturar tags, sem criar equipe e sem apresentar esses grupos como equipes reais

#### Scenario: Recurso inativo não aparece

- **WHEN** um recurso tem `ativo = false`
- **THEN** ele não aparece na tabela nem na contagem do grupo

#### Scenario: Recurso sem separador no ARN

- **WHEN** um recurso tem `arn` sem `/` ou `:`
- **THEN** a coluna Recurso mostra o ARN inteiro

#### Scenario: Ausência de coluna de valor

- **WHEN** a tabela de recursos é exibida
- **THEN** não há coluna de valor, de custo nem de tendência

### Requirement: Aviso de recursos sem responsável

A página SHALL exibir o bloco "Recursos sem responsável" quando o inventário de `GET /projetos/{id}/recursos` tiver ao menos um recurso com `ativo = true` cujo vínculo de equipe seja ausente (`equipe_id` null ou 0) e cuja `codigo_equipe_tag` esteja vazia. Essa é a única condição de exibição do bloco: a página MUST NOT usar custo maior que zero para decidir se existem recursos sem responsável. O bloco SHALL conter a explicação de que esses recursos pertencem ao projeto, mas não têm tag de equipe.

Quando `moeda` não for nula, o bloco SHALL mostrar a linha "Custo acumulado sem responsável: US$ X" com o valor de `sem_responsavel.total` do backend, como informação financeira adicional, mesmo que o valor seja zero. A página MUST NOT calcular esse valor, MUST NOT associar custo a um recurso individual e MUST NOT inventar associação entre custo e recurso.

O botão **"Notificar DevOps"** SHALL aparecer no mesmo local do design de referência, **desabilitado**, sem ação associada. A página MUST NOT exibir mensagem de sucesso, MUST NOT enviar e-mail e MUST NOT chamar qualquer endpoint de notificação nesta versão.

#### Scenario: Bloco com recursos sem equipe

- **WHEN** há recursos ativos com `equipe_id` null ou 0 e tag de equipe vazia
- **THEN** o bloco aparece, com o botão "Notificar DevOps" desabilitado

#### Scenario: Sem recursos sem equipe

- **WHEN** não há recursos ativos sem equipe e sem tag
- **THEN** o bloco não aparece, mesmo que `sem_responsavel.total` seja maior que zero

#### Scenario: Recursos sem equipe com custo classificado zero

- **WHEN** há recursos ativos sem equipe e sem tag e `custos-equipe` retorna `moeda = "USD"` com `sem_responsavel.total = 0`
- **THEN** o bloco aparece e mostra "Custo acumulado sem responsável: US$ 0.00" como informação adicional

#### Scenario: Custo sem responsável com lista de recursos

- **WHEN** há recursos ativos sem equipe e sem tag e `sem_responsavel.total = 1239.73` em `moeda = "USD"`
- **THEN** o bloco mostra a lista de recursos e o valor "US$ 1,239.73" como custo acumulado, sem associar esse valor a nenhum recurso específico

#### Scenario: Botão desabilitado

- **WHEN** o usuário tenta acionar "Notificar DevOps"
- **THEN** nenhuma ação ocorre e nenhuma mensagem de sucesso é exibida

### Requirement: Exportação CSV com dados reais

A página SHALL oferecer "Exportar Dados" (cabeçalho) e "Exportar CSV" (bloco de recursos), que geram o mesmo arquivo CSV a partir dos recursos carregados na tela. O arquivo SHALL conter as colunas `Equipe`, `Recurso`, `ARN`, `Serviço` e `Região`, sem colunas de valor, tendência ou projeção. Recursos sem equipe SHALL aparecer com `Equipe = Sem responsável`. O arquivo SHALL ser gerado com o módulo `csv` e entregue com `rx.download`, com nome `costguard-recursos-{codigo}.csv`, em minúsculas para o código do projeto.

#### Scenario: Conteúdo do CSV

- **WHEN** o usuário clica em "Exportar CSV" com recursos carregados
- **THEN** o arquivo tem o cabeçalho `Equipe,Recurso,ARN,Serviço,Região` e uma linha por recurso ativo exibido

#### Scenario: Sem recursos

- **WHEN** o usuário exporta sem recursos ativos
- **THEN** o arquivo contém apenas o cabeçalho, sem valores fictícios

#### Scenario: Campos com vírgula

- **WHEN** um campo contém vírgula ou aspas
- **THEN** o campo é escapado conforme o padrão CSV pelo módulo `csv`

### Requirement: Estados de erro independentes por bloco

Falhas em `custos-equipe` SHALL afetar somente as métricas e o bloco de custo por equipe. Falhas em `recursos` ou `equipes` SHALL afetar somente o bloco de recursos. Quando `custos-equipe` retornar `inputerror` de moedas diferentes, a página SHALL mostrar a mensagem de erro de entrada informada pelo backend, quando houver, ou mensagem genérica. Nenhuma mensagem exibe corpo técnico cru.

#### Scenario: Falha só no inventário

- **WHEN** `GET /projetos/{id}/recursos` falha e `custos-equipe` responde com sucesso
- **THEN** as métricas e o custo por equipe aparecem, e o bloco de recursos mostra mensagem genérica

#### Scenario: Moedas diferentes no período

- **WHEN** `custos-equipe` responde `inputerror` informando moedas diferentes
- **THEN** a página mostra a mensagem de erro de entrada e não exibe valores somados

### Requirement: Somente leitura e sem backend novo

A página SHALL usar somente métodos `GET` nos endpoints listados. A página MUST NOT chamar `POST`, `PATCH` ou `DELETE` nem qualquer endpoint de notificação. A página MUST NOT depender de endpoints inexistentes, como `GET /projetos/{id}/detalhe`. A autorização real permanece no backend, e nenhum token é registrado em log ou exibido na tela.

#### Scenario: Chamadas da página

- **WHEN** a página é carregada e o usuário interage com ela
- **THEN** somente chamadas `GET` a `/projetos/{id}`, `/projetos/{id}/custos-equipe`, `/projetos/{id}/recursos` e `/projetos/{id}/equipes` são feitas

#### Scenario: Acesso de leitura

- **WHEN** um usuário com role leitura acessa o detalhamento
- **THEN** a página exibe os dados normalmente, sem controles de escrita
