# custos-equipe Specification

## Purpose
Classificação do custo AWS diário por projeto e equipe do CostGuard. Consulta o AWS Cost Explorer
agrupado pelas Tag Keys de projeto e de equipe configuradas no provedor (fallback `EQP` para a de
equipe), atribui cada custo à equipe pela dimensão histórica de tag do período e preserva o custo de
projeto ativo sem equipe como "Sem responsável", sem equipe fictícia. A persistência é idempotente,
com reconciliação da janela por `sync_id` executada só após sucesso completo, e cada execução é
registrada de forma não silenciosa. Inclui a leitura agregada por projeto e equipe no intervalo.
Admin-only para classificar, read-only na AWS e segredos jamais expostos.

## Requirements

### Requirement: Tag Keys de projeto e de equipe vindas do provedor

O sistema SHALL identificar o projeto pela Tag Key `provedores.tag_alocacao_projeto` e a equipe
pela Tag Key efetiva de equipe, que SHALL ser `provedores.tag_alocacao_equipe` quando preenchida
(após `trim`) e `EQP` quando nula ou vazia. Em cada grupo do Cost Explorer, o sistema SHALL obter
o valor removendo exatamente o prefixo `"<Key>$"` e normalizando com `trim` e maiúsculas. O valor
de projeto SHALL ser comparado com `projetos.codigo` e o valor de equipe com `equipes.codigo`
dentro do projeto. O sistema MUST NOT fazer hardcode das Keys `PRJ` ou `EQP`, exceto o fallback
`EQP` da Key de equipe.

#### Scenario: Keys configuradas no provedor

- **WHEN** o provedor tem `tag_alocacao_projeto = PRJ` e `tag_alocacao_equipe = EQP` e a AWS retorna o grupo `["PRJ$PAGAMENTOS", "EQP$BACKEND"]`
- **THEN** o custo é atribuído ao projeto `PAGAMENTOS` e à equipe `BACKEND` desse projeto

#### Scenario: Key de equipe customizada

- **WHEN** o provedor tem `tag_alocacao_equipe = Team` e a AWS retorna o grupo `["PRJ$PAGAMENTOS", "Team$BACKEND"]`
- **THEN** o custo é atribuído à equipe `BACKEND` do projeto `PAGAMENTOS`

#### Scenario: Fallback da Key de equipe

- **WHEN** o provedor tem `tag_alocacao_equipe` nula ou vazia
- **THEN** a consulta usa `EQP` como Key de equipe

### Requirement: Entidade Custo por equipe

O sistema SHALL persistir o custo diário por equipe em uma entidade `custos_equipe`, distinta de
`custos` e `custos_projeto`, com, no mínimo: `provedor_id`, `projeto_id`, `equipe_id` (nullable),
`codigo_equipe` (normalizado `trim` + maiúsculas), `data` (um dia), `metrica`, `valor`, `moeda`,
`estimado`, `sync_id` (privado) e `coletado_em`. A chave única SHALL ser
`(provedor_id, projeto_id, codigo_equipe, data, metrica)`. O valor SHALL ser expresso em USD. As
entidades `custos`, `custos_projeto` e `recursos` MUST NOT ter registros criados, alterados ou
removidos por esta capability.

#### Scenario: Custo por equipe persistido

- **WHEN** uma classificação bem-sucedida processa um dia, um projeto ativo e uma equipe com custo
- **THEN** passa a existir um registro com provedor, projeto, equipe, `codigo_equipe`, data, métrica, valor em USD, `estimado` e o `sync_id` da execução

#### Scenario: Demais tabelas de custo permanecem inalteradas

- **WHEN** a classificação de custos por equipe é executada
- **THEN** nenhum registro de `custos`, `custos_projeto` ou `recursos` é criado, alterado ou removido

### Requirement: Classificação por equipe restrita a admin

O sistema SHALL permitir executar `POST /provedores/{id}/classificar-custos-equipe` apenas a
usuários autenticados com `role = admin`, validando a autorização no backend. Um usuário com
`role = leitura` MUST NOT conseguir executar a classificação. Uma requisição sem token válido
SHALL receber HTTP 401.

