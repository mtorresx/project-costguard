## 1. Confronto do backend Xano existente com a spec

- [ ] 1.1 Confrontar `xano/api/auth/login_POST.xs` com os requisitos "Login por username e password" e "Emissão de token": confirmar validação exclusiva no backend, comparação via `security.check_password`, rejeição de usuário inativo, mensagem única anti-enumeração e emissão de token. Verificação: registrar a conformidade item a item; divergência interrompe e é registrada sem alterar fora do escopo.
- [ ] 1.2 Confrontar `xano/api/auth/me_GET.xs` com os requisitos "Identificação do usuário autenticado" e "Validação de token e tratamento de 401": confirmar `auth = "usuarios"`, retorno com identidade e `role`, e resposta 401 para token ausente/inválido/expirado. Verificação: registrar conformidade; divergência interrompe e é registrada.
- [ ] 1.3 Confirmar via Xano Developer MCP qualquer dúvida remanescente (ex.: formato do 401, cabeçalho de autenticação esperado) e validar os `.xs` de auth com o Developer MCP. Verificação: dúvidas resolvidas e XanoScript validado antes de qualquer alteração.

## 2. Renomeação da coluna e padronização de nomenclatura no backend Xano (username/password/role)

- [ ] 2.1 Renomear em `xano/table/usuarios.xs` o campo `usuario`→`username` e o índice `btree|unique` correspondente. Não renomear `senha_hash`. Verificação: schema alvo `username`, `senha_hash`, `role`; XanoScript validado via Xano Developer MCP.
- [ ] 2.2 Padronizar `xano/api/auth/login_POST.xs`: inputs `usuario`→`username` e `senha`→`password`; `db.get field_name = "usuario"` → `"username"`; `text_password` lê o novo input; claims do JWT que referenciam o campo acompanham `username`. Verificação: `.xs` validado e login aceita `{username, password}`.
- [ ] 2.3 Padronizar `xano/api/auth/me_GET.xs`: leitura `.usuario`→`.username` e chave de resposta `usuario`→`username`, mantendo `role`. Verificação: `/me` responde `{username, role}` (podendo incluir `nome`).
- [ ] 2.4 Atualizar `xano/api/auth/criar_usuario_POST.xs`: input, `db.get field_name="usuario"`, `db.add {usuario: ...}` e resposta `{usuario: ...}` passam a usar `username`. Verificação: nenhuma referência ao campo `usuario` permanece; `.xs` validado; nenhuma outra funcionalidade alterada.
- [ ] 2.5 Atualizar `xano/api/auth/editar_usuario_PATCH.xs`: resposta expõe `.usuario`→`.username`. Verificação: nenhuma referência ao campo antigo permanece; `.xs` validado; nenhuma outra funcionalidade alterada.
- [ ] 2.6 Confirmar que endpoints de projetos/custos (`listar_projetos_GET`, `criar_projeto_POST`, `editar_projeto_PATCH`, `desativar_projeto_POST`, `deletar_usuario_DELETE`, `aws/costs_POST`) não foram tocados e que o campo de senha permanece `password senha_hash` (tipo `password`, hashing automático). Verificação: `git diff` restrito aos cinco arquivos de usuário/autenticação; campo de senha inalterado.

## 3. Verificação funcional dos endpoints Xano

- [ ] 3.1 Exercitar `login` com `{username, password}` de um usuário de teste ativo já existente (ou credenciais fornecidas pelo usuário) e verificar token na resposta. Verificação: chamada real retorna sucesso + token. Não criar nem remover usuários para o teste.
- [ ] 3.2 Exercitar `login` com password incorreto, usuário inexistente e usuário inativo e verificar erro sem token e sem revelar existência da conta. Verificação: as três chamadas retornam a mesma mensagem genérica, sem token.
- [ ] 3.3 Exercitar `/me` com token válido (retorna `{username, role}`) e sem token/token inválido (retorna 401). Verificação: os dois casos observados conforme a spec.

