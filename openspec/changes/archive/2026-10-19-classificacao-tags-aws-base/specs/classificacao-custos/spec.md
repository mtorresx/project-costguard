## Purpose

Coleta e persistência de custos AWS atribuídos a projetos do CostGuard a partir da
convenção em que a Tag Key identifica a finalidade (recomendada `PRJ`) e o Tag Value é
diretamente o `projetos.codigo`. Consulta o AWS Cost Explorer (`GetCostAndUsage`)
agrupado por essa tag de alocação de custo, de forma read-only e idempotente, relaciona
o Value da tag ao `projetos.codigo`, persiste o custo por projeto/dia/serviço sem alterar
a tabela `custos` base, trata de modo não silencioso os casos de borda (custo sem tag,
tag sem projeto correspondente, projeto inativo, tag de alocação inativa) e registra o
estado de cada execução, com autorização validada no backend Xano e sem jamais expor
segredos.

## ADDED Requirements

### Requirement: Convenção de tag de projeto (Key = finalidade, Value = codigo)

O sistema SHALL relacionar os custos AWS aos projetos pela convenção em que a **Tag Key**
(`provedores.tag_alocacao_projeto`, Key recomendada `PRJ`) identifica a finalidade da tag e o
**Tag Value** é diretamente o `projetos.codigo` (ex.: Key `PRJ`, Value `PAGAMENTOS` ↔
`projetos.codigo = PAGAMENTOS`). Na resposta do Cost Explorer agrupada por tag, o grupo vem no
formato `"<Key>$<Value>"` (ex.: `PRJ$PAGAMENTOS`); o sistema SHALL obter o Value removendo
exatamente o prefixo `"<Key>$"` e SHALL comparar o Value diretamente com `projetos.codigo` de
forma case-insensitive (considerando que `projetos.codigo` é normalizado em maiúsculas). O
sistema MUST NOT exigir, verificar ou remover qualquer prefixo (como `PRJ_`) dentro do Value.
O sistema MUST NOT fazer hardcode da Key `PRJ`: a Key é a configurada no provedor. O sistema
MUST NOT alterar silenciosamente esta convenção.

#### Scenario: Value corresponde a projeto existente

- **WHEN** a Key configurada é `PRJ` e a classificação encontra o grupo `PRJ$PAGAMENTOS` e existe um projeto com `codigo = PAGAMENTOS`
- **THEN** o custo correspondente é atribuído a esse projeto

#### Scenario: Convenção de Key configurável (não hardcoded)

- **WHEN** a Key configurada é `Project` e a classificação encontra o grupo `Project$PAGAMENTOS` e existe um projeto com `codigo = PAGAMENTOS`
- **THEN** o custo é atribuído a esse projeto, pois o Value `PAGAMENTOS` é comparado diretamente com `projetos.codigo`

#### Scenario: Value vazio não é tag de projeto

- **WHEN** a classificação encontra um grupo cujo Value (após remover `"<Key>$"`) está vazio
- **THEN** o custo não é atribuído a nenhum projeto por essa tag e é tratado como custo não alocado

### Requirement: Entidade Custo por projeto

O sistema SHALL persistir custos atribuídos a projetos em uma entidade distinta da tabela
`custos` base, com, no mínimo: referência ao provedor de origem, referência ao projeto,
data do custo (granularidade diária), serviço AWS, métrica, valor, moeda e um indicador de
valor estimado. O valor SHALL ser expresso em USD. A entidade `custos` existente (custo por
provedor/dia/serviço) MUST NOT ter sua semântica alterada por esta capability.

#### Scenario: Custo por projeto persistido

- **WHEN** uma classificação bem-sucedida processa um dia, um projeto e um serviço com custo
- **THEN** passa a existir um registro de custo por projeto com provedor de origem, projeto, data, serviço, métrica, valor em USD e o indicador `estimado`

#### Scenario: Tabela de custos base permanece inalterada

- **WHEN** a classificação por projeto é executada
- **THEN** os registros da tabela `custos` (custo por provedor/dia/serviço) não são criados, alterados nem removidos por esta operação

