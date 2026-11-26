## Contexto

A tabela `usuarios` já existe (`nome`, `username` único, `email` único, `senha_hash` do tipo `password`, `role` admin/leitura, `status` ativo/inativo). O login (`POST /login`, api_group `auth`) já recusa usuário inativo com a mensagem genérica. Não existe endpoint de gestão.

## Decisões

### D1. Endpoints no api_group `app`

Os endpoints de gestão ficam no grupo `app` (mesma base `XANO_APP_BASE_URL` das demais operações de negócio). O grupo `auth` continua com `login` e `me`.

### D2. Autorização: admin ativo

Todo endpoint de gestão carrega o usuário do token e exige `status = ativo` e `role = admin` (`accessdenied`, HTTP 403). A listagem também é restrita a admin: ela expõe e-mails (dado pessoal) e gerenciar usuários é atribuição exclusiva do admin (`project-overview.md`, seção 4).

### D3. Senha inicial definida pelo admin

Decisão do usuário (2026-10-27): sem provedor de e-mail, o admin informa a senha inicial. A senha é gravada no campo `senha_hash` (tipo `password` do Xano, que nunca armazena texto puro) e nunca retorna em resposta. Mínimo de 8 caracteres, validado no backend. O mesmo vale para `POST /usuarios/{id}/senha`.

### D4. Pelo menos um admin ativo

Um admin não pode desativar a si mesmo (verificado antes de qualquer gravação). Toda **edição** (`PATCH /usuarios/{id}`) e toda **desativação** passam por uma **trava de exclusão mútua**; com a trava, o endpoint relê o alvo, conta os admins ativos e faz uma única gravação calculada a partir dessa releitura. Se a operação deixaria o sistema sem admin ativo, é recusada com HTTP 400, sem gravar. A edição inteira passa pela trava (não só o rebaixamento) para que nenhuma gravação use um papel lido antes de uma alteração concorrente (achado da revisão pontual do Codex).

**Mecanismo (decisão do usuário em 2026-10-27: não aceitar risco de zero admins, nem diante de falhas):**

- Tabela técnica `travas` com índice único em `nome`. Adquirir = `db.add travas {nome: "admins", adquirida_em}`; o índice único garante no banco que só uma requisição por vez consegue inserir. Tentativas a cada 0,5 s, até 20 (~10 s); esgotadas, HTTP 400 "Outra operação de administração está em andamento...". Só o conflito com uma trava existente conta como "ocupado"; outra falha de banco na aquisição interrompe e responde erro genérico.
- Seção crítica sem lançar erro: releitura do solicitante (autorização refeita com a trava; HTTP 403 se deixou de ser admin ativo), releitura do alvo, contagem e uma única gravação (`db.edit`); recusa ou falha registradas em variáveis; a trava é removida no `finally` e só depois o endpoint responde o erro (`try`/`finally` sem `catch` engole o erro no XanoScript — observado no teste).
- **A trava não expira.** Uma expiração automática permitiria que outra requisição assumisse a trava enquanto a titular ainda estivesse viva e suspensa (não há limite de execução documentado no Xano), quebrando a exclusão mútua (achado bloqueante da revisão pontual). Assim, a segurança nunca depende de tempo.
- **Falhas:** a única gravação de negócio é uma instrução atômica, feita após a verificação sob a trava; não existe estado intermediário que viole a regra. Se o servidor cair depois de adquirir e antes do `finally`, a linha da trava permanece: edições e desativações de usuários respondem "Outra operação... em andamento" até que a linha seja removida da tabela `travas` no painel do Xano. O sistema nunca fica sem admin; fica, no máximo, temporariamente impedido de editar ou desativar usuários.

**Por que uma tabela nova (necessidade comprovada):**

1. `db.direct_query` (SQL direto, que permitiria um `UPDATE` atômico com `SELECT ... FOR UPDATE`) responde HTTP 403 "Not supported. Please upgrade your Xano instance." no plano atual (teste em 2026-10-27).
2. `db.transaction` não serializou duas requisições: com uma gravação na mesma linha dentro da transação e uma pausa de 6 s, a segunda requisição concluiu enquanto a primeira ainda dormia (teste em 2026-10-27). A documentação do Xano não descreve travas nem isolamento e informa que só operações de banco disparam rollback.
3. Nenhuma tabela existente oferece um índice único utilizável como trava sem gravar dados de negócio.

A tabela `travas` não guarda dados de negócio; suas linhas existem apenas durante a operação.

### D5. Unicidade

`username` e `email` são únicos (índices existentes). O backend confere antes de gravar e responde `inputerror` com mensagem específica; o índice único é a garantia final. `username` é normalizado com `trim` e não pode ter espaços; `email` com `trim|lower` e formato básico (`@` e `.` após o `@`).

### D6. Usuário desativado perde acesso

- `GET /me` responde 401 (`unauthorized`) se o usuário do token não existe ou está inativo. O frontend valida a sessão com `/me` em cada carregamento de página (`AuthState.require_auth`), então o usuário desativado é deslogado na próxima navegação.
- Endpoints de escrita existentes recebem a precondição `status == "ativo"` (`accessdenied`) logo após a de existência.

### D7. Respostas

Usuário serializado como `{id, nome, username, email, role, status}`. Nunca `senha_hash`. Erros seguem o padrão Xano (`{code, message}`), que o frontend já trata em `_mensagem_erro`.

### D8. Frontend

`UsuariosState` segue o padrão de `ProjetosState`: `carregar` no `on_load`, 401 → `AuthState.handle_unauthenticated`, 403 → mensagem de acesso restrito, mensagens de erro do backend exibidas no formulário. Ações: criar, editar (nome, e-mail, papel), definir senha, desativar/reativar. A senha digitada é descartada do estado logo após a requisição, qualquer que seja o resultado (achado 3 da revisão); nova tentativa exige nova digitação. O próprio usuário logado não tem botão de desativar. Design adaptado da referência: KPIs (usuários, admins, ativos), busca, tabela com avatar de iniciais, pill de papel e indicador de status.

## Riscos

- **R1:** com muitas edições/desativações simultâneas, uma delas pode esgotar as tentativas (~10 s) e responder "Outra operação de administração está em andamento"; basta repetir. A regra é preservada.
- **R1b:** trava abandonada por falha do servidor entre a aquisição e o `finally` bloqueia edições e desativações de usuários até remoção manual da linha em `travas` (painel do Xano). Escolha deliberada de segurança sobre disponibilidade; não compromete a regra. Criação, reativação, definição de senha e login não usam a trava.
- **R1c:** se `db.add` na tabela `travas` falhar por um motivo diferente do conflito enquanto existir uma trava legítima, a falha é tratada como "ocupado" e, esgotadas as tentativas, a resposta é "Outra operação... em andamento" (mensagem imprecisa; nenhuma gravação ocorre). O XanoScript não expõe de forma documentada o tipo do erro capturado.
- **R2:** endpoints somente leitura não conferem `status`; um token emitido antes da desativação ainda lê dados por até 8 h via chamada direta à API. A interface desloga na próxima navegação (D6). Aceito nesta change.
- **R3:** testes que criam ou alteram usuários gravariam dados reais; sem autorização, são verificados por precondições que falham antes da escrita e por revisão.
