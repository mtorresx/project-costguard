# provedores Specification

## Purpose

Configuração base de Provedores Cloud do CostGuard: a entidade `provedores`, com suporte inicial ao tipo AWS usando credencial somente leitura cujo segredo nunca é retornado ao frontend, suas operações de leitura (qualquer usuário autenticado) e de escrita (restritas a admin, incluindo o teste de conexão AWS executado no backend), com autenticação e autorização validadas no backend Xano, e a página `/provedores` em Reflex consumindo esses dados reais.

## Requirements

### Requirement: Entidade Provedor

O sistema SHALL persistir provedores com os campos conceituais: `id`, `apelido`, `tipo`, `identificador_conta`, `tipo_credencial`, credencial, `tag_alocacao_projeto` e `status`. O `apelido` SHALL identificar o provedor para o usuário. O `tipo` SHALL indicar o provedor cloud e, nesta fase, SHALL aceitar somente o valor `aws`. O `identificador_conta` SHALL representar a identificação da conta cloud (ex.: o Account ID AWS). O `tipo_credencial` SHALL indicar a forma de autenticação utilizada (nesta fase, chave de acesso AWS). O `tag_alocacao_projeto` SHALL representar a **Key** da tag de alocação de custo (user-defined cost allocation tag) usada para agrupar os custos por projeto no Cost Explorer (ex.: `Projeto`); SHALL ser opcional e, quando ausente, a classificação de custos por projeto MUST NOT ser executada. O `status` SHALL distinguir, no mínimo, provedor com conexão válida (`ok`), com erro de conexão (`erro`), ainda não testado (`pendente`) e desativado logicamente (`inativo`).

#### Scenario: Provedor persistido com os campos do contrato

- **WHEN** um provedor é criado com sucesso
- **THEN** ele passa a existir com `id`, `apelido`, `tipo`, `identificador_conta`, `tipo_credencial` e `status`

#### Scenario: Provedor com Key da tag de alocação definida

- **WHEN** um admin define a Key da tag de alocação de custo (`tag_alocacao_projeto`) de um provedor AWS
- **THEN** o valor é persistido no provedor e passa a ser usado como a Key do agrupamento por tag na classificação de custos por projeto

#### Scenario: Provedor sem Key da tag de alocação

- **WHEN** um provedor AWS não possui `tag_alocacao_projeto` definido
- **THEN** o provedor continua válido para a coleta base de custos, mas a classificação de custos por projeto não pode ser executada até que a Key seja definida

### Requirement: Suporte inicial exclusivo a AWS

O sistema SHALL aceitar, nesta fase, apenas provedores do tipo `aws`. Uma tentativa de cadastrar um provedor com `tipo` diferente de `aws` SHALL ser rejeitada pelo backend.

#### Scenario: Cadastro AWS aceito

- **WHEN** um admin cadastra um provedor com `tipo` igual a `aws` e dados válidos
- **THEN** o backend cria o provedor

#### Scenario: Tipo não suportado rejeitado

- **WHEN** um admin tenta cadastrar um provedor com `tipo` diferente de `aws`
- **THEN** o backend rejeita a operação com erro de validação e não cria o provedor

### Requirement: Credencial AWS somente leitura e nunca exposta

O sistema SHALL tratar a credencial AWS como uma chave de acesso composta por um identificador público (`access_key_id`) e um segredo (`secret_access_key`), provenientes de uma credencial IAM dedicada. O segredo SHALL ser armazenado de forma cifrada e protegida no backend e MUST NOT ser retornado em nenhuma resposta de API (nem em listagem, nem em detalhe, nem após criação ou edição). O sistema MUST NOT registrar o segredo em logs. O mecanismo de cifra MUST NOT reutilizar um vetor de inicialização (IV/nonce) fixo e global: cada gravação do segredo SHALL usar um IV/nonce único (armazenado de forma privada junto ao ciphertext) ou um mecanismo de criptografia autenticada que gerencie o nonce com segurança. A credencial SHALL possuir apenas permissões de leitura (privilégio mínimo) e MUST NOT ser uma credencial root; o CostGuard MUST NOT depender de permissões de escrita no provedor. Após salvo, o segredo MUST NOT ser reapresentado ao usuário; a troca do segredo SHALL ocorrer apenas pelo reenvio de um novo valor.