#### Scenario: Admin executa a classificação

- **WHEN** um admin solicita a classificação de custos por equipe de um provedor elegível
- **THEN** o backend executa a classificação

#### Scenario: Usuário leitura não executa

- **WHEN** um usuário com role leitura solicita a classificação
- **THEN** o backend nega com erro de autorização, sem chamar a AWS e sem gravar nada

#### Scenario: Sem autenticação

- **WHEN** a requisição é feita sem token válido
- **THEN** o backend responde com HTTP 401

### Requirement: Pré-condições do provedor

O sistema SHALL executar a classificação apenas para um provedor existente com `tipo = aws`,
`status = ok`, credencial presente e `tag_alocacao_projeto` preenchida. Se qualquer condição
falhar, o sistema MUST NOT chamar a AWS e SHALL rejeitar a operação com indicação explícita do
motivo (`notfound` para provedor inexistente, `inputerror` nos demais casos). Para
`usar_mock = true`, a ausência de `MOCK_BASE_URL` SHALL ser rejeitada da mesma forma.

#### Scenario: Provedor sem Key de projeto

- **WHEN** o provedor não tem `tag_alocacao_projeto` preenchida
- **THEN** o backend rejeita sem chamar a AWS e informa o motivo

#### Scenario: Provedor não conectado

- **WHEN** o provedor tem `status` igual a `pendente`, `erro` ou `inativo`
- **THEN** o backend rejeita sem chamar a AWS e informa o motivo

#### Scenario: Provedor inexistente

- **WHEN** o `id` informado não corresponde a nenhum provedor
- **THEN** o backend responde com erro de recurso não encontrado

### Requirement: Consulta ao Cost Explorer agrupada por projeto e equipe

O sistema SHALL consultar o AWS Cost Explorer (`GetCostAndUsage`) com granularidade `DAILY`,
métrica `UnblendedCost` e `GroupBy` contendo exatamente
`[{Type: TAG, Key: <Key de projeto>}, {Type: TAG, Key: <Key de equipe efetiva>}]`, sem a dimensão
`SERVICE`. A chamada SHALL reutilizar a mesma implementação de SigV4 e a mesma resolução de
destino por `usar_mock` dos endpoints existentes (AWS real ou AWS Mock, com host e canonical URI
coerentes). A consulta SHALL ser read-only e o sistema MUST NOT ativar, desativar ou alterar Cost
Allocation Tags nem qualquer recurso da conta.

#### Scenario: Corpo da consulta

- **WHEN** a classificação é executada
- **THEN** o backend envia `GetCostAndUsage` com `DAILY`, `UnblendedCost` e `GroupBy` com as duas Tag Keys do provedor, sem `SERVICE`

#### Scenario: Provedor Mock

- **WHEN** a classificação é executada para um provedor com `usar_mock = true`
- **THEN** a chamada vai para `{MOCK_BASE_URL normalizada}/aws/{identificador_conta}/ce/`, assinada com o host e o canonical URI do Mock

#### Scenario: Provedor real nunca chama o Mock

- **WHEN** a classificação é executada para um provedor com `usar_mock = false`
- **THEN** a chamada vai para o endpoint real do Cost Explorer, sem ler `MOCK_BASE_URL`

### Requirement: Paginação completa antes de persistir

O sistema SHALL buscar todas as páginas (`NextPageToken`), reassinando cada uma, antes de gravar
qualquer registro em `custos_equipe`. Se qualquer página falhar, ou se o limite de iterações de
paginação for atingido com `NextPageToken` ainda presente, o sistema SHALL tratar a execução como
`erro` sanitizado, MUST NOT gravar nem remover registros de `custos_equipe` e MUST NOT executar a
reconciliação.

#### Scenario: Resposta paginada

- **WHEN** a AWS retorna `NextPageToken`
- **THEN** o backend busca as páginas seguintes e só passa à persistência após a última

#### Scenario: Falha em uma página

