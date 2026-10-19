## Purpose

Característica opcional de provedor AWS que direciona as chamadas do Cost Explorer ao AWS
Mock Simulator externo quando ativada (`usar_mock = true`), por conta
(`/aws/{identificador_conta}/ce/`), reutilizando o mesmo armazenamento JWE, a mesma
assinatura SigV4 e os mesmos fluxos de coleta e teste de conexão (sem STS), com isolamento
total do fluxo AWS real, suporte a múltiplos provedores Mock e limitações de validação
explicitamente documentadas.

## ADDED Requirements

### Requirement: Provedor com característica Mock opcional

O sistema SHALL permitir que um provedor `tipo = aws` seja marcado com `usar_mock = true`,
indicando que suas chamadas ao Cost Explorer devem usar o AWS Mock Simulator em vez do
endpoint AWS real. O `usar_mock` SHALL ter default `false`. O sistema MUST NOT criar um novo
tipo de provedor para o Mock: o provedor permanece `tipo = aws`. O sistema MUST NOT exigir que
o Mock esteja disponível para operar provedores com `usar_mock = false`.

#### Scenario: Provedor Mock é um provedor AWS com a característica ativada

- **WHEN** um admin cadastra um provedor com `tipo = aws` e `usar_mock = true`
- **THEN** o provedor é criado como `tipo = aws` com `usar_mock = true`, usando os mesmos campos (apelido, Account ID, Access Key, Secret) de um provedor AWS real

#### Scenario: Default preserva o fluxo real

- **WHEN** um provedor é criado sem informar `usar_mock`
- **THEN** o provedor é persistido com `usar_mock = false` e segue o fluxo AWS real

### Requirement: Isolamento do fluxo AWS real

O sistema SHALL garantir que a indisponibilidade, erro, inacessibilidade ou remoção do AWS
Mock Simulator NÃO afete provedores com `usar_mock = false`. Um provedor com `usar_mock = false`
MUST NOT realizar nenhuma chamada ao Mock em nenhum fluxo (teste, coleta, classificação). O
sistema MUST NOT introduzir dependência global do Mock nem alterar os defaults do fluxo AWS
real.

#### Scenario: Mock offline não afeta provedor real

- **WHEN** o AWS Mock Simulator está offline e um admin executa teste/coleta em um provedor com `usar_mock = false`
- **THEN** a operação usa o endpoint AWS real normalmente e não é impactada pela indisponibilidade do Mock

#### Scenario: Provedor real nunca chama o Mock

- **WHEN** qualquer fluxo (teste, coleta, classificação) é executado para um provedor com `usar_mock = false`
- **THEN** nenhuma requisição é feita ao domínio do Mock

### Requirement: Destino do Cost Explorer resolvido por provedor

O sistema SHALL resolver o endpoint do Cost Explorer a partir do provedor: quando
`usar_mock = false`, o endpoint AWS real atual; quando `usar_mock = true`, a base do Mock
seguida de `/aws/{identificador_conta}/ce/`, onde `{identificador_conta}` é o Account ID do
próprio provedor. A base do Mock SHALL vir de configuração de ambiente (`MOCK_BASE_URL`),
disponível **apenas no backend** e MUST NOT ser enviada ao frontend; MUST NOT ser hardcoded no
código e MUST NOT ser global por conta (o Account ID vem sempre do provedor). Ao montar a URL do
Mock, o sistema SHALL normalizar a base removendo eventual barra final, de modo que tanto
`https://host` quanto `https://host/` produzam a mesma URL e MUST NOT gerar barra dupla
(ex.: `//aws/...`). O caminho `usar_mock = false` MUST NOT ler nem depender de `MOCK_BASE_URL`.

#### Scenario: Destino Mock montado por provedor

- **WHEN** a coleta é executada para um provedor com `usar_mock = true` e `identificador_conta = <conta>`
- **THEN** a chamada ao Cost Explorer usa `{base_normalizada}/aws/<conta>/ce/`

#### Scenario: Base com barra final não gera barra dupla

- **WHEN** `MOCK_BASE_URL` termina com barra (ex.: `https://aws-mock.costguard.com.br/`)
- **THEN** a URL montada é `https://aws-mock.costguard.com.br/aws/<conta>/ce/`, sem barra dupla

#### Scenario: Destino real quando Mock desativado

- **WHEN** a coleta é executada para um provedor com `usar_mock = false`
- **THEN** a chamada usa o endpoint AWS real atual, sem ler `MOCK_BASE_URL` nem referenciar o Mock

### Requirement: Assinatura SigV4 coerente com o destino efetivo

O sistema SHALL usar uma única implementação de SigV4 para provedores reais e Mock, parametrizando
os componentes que dependem do destino de modo que a assinatura corresponda sempre ao host e ao
canonical URI efetivamente usados na requisição. Quando `usar_mock = false`, a assinatura SHALL
usar host `ce.us-east-1.amazonaws.com` e canonical URI `/` (comportamento atual). Quando
`usar_mock = true`, a assinatura SHALL usar host `aws-mock.costguard.com.br` (derivado de
`MOCK_BASE_URL`) e canonical URI `/aws/{identificador_conta}/ce/`, que são o host e o path da
requisição efetivamente enviada. O sistema MUST NOT assinar com o host AWS real e enviar a
requisição ao Mock, nem vice-versa. O sistema MUST NOT criar uma segunda implementação de SigV4.
O `service` (`ce`) e a `region` (`us-east-1`) permanecem os mesmos nos dois casos.

