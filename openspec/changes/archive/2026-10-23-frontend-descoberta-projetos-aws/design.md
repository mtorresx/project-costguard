## Context

Ver `proposal.md` — Why. Estado atual relevante (lido na análise):

- Frontend Reflex do projeto (`c:\projetoImpacta\projetoImpacta`): `AuthState` (token em
  `rx.SessionStorage`, `is_admin`, `handle_unauthenticated` para 401), `config.get_xano_app_base_url()`,
  `components/layout.app_shell`, `components/pill.pill`, `components/tabela.th`, `theme` (tokens
  `PRIMARY`, `SURFACE`, `TEXT_*`, etc.). Reflex `0.9.12`.
- `pages/provedores.py` + `pages/provedores_state.py`: já consomem o backend real (`/provedores`,
  criar/editar/listar/detalhe/testar/desativar), com modais via `rx.dialog`, ações admin-only por
  `rx.cond(AuthState.is_admin, ...)`, e tratamento de 401 via `AuthState.handle_unauthenticated`.
  O state já tem `usar_mock`/`tag_alocacao_projeto` no contrato `Provedor`.
- Backend publicado: `POST /provedores/{id}/descobrir-projetos` →
  `{ provedor_id, tag_key, status, mensagem, descobertos: [{codigo, existente, projeto_id}], diagnostico }`;
  `POST /provedores/{id}/importar-projetos` (body `{ codigos: [...] }`) →
  `{ provedor_id, criados: [{codigo, projeto_id}], ignorados: [{codigo, motivo, projeto_id}] }`.

Sobre `C:\frontend-costguard`: é um protótipo visual anterior, com **contratos divergentes** do
backend atual (multi-cloud, `credencial`/`credencial_id`, `sincronizar`, `DELETE`, `custo_mensal_usd`,
cards com `PRJ_<codigo>`). Ele é usado **apenas como referência de linguagem visual/UX**
(espaçamento, tipografia, `rx.dialog` como "sheet"/modal, `pill` de status, `th` de tabela,
padrões de loading/erro/feedback). Seus componentes `pill.py`/`tabela.py` são idênticos aos do
projeto. NÃO importar nem copiar lógica de lá; reutilizar os componentes já incorporados no
projeto.

## Goals / Non-Goals

**Goals:**

- Entregar o fluxo descobrir → revisar → selecionar novos → importar → feedback → atualizar,
  dentro de `/provedores`, admin-only.
- Reutilizar componentes/padrões existentes (sem redesenho) e o padrão de chamadas ao Xano.
- Mapear fielmente os contratos reais dos dois endpoints.

**Non-Goals (nível de design):**

- Nenhuma alteração de backend, schema, auth, classificação, coleta ou Mock.
- Nenhuma página nova; nenhuma edição em `C:\frontend-costguard`.
- Sem edição de budget no fluxo (projetos nascem budget 0 no backend).

## Decisions

### D1 — O fluxo vive em `/provedores`, num modal por provedor

A descoberta parte de um provedor específico (precisa do `id`). O ponto natural é a própria linha/
card do provedor na página `/provedores`, com uma ação admin-only "Descobrir projetos" que abre um
`rx.dialog` (mesmo padrão dos modais de criar/editar provedor). O modal concentra: lista de
descobertos, seleção dos novos, botão importar, loading/erro/feedback. Alternativa descartada:
página dedicada `/provedores/{id}/descoberta` — desnecessária para o MVP e fugiria do "sem nova
página".

### D2 — Estado em um `DescobertaState` dedicado

Criar `pages/descoberta_state.py` com um `rx.State` dedicado ao fluxo, em vez de inflar
`ProvedoresState`. Campos: `aberto` (bool), `provedor_id` (int), `tag_key` (str),
`descobertos` (lista de `{codigo, existente, projeto_id}`), `selecionados` (lista/conjunto de
códigos novos marcados), `loading_descoberta` (bool), `loading_importacao` (bool),
`erro` (str sanitizada), `feedback` (str: "X criados, Y ignorados"). Eventos: `abrir(provedor)`,
`fechar`, `descobrir`, `toggle_codigo(codigo)`, `selecionar_todos_novos`, `importar`. Segue o
padrão existente (`AuthState`, `httpx`, `get_xano_app_base_url()`, 401 → `handle_unauthenticated`).
Isso mantém `ProvedoresState` focado no CRUD e evita acoplamento. A ação "Descobrir projetos" na
página de provedores chama `DescobertaState.abrir(provedor)`.