- **WHEN** uma das páginas falha
- **THEN** nenhum registro de `custos_equipe` é gravado ou removido, e a execução é registrada como `erro` com mensagem sanitizada

#### Scenario: Limite de paginação atingido

- **WHEN** o limite de iterações é atingido com `NextPageToken` ainda presente
- **THEN** a execução é registrada como `erro`, sem persistência e sem reconciliação

### Requirement: Normalização e agregação dos valores de tag

O sistema SHALL normalizar os valores de projeto e de equipe com `trim` e maiúsculas e SHALL
considerar vazio um valor que fique vazio após o `trim`. Antes de persistir, o sistema SHALL
agregar em memória, somando `valor`, todos os grupos que resultem na mesma chave
`(projeto_id, codigo_equipe, data)`. Valores zero e negativos SHALL ser persistidos como
retornados pela AWS. O sistema MUST NOT somar grupos com unidades (`Unit`) diferentes na mesma
chave: se isso ocorrer, a execução SHALL terminar com `status = erro` e mensagem sanitizada,
antes de qualquer persistência e sem reconciliação.

#### Scenario: Variantes de caixa e espaço são somadas

- **WHEN** no mesmo dia a AWS retorna `["PRJ$PAGAMENTOS", "EQP$BACKEND"]` com 10 e `["PRJ$pagamentos", "EQP$ backend "]` com 5
- **THEN** é gravado um único registro para `PAGAMENTOS`/`BACKEND` naquele dia com valor 15

#### Scenario: Valor só com espaços

- **WHEN** a AWS retorna o valor de equipe `"EQP$   "` para um projeto ativo
- **THEN** o custo é tratado como "Sem responsável"

#### Scenario: Custo zero

- **WHEN** um grupo de projeto ativo retorna `Amount = "0"`
- **THEN** o registro é persistido com valor 0

#### Scenario: Unidades diferentes na mesma chave

- **WHEN** dois grupos que resultam na mesma chave `(projeto_id, codigo_equipe, data)` vêm com `Unit` diferentes
- **THEN** a execução termina com `status = erro` e mensagem sanitizada, nada é gravado ou removido e nenhuma conversão é feita

### Requirement: Moeda dos custos por equipe

O sistema SHALL operar sob a premissa de que os custos são expressos em USD, coerente com o
domínio (moeda inicial USD, sem conversão de moeda) e com as coletas existentes. O sistema SHALL
persistir em `moeda` a unidade retornada pelo Cost Explorer (`Metrics.UnblendedCost.Unit`), com
`USD` apenas quando a AWS não informar a unidade, exatamente como `custos` e `custos_projeto`. O
sistema MUST NOT converter valores entre moedas e MUST NOT somar silenciosamente valores de moedas
diferentes em nenhuma agregação, seja na classificação ou na leitura.

#### Scenario: Unidade da AWS persistida

- **WHEN** a AWS retorna `Unit = "USD"` para um grupo gravado
- **THEN** o registro é persistido com `moeda = "USD"`

#### Scenario: Unidade ausente

- **WHEN** a AWS não informa `Unit` para um grupo gravado
- **THEN** o registro é persistido com `moeda = "USD"`

#### Scenario: Sem conversão cambial

- **WHEN** existe um registro com moeda diferente de USD
- **THEN** o valor é mantido como retornado pela AWS, sem conversão

### Requirement: Resolução de projeto

O sistema SHALL resolver o projeto antes da equipe. Quando o valor de projeto estiver vazio, o
custo SHALL ser contabilizado em `nao_alocados`, mesmo que haja valor de equipe. Quando não
existir projeto com o código, o sistema MUST NOT criar projeto, MUST NOT gravar custo e SHALL
contabilizar em `tags_sem_projeto`. Quando o projeto existir com `status = inativo`, o sistema
MUST NOT gravar custo, MUST NOT criar equipe e SHALL contabilizar em `projetos_inativos`. Os
contadores SHALL contar grupos da resposta da AWS. O custo não gravado MUST NOT ser removido da
coleta base `custos`.

