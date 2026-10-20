# descoberta-projetos Specification

## Purpose
Descoberta e importação de projetos do CostGuard a partir das tags de um provedor AWS (real ou
Mock). Consulta o Cost Explorer (`GetTags`) usando a Tag Key `provedores.tag_alocacao_projeto`,
extrai os valores distintos (ignorando valor vazio), compara-os com `projetos.codigo` existentes
e permite ao admin importar explicitamente apenas os projetos inexistentes, sem duplicar, com
normalização `trim+upper`, reaproveitando o routing AWS real/Mock, o SigV4 e o isolamento já
consolidados, com autorização no backend e sem jamais expor segredos.

## Requirements

### Requirement: Descoberta restrita a admin

O sistema SHALL permitir executar a descoberta e a importação de projetos apenas a usuários
autenticados com `role = admin`. A autorização SHALL ser validada no backend. O usuário com
`role = leitura` MUST NOT conseguir executar a descoberta nem a importação. Uma requisição sem
token válido SHALL receber HTTP 401.

#### Scenario: Admin executa descoberta

- **WHEN** um admin solicita a descoberta de projetos de um provedor elegível
- **THEN** o backend executa a descoberta

#### Scenario: Usuário leitura não executa descoberta

- **WHEN** um usuário com role leitura tenta executar a descoberta ou a importação
- **THEN** o backend nega a operação com erro de autorização e nada é consultado ou gravado

#### Scenario: Descoberta sem autenticação

- **WHEN** uma requisição de descoberta ou importação é feita sem token válido
- **THEN** o backend responde com HTTP 401

### Requirement: Descoberta exige provedor AWS conectado e Tag Key definida

O sistema SHALL executar a descoberta apenas para um provedor existente com `tipo = aws` e
`status = ok`, que possua `tag_alocacao_projeto` definido. Se o provedor não existir, não for
AWS, estiver com `status` diferente de `ok`, ou não tiver a Tag Key definida, o sistema MUST NOT
chamar a AWS/Mock e SHALL rejeitar a operação com indicação explícita do motivo.

#### Scenario: Provedor elegível é aceito

- **WHEN** um admin solicita a descoberta para um provedor `aws` com `status = ok` e `tag_alocacao_projeto` definido
- **THEN** o backend prossegue com a descoberta

#### Scenario: Provedor sem Tag Key é rejeitado

- **WHEN** um admin solicita a descoberta para um provedor sem `tag_alocacao_projeto`
- **THEN** o backend rejeita a operação sem chamar a AWS/Mock e informa o motivo

#### Scenario: Provedor inativo, com erro ou pendente é rejeitado

- **WHEN** um admin solicita a descoberta para um provedor com `status` igual a `inativo`, `erro` ou `pendente`
- **THEN** o backend rejeita a operação sem chamar a AWS/Mock e informa o motivo

#### Scenario: Provedor inexistente

- **WHEN** um admin solicita a descoberta para um `id` de provedor que não existe
- **THEN** o backend responde com erro de recurso não encontrado

### Requirement: Descoberta consulta GetTags reaproveitando routing e SigV4

O sistema SHALL descobrir os valores da Tag Key chamando o Cost Explorer com `X-Amz-Target:
AWSInsightsIndexService.GetTags`, passando `TagKey = provedores.tag_alocacao_projeto` e um
`TimePeriod` válido, de forma read-only. O destino, o host e o canonical URI SHALL ser resolvidos
a partir do provedor exatamente como nas capacidades já consolidadas: `usar_mock = false` usa o
endpoint AWS real (host `ce.us-east-1.amazonaws.com`, canonical URI `/`); `usar_mock = true` usa
`{MOCK_BASE_URL}/aws/{identificador_conta}/ce/` (host do Mock, canonical URI
`/aws/{identificador_conta}/ce/`, com `MOCK_BASE_URL` apenas no backend e barra final
normalizada). A assinatura SigV4 SHALL ser a mesma implementação já existente, coerente com o
destino. O segredo SHALL ser decifrado apenas em memória. O sistema MUST NOT ativar/desativar
cost allocation tags nem modificar a conta AWS.

#### Scenario: Descoberta real usa endpoint AWS real

- **WHEN** a descoberta é executada para um provedor `usar_mock = false`
- **THEN** o backend chama `GetTags` no endpoint AWS real, assinado com host `ce.us-east-1.amazonaws.com` e canonical URI `/`

#### Scenario: Descoberta Mock usa endpoint do Mock

- **WHEN** a descoberta é executada para um provedor `usar_mock = true` e `identificador_conta = <conta>`
- **THEN** o backend chama `GetTags` em `{base_normalizada}/aws/<conta>/ce/`, assinado com host do Mock e canonical URI `/aws/<conta>/ce/`

#### Scenario: AWS/Mock não são modificados

- **WHEN** a descoberta é executada
- **THEN** o backend realiza apenas chamadas de leitura (`GetTags`) e não altera tags nem recursos

### Requirement: Paginação de GetTags consolidada

O sistema SHALL tratar a paginação de `GetTags` (`NextPageToken`, quando presente), consultando
todas as páginas e consolidando os valores antes de responder. Se qualquer página falhar, o
sistema SHALL retornar erro sanitizado (não silencioso) e MUST NOT retornar uma lista parcial
como se fosse completa.

#### Scenario: Resposta paginada é consolidada

