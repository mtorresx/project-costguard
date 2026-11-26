## ADDED Requirements

### Requirement: Gestão de usuários restrita a admin ativo

Todos os endpoints de gestão de usuários SHALL exigir token válido (HTTP 401 sem token) e SHALL negar com HTTP 403 quando o usuário do token não for `admin` ou estiver `inativo`. A autorização MUST ser aplicada no backend.

#### Scenario: Admin ativo acessa a gestão

- **WHEN** um admin ativo chama `GET /usuarios`
- **THEN** o backend responde HTTP 200 com a lista de usuários

#### Scenario: Usuário leitura é negado

- **WHEN** um usuário com role `leitura` chama qualquer endpoint de gestão de usuários
- **THEN** o backend responde HTTP 403 e não altera dados

#### Scenario: Sem token

- **WHEN** um endpoint de gestão é chamado sem token
- **THEN** o backend responde HTTP 401

### Requirement: Listagem de usuários sem segredos

`GET /usuarios` SHALL retornar todos os usuários, ativos e inativos, com `id`, `nome`, `username`, `email`, `role` e `status`. A resposta MUST NOT conter a senha nem sua representação segura.

#### Scenario: Campos da listagem

- **WHEN** um admin lista os usuários
- **THEN** cada item contém exatamente `id`, `nome`, `username`, `email`, `role` e `status`, sem `senha_hash`

### Requirement: Criação de usuário pelo admin com senha inicial

`POST /usuarios` SHALL criar um usuário com `nome`, `username`, `email`, `role` (`admin` ou `leitura`) e `senha` inicial informada pelo admin, com `status = ativo`. O backend SHALL validar: campos obrigatórios não vazios; `username` sem espaços; `email` em formato válido; `senha` com pelo menos 8 caracteres; `role` válido; `username` e `email` ainda não usados por outro usuário. Em falha de validação, SHALL responder HTTP 400 com mensagem específica e MUST NOT gravar. A senha MUST ser armazenada apenas na representação segura e MUST NOT ser retornada.

#### Scenario: Criação válida

- **WHEN** um admin envia dados válidos e um `username` e `email` inéditos
- **THEN** o usuário é criado com `status = ativo` e a resposta contém seus dados sem a senha

#### Scenario: Username duplicado

- **WHEN** o `username` informado já pertence a outro usuário
- **THEN** o backend responde HTTP 400 com mensagem de username em uso e não grava

#### Scenario: E-mail duplicado

- **WHEN** o `email` informado já pertence a outro usuário
- **THEN** o backend responde HTTP 400 com mensagem de e-mail em uso e não grava

#### Scenario: Senha curta

- **WHEN** a senha tem menos de 8 caracteres
- **THEN** o backend responde HTTP 400 e não grava

#### Scenario: E-mail inválido

- **WHEN** o e-mail não tem formato válido
- **THEN** o backend responde HTTP 400 e não grava

### Requirement: Edição de usuário

`PATCH /usuarios/{id}` SHALL permitir alterar `nome`, `email` e `role`, com as mesmas validações da criação para os campos enviados. O `username` MUST NOT ser alterável. Usuário inexistente SHALL resultar em HTTP 404.

#### Scenario: Edição válida

- **WHEN** um admin altera o nome e o papel de um usuário existente
- **THEN** o backend grava as alterações e responde com o usuário atualizado

#### Scenario: Usuário inexistente

- **WHEN** o `id` não corresponde a um usuário
- **THEN** o backend responde HTTP 404

### Requirement: Pelo menos um administrador ativo

O backend SHALL impedir qualquer operação que deixe o sistema sem administrador ativo: rebaixar para `leitura` ou desativar o único admin ativo SHALL ser recusado com HTTP 400 e mensagem explicativa, sem gravar. A garantia SHALL valer também para requisições simultâneas e diante de falhas: as edições e desativações de usuários SHALL ser executadas sob exclusão mútua garantida pelo banco, com releitura e contagem antes da única gravação, calculada a partir da releitura; a exclusão mútua MUST NOT depender de expiração por tempo; e uma falha durante a operação MUST NOT deixar o sistema sem admin ativo.

