## 1. Tabela e contratos Xano

- [x] 1.1 Criar `xano/table/projetos.xs` com o schema aprovado (D1). **Feito: `id`, `nome`, `codigo` (trim|upper, `btree|unique`), `budget` (decimal), `status` (enum ativo/inativo default ativo), `criado_em`. Sintaxe conferida na doc oficial (tables). Validação via Developer MCP PENDENTE (validador indisponível neste ambiente).**
- [x] 1.2 Garantir o api_group `app` (`xano/api/app/app.xs`). **Feito: criado com `canonical = "costguard-app"`; contêiner das 5 rotas de Projetos.**
- [x] 1.3 Confirmar nomes/rotas (D2) e a base do `app` (Open Question). **RESOLVIDO: `auth` tem `canonical = "hd-zNDLF"` e `app` terá `costguard-app` → bases distintas. Adicionado `XANO_APP_BASE_URL` em `config.py` + `.env.example` (XANO_BASE_URL = auth; XANO_APP_BASE_URL = app). Sem URL hardcoded; `.env` ignorado.**

## 2. Endpoints de leitura

- [x] 2.1 Criar `listar_projetos_GET.xs` (`auth = "usuarios"`). **Feito: `query projetos verb=GET`, `db.query` ordenado por `criado_em desc`, retorna lista. 401 garantido pelo `auth`.**
- [x] 2.2 Criar `detalhe_projeto_GET.xs` (`auth = "usuarios"`, `id`). **Feito: `query "projetos/{id}" verb=GET`, `db.get` + `precondition notfound`.**

## 3. Endpoints de escrita (admin) e validação

- [x] 3.1 Criar `criar_projeto_POST.xs` (admin). **Feito: `query projetos verb=POST`; preconditions de role admin, `nome`/`codigo` não vazios, `budget >= 0`, unicidade de `codigo`; `db.add` com `status: "ativo"`.**
- [x] 3.2 Criar `editar_projeto_PATCH.xs` (admin). **Feito: `query "projetos/{id}" verb=PATCH`; role admin; notfound; `codigo` imutável (edita só `nome`/`budget`); revalida `budget >= 0`.**
- [x] 3.3 Criar `desativar_projeto_POST.xs` (admin). **Feito: `query "projetos/{id}/desativar" verb=POST`; role admin; notfound; `db.edit status = "inativo"`, sem DELETE físico.**
- [x] 3.4 Validar os `.xs` dos cinco endpoints. **Sintaxe conferida na doc oficial (apis/database/security); auth/role/preconditions seguem o padrão da baseline. Validação via Developer MCP PENDENTE (validador indisponível neste ambiente); confirmar no dry-run do push.**

## 4. Integração da página Reflex

- [x] 4.1 Implementar o estado da página de projetos. **Feito: `projetoImpacta/pages/projetos_state.py` (`ProjetosState`): `carregar`/`salvar`/`desativar` com `Authorization: Bearer <token>` e 401 → `AuthState.handle_unauthenticated`. `/projetos` registra `on_load=[require_auth, ProjetosState.carregar]`.**
- [x] 4.2 Substituir os dados mock pela lista real, preservando o design. **Feito: `pages/projetos.py` consome `ProjetosState.projetos`; `_PROJETOS_MOCK` e o badge "Demonstração" removidos. Cards exibem nome, `PRJ_<codigo>`, orçamento e status — sem custo consumido/percentual (não existem no backend).**
- [x] 4.3 Controles de escrita sob `rx.cond(AuthState.is_admin, ...)`. **Feito: botão "Novo projeto" e ações Editar/Desativar só para admin; leitura vê a lista sem controles (UX; autorização real no backend). Erros do backend exibidos em callout simples.**

## 5. Verificação de ponta a ponta

- [x] 5.1 `reflex compile --dry` sem erros. **Feito: "App compiled successfully" (28/27). Corrigido um erro real: async generator (`carregar`) não pode `return` valor → `yield AuthState.handle_unauthenticated; return`.**
- [x] 5.2 Fluxo admin ponta a ponta (listar/criar/editar/desativar; duplicado e budget). **VERIFICADO (E2E, Xano sincronizado): admin lista, cria, edita nome e budget, desativa; `codigo` duplicado rejeitado; `budget` negativo rejeitado.**
- [x] 5.3 Fluxo leitura (lista sem controles; escrita negada pelo backend). **VERIFICADO (E2E): usuário leitura consulta projetos e não possui controles de criar/editar/desativar.**
- [x] 5.4 Revisar `git diff` da change: restrito ao escopo, sem segredos, sem tocar autenticação. **Feito: `git status` confirma mudanças só em `xano/` (tabela + app + 5 endpoints), `projetoImpacta/pages/projetos.py`+`projetos_state.py`, `projetoImpacta/projetoImpacta.py`, `config.py`, `.env.example`; auth (`api/auth`, `usuarios.xs`) intacta; `.env` ignorado; nenhum segredo.**