#### Scenario: Custo sem projeto e com equipe

- **WHEN** a AWS retorna `["PRJ$", "EQP$BACKEND"]`
- **THEN** nada é gravado em `custos_equipe` e o grupo é contabilizado em `nao_alocados`

#### Scenario: Projeto desconhecido

- **WHEN** a AWS retorna `["PRJ$LEGADO", "EQP$BACKEND"]` e não existe projeto `LEGADO`
- **THEN** nenhum projeto ou equipe é criado, nada é gravado e o grupo é contabilizado em `tags_sem_projeto`

#### Scenario: Projeto inativo

- **WHEN** a AWS retorna `["PRJ$MARKETING", "EQP$MARKETING"]` e o projeto `MARKETING` está inativo
- **THEN** nada é gravado, nenhuma equipe é criada e o grupo é contabilizado em `projetos_inativos`

### Requirement: Resolução de equipe e estado "Sem responsável"

Para um projeto ativo, quando o valor de equipe estiver vazio, o sistema SHALL gravar o custo com
`equipe_id = null` e `codigo_equipe = ""`, representando "Sem responsável", e MUST NOT criar
equipe fictícia para esse estado. Quando houver valor de equipe, o sistema SHALL buscar a equipe
por `(projeto_id, codigo)`, reutilizando-a se existir ou criando-a conforme a capability
`equipes` (`nome = codigo`, `auto_gerada = true`) se não existir, e SHALL gravar o custo com o
`equipe_id` resolvido e `codigo_equipe = codigo`. O sistema SHALL manter a invariante
`codigo_equipe = ""` se e somente se `equipe_id = null`.

#### Scenario: Equipe existente reutilizada

- **WHEN** a AWS retorna `["PRJ$PAGAMENTOS", "EQP$BACKEND"]` e já existe a equipe `BACKEND` no projeto
- **THEN** o custo é gravado com o `equipe_id` existente e nenhuma equipe é criada

#### Scenario: Equipe desconhecida criada

- **WHEN** a AWS retorna `["PRJ$PAGAMENTOS", "EQP$SRE"]` e não existe a equipe `SRE` no projeto ativo
- **THEN** a equipe `SRE` é criada com `auto_gerada = true`, o custo é gravado com o novo `equipe_id` e `equipes_criadas` é incrementado

#### Scenario: Sem responsável

- **WHEN** a AWS retorna `["PRJ$PAGAMENTOS", "EQP$"]`
- **THEN** o custo é gravado com `equipe_id = null` e `codigo_equipe = ""`, e nenhuma equipe é criada

### Requirement: Atribuição histórica pelo Cost Explorer

O sistema SHALL atribuir a equipe de cada custo exclusivamente a partir da dimensão de tag
retornada pelo Cost Explorer para o dia correspondente. O sistema MUST NOT usar o inventário
atual (`recursos`) para atribuir ou reclassificar custo histórico. Quando a tag de equipe mudar na
AWS, a nova equipe SHALL refletir-se nos dias que a AWS retornar com o novo valor, sem alterar
dias que a AWS continuar retornando com o valor anterior.

#### Scenario: Inventário atual não altera custo histórico

- **WHEN** um recurso hoje tem `EQP = BACKEND` no inventário, mas a AWS retorna seu custo de um dia passado como `EQP$DADOS`
- **THEN** o custo daquele dia é atribuído à equipe `DADOS`

#### Scenario: Reatribuição em períodos futuros

- **WHEN** a tag de equipe de um recurso muda de `BACKEND` para `DADOS` na AWS e a classificação é executada para um período posterior à mudança
- **THEN** o custo desse período é atribuído a `DADOS`, e os dias anteriores retornados pela AWS como `BACKEND` permanecem em `BACKEND`

### Requirement: Upsert idempotente com identificador de execução