#### Scenario: Rebaixar o único admin ativo

- **WHEN** um admin tenta alterar para `leitura` o papel do único admin ativo
- **THEN** o backend responde HTTP 400 e o papel permanece `admin`

#### Scenario: Desativações simultâneas

- **WHEN** dois admins ativos são desativados ou rebaixados por requisições simultâneas
- **THEN** as operações são executadas uma de cada vez, ao final permanece pelo menos um admin ativo e a operação que reduziria a zero responde HTTP 400 sem gravar

#### Scenario: Falha durante a operação

- **WHEN** o servidor falha durante uma desativação ou rebaixamento de admin
- **THEN** nenhuma gravação parcial viola a regra e as edições e desativações seguintes são recusadas, sem gravar, até a trava pendente ser removida

#### Scenario: Desativar o único admin ativo

- **WHEN** a desativação atingiria o único admin ativo
- **THEN** o backend responde HTTP 400 e o status permanece `ativo`

### Requirement: Desativação e reativação lógicas

`POST /usuarios/{id}/desativar` SHALL alterar `status` para `inativo` e `POST /usuarios/{id}/reativar` SHALL alterar para `ativo`. Usuários MUST NOT ser excluídos fisicamente. Um admin MUST NOT poder desativar a si mesmo (HTTP 400).

#### Scenario: Desativação de outro usuário

- **WHEN** um admin desativa outro usuário, respeitada a regra de admin ativo
- **THEN** o usuário passa a `inativo`, continua listado e não consegue mais fazer login

#### Scenario: Auto desativação

- **WHEN** um admin tenta desativar a si mesmo
- **THEN** o backend responde HTTP 400 e não grava

#### Scenario: Reativação

- **WHEN** um admin reativa um usuário inativo
- **THEN** o usuário passa a `ativo` e volta a conseguir fazer login com sua senha

### Requirement: Definição de senha pelo admin

`POST /usuarios/{id}/senha` SHALL substituir a representação segura da senha do usuário pela nova senha informada, com no mínimo 8 caracteres. A senha anterior MUST NOT ser recuperável e a nova MUST NOT ser retornada.

#### Scenario: Nova senha válida

- **WHEN** um admin define uma nova senha com 8 ou mais caracteres
- **THEN** o login passa a aceitar a nova senha e não a anterior

#### Scenario: Nova senha curta

- **WHEN** a nova senha tem menos de 8 caracteres
- **THEN** o backend responde HTTP 400 e não grava

### Requirement: Página /usuarios com dados reais

O frontend SHALL exibir em `/usuarios` os usuários reais obtidos do backend, sem dados fictícios, adaptando o design da referência: indicadores de total de usuários, admins e ativos; busca por nome, username ou e-mail; tabela com nome, e-mail, papel e status. O admin SHALL ter ações de criar, editar, definir senha, desativar e reativar; o próprio usuário logado MUST NOT ter ação de desativar. Erros do backend SHALL ser exibidos de forma sanitizada. Em HTTP 401 o frontend SHALL aplicar o tratamento central; em HTTP 403 SHALL exibir aviso de acesso restrito a administradores, sem dados.

#### Scenario: Admin vê a gestão

- **WHEN** um admin acessa `/usuarios`
- **THEN** vê os usuários reais, os indicadores e as ações de gestão

#### Scenario: Usuário leitura

- **WHEN** um usuário leitura acessa `/usuarios`
- **THEN** vê o aviso de acesso restrito, sem lista e sem ações

#### Scenario: Erro de validação exibido

- **WHEN** o backend recusa uma criação por username duplicado
- **THEN** o formulário permanece aberto e exibe a mensagem do backend