#### Scenario: Listagem não contém o segredo

- **WHEN** qualquer usuário autenticado lista os provedores
- **THEN** a resposta não contém o `secret_access_key` de nenhum provedor

#### Scenario: Detalhe não contém o segredo

- **WHEN** um usuário autenticado consulta o detalhe de um provedor
- **THEN** a resposta não contém o `secret_access_key`

#### Scenario: Resposta de criação não contém o segredo

- **WHEN** um admin cria um provedor enviando a credencial
- **THEN** a resposta de sucesso não contém o `secret_access_key`

#### Scenario: Segredo não é reapresentado após salvo

- **WHEN** um admin abre a edição de um provedor já cadastrado
- **THEN** o segredo salvo não é devolvido pelo backend nem reexibido na interface
- **AND** para alterar o segredo o admin precisa informar um novo valor

#### Scenario: IV/nonce não é fixo nem reutilizado globalmente

- **WHEN** o segredo de dois provedores (ou do mesmo provedor em gravações distintas) é cifrado
- **THEN** cada gravação usa um IV/nonce único, nunca um IV fixo compartilhado entre as gravações

### Requirement: Leitura de provedores por usuário autenticado

O sistema SHALL permitir que qualquer usuário autenticado liste os provedores e consulte o detalhe de um provedor. A leitura MUST NOT exigir role admin. As respostas de leitura SHALL incluir os metadados do provedor (`id`, `apelido`, `tipo`, `identificador_conta`, `tipo_credencial`, `status`) e MUST NOT incluir o segredo.

#### Scenario: Listar provedores autenticado

- **WHEN** um usuário autenticado (admin ou leitura) solicita a lista de provedores
- **THEN** o backend responde com os provedores existentes e seus status, sem o segredo

#### Scenario: Detalhe de provedor autenticado

- **WHEN** um usuário autenticado solicita o detalhe de um provedor existente
- **THEN** o backend responde com os metadados do provedor, sem o segredo

#### Scenario: Detalhe de provedor inexistente

- **WHEN** um usuário autenticado solicita o detalhe de um `id` que não existe
- **THEN** o backend responde com erro de recurso não encontrado

#### Scenario: Leitura sem autenticação

- **WHEN** uma requisição de leitura de provedores é feita sem token válido
- **THEN** o backend responde com HTTP 401

### Requirement: Cadastro de provedor restrito a admin

O sistema SHALL permitir o cadastro de provedor apenas a usuários autenticados com `role = admin`. A autorização SHALL ser validada no backend. O cadastro SHALL exigir `apelido` não vazio, `tipo` igual a `aws`, `identificador_conta` não vazio e uma credencial AWS completa (`access_key_id` e `secret_access_key`). Um provedor recém-criado SHALL iniciar com `status` indicando que a conexão ainda não foi validada (`pendente`).

#### Scenario: Admin cadastra provedor AWS válido

- **WHEN** um admin envia `apelido`, `tipo = aws`, `identificador_conta` e credencial AWS válidos
- **THEN** o backend cria o provedor com `status` pendente e o retorna sem o segredo

#### Scenario: Usuário leitura não cadastra provedor

- **WHEN** um usuário com role leitura tenta cadastrar um provedor
- **THEN** o backend nega a operação com erro de autorização e não cria o provedor

#### Scenario: Campos obrigatórios ausentes

- **WHEN** um admin tenta cadastrar um provedor sem `apelido`, sem `identificador_conta` ou sem a credencial completa
- **THEN** o backend rejeita a operação com erro de validação

### Requirement: Edição de provedor restrita a admin