O sistema SHALL gerar um `sync_id` único por execução. Para cada linha agregada, o sistema SHALL
atualizar o registro existente da chave única (valor, moeda, estimado, `equipe_id`, `sync_id`,
`coletado_em`) ou inserir um novo registro com o `sync_id` atual. Reexecutar a mesma janela MUST
NOT criar registros duplicados.

#### Scenario: Reexecução não duplica

- **WHEN** a classificação é executada duas vezes para o mesmo provedor e a mesma janela, sem mudanças na AWS
- **THEN** não existem registros duplicados para a mesma chave e os valores permanecem iguais

#### Scenario: Reexecução atualiza valor

- **WHEN** a AWS retorna, numa segunda execução, um valor diferente para uma chave existente
- **THEN** o registro existente é atualizado com o novo valor e o novo `sync_id`

### Requirement: Reconciliação da janela por sync_id

O `sync_id` SHALL identificar uma execução específica da classificação: é gerado uma única vez
por execução, é único entre execuções e é gravado em todo registro de `custos_equipe` inserido ou
atualizado por ela.

A reconciliação SHALL ocorrer somente se a execução tiver concluído completamente, nesta ordem:
(1) a obtenção de todas as páginas da AWS; (2) a normalização e a agregação de todos os dados; e
(3) todos os upserts. Se qualquer uma dessas etapas falhar ou não terminar, o sistema MUST NOT
executar a reconciliação.

A reconciliação SHALL remover apenas registros da tabela `custos_equipe` que satisfaçam
**todas** as condições abaixo:

- `provedor_id` igual ao provedor da execução;
- `data >= data_inicio` e `data < data_fim`, sendo `[data_inicio, data_fim)` exatamente a janela
  consultada na execução;
- `projeto_id` de um projeto com `status = ativo` no momento da reconciliação;
- `sync_id` diferente do `sync_id` da execução atual, ou nulo.

O sistema MUST NOT remover registros de outros provedores, registros com `data` fora de
`[data_inicio, data_fim)`, registros de projetos atualmente inativos, registros com o `sync_id` da
execução atual, nem registros de qualquer outra tabela. O contador `registros_removidos` SHALL
contar somente os registros removidos por essa reconciliação, e SHALL ser `0` quando a
reconciliação não ocorrer.

#### Scenario: Combinação que desapareceu é removida

- **WHEN** uma execução anterior gravou `PAGAMENTOS`/"Sem responsável" num dia e, após reprocessamento na AWS, a nova execução da mesma janela retorna esse custo apenas como `PAGAMENTOS`/`BACKEND`
- **THEN** o registro "Sem responsável" daquele dia é removido e o total do projeto não é contado em dobro

#### Scenario: Histórico de projeto inativo é preservado

- **WHEN** o projeto `MARKETING` tinha registros na janela e hoje está inativo
- **THEN** a reconciliação não remove esses registros

#### Scenario: Fora da janela e outros provedores

- **WHEN** a reconciliação é executada para o provedor A na janela `[inicio, fim)`
- **THEN** registros do provedor A fora da janela e registros de outros provedores permanecem intactos

#### Scenario: Registros da execução atual não são removidos

- **WHEN** a reconciliação é executada
- **THEN** nenhum registro com o `sync_id` da execução atual é removido, e `registros_removidos` conta apenas os registros removidos nessa reconciliação

#### Scenario: Limites da janela

- **WHEN** a janela é `[2026-09-01, 2026-10-01)` e existem registros antigos do mesmo provedor e de projeto ativo em `2026-08-31`, `2026-09-01`, `2026-09-30` e `2026-10-01`
- **THEN** apenas os registros de `2026-09-01` e `2026-09-30` são candidatos à remoção; os de `2026-08-31` e `2026-10-01` permanecem

#### Scenario: Falha nos upserts não reconcilia

- **WHEN** a execução falha durante os upserts
- **THEN** nenhum registro é removido, `registros_removidos = 0` e a execução é registrada como `erro`

#### Scenario: Falha na busca ou na normalização não reconcilia

- **WHEN** a execução falha ao obter uma página da AWS ou durante a normalização/agregação
- **THEN** nenhum registro é gravado nem removido, `registros_removidos = 0` e a execução é registrada como `erro`

