# provedores Specification

## Purpose

Configuração base de Provedores Cloud do CostGuard: a entidade `provedores`, com suporte inicial ao tipo AWS usando credencial somente leitura cujo segredo nunca é retornado ao frontend, suas operações de leitura (qualquer usuário autenticado) e de escrita (restritas a admin, incluindo o teste de conexão AWS executado no backend), com autenticação e autorização validadas no backend Xano, e a página `/provedores` em Reflex consumindo esses dados reais.

## Requirements

### Requirement: Entidade Provedor

O sistema SHALL persistir provedores com os campos conceituais: `id`, `apelido`, `tipo`, `identificador_conta`, `tipo_credencial`, credencial e `status`. O `apelido` SHALL identificar o provedor para o usuário. O `tipo` SHALL indicar o provedor cloud e, nesta fase, SHALL aceitar somente o valor `aws`. O `identificador_conta` SHALL representar a identificação da conta cloud (ex.: o Account ID AWS). O `tipo_credencial` SHALL indicar a forma de autenticação utilizada (nesta fase, chave de acesso AWS). O `status` SHALL distinguir, no mínimo, provedor com conexão válida (`ok`), com erro de conexão (`erro`), ainda não testado (`pendente`) e desativado logicamente (`inativo`).

#### Scenario: Provedor persistido com os campos do contrato

- **WHEN** um provedor é criado com sucesso
- **THEN** ele passa a existir com `id`, `apelido`, `tipo`, `identificador_conta`, `tipo_credencial` e `status`

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

O sistema SHALL permitir que um admin teste a conexão de um provedor AWS. O teste SHALL ser executado no backend, usando a credencial armazenada do provedor para realizar uma chamada somente leitura à AWS (STS `GetCallerIdentity`) que confirme a validade da credencial. O resultado do teste SHALL atualizar o `status` do provedor: `ok` quando a credencial é autenticada com sucesso, `erro` quando a credencial é inválida ou a chamada falha. O `status = ok` SHALL significar apenas que a credencial AWS foi autenticada com sucesso e MUST NOT ser interpretado como confirmação de que as demais permissões necessárias ao CostGuard (ex.: Cost Explorer, listagem de recursos) estão disponíveis; essa validação pertence à funcionalidade de importação AWS. O teste MUST NOT exigir que o segredo seja enviado pelo frontend, e a resposta do teste MUST NOT conter o segredo. A falha de conexão MUST NOT ser silenciosa: o backend SHALL retornar uma indicação de falha ao solicitante.

#### Scenario: Teste bem-sucedido atualiza status para ok

- **WHEN** um admin testa a conexão de um provedor cuja credencial AWS é válida
- **THEN** o backend confirma a autenticação da credencial (STS), define o `status` do provedor como `ok` e retorna sucesso sem o segredo
- **AND** o `status = ok` indica apenas credencial autenticada, não a validação de todas as permissões futuras do CostGuard

#### Scenario: Teste com credencial inválida atualiza status para erro

- **WHEN** um admin testa a conexão de um provedor cuja credencial AWS é inválida ou cuja chamada falha
- **THEN** o backend define o `status` do provedor como `erro` e retorna uma indicação explícita de falha

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