O sistema SHALL permitir a edição de provedor apenas a admin, validando a autorização no backend. A edição SHALL permitir alterar metadados (`apelido`, `identificador_conta`) e, opcionalmente, substituir a credencial. Quando a credencial não for enviada na edição, o segredo armazenado SHALL ser preservado. Quando uma nova credencial for enviada, ela SHALL substituir a anterior. O `tipo` MUST NOT ser alterado para um valor não suportado.

#### Scenario: Admin edita metadados sem reenviar credencial

- **WHEN** um admin edita `apelido` ou `identificador_conta` sem enviar nova credencial
- **THEN** o backend aplica as alterações, preserva o segredo armazenado e retorna o provedor sem o segredo

#### Scenario: Admin substitui a credencial

- **WHEN** um admin envia uma nova credencial AWS na edição
- **THEN** o backend substitui o segredo armazenado pelo novo valor

#### Scenario: Usuário leitura não edita provedor

- **WHEN** um usuário com role leitura tenta editar um provedor
- **THEN** o backend nega a operação com erro de autorização

### Requirement: Teste de conexão AWS restrito a admin

O sistema SHALL permitir que um admin teste a conexão de um provedor AWS. O teste SHALL ser executado no backend, usando a credencial armazenada do provedor. Quando `usar_mock = false`, o teste SHALL realizar uma chamada somente leitura à AWS (STS `GetCallerIdentity`) que confirme a validade da credencial. Quando `usar_mock = true`, o teste MUST NOT chamar STS: SHALL chamar o Cost Explorer do Mock com `X-Amz-Target: AWSInsightsIndexService.GetTags`, corpo com `TagKey = PRJ` e um `TimePeriod` válido, assinado via SigV4 coerente com o destino do Mock (host `<URL-DO-SIMULADOR>`, canonical URI `/aws/{identificador_conta}/ce/`), validando endpoint, Account ID, comunicação HTTPS, contrato AWS JSON e a execução da assinatura pelo CostGuard. Uma resposta HTTP 2xx no contrato esperado SHALL ser sucesso mesmo que a lista de Tags venha vazia, e o teste MUST NOT ser condicionado à existência de custos ou de um projeto específico. O resultado do teste SHALL atualizar o `status` do provedor: `ok` quando a verificação aplicável tem sucesso, `erro` quando a credencial é inválida (real) ou a chamada falha (real ou mock: Account ID inexistente, resposta incompatível ou Mock indisponível). No caso real, `status = ok` SHALL significar apenas que a credencial AWS foi autenticada com sucesso e MUST NOT ser interpretado como confirmação de que as demais permissões necessárias ao CostGuard estão disponíveis. No caso Mock, `status = ok` SHALL significar apenas que o endpoint respondeu e o Account ID é acessível e MUST NOT ser interpretado como autenticação criptográfica das credenciais: como o Mock não valida SigV4, uma Access Key ou Secret incorreta ainda pode resultar em `ok` — limitação que SHALL ser documentada e não ocultada. O teste MUST NOT exigir que o segredo seja enviado pelo frontend, e a resposta do teste MUST NOT conter o segredo. A falha de conexão MUST NOT ser silenciosa: o backend SHALL retornar uma indicação de falha ao solicitante.

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

### Requirement: Desativação de provedor restrita a admin

O sistema SHALL permitir desativar um provedor apenas a admin, alterando seu `status` para `inativo`. O sistema MUST NOT excluir fisicamente o provedor nesta operação.

#### Scenario: Admin desativa provedor

- **WHEN** um admin desativa um provedor
- **THEN** o `status` do provedor passa a `inativo` e o registro continua existindo

#### Scenario: Usuário leitura não desativa provedor

- **WHEN** um usuário com role leitura tenta desativar um provedor
- **THEN** o backend nega a operação com erro de autorização

### Requirement: Página /provedores com dados reais