### Requirement: Classificação restrita a admin

O sistema SHALL permitir executar a classificação de custos por projeto apenas a usuários
autenticados com `role = admin`. A autorização SHALL ser validada no backend. O usuário com
`role = leitura` MUST NOT conseguir executar a classificação. A leitura dos custos por
projeto MUST NOT disparar coleta ou escrita.

#### Scenario: Admin executa classificação

- **WHEN** um admin solicita a classificação de custos de um provedor elegível
- **THEN** o backend executa a classificação

#### Scenario: Usuário leitura não executa classificação

- **WHEN** um usuário com role leitura tenta executar a classificação
- **THEN** o backend nega a operação com erro de autorização e nenhuma classificação é realizada

#### Scenario: Classificação sem autenticação

- **WHEN** uma requisição de classificação é feita sem token válido
- **THEN** o backend responde com HTTP 401

### Requirement: Classificação exige provedor AWS conectado e tag de alocação definida

O sistema SHALL executar a classificação apenas para um provedor existente com `tipo = aws`
e `status = ok`. Se o provedor não existir, não for AWS, ou estiver com `status` diferente de
`ok`, o sistema MUST NOT chamar a AWS e SHALL rejeitar a operação com indicação explícita do
motivo. A classificação SHALL exigir que o provedor possua a Key da tag de alocação de custo
definida; se ela estiver ausente, o sistema MUST NOT chamar a AWS e SHALL rejeitar a operação
com indicação explícita do motivo.

#### Scenario: Provedor conectado com tag de alocação definida é aceito

- **WHEN** um admin solicita a classificação para um provedor `aws` com `status = ok` e Key da tag de alocação definida
- **THEN** o backend prossegue com a classificação

#### Scenario: Provedor sem Key da tag de alocação é rejeitado

- **WHEN** um admin solicita a classificação para um provedor sem a Key da tag de alocação definida
- **THEN** o backend rejeita a operação sem chamar a AWS e informa o motivo

#### Scenario: Provedor inativo, com erro ou pendente é rejeitado

- **WHEN** um admin solicita a classificação para um provedor com `status` igual a `inativo`, `erro` ou `pendente`
- **THEN** o backend rejeita a operação sem chamar a AWS e informa o motivo

#### Scenario: Provedor inexistente

- **WHEN** um admin solicita a classificação para um `id` de provedor que não existe
- **THEN** o backend responde com erro de recurso não encontrado

### Requirement: Consulta ao Cost Explorer agrupada por tag

O sistema SHALL obter os custos por projeto chamando o AWS Cost Explorer (`GetCostAndUsage`),
autenticado com AWS SigV4, usando a credencial do provedor decifrada apenas no backend, com
granularidade `DAILY`, métrica `UnblendedCost` e `GroupBy` incluindo `{ Type: "TAG", Key:
<tag de alocação do provedor> }`. A consulta SHALL ser read-only. O sistema SHALL mapear a
resposta de forma que o Value da tag de cada grupo (ex.: `PAGAMENTOS` em `PRJ$PAGAMENTOS`)
determine o projeto correspondente, e o serviço, a data, o valor, a moeda e o indicador
`estimado` sejam derivados da resposta. O sistema MUST NOT ativar ou desativar cost
allocation tags.

#### Scenario: Classificação diária agrupada por tag

- **WHEN** a classificação é executada para um intervalo válido
- **THEN** o backend consulta o Cost Explorer com granularidade diária, métrica `UnblendedCost` e agrupamento pela tag de alocação, atribuindo o custo de cada grupo ao projeto correspondente ao valor da tag

#### Scenario: AWS não é modificada

- **WHEN** a classificação é executada
- **THEN** o backend realiza apenas chamadas de leitura ao Cost Explorer e não altera cost allocation tags nem qualquer recurso da conta AWS

### Requirement: Paginação consolidada antes de persistir