### D3 — Contratos reais mapeados (não os do protótipo)

- **Descoberta**: POST sem corpo obrigatório; resposta tem `status` (`sucesso`/`erro`), `tag_key`,
  `descobertos[]`, `mensagem`, `diagnostico`. Em `status = "erro"` ou HTTP não-2xx → `erro`
  sanitizado (usar `mensagem` quando houver; nunca `diagnostico`).
- **Importação**: body `{ codigos: [<novos selecionados>] }`; resposta `criados[]` e `ignorados[]`
  (com `motivo`). Feedback = contagem de `criados` e, se houver, `ignorados`.
- `codigo` já vem normalizado do backend; a UI envia os códigos como recebidos dos itens novos
  selecionados (não re-normaliza).

### D4 — Distinção existentes/novos e seleção

Cada item de `descobertos`: se `existente = true` → render com `pill` "Já existe" (estilo do
`pill` de status) e **sem checkbox**; se `existente = false` → `pill` "Novo" + `rx.checkbox`
ligado a `selecionados`. "Selecionar todos os novos" marca todos os `existente = false`. O botão
"Importar selecionados" fica `disabled` quando `selecionados` está vazio ou durante
`loading_importacao` (impede duplo clique). A lista usa os elementos de tabela já existentes
(`th`) ou uma lista simples dentro do dialog, conforme o layout atual.

### D5 — Loading, erro e feedback

- `loading_descoberta`/`loading_importacao` controlam spinners e desabilitam os botões (previne
  disparo duplo). 
- Erros: mensagens claras e sanitizadas; nunca renderizar `diagnostico`/status cru. 401 →
  `AuthState.handle_unauthenticated` (padrão central).
- Após importação bem-sucedida: exibir feedback e **redescobrir** (chamar `descobrir` de novo),
  de modo que os importados retornem como `existente = true` e saiam da seleção. Opcional:
  também acionar `ProjetosState.carregar` se a lista de projetos estiver visível em outra tela;
  no MVP, a redescoberta no próprio modal já reflete o novo estado.

### D6 — Admin-only como UX

Toda a ação (botão de descobrir, checkboxes, importar) é renderizada sob `rx.cond(AuthState.is_admin, ...)`.
A segurança real é do backend (já rejeita não-admin). Nenhuma lógica de autorização nova no front.

## Risks / Trade-offs

- **Protótipo de referência divergente do backend** → mitigado: tratado só como referência visual;
  contratos reais vêm dos endpoints publicados (D3), não do protótipo.
- **Descoberta pode demorar (chamada externa AWS/Mock)** → mitigado: `loading_descoberta`, botão
  desabilitado, sem bloquear a página; timeout de httpx como nas demais chamadas.
- **Estado de seleção obsoleto após importar** → mitigado: redescoberta pós-sucesso (D5) recarrega
  `descobertos` e limpa `selecionados`.
- **Dependência de backend** → nenhuma nova identificada; os dois endpoints já existem e foram
  validados em E2E. Se algo faltar, registrar como dependência (não implementar backend).

## Dependências / Decisões que dependem do usuário

- Nenhuma dependência de backend nova. Pontos menores de UX a confirmar (não bloqueiam o MVP):
  (a) o gatilho "Descobrir projetos" fica como botão por linha/card do provedor ou dentro do
  menu de ações já existente; (b) se, além de redescobrir no modal, deve-se também atualizar a
  página `/projetos` automaticamente após importar. Ambos têm default razoável no design (botão
  por provedor; redescoberta no modal) e podem ser ajustados na implementação sem mudar as specs.