#### Scenario: Assinatura Mock usa host e URI do Mock

- **WHEN** a coleta ou o teste é executado para um provedor `usar_mock = true` com `identificador_conta = <conta>`
- **THEN** a requisição é assinada com host `aws-mock.costguard.com.br` e canonical URI `/aws/<conta>/ce/`, coerentes com a URL de destino

#### Scenario: Assinatura real inalterada

- **WHEN** a coleta ou o teste é executado para um provedor `usar_mock = false`
- **THEN** a requisição é assinada com host `ce.us-east-1.amazonaws.com` e canonical URI `/`, exatamente como hoje

### Requirement: Múltiplos provedores Mock

O sistema SHALL permitir N provedores com `usar_mock = true`, cada um com seu próprio Account
ID, Access Key, Secret e apelido. O sistema MUST NOT usar um Account ID, credencial ou base de
Mock global/compartilhada entre provedores. O Account ID usado na URL do Mock SHALL ser sempre
o `identificador_conta` do provedor em questão.

#### Scenario: Contas Mock independentes

- **WHEN** existem provedores Mock distintos (ex.: AWS-DATA, AWS-DEV, AWS-PROD), cada um com seu Account ID
- **THEN** cada provedor direciona suas chamadas para `{MOCK_BASE_URL}/aws/{seu_identificador_conta}/ce/`, sem compartilhar Account ID ou credencial

### Requirement: Credenciais Mock tratadas como as reais

O sistema SHALL armazenar a Access Key e o Secret de um provedor Mock pelos mesmos campos e
mecanismo de um provedor AWS real: o Secret SHALL ser cifrado via JWE e decifrado apenas em
memória quando necessário. O sistema MUST NOT retornar o Secret em respostas de API nem
registrá-lo em logs, mesmo para provedores Mock. O sistema MUST NOT enviar credenciais AWS
reais ao Mock e MUST NOT usar credenciais de um provedor Mock em endpoints AWS reais.

#### Scenario: Secret Mock cifrado e nunca exposto

- **WHEN** um admin cadastra um provedor Mock com Access Key e Secret fictícios
- **THEN** o Secret é cifrado via JWE e as respostas de API não contêm o Secret

#### Scenario: Credenciais não cruzam ambientes

- **WHEN** um provedor Mock executa uma chamada
- **THEN** a chamada vai apenas ao Mock, e credenciais de provedores reais nunca são enviadas ao Mock (e vice-versa)

### Requirement: Teste de conexão Mock sem STS

O sistema SHALL, quando `usar_mock = true`, testar a conexão SEM chamar STS. O teste SHALL
chamar o Cost Explorer do Mock com `X-Amz-Target: AWSInsightsIndexService.GetTags`, corpo
contendo `TagKey = PRJ` e um `TimePeriod` válido, assinado via SigV4 coerente com o destino do
Mock (host `aws-mock.costguard.com.br`, canonical URI `/aws/{identificador_conta}/ce/`). O teste
SHALL validar: o endpoint, o Account ID, a comunicação HTTPS, o contrato AWS JSON do Cost
Explorer e a execução da assinatura SigV4 pelo CostGuard. Uma resposta HTTP 2xx no contrato
esperado SHALL resultar em conexão OK **mesmo que a lista de Tags venha vazia**. O teste MUST NOT
ser condicionado à existência de custos nem de um projeto específico. Account ID inexistente,
resposta incompatível com o contrato, ou Mock indisponível SHALL resultar em erro sanitizado
(não silencioso). O teste Mock **MUST NOT** ser interpretado como autenticação criptográfica das
credenciais: como o Mock não valida SigV4, uma Access Key ou Secret incorreta ainda pode resultar
em conexão OK. Essa limitação SHALL ser documentada e não ocultada.

#### Scenario: Teste Mock com Account ID válido e tags vazias

- **WHEN** um admin testa a conexão de um provedor `usar_mock = true` cujo Account ID existe, o Mock responde a `GetTags` (TagKey `PRJ`) com HTTP 2xx no contrato esperado e a lista de Tags vem vazia
- **THEN** o backend define o status como `ok`, sem chamar STS e sem exigir custos ou projetos

#### Scenario: Teste Mock com Account ID inexistente ou resposta incompatível

- **WHEN** o Account ID não existe no Mock ou a resposta não segue o contrato do Cost Explorer
- **THEN** o backend define o status como `erro` e retorna uma indicação sanitizada de falha

#### Scenario: Teste Mock com Mock offline

- **WHEN** o Mock está offline ou inacessível
- **THEN** o backend define o status como `erro` e retorna uma indicação sanitizada, sem impactar provedores reais

#### Scenario: Teste Mock não autentica credenciais

- **WHEN** um provedor Mock tem Access Key/Secret incorretos mas Account ID válido e o Mock responde
- **THEN** o teste pode resultar em `ok`, pois o Mock não valida SigV4; essa limitação é documentada e não ocultada
