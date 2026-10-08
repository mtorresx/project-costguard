## Why

Outro integrante desenvolveu, em um repositório separado (`C:\frontend-costguard`, branch `development-fernando-alertas`), o design visual do CostGuard: tema, componentes reutilizáveis e as telas de landing, alertas, projetos, provedores e usuários, além de um visual de login. O projeto oficial (`C:\projetoImpacta`) já tem a autenticação base implementada e validada, mas visualmente ainda está mínimo.

Esta change incorpora esse design ao projeto principal **sem** substituir a lógica existente. O frontend externo é fonte de **design e componentes**; o projeto principal continua sendo a fonte de verdade para **lógica, configuração e autenticação**. O objetivo é dar ao MVP acadêmico uma interface coesa, preservando integralmente a autenticação (AuthState, SessionStorage, `/login`, `/me`, logout e tratamento de 401).

## What Changes

- **Incorporar o design visual**: `theme.py` (tokens de cor/tipografia), `assets/` (CSS, logo, vídeo) e os `components/` reutilizáveis aplicáveis (layout, pill, pulso, tabela e os blocos visuais de formulário de login).
- **Incorporar as páginas visuais** landing, alertas, projetos, provedores e usuários como apresentação; páginas cujo backend ainda não existe permanecem **visuais/mock**.
- **Incorporar o design da página de login ao login funcional já existente** — reusar o visual (card, campos, banner de erro), mantendo o fluxo e o contrato atuais (`AuthState.do_login` com `{username, password}`).
- **Adaptar imports** do pacote externo `costguard` para o pacote atual `projetoImpacta`.
- **Adaptar o frontend para a versão atual do Reflex do projeto** (`reflex==0.9.12`); o externo usa `0.9.10.post1`. É adaptação para cima — **não** há downgrade.
- **Registrar as páginas necessárias no app** (`app.add_page`), preservando o mapa de rotas da autenticação atual.
- **Preservar** AuthState, `rx.SessionStorage`, `/login`, `/me`, logout e tratamento de 401 — sem substituir a autenticação.

## Capabilities

### New Capabilities

- `interface-frontend`: Interface visual do CostGuard em Reflex — tema, assets e componentes reutilizáveis incorporados do frontend externo; páginas landing, alertas, projetos, provedores e usuários (as sem backend permanecem como apresentação/mock); e o design do login aplicado ao login funcional existente. Define o comportamento observável de navegação/apresentação e a fronteira com a autenticação, que permanece inalterada.

### Modified Capabilities

<!-- Nenhum requisito da capability `autenticacao` é alterado. Esta change preserva o contrato e o comportamento de autenticação existentes; apenas reusa o visual do login sobre o fluxo atual. -->

## Impact

- **Frontend Reflex (projeto principal — escopo desta change)**:
  - Novos: `projetoImpacta/theme.py`, `projetoImpacta/components/` (os reutilizáveis aplicáveis), `projetoImpacta/pages/{landing,alertas,projetos,provedores,usuarios}.py`, e `assets/` (CSS/logo/vídeo).
  - Alterados: `projetoImpacta/projetoImpacta.py` (registro das páginas, mantendo a proteção de rota atual) e `projetoImpacta/pages/login.py` (aplicar o design ao login funcional existente).
  - Preservados sem alteração de lógica: `projetoImpacta/state.py` (`AuthState`), `projetoImpacta/config.py`.
- **Fonte externa (somente leitura/adaptação, não é cópia cega)**: `C:\frontend-costguard` branch `development-fernando-alertas` — origem de design/assets/componentes.
- **Configuração**: eventual ajuste de `rxconfig.py`/`requirements.txt` apenas para acomodar o visual na versão atual do Reflex, sem trocar a versão do projeto.

### Fora do escopo

- Alterar Xano; criar tabelas; criar endpoints; implementar backend de projetos, usuários, provedores ou alertas.
- Recuperação/redefinição de senha (as páginas externas correspondentes **não** são incorporadas).
- Substituir a autenticação existente ou alterar seus contratos de API.
- Downgrade do Reflex.
- Trazer a lógica de auth do frontend externo (`auth/state.py`, `auth/guards.py`, `LoginFormState`) — a autenticação do projeto principal prevalece.
