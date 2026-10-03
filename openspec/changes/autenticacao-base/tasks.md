## 1. Baseline mínima do backend Xano (criada do zero)

- [ ] 1.1 Criar `xano/table/usuarios.xs` com `auth = true` e os campos: `username` (text, único), `senha_hash` (tipo `password`, sensitive), `role` (enum {admin, leitura}), `status` (enum {ativo, inativo}), `nome` (text), `email` (email, único), além de `id` e `created_at`. Verificação: schema reflete exatamente esses campos; `senha_hash` é tipo `password`; índice único em `username`; XanoScript validado via Xano Developer MCP.
- [ ] 1.2 Criar `xano/api/auth/auth.xs` definindo o api_group `auth`. Verificação: api_group `auth` existe e é o contêiner de `login` e `me`.
- [ ] 1.3 Criar `xano/api/auth/login_POST.xs`: entrada `{username, password}`; `db.get` por `username`; `security.check_password(password, senha_hash)`; rejeitar `status != "ativo"`; mensagem de erro genérica (sem enumeração); emitir token via `security.create_auth_token`. Verificação: `.xs` validado; login aceita `{username, password}` e retorna token no sucesso.
- [ ] 1.4 Criar `xano/api/auth/me_GET.xs`: `auth = "usuarios"`; resolve `$auth.id`; saída mínima `{username, role}` (pode incluir `nome`). Verificação: `.xs` validado; `/me` responde `{username, role}` com token válido e 401 sem token/token inválido.
- [ ] 1.5 Confirmar que a baseline inclui apenas os quatro artefatos acima e que o campo de senha é `senha_hash` tipo `password`. Verificação: nenhum outro artefato Xano (gestão de usuários, custos, Quick Start, addons, exemplos/IA) faz parte da change.

## 2. Verificação funcional dos endpoints Xano

- [ ] 2.1 Exercitar `login` com `{username, password}` do admin de teste cadastrado manualmente no painel Xano e verificar token na resposta. Verificação: chamada real retorna sucesso + token. Não versionar credenciais; não criar usuários por código.
- [ ] 2.2 Exercitar `login` com password incorreto, usuário inexistente e usuário inativo e verificar erro sem token e sem revelar existência da conta. Verificação: as três chamadas retornam a mesma mensagem genérica, sem token.
- [ ] 2.3 Exercitar `/me` com token válido (retorna `{username, role}`) e sem token/token inválido (retorna 401). Verificação: os dois casos observados conforme a spec.

## 3. Configuração base do frontend Reflex

- [ ] 3.1 Definir a URL base do backend Xano por configuração/variável de ambiente, sem versionar segredos, e confirmar leitura no runtime do Reflex. Verificação: URL lida de configuração e nenhum segredo em arquivos versionados (checar `.gitignore`).
- [ ] 3.2 Consultar as Reflex Agent Skills (reflex-docs) para confirmar, em `reflex==0.9.12`, as APIs de `rx.State`, event handlers com cliente HTTP (D4) e `on_load`/redirecionamento (D6). `rx.SessionStorage` e seus removedores já estão fixados por D3. Verificação: decisões do design confirmadas ou ajustadas antes de codificar.

## 4. Estado de sessão e integração com o Xano

- [ ] 4.1 Implementar o State de autenticação (token, `username`, `role`, flag de autenticado) conforme D2. Verificação: o State expõe os campos e um indicador de autenticação consultável pela UI.
- [ ] 4.2 Persistir o token/sessão em `rx.SessionStorage` conforme D3. Verificação: após login e reload da página, a sessão permanece; após fechar e reabrir o navegador, a sessão não é exigida (novo login).
- [ ] 4.3 Implementar o event handler de login que envia `{username, password}` ao endpoint `login` do Xano e estabelece a sessão em caso de sucesso (D4). O `password` MUST NOT ser logado nem persistido. Verificação: credenciais válidas estabelecem sessão; inválidas não; nenhum log expõe o password.
- [ ] 4.4 Implementar a chamada a `/me` com o token para obter/validar `username` e `role` após login e ao carregar com token presente (D8). Verificação: `username` e `role` no State refletem a resposta de `/me`.
- [ ] 4.5 Implementar o envio do token (`Authorization: Bearer <token>`) nas requisições autenticadas e o tratamento centralizado de HTTP 401, que descarta a sessão e trata o usuário como não autenticado (D4, D7). Verificação: requisição autenticada inclui o token; um 401 simulado limpa a sessão.
- [ ] 4.6 Implementar o logout local, descartando token e dados de sessão do cliente. Verificação: após logout, o token não é mais enviado e o usuário é tratado como não autenticado.

## 5. Rotas e proteção

- [ ] 5.1 Implementar a página de login em `/login` (campos `username` e `password`, submissão e mensagem de falha genérica). Verificação: credenciais válidas encaminham a `/`; inválidas exibem falha sem revelar existência da conta.
- [ ] 5.2 Implementar a área autenticada mínima em `/` e sua proteção com redirecionamento para `/login` quando não houver sessão (D6). `/login` permanece pública. Verificação: acesso não autenticado a `/` redireciona a `/login`; acesso autenticado exibe `/`; `/login` não redireciona usuário não autenticado.

## 6. Verificação de ponta a ponta

- [ ] 6.1 Compilar o app Reflex (`reflex compile --dry`) e verificar ausência de erros de compilação. Verificação: compila sem erros.
- [ ] 6.2 Executar o fluxo completo com o admin de teste: acesso não autenticado a `/` → redirecionado a `/login` → login válido → sessão com `username`/`role` → navegação em `/` → reload mantém sessão → logout → volta a `/login`. Verificação: fluxo conforme os cenários da spec.
- [ ] 6.3 Verificar expiração/401: com token inválido ou expirado, o frontend limpa a sessão e redireciona a `/login`. Verificação: comportamento conforme "Frontend reage a 401".
- [ ] 6.4 Revisar `git diff` da change e confirmar ausência de segredos/credenciais versionados e que apenas os artefatos no escopo (baseline Xano + frontend) foram alterados. Verificação: diff limpo e restrito ao escopo desta change.
