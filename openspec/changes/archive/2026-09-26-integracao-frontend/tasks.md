## 1. Preparação e decisões

- [x] 1.1 Resolver a Open Question do design (destino da rota `/`). **DECIDIDO (grupo): `/` continua a área principal AUTENTICADA; o visual da landing externa é adaptado como home autenticada em `/` (não site público). `/login` é a única pública; `/projetos`, `/provedores`, `/alertas`, `/usuarios` exigem sessão. Sem site institucional/marketing.**
- [x] 1.2 Consultar reflex-docs para confirmar diferenças de API relevantes entre `0.9.10.post1` e `0.9.12`. **Feito: a diferença relevante encontrada foi `App(theme=...)` depreciado em 0.9.0 → mover para `rx.plugins.RadixThemesPlugin(theme=...)` no `rxconfig.py` (aplicado). Demais componentes (box/vstack/table/dialog/menu/slider/avatar/badge/icon/image/el.input) compilam sem mudança.**
- [x] 1.3 Mapear o que entra e o que fica de fora. **Feito. Entram: `theme.py`, `components/{layout,auth_ui,pill,pulso,tabela}`, páginas `{home(landing),projetos,provedores,alertas,usuarios,login}`, assets `costguard.css`+`logo-costguard.svg`. Ficam de fora: `auth/state.py`, `auth/guards.py`, `api.py`, `components/splash.py`, `pages/{recuperacao_senha,redefinir_senha}` e o vídeo do splash (ver descartes no relatório).**

## 2. Tema e assets

- [x] 2.1 Incorporar `theme.py` em `projetoImpacta/theme.py`. **Feito: port direto dos tokens; sem imports de `costguard`.**
- [x] 2.2 Incorporar os assets. **Feito: `assets/costguard.css` e `assets/logo-costguard.svg` copiados; `favicon.ico` preservado. O vídeo do splash NÃO foi copiado (splash descartado — ver relatório).**
- [x] 2.3 Garantir a aparência (dark/accent) compatível com o `rxconfig.py` do projeto, sem alterar a versão do Reflex. **Feito: tema movido para `RadixThemesPlugin(theme=rx.theme(appearance="dark", accent_color="teal", has_background=False))` no `rxconfig.py`; `reflex==0.9.12` inalterado.**

## 3. Componentes reutilizáveis

- [x] 3.1 Incorporar os componentes aplicáveis em `projetoImpacta/components/`. **Feito: `layout.py` (app shell sidebar+topbar), `auth_ui.py` (visual do login), `pill.py`, `pulso.py`, `tabela.py`. Imports adaptados; grep confirma zero imports `costguard`.**
- [x] 3.2 Não incorporar a lógica de auth externa; religar ao `AuthState` do projeto. **Feito: `layout.py` usa `projetoImpacta.state.AuthState` (com `is_admin`/`initial` adicionados como `@rx.var` derivados). Os estados que chamavam API (`ContadorAlertasState`, `ContadorProvedoresState`, `SettingsState`) foram substituídos por `UIState` (modais + preferências só em memória) e status/contadores viraram apresentação/mock.**

## 4. Login (design sobre o fluxo existente)

- [x] 4.1 Aplicar o visual de login ao `pages/login.py`, mantendo `AuthState.do_login` e `{username, password}`. **Feito: card/visual de `auth_ui` sobre `rx.form(on_submit=AuthState.do_login)` com inputs `name="username"`/`name="password"`. Botão de submit próprio (type=submit) para não disparar login em duplicidade. Nenhum `LoginFormState`/`set_session`/`XANO_BASE_URL`/`SplashState` externos.**
- [x] 4.2 Exibir falha de login no visual com mensagem genérica, sem links de recuperação. **Feito: `error_banner(AuthState.login_error)` genérico; sem link "Esqueci minha senha" e sem rotas de recuperação.**

## 5. Páginas de apresentação

- [x] 5.1 Incorporar as páginas em `projetoImpacta/pages/`, substituindo chamadas de backend por dados mock. **Feito: `home.py` (visual da landing adaptado como home autenticada), `projetos.py`, `provedores.py`, `alertas.py`, `usuarios.py` — todas apresentação/mock com dados ilustrativos e badge "Demonstração — sem backend"; nenhuma chamada de API nem estado persistente.**
- [x] 5.2 Registrar as páginas no app conforme o mapa de rotas decidido (1.1), preservando `/login` pública e a proteção de sessão. **Feito: `/login` pública; `/`, `/projetos`, `/provedores`, `/alertas`, `/usuarios` com `on_load=AuthState.require_auth` (validação via `/me` preservada da capability `autenticacao`).**

## 6. Verificação

- [x] 6.1 `reflex compile --dry` sem erros e sem imports residuais de `costguard`. **Feito: "App compiled successfully" (28/27); grep por `costguard` nos `.py` do projeto não retorna imports. Deprecation de `App(theme=...)` corrigida movendo o tema para o `rxconfig.py`.**
- [x] 6.2 Regressão de autenticação (login/reload/logout/401/proteção de rota). **VERIFICADO (smoke test E2E): login válido → `/`; F5 em `/` mantém a sessão; `/projetos`, `/provedores`, `/alertas` e `/usuarios` acessíveis autenticado; logout → `/login`; acesso direto a rota protegida sem sessão → `/login`. Sem regressão na capability `autenticacao`.**
- [x] 6.3 Revisar `git diff` da change: restrito a `projetoImpacta/`, `assets/` e `rxconfig.py`, sem segredos e sem alterar Xano. **Feito: `git status`/`git diff --stat` confirmam apenas esses caminhos + `tasks.md` da change; scan sem segredos (o `XANO_BASE_URL` hardcoded externo NÃO foi trazido — o projeto lê de env via `config.py`); nenhum arquivo de `xano/` tocado.**
