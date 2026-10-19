## ADDED Requirements

### Requirement: Característica usar_mock do provedor

O sistema SHALL persistir no provedor um campo `usar_mock` (boolean, default `false`) que
indica se as chamadas ao Cost Explorer daquele provedor devem usar o AWS Mock Simulator. O
provedor permanece `tipo = aws`. O `usar_mock` SHALL ser aceito e persistido na criação e na
edição do provedor, e SHALL ser retornado na listagem e no detalhe como metadado. Um provedor
criado sem `usar_mock` informado SHALL ter `usar_mock = false`. A inclusão deste campo MUST NOT
expor o segredo da credencial nem alterar as demais regras (autorização admin para escrita,
leitura por usuário autenticado, JWE preservado).

#### Scenario: Criação persiste usar_mock

- **WHEN** um admin cria um provedor informando `usar_mock = true`
- **THEN** o provedor é criado com `usar_mock = true` e retornado sem o segredo

#### Scenario: Default usar_mock false

- **WHEN** um admin cria um provedor sem informar `usar_mock`
- **THEN** o provedor é persistido com `usar_mock = false`

#### Scenario: Edição altera usar_mock

- **WHEN** um admin edita um provedor alterando `usar_mock`
- **THEN** o backend aplica a alteração e retorna o provedor sem o segredo

#### Scenario: Leitura inclui usar_mock sem segredo

- **WHEN** um usuário autenticado lista ou consulta o detalhe de provedores
- **THEN** as respostas incluem `usar_mock` e nunca o `secret_access_key`

## MODIFIED Requirements

### Requirement: Teste de conexão AWS restrito a admin

O sistema SHALL permitir que um admin teste a conexão de um provedor AWS. O teste SHALL ser executado no backend, usando a credencial armazenada do provedor. Quando `usar_mock = false`, o teste SHALL realizar uma chamada somente leitura à AWS (STS `GetCallerIdentity`) que confirme a validade da credencial. Quando `usar_mock = true`, o teste MUST NOT chamar STS: SHALL chamar o Cost Explorer do Mock com `X-Amz-Target: AWSInsightsIndexService.GetTags`, corpo com `TagKey = PRJ` e um `TimePeriod` válido, assinado via SigV4 coerente com o destino do Mock (host `aws-mock.costguard.com.br`, canonical URI `/aws/{identificador_conta}/ce/`), validando endpoint, Account ID, comunicação HTTPS, contrato AWS JSON e a execução da assinatura pelo CostGuard. Uma resposta HTTP 2xx no contrato esperado SHALL ser sucesso mesmo que a lista de Tags venha vazia, e o teste MUST NOT ser condicionado à existência de custos ou de um projeto específico. O resultado do teste SHALL atualizar o `status` do provedor: `ok` quando a verificação aplicável tem sucesso, `erro` quando a credencial é inválida (real) ou a chamada falha (real ou mock: Account ID inexistente, resposta incompatível ou Mock indisponível). No caso real, `status = ok` SHALL significar apenas que a credencial AWS foi autenticada com sucesso e MUST NOT ser interpretado como confirmação de que as demais permissões necessárias ao CostGuard estão disponíveis. No caso Mock, `status = ok` SHALL significar apenas que o endpoint respondeu e o Account ID é acessível e MUST NOT ser interpretado como autenticação criptográfica das credenciais: como o Mock não valida SigV4, uma Access Key ou Secret incorreta ainda pode resultar em `ok` — limitação que SHALL ser documentada e não ocultada. O teste MUST NOT exigir que o segredo seja enviado pelo frontend, e a resposta do teste MUST NOT conter o segredo. A falha de conexão MUST NOT ser silenciosa: o backend SHALL retornar uma indicação de falha ao solicitante.

#### Scenario: Teste bem-sucedido atualiza status para ok

- **WHEN** um admin testa a conexão de um provedor `usar_mock = false` cuja credencial AWS é válida
- **THEN** o backend confirma a autenticação da credencial (STS), define o `status` do provedor como `ok` e retorna sucesso sem o segredo
- **AND** o `status = ok` indica apenas credencial autenticada, não a validação de todas as permissões futuras do CostGuard

#### Scenario: Teste com credencial inválida atualiza status para erro

- **WHEN** um admin testa a conexão de um provedor `usar_mock = false` cuja credencial AWS é inválida ou cuja chamada falha
- **THEN** o backend define o `status` do provedor como `erro` e retorna uma indicação explícita de falha

#### Scenario: Teste Mock usa GetTags e não STS

- **WHEN** um admin testa a conexão de um provedor `usar_mock = true` com Account ID válido e o Mock responde a `GetTags` (TagKey `PRJ`) com HTTP 2xx no contrato esperado, inclusive com lista de Tags vazia
- **THEN** o backend valida via Cost Explorer do Mock (sem STS, assinatura coerente com o host/URI do Mock), define o `status` como `ok` e retorna sucesso sem o segredo
- **AND** o `status = ok` indica apenas endpoint acessível e Account ID válido, não autenticação criptográfica das credenciais

#### Scenario: Teste Mock com Account ID inexistente ou Mock offline

- **WHEN** um admin testa a conexão de um provedor `usar_mock = true` cujo Account ID não existe ou cujo Mock está indisponível
- **THEN** o backend define o `status` como `erro` e retorna uma indicação sanitizada de falha, sem impactar provedores reais

#### Scenario: Usuário leitura não testa conexão

- **WHEN** um usuário com role leitura tenta testar a conexão de um provedor
- **THEN** o backend nega a operação com erro de autorização