O frontend SHALL exibir em `/provedores` os provedores reais obtidos do backend, substituindo os dados mock. As requisições SHALL incluir o token da sessão e reagir a HTTP 401 conforme o tratamento central já existente (limpando a sessão e redirecionando ao login). A página SHALL exibir o status da conexão de cada provedor. Os controles de cadastro, configuração e teste de conexão SHALL ser apresentados apenas quando o usuário for admin; essa ocultação é apenas UX e a autorização real permanece no backend. A página MUST NOT reapresentar o segredo de uma credencial já salva. O design incorporado SHALL ser preservado.

#### Scenario: Lista real exibida com status

- **WHEN** um usuário autenticado acessa `/provedores`
- **THEN** a página exibe os provedores obtidos do backend com seus status, sem dados mock

#### Scenario: Admin vê controles de escrita e teste

- **WHEN** um admin acessa `/provedores`
- **THEN** a página oferece ações de cadastrar/configurar provedor e testar a conexão

#### Scenario: Usuário leitura apenas consulta

- **WHEN** um usuário com role leitura acessa `/provedores`
- **THEN** a página exibe os provedores e seus status sem os controles de cadastrar, configurar, testar ou desativar
- **AND** essa ocultação é apenas UX; a autorização real permanece no backend

#### Scenario: Segredo nunca reexibido na interface

- **WHEN** um admin abre a configuração de um provedor já cadastrado
- **THEN** o campo do segredo aparece vazio e o valor salvo não é exibido

#### Scenario: 401 na página de provedores

- **WHEN** uma requisição de `/provedores` recebe HTTP 401
- **THEN** o frontend limpa a sessão e redireciona ao login, conforme o tratamento existente

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

### Requirement: Tag Key de equipe do provedor

O sistema SHALL persistir no provedor um campo opcional `tag_alocacao_equipe` que representa a
**Tag Key** da tag de equipe (user-defined tag) usada para identificar a equipe dona de um recurso
no inventário (Tag Key recomendada: `EQP`). Esse campo SHALL ser aceito e persistido na criação e
na edição do provedor, e SHALL ser retornado na listagem e no detalhe como metadado (não é
segredo). O valor padrão/recomendado SHALL ser `EQP`: um provedor criado sem informar o campo
SHALL resultar em `tag_alocacao_equipe = "EQP"`; quando o admin informar explicitamente outro
valor válido, este SHALL ser preservado; uma edição (PATCH) que não envie o campo MUST NOT apagar
o valor existente. Para provedores legados cujo valor seja `null`/vazio (ex.: após a adição do
campo), a sincronização SHALL aplicar o fallback `EQP` em tempo de execução, de modo que esses
provedores não transformem silenciosamente todos os recursos em "Sem responsável". O
`tag_alocacao_equipe` MUST NOT ser hardcoded na lógica: o valor efetivo vem do provedor (ou do
fallback padrão `EQP`). A inclusão deste campo MUST NOT expor o segredo da credencial nem
alterar as demais regras do provedor (autorização admin para escrita, leitura por autenticado,
JWE preservado).

#### Scenario: Provedor com Tag Key de equipe definida

- **WHEN** um admin define `tag_alocacao_equipe = EQP` em um provedor AWS
- **THEN** o valor é persistido e passa a ser usado como a Tag Key de equipe na resolução do inventário

#### Scenario: Provedor criado sem informar a Tag Key de equipe usa o default EQP

- **WHEN** um admin cria um provedor AWS sem informar `tag_alocacao_equipe`
- **THEN** o provedor é persistido com `tag_alocacao_equipe = "EQP"`

#### Scenario: Provedor legado com Tag Key de equipe nula usa fallback EQP na sincronização

- **WHEN** um provedor legado tem `tag_alocacao_equipe` nulo/vazio e uma sincronização é executada
- **THEN** o inventário usa a Key `EQP` por fallback, resolvendo equipes normalmente, sem marcar todos os recursos como "Sem responsável" apenas por causa do campo ausente

#### Scenario: Leitura inclui a Tag Key de equipe sem segredo

- **WHEN** um usuário autenticado lista ou consulta o detalhe de provedores
- **THEN** as respostas incluem `tag_alocacao_equipe` (quando definido) e nunca o `secret_access_key`