O sistema SHALL tratar a paginação da AWS (`NextPageToken`), consultando todas as páginas
antes de persistir qualquer registro. O sistema MUST NOT persistir resultados de uma
classificação enquanto a consulta a todas as páginas não tiver sido concluída com sucesso.
Se qualquer página falhar, o sistema MUST NOT gravar um lote incompleto, SHALL registrar a
execução com `status = erro` e mensagem sanitizada, e os dados de classificações anteriores
SHALL permanecer intactos.

#### Scenario: Resposta paginada é consolidada

- **WHEN** a resposta da AWS inclui `NextPageToken`
- **THEN** o backend busca as páginas seguintes e só conclui a classificação como sucesso após processar todas

#### Scenario: Falha em uma página não altera os custos por projeto

- **WHEN** uma classificação falha ao buscar uma das páginas da AWS
- **THEN** nenhum registro desta execução é gravado ou atualizado
- **AND** o estado da execução registra `erro` com mensagem sanitizada
- **AND** os registros de classificações anteriores permanecem inalterados

### Requirement: Idempotência da classificação por período

O sistema SHALL garantir que reexecutar a classificação para o mesmo provedor e o mesmo
período não crie registros de custo por projeto duplicados. Um registro SHALL ser único pela
combinação de provedor, projeto, data, serviço e métrica. Quando uma nova execução
(bem-sucedida em todas as páginas) retornar um valor para uma combinação já existente, o
sistema SHALL atualizar o valor existente em vez de inserir um novo registro.

#### Scenario: Reexecução não duplica registros

- **WHEN** a classificação é executada duas vezes para o mesmo provedor e o mesmo período
- **THEN** não existem registros duplicados para a mesma combinação de provedor, projeto, data, serviço e métrica

#### Scenario: Reexecução atualiza valor alterado

- **WHEN** a AWS retorna, numa segunda execução, um valor diferente para uma combinação já existente
- **THEN** o registro existente é atualizado com o novo valor, sem criar duplicata

### Requirement: Intervalo de consulta definido

O sistema SHALL aceitar um intervalo de consulta com data inicial (`Start`) inclusiva e data
final (`End`) exclusiva, conforme a semântica do Cost Explorer. Quando o intervalo não for
informado, o sistema SHALL usar o padrão determinístico: os últimos 30 dias completos até
ontem, com `Start = hoje (UTC) − 30 dias` e `End = hoje (UTC)`.

#### Scenario: Intervalo informado é respeitado

- **WHEN** um admin informa `data_inicio` e `data_fim`
- **THEN** a classificação consulta exatamente esse intervalo, com `Start` inclusivo e `End` exclusivo

#### Scenario: Intervalo padrão quando omitido

- **WHEN** um admin executa a classificação sem informar o intervalo
- **THEN** o backend usa `Start = hoje (UTC) − 30 dias` e `End = hoje (UTC)`

### Requirement: Tratamento de custo sem tag de projeto

O sistema MUST NOT descartar custos cujo Value da tag de alocação esteja ausente ou vazio. Os
custos cujo grupo de tag não possua Value (ex.: `PRJ$`) SHALL ser classificados como **não
alocados** a projeto, de forma rastreável no resultado da execução (ex.: contagem/total de não
alocados), permanecendo disponíveis na coleta base `custos`. Esta capability MUST NOT atribuir
esse custo a nenhum projeto.

#### Scenario: Custo sem Value de tag é tratado como não alocado

- **WHEN** a AWS retorna um grupo cujo Value da tag de alocação está ausente ou vazio (ex.: `PRJ$`)
- **THEN** o custo não é atribuído a nenhum projeto e é contabilizado como não alocado no resultado da execução, sem ser descartado

### Requirement: Tratamento de Value sem projeto correspondente

O sistema MUST NOT criar projetos automaticamente a partir de tags. Quando a AWS retornar um
Value para o qual não exista projeto com `codigo = <Value>` no CostGuard, o sistema MUST NOT
persistir custo por projeto para essa tag e SHALL contabilizar a ocorrência de forma rastreável
no resultado da execução (ex.: contagem de Values sem projeto correspondente), sem falhar a
execução por esse motivo.