- **WHEN** a resposta de `GetTags` inclui `NextPageToken`
- **THEN** o backend busca as páginas seguintes e só responde após consolidar todas

#### Scenario: Falha de página é erro sanitizado

- **WHEN** uma página de `GetTags` falha
- **THEN** o backend retorna erro sanitizado e não apresenta uma lista parcial como completa

### Requirement: Normalização e filtragem dos valores descobertos

O sistema SHALL normalizar cada valor de tag retornado aplicando `trim` e maiúsculas (`upper`),
coerente com `projetos.codigo` (que é `trim|upper`). O sistema SHALL ignorar valores vazios
(ex.: `PRJ$` → valor vazio) e MUST NOT considerá-los projetos. O sistema SHALL considerar apenas
valores distintos (sem repetição) no resultado da descoberta.

#### Scenario: Valor vazio é ignorado

- **WHEN** `GetTags` retorna um valor vazio para a Tag Key
- **THEN** esse valor não aparece entre os projetos descobertos

#### Scenario: Valores normalizados e distintos

- **WHEN** `GetTags` retorna valores com variação de caixa/espaços ou repetidos
- **THEN** o resultado apresenta cada código uma única vez, normalizado em `trim+upper`

### Requirement: Descoberta compara com projetos existentes sem gravar

O sistema SHALL, para cada valor descoberto, indicar se já existe um projeto com `codigo` igual
(comparação sobre o valor normalizado) e, quando existir, o identificador do projeto. A operação
de descoberta MUST NOT criar, alterar ou remover projetos nem qualquer outro dado: é estritamente
read-only. O resultado SHALL conter, no mínimo, o `provedor_id`, a `tag_key` usada e a lista de
descobertos com `codigo`, `existente` (bool) e `projeto_id` (ou nulo).

#### Scenario: Descoberta marca existentes e inexistentes

- **WHEN** a descoberta encontra os valores `PAGAMENTOS` (projeto id 4), `MARKETING` (projeto id 6) e `INFRAESTRUTURA` (sem projeto)
- **THEN** o resultado lista `PAGAMENTOS`/`existente=true`/`projeto_id=4`, `MARKETING`/`existente=true`/`projeto_id=6` e `INFRAESTRUTURA`/`existente=false`/`projeto_id=null`

#### Scenario: Descoberta não grava nada

- **WHEN** a descoberta é executada
- **THEN** nenhum projeto é criado, alterado ou removido

### Requirement: Importação explícita cria apenas projetos inexistentes

O sistema SHALL expor uma operação de importação separada (admin-only) que recebe uma lista de
códigos selecionados e cria projetos apenas para os códigos que ainda não existem. Para cada
código novo, o projeto SHALL ser criado com `nome = codigo`, `codigo = <valor normalizado
trim+upper>`, `budget = 0` e `status = ativo`. O sistema MUST NOT criar duplicados: um código
cujo projeto já existe SHALL ser ignorado (não recriado, não reativado, não alterado). O sistema
MUST NOT criar projetos durante a descoberta — a criação ocorre apenas nesta importação
explícita. O sistema SHALL ignorar entradas de código vazias na lista. O resultado SHALL
distinguir, de forma rastreável, os códigos criados dos ignorados (já existentes/invalidos).

#### Scenario: Importa apenas inexistentes

- **WHEN** um admin importa os códigos `PAGAMENTOS` (já existe) e `INFRAESTRUTURA` (não existe)
- **THEN** o backend cria apenas `INFRAESTRUTURA` com `nome = INFRAESTRUTURA`, `budget = 0`, `status = ativo`, e ignora `PAGAMENTOS` sem alterá-lo

#### Scenario: Não duplica codigo existente

- **WHEN** um admin importa um código cujo projeto já existe
- **THEN** nenhum projeto é criado para esse código e o existente permanece inalterado (inclusive seu `status`)

#### Scenario: Código vazio é ignorado na importação

- **WHEN** a lista de importação contém uma entrada de código vazia
- **THEN** o backend ignora essa entrada e não cria projeto para ela

#### Scenario: Importação restrita a admin

- **WHEN** um usuário com role leitura tenta importar projetos
- **THEN** o backend nega a operação com erro de autorização e nenhum projeto é criado

### Requirement: Segredos nunca expostos na descoberta e importação

O sistema MUST NOT retornar nem registrar em log a AWS Secret Access Key, a chave
`PROV_ENC_KEY`, o header `Authorization` SigV4, as signing keys ou o segredo JWE decifrado, em
nenhuma das operações. O segredo SHALL ser decifrado apenas no backend, em memória, imediatamente
antes da assinatura. Qualquer diagnóstico de erro SHALL limitar-se a status HTTP, `Error.Code`,
`Error.Message` sanitizada e `RequestId`. `MOCK_BASE_URL` MUST NOT ser exposta ao frontend.

#### Scenario: Resposta da descoberta não contém segredo

- **WHEN** a descoberta é executada (com sucesso ou erro)
- **THEN** a resposta não contém a Secret Access Key, `PROV_ENC_KEY`, o Authorization SigV4, signing keys nem o JWE decifrado

#### Scenario: Diagnóstico de erro é sanitizado

- **WHEN** a descoberta ou a importação falha e um diagnóstico é retornado
- **THEN** o diagnóstico contém no máximo status HTTP, `Error.Code`, `Error.Message` sanitizada e `RequestId`
