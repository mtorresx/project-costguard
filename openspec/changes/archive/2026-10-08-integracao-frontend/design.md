## Context

Ver `proposal.md` — Why. Esta change integra o design do frontend externo (frontend de referência, em sua branch de desenvolvimento, pacote `costguard`, `reflex==0.9.10.post1`) ao projeto principal (raiz do repositório, pacote `projetoImpacta`, `reflex==0.9.12`), sem substituir a autenticação já implementada e validada (capability `autenticacao`).

Estado atual relevante (inspecionado):

- **Projeto principal** — `projetoImpacta/`: `state.py` (`AuthState` com `token`/`username`/`role` em `rx.SessionStorage`; `do_login`, `load_me`, `require_auth` validando via `/me`, `handle_unauthenticated`, `logout`); `config.py` (`XANO_BASE_URL` via env); `pages/login.py` (login funcional); `projetoImpacta.py` registra `/` (área autenticada protegida, `on_load=require_auth`) e `/login` (pública). Contrato: `POST /login {username,password}`, `GET /me {username,role}`.
- **Frontend externo** — `costguard/`: `theme.py`; `components/` (`layout`, `pill`, `pulso`, `splash`, `tabela`, `auth_ui`); `pages/` (`landing`, `alertas`, `projetos`, `provedores`, `usuarios`, `login`, `recuperacao_senha`, `redefinir_senha`); `auth/` (`state.py`, `guards.py`); `api.py`; `assets/` (`costguard.css`, `logo-costguard.svg`, `videos/logo-loading.mp4`, `favicon.ico`). O `rxconfig.py` externo usa tema Radix dark (`appearance="dark"`, `accent_color="blue"`, `has_background=False`) e `stylesheets=["/costguard.css"]`.

Divergências que esta change precisa resolver (não inventar):
1. **Rotas**: no externo `/` é landing pública e autenticados vão a um dashboard; no projeto principal `/` é a área autenticada protegida.
2. **Autenticação**: o login externo usa o contrato antigo (`usuario`/`senha`, `me_data.get("usuario")`), um `LoginFormState` próprio e `AuthState.set_session` + `SplashState`. O projeto usa `username`/`password`/`role` e `AuthState.do_login`.
3. **Versão do Reflex**: externo `0.9.10.post1` → projeto `0.9.12`.

## Goals / Non-Goals

**Goals:**
- Trazer tema, assets, componentes e páginas de apresentação para `projetoImpacta`, com imports adaptados e compatíveis com Reflex 0.9.12.
- Aplicar o visual de login ao login funcional existente, preservando contrato e `AuthState`.
- Resolver o mapa de rotas sem quebrar a proteção/validação de sessão atuais.

**Non-Goals (design):**
- Não portar a lógica de auth externa (`auth/state.py`, `auth/guards.py`, `LoginFormState`, `SplashState` acoplado ao login) como substituta.
- Não implementar backend para projetos/usuários/provedores/alertas; páginas sem backend ficam mock.
- Não trazer `recuperacao_senha`/`redefinir_senha` (fora do escopo).
- Não alterar `rxconfig.py` do projeto de forma a mudar a versão do Reflex.

## Decisions

### D1 — Fronteira: externo é design, principal é lógica
Incorporar apenas apresentação (tema, assets, componentes, markup das páginas). Lógica, configuração e autenticação permanecem as do projeto principal. Nada do pacote `costguard` deve restar como import.

### D2 — Renomear pacote e adaptar imports `costguard` → `projetoImpacta`
Todos os módulos trazidos passam a viver sob `projetoImpacta/` e seus imports relativos/absolutos são reescritos (`from costguard...` / `from .. import theme` → equivalentes em `projetoImpacta`). O CSS referenciado passa a `stylesheets=["/costguard.css"]` servido de `assets/` do projeto (o nome do arquivo pode ser mantido).

### D3 — Mapa de rotas (decisão a confirmar na implementação)
Conflito real entre `/` landing-pública (externo) e `/` área-autenticada (projeto). Proposta de resolução que preserva a autenticação:
- `/login` permanece a página pública de login (com o novo visual).
- As páginas de apresentação são registradas em rotas próprias: `/landing` (ou a landing como pública), `/projetos`, `/provedores`, `/alertas`, `/usuarios`.
- A área autenticada protegida atual (`/`) é preservada; se a landing pública assumir `/`, a área autenticada passa a uma rota como `/app` ou `/dashboard`, atualizando `require_auth`/redirecionamentos de forma consistente com a capability `autenticacao`.
- **Decisão exata do destino de `/` fica como Open Question**, pois afeta navegação observável; resolver com o grupo antes de registrar as rotas. Em nenhuma hipótese a proteção/validação de sessão é removida.

### D4 — Login: reusar visual, manter fluxo
Aproveitar os blocos visuais de `components/auth_ui` e o layout do card de login externo, mas ligados ao `AuthState.do_login` atual e ao contrato `{username, password}`. Descartar `LoginFormState`, `AuthState.set_session`, `XANO_BASE_URL` do externo e o acoplamento ao `SplashState`. O "Esqueci minha senha" e links para recuperação não são incorporados (fora do escopo).

### D5 — Páginas sem backend ficam mock
`alertas`, `projetos`, `provedores`, `usuarios` e `landing` entram como apresentação. Onde o markup externo chamava API (via `api.py`/estados próprios), substituir por dados de apresentação/mock locais, sem depender de endpoints inexistentes. Não criar integração de backend.

### D6 — Adaptação Reflex 0.9.10.post1 → 0.9.12 (upgrade)
Ajustar apenas o necessário para compilar na versão do projeto (assinaturas de componentes/props que tenham mudado entre as versões). Confirmar diferenças via reflex-docs no apply. Sem downgrade; o projeto permanece em 0.9.12. `requirements.txt` do projeto não regride.

### D7 — Componentes/arquivos a excluir da incorporação
Não trazer (ou trazer sem fiação de lógica): `auth/state.py`, `auth/guards.py`, `api.py` (se só servia às páginas com backend), `pages/recuperacao_senha.py`, `pages/redefinir_senha.py`. `splash.py` só é incorporado se desacoplado do fluxo de login; caso contrário fica fora.

## Risks / Trade-offs

- **Conflito de rota `/` (D3)** → Mitigação: decisão explícita antes de registrar rotas; a proteção de sessão nunca é removida. Registrado em Open Questions.
- **Diferenças de API entre Reflex 0.9.10 e 0.9.12 (D6)** → Mitigação: `reflex compile --dry` como porta de verificação; corrigir props/assinaturas conforme reflex-docs.
- **Páginas externas acopladas à auth/estados antigos** → Mitigação: trazer só o markup/visual; religar ao `AuthState` atual ou converter em mock (D4/D5), sem herdar o contrato antigo.
- **Regressão na autenticação** → Mitigação: a capability `autenticacao` é preservada; validar login/`/me`/logout/401 após a integração.

## Open Questions

- **Destino da rota `/`**: a landing pública assume `/` (movendo a área autenticada para `/app` ou `/dashboard`) ou a landing fica em `/landing` e `/` continua sendo a área autenticada protegida? Afeta navegação observável e os redirecionamentos de `require_auth`; decidir com o grupo antes de registrar as páginas. Não altera os requisitos da capability `autenticacao`, apenas o caminho da área protegida.