## 4. Configuração base do frontend Reflex

- [ ] 4.1 Definir a URL base do backend Xano por configuração/variável de ambiente, sem versionar segredos, e confirmar leitura no runtime do Reflex. Verificação: URL lida de configuração e nenhum segredo em arquivos versionados (checar `.gitignore`).
- [ ] 4.2 Consultar as Reflex Agent Skills (reflex-docs) para confirmar, em `reflex==0.9.12`, as APIs de `rx.State`, event handlers com cliente HTTP (D4) e `on_load`/redirecionamento (D6). `rx.SessionStorage` e seus removedores já estão fixados por D3. Verificação: decisões do design confirmadas ou ajustadas antes de codificar.

## 5. Estado de sessão e integração com o Xano

- [ ] 5.1 Implementar o State de autenticação (token, `username`, `role`, flag de autenticado) conforme D2. Verificação: o State expõe os campos e um indicador de autenticação consultável pela UI.
- [ ] 5.2 Persistir o token/sessão em `rx.SessionStorage` conforme D3. Verificação: após login e reload da página, a sessão permanece; após fechar e reabrir o navegador, a sessão não é exigida (novo login).
- [ ] 5.3 Implementar o event handler de login que envia `{username, password}` ao endpoint `login` do Xano e estabelece a sessão em caso de sucesso (D4). O `password` MUST NOT ser logado nem persistido. Verificação: credenciais válidas estabelecem sessão; inválidas não; nenhum log expõe o password.
- [ ] 5.4 Implementar a chamada a `/me` com o token para obter/validar `username` e `role` após login e ao carregar com token presente (D8). Verificação: `username` e `role` no State refletem a resposta de `/me`.
- [ ] 5.5 Implementar o envio do token (`Authorization: Bearer <token>`) nas requisições autenticadas e o tratamento centralizado de HTTP 401, que descarta a sessão (via `rx.remove_session_storage`/`rx.clear_session_storage`) e trata o usuário como não autenticado (D4, D7). Verificação: requisição autenticada inclui o token; um 401 simulado limpa a sessão.
- [ ] 5.6 Implementar o logout local, descartando token e dados de sessão do cliente. Verificação: após logout, o token não é mais enviado e o usuário é tratado como não autenticado.

## 6. Rotas e proteção

- [ ] 6.1 Implementar a página de login em `/login` (campos `username` e `password`, submissão e mensagem de falha genérica). Verificação: credenciais válidas encaminham a `/`; inválidas exibem falha sem revelar existência da conta.
- [ ] 6.2 Implementar a área autenticada mínima em `/` e sua proteção com redirecionamento para `/login` quando não houver sessão (D6). `/login` permanece pública. Verificação: acesso não autenticado a `/` redireciona a `/login`; acesso autenticado exibe `/`; `/login` não redireciona usuário não autenticado.

## 7. Verificação de ponta a ponta

- [ ] 7.1 Compilar e iniciar o app Reflex seguindo a skill reflex-process-management e verificar ausência de erros de compilação/execução. Verificação: app sobe sem erros.
- [ ] 7.2 Executar o fluxo completo com usuário de teste existente: acesso não autenticado a `/` → redirecionado a `/login` → login válido → sessão com `username`/`role` → navegação em `/` → reload mantém sessão → logout → volta a `/login`. Verificação: fluxo conforme os cenários da spec.
- [ ] 7.3 Verificar expiração/401: com token inválido ou expirado, o frontend limpa a sessão e redireciona a `/login`. Verificação: comportamento conforme "Frontend reage a 401".
- [ ] 7.4 Revisar `git diff` da change e confirmar ausência de segredos versionados, que nenhuma funcionalidade fora do escopo foi alterada e que endpoints de projetos/custos permanecem intactos. Verificação: diff limpo e restrito ao escopo desta change.