### Requirement: Convergência após falha parcial

O sistema MUST NOT ser descrito nem tratado como gravação atômica, pois não há transação global
comprovada no backend. O sistema SHALL garantir: busca completa antes da persistência; upsert
idempotente; reconciliação apenas após sucesso completo; e convergência, isto é, reexecutar a
mesma janela após uma falha parcial SHALL levar ao mesmo estado de uma execução bem-sucedida
única. Uma falha durante a persistência SHALL ser registrada como `erro` com mensagem sanitizada,
não silenciosa.

#### Scenario: Reexecução após falha parcial converge

- **WHEN** uma execução falha após gravar parte dos upserts e, em seguida, a mesma janela é executada com sucesso
- **THEN** o estado final de `custos_equipe` na janela é o mesmo de uma execução bem-sucedida única, sem duplicatas e sem linhas antigas remanescentes de projetos ativos

### Requirement: Intervalo de consulta

O sistema SHALL aceitar `data_inicio` (inclusiva) e `data_fim` (exclusiva) no formato
`YYYY-MM-DD`. Quando omitidas, SHALL usar `data_inicio = hoje (UTC) − 30 dias` e
`data_fim = hoje (UTC)`. Quando `data_inicio` não for anterior a `data_fim`, SHALL rejeitar com
erro de entrada, sem chamar a AWS.

#### Scenario: Intervalo padrão

- **WHEN** um admin executa a classificação sem informar o intervalo
- **THEN** a consulta usa os últimos 30 dias completos até ontem

#### Scenario: Intervalo inválido

- **WHEN** `data_inicio` é igual ou posterior a `data_fim`
- **THEN** o backend rejeita a operação sem chamar a AWS

### Requirement: Aviso de Tag Key de equipe possivelmente não ativada

Quando houver ao menos um custo de projeto ativo na janela e nenhum deles tiver equipe (todos
"Sem responsável"), o sistema SHALL concluir a execução com `status = sucesso` e SHALL retornar e
registrar um `aviso` não bloqueante orientando a conferir se a Tag Key de equipe efetiva está
ativada como Cost Allocation Tag na conta AWS. Essa situação MUST NOT ser tratada como erro. O
sistema MUST NOT chamar `ListCostAllocationTags` para essa verificação.

#### Scenario: Nenhuma equipe na janela

- **WHEN** todos os custos de projetos ativos da janela vêm com valor de equipe vazio
- **THEN** a execução termina com `status = sucesso`, os custos são gravados como "Sem responsável" e a resposta contém o `aviso`

#### Scenario: Há equipes na janela

- **WHEN** ao menos um custo de projeto ativo da janela tem equipe
- **THEN** a resposta não contém `aviso`

### Requirement: Estado da execução registrado

O sistema SHALL registrar cada execução em `coletas_custos_equipe` com, no mínimo: `provedor_id`,
`sync_id` (privado), `intervalo_inicio`, `intervalo_fim`, `status` (`sucesso` ou `erro`),
`registros_gravados`, `registros_removidos`, `nao_alocados`, `tags_sem_projeto`,
`projetos_inativos`, `sem_responsavel`, `equipes_criadas`, `aviso`, `mensagem` sanitizada e
`executado_em`. A resposta do endpoint SHALL conter os mesmos indicadores (exceto `sync_id`) e,
em erro, o `diagnostico` sanitizado. A falha MUST NOT ser silenciosa.

#### Scenario: Sucesso registrado

- **WHEN** uma execução termina com sucesso
- **THEN** o registro contém `status = sucesso`, o intervalo, o momento e todos os contadores

#### Scenario: Erro registrado

- **WHEN** uma execução falha na AWS, na paginação ou na persistência
- **THEN** o registro contém `status = erro` e mensagem sanitizada, e a resposta indica a falha explicitamente

### Requirement: Leitura de custos por equipe de um projeto

