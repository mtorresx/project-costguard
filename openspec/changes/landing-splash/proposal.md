## Por quê

Pedido do usuário (2026-11-03): incorporar a landing page e a animação de entrada pós-login feitas no frontend de referência (`pages/landing.py`, `components/splash.py` e `assets/videos/logo-loading.mp4`) e **suavizar a transição** da animação para o painel.

## O que muda

- **Landing pública em `/`**, adaptada do design da referência (navbar com âncoras, hero, Quem somos, O que fazemos, CTA, rodapé). O texto foi restrito ao que o CostGuard faz: a referência citava Azure/GCP, projeções de orçamento e alertas por Slack/Teams/e-mail (fora do escopo) e um mockup com números fictícios. A ilustração do painel passa a não exibir números (as regras operacionais do projeto, §16) e o rodapé não tem links para páginas inexistentes. Usuário com sessão é levado ao painel.
- **Painel autenticado passa de `/` para `/inicio`** (menu, logotipo e redirecionamentos atualizados).
- **Animação de entrada pós-login** com o vídeo do logotipo, acima das rotas. Transição suavizada em relação à referência:
  - fade-in curto do overlay sobre o login (a referência aparecia de uma vez);
  - a rota troca para o painel logo no início, **por baixo do overlay opaco**, para os dados carregarem durante o vídeo (a referência só trocava no fim e revelava o painel ainda carregando);
  - ao terminar, o logotipo some com fade e leve aproximação e o overlay se dissolve em 800 ms com curva suave (a referência usava 350 ms);
  - sem animação para quem pede "reduzir movimento".
- Link "Voltar ao início" na tela de login, para a landing.

## Capabilities

### New Capabilities

- `landing-publica`: landing page pública.
- `splash-pos-login`: animação de entrada após o login.

### Modified Capabilities

- `autenticacao`: rotas — `/` pública (landing), painel autenticado em `/inicio`; login bem-sucedido encaminha ao painel pela animação de entrada.

## Impacto

- **Reflex:** novos `pages/landing.py` e `components/splash.py`; `projetoImpacta.py` (rotas e `extra_app_wraps`), `state.py` (encaminhamento após `/me`), `components/layout.py` (links do menu e do logotipo), `pages/login.py` (link de volta), `pages/home.py` (docstring).
- **Assets:** `assets/videos/logo-loading.mp4` (copiado da referência, 683 KB).
- **Xano:** nenhum.

## Fora do escopo

- Recuperação e redefinição de senha da referência (adiadas por decisão do usuário).
- Páginas de Privacidade, Termos e Contato.
