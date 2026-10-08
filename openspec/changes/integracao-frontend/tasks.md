## 1. Preparação e decisões

- [ ] 1.1 Resolver a Open Question do design (destino da rota `/`): landing pública em `/` com a área autenticada em `/app` (ou `/dashboard`), **ou** landing em `/landing` mantendo `/` como área autenticada. Verificação: decisão registrada na change antes de registrar rotas; redirecionamentos de `require_auth` alinhados à decisão.
- [ ] 1.2 Consultar reflex-docs para confirmar diferenças de API relevantes entre `0.9.10.post1` e `0.9.12` nos componentes usados pelo frontend externo. Verificação: lista de ajustes necessários anotada antes de portar o código.
- [ ] 1.3 Mapear, a partir de `C:\frontend-costguard` (branch `development-fernando-alertas`), exatamente quais arquivos entram (tema, assets, componentes, páginas de apresentação, visual do login) e quais ficam de fora (`auth/state.py`, `auth/guards.py`, `recuperacao_senha`, `redefinir_senha`, e `splash`/`api` se acoplados). Verificação: lista de inclusão/exclusão registrada, coerente com D7.

## 2. Tema e assets

- [ ] 2.1 Incorporar `theme.py` em `projetoImpacta/theme.py`, adaptando imports. Verificação: `projetoImpacta` importa o tema sem referência a `costguard`.
- [ ] 2.2 Incorporar os assets (`costguard.css`, `logo-costguard.svg`, `videos/logo-loading.mp4`) em `assets/` do projeto, sem sobrescrever o `favicon.ico` existente indevidamente. Verificação: assets presentes e referenciados por caminho do projeto; `.gitignore` não bloqueia os assets necessários.
- [ ] 2.3 Garantir a aparência (dark/accent) de forma compatível com o `rxconfig.py` do projeto, sem alterar a versão do Reflex. Verificação: tema aplicado nas páginas; versão do Reflex do projeto inalterada.

## 3. Componentes reutilizáveis

- [ ] 3.1 Incorporar os componentes aplicáveis (`layout`, `pill`, `pulso`, `tabela` e os blocos visuais de formulário de login) em `projetoImpacta/components/`, com imports adaptados e compatíveis com Reflex 0.9.12. Verificação: componentes importáveis sob `projetoImpacta`; nenhum import `costguard`.
- [ ] 3.2 Não incorporar a lógica de auth externa como componente (`auth/state.py`, `auth/guards.py`); se algum componente visual depender dela, religar ao `AuthState` do projeto ou torná-lo apresentacional. Verificação: componentes incorporados não referenciam estados de auth externos.

## 4. Login (design sobre o fluxo existente)

- [ ] 4.1 Aplicar o visual de login incorporado a `projetoImpacta/pages/login.py`, mantendo `on_submit=AuthState.do_login` e o contrato `{username, password}`. Descartar `LoginFormState`, `AuthState.set_session`, `XANO_BASE_URL` externo e acoplamento a `SplashState`. Verificação: o login redesenhado envia `{username, password}` pelo fluxo atual; nenhuma lógica de auth antiga permanece.
- [ ] 4.2 Exibir a falha de login no novo visual com a mensagem genérica atual, sem links de recuperação de senha (fora do escopo). Verificação: erro genérico exibido; sem `/recuperar-senha` nem `/redefinir-senha`.

## 5. Páginas de apresentação

- [ ] 5.1 Incorporar `landing`, `alertas`, `projetos`, `provedores` e `usuarios` em `projetoImpacta/pages/`, adaptando imports e substituindo chamadas a backend inexistente por dados de apresentação/mock locais. Verificação: cada página renderiza como visual/mock, sem depender de endpoints inexistentes.
- [ ] 5.2 Registrar as páginas no `projetoImpacta/projetoImpacta.py` conforme o mapa de rotas decidido em 1.1, preservando `/login` pública e a proteção/validação de sessão da área autenticada (capability `autenticacao`). Verificação: rotas acessíveis; `require_auth`/redirecionamento intactos; `/login` pública.

## 6. Verificação

- [ ] 6.1 `reflex compile --dry` sem erros e sem imports residuais de `costguard`. Verificação: compila com sucesso; busca por `costguard` nos arquivos do projeto não retorna imports.
- [ ] 6.2 Regressão de autenticação: login válido estabelece sessão; reload mantém; logout limpa; acesso não autenticado à área protegida redireciona a `/login`; token adulterado + reload é revalidado via `/me` e limpa a sessão. Verificação: comportamento igual ao da capability `autenticacao` (sem regressão). Depende do Xano com o admin de teste; marcar pendente se o backend não estiver disponível.
- [ ] 6.3 Revisar `git diff` da change: alterações restritas a `projetoImpacta/` e `assets/` (+ ajustes mínimos de config se necessários), sem segredos versionados e sem alteração de Xano. Verificação: diff limpo e no escopo.