O sistema SHALL oferecer `GET /projetos/{id}/custos-equipe?data_inicio&data_fim` a qualquer
usuário autenticado, sem exigir role admin, com a mesma semântica e o mesmo padrão de intervalo da
classificação. A leitura MUST NOT disparar coleta nem escrita. A resposta SHALL agregar os
registros de `custos_equipe` do projeto no intervalo, entre todos os provedores, e conter:
`projeto_id`, `intervalo`, `moeda`, `equipes` (lista com `equipe_id`, `codigo`, `nome` e `total`,
apenas equipes com custo no intervalo, ordenada por `codigo`), `sem_responsavel.total` e
`total_projeto` (soma das equipes mais "Sem responsável"). "Sem responsável" MUST NOT aparecer
como item de `equipes`. A resposta MUST NOT conter série diária, filtro por provedor nem
detalhamento por serviço. Projeto inexistente SHALL retornar erro de recurso não encontrado; sem
token válido, HTTP 401.

O campo `moeda` SHALL ser a moeda única dos registros agregados. Antes de somar, o sistema SHALL
verificar as moedas distintas dos registros do projeto no intervalo: se houver exatamente uma,
SHALL retorná-la em `moeda`; se não houver registros, SHALL retornar `moeda = null` com totais
zero e `equipes` vazia; se houver mais de uma, o sistema MUST NOT somar os valores e SHALL
responder com erro controlado de entrada (`inputerror`) informando que os custos do intervalo
estão em moedas diferentes e não podem ser agregados, sem conversão.

#### Scenario: Totais por equipe

- **WHEN** um usuário autenticado consulta um projeto com custos de `BACKEND`, `QA` e "Sem responsável" no intervalo
- **THEN** a resposta lista `BACKEND` e `QA` com seus totais, `sem_responsavel.total` separado e `total_projeto` igual à soma de todos

#### Scenario: Usuário leitura consulta

- **WHEN** um usuário com role leitura consulta os custos por equipe de um projeto
- **THEN** o backend responde com os totais, sem gravar nada

#### Scenario: Projeto inexistente

- **WHEN** o `id` não corresponde a nenhum projeto
- **THEN** o backend responde com erro de recurso não encontrado

#### Scenario: Moeda única

- **WHEN** todos os registros do projeto no intervalo têm `moeda = "USD"`
- **THEN** a resposta contém `moeda = "USD"` e os totais somados

#### Scenario: Moedas diferentes não são somadas

- **WHEN** os registros do projeto no intervalo têm mais de uma moeda (ex.: provedor A em `USD` e provedor B em outra unidade)
- **THEN** o backend responde com erro controlado `inputerror`, sem somar nem converter valores

#### Scenario: Intervalo sem custos

- **WHEN** o projeto não tem registros no intervalo
- **THEN** a resposta contém `moeda = null`, `equipes` vazia, `sem_responsavel.total = 0` e `total_projeto = 0`

#### Scenario: Sem autenticação de leitura

- **WHEN** a leitura é feita sem token válido
- **THEN** o backend responde com HTTP 401

### Requirement: Segredos e diagnóstico sanitizado

O sistema MUST NOT retornar nem registrar em log a AWS Secret Access Key, a chave `PROV_ENC_KEY`,
o header `Authorization` SigV4, as signing keys ou o segredo JWE decifrado. O segredo SHALL ser
decifrado apenas no backend, em memória, imediatamente antes da assinatura. O diagnóstico de erro
SHALL limitar-se a status HTTP, `Error.Code`, `Error.Message` sanitizada e `RequestId`. O
`sync_id` MUST NOT ser exposto nas respostas.

#### Scenario: Resposta sem segredos

- **WHEN** a classificação é executada, com sucesso ou erro
- **THEN** a resposta não contém Secret Access Key, `PROV_ENC_KEY`, Authorization, signing keys, JWE decifrado nem `sync_id`

#### Scenario: Diagnóstico sanitizado

- **WHEN** a classificação falha na AWS
- **THEN** o diagnóstico contém no máximo status HTTP, `Error.Code`, `Error.Message` sanitizada e `RequestId`