#### Scenario: Value sem projeto correspondente não cria projeto

- **WHEN** a AWS retorna o grupo `PRJ$LEGADO` e não existe projeto com `codigo = LEGADO`
- **THEN** nenhum projeto é criado, nenhum custo por projeto é persistido para `LEGADO`, e a ocorrência é registrada de forma rastreável no resultado

### Requirement: Tratamento de projeto inativo

O sistema SHALL atribuir custo apenas a projetos cujo `status` seja `ativo`. Quando o valor
de tag corresponder a um projeto com `status = inativo`, o sistema MUST NOT persistir custo
por projeto para ele e SHALL registrar a ocorrência de forma rastreável no resultado da
execução, sem descartar silenciosamente o custo subjacente (que permanece na coleta base).

#### Scenario: Projeto inativo não recebe custo por projeto

- **WHEN** o valor de tag corresponde a um projeto com `status = inativo`
- **THEN** nenhum custo por projeto é persistido para esse projeto e a ocorrência é registrada de forma rastreável no resultado

### Requirement: Tratamento de tag de alocação inativa ou não propagada

O sistema SHALL depender da tag de alocação de custo estar ativada na conta AWS para que ela
apareça no agrupamento do Cost Explorer, e MUST NOT ativá-la automaticamente. Quando a tag de
alocação definida no provedor não estiver ativa ou ainda não tiver propagado — detectável
quando a consulta agrupada por tag não retorna a dimensão de tag esperada, ou quando a
detecção por `ListCostAllocationTags`/`GetTags` indicar tag ausente ou inativa — o sistema
SHALL tratar a situação como erro sanitizado (não silencioso) e registrar o estado da
execução, sem modificar a conta AWS.

#### Scenario: Tag de alocação inativa é tratada como erro sanitizado

- **WHEN** a classificação é executada e a tag de alocação definida não está ativa ou não propagou na conta AWS
- **THEN** o backend registra a execução com `status = erro` e mensagem sanitizada, sem tentar ativar a tag na AWS

### Requirement: Estado da classificação registrado

O sistema SHALL registrar o estado de cada execução de classificação, contendo no mínimo: o
provedor de origem, o intervalo consultado, o resultado (`sucesso` ou `erro`), o momento da
execução, uma mensagem sanitizada em caso de erro, e indicadores rastreáveis dos casos de
borda (não alocados, tags sem projeto correspondente, projetos inativos ignorados). A falha
MUST NOT ser silenciosa.

#### Scenario: Classificação bem-sucedida registra estado

- **WHEN** uma classificação termina com sucesso
- **THEN** o estado registra `sucesso`, o intervalo consultado, o momento e os indicadores dos casos de borda

#### Scenario: Classificação com erro registra estado sanitizado

- **WHEN** uma classificação falha (erro da AWS, falha ao paginar ou pré-condição não satisfeita)
- **THEN** o estado registra `erro`, o momento e uma mensagem sanitizada, e o backend retorna indicação explícita de falha

### Requirement: Segredos e material de assinatura nunca expostos

O sistema MUST NOT retornar nem registrar em log: a AWS Secret Access Key, a chave
`PROV_ENC_KEY`, o header `Authorization` SigV4, as signing keys intermediárias ou o segredo
JWE decifrado. O segredo SHALL ser decifrado apenas no backend, em memória, imediatamente
antes da assinatura. Qualquer diagnóstico de erro SHALL limitar-se a: status HTTP,
`Error.Code`, `Error.Message` sanitizada e `RequestId`.

#### Scenario: Resposta da classificação não contém segredo

- **WHEN** a classificação é executada (com sucesso ou erro)
- **THEN** a resposta não contém a Secret Access Key, `PROV_ENC_KEY`, o Authorization SigV4, signing keys nem o JWE decifrado

#### Scenario: Diagnóstico de erro é sanitizado

- **WHEN** a classificação falha e um diagnóstico é retornado
- **THEN** o diagnóstico contém no máximo status HTTP, `Error.Code`, `Error.Message` sanitizada e `RequestId`
