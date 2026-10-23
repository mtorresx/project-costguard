## 1. Análise/adaptação da UI (referência visual)

- [x] 1.1 Mapear os padrões visuais reutilizáveis já presentes no projeto (`app_shell`, `rx.dialog`, `pill`, `th`, tokens de `theme`) e confirmar que cobrem a UI do fluxo (modal, tabela/lista, badges, botões, loading). Verificação: lista de componentes/padrões a reutilizar registrada; nenhum novo componente visual necessário além dos existentes. NÃO alterar `C:\frontend-costguard`.

## 2. Estado Reflex

- [x] 2.1 Criar `pages/descoberta_state.py` com `DescobertaState` (campos: `aberto`, `provedor_id`, `tag_key`, `descobertos`, `selecionados`, `loading_descoberta`, `loading_importacao`, `erro`, `feedback`) e eventos `abrir`/`fechar`, seguindo o padrão do projeto (`AuthState`, `httpx`, `get_xano_app_base_url()`). Verificação: app compila (`reflex compile --dry`); abrir/fechar alterna `aberto` e guarda `provedor_id`.

## 3. Chamada descobrir-projetos

- [x] 3.1 Implementar o evento `descobrir`: `POST /provedores/{id}/descobrir-projetos` com `Authorization: Bearer`, tratando 401 via `AuthState.handle_unauthenticated`; preencher `tag_key` e `descobertos` em sucesso; em `status="erro"`/HTTP não-2xx, preencher `erro` sanitizado (usar `mensagem`, nunca `diagnostico`). Verificação: sucesso popula a lista; erro popula mensagem sanitizada; 401 redireciona ao login.

## 4. Apresentação dos resultados

- [x] 4.1 No modal (`rx.dialog` em `pages/provedores.py`), renderizar os `descobertos` com `codigo` e um `pill` "Já existe" (existente) ou "Novo" (novo), reutilizando o design atual. Verificação: itens existentes e novos aparecem visualmente distintos; sem redesenho.

## 5. Seleção de novos projetos

- [x] 5.1 Novos (`existente=false`) exibem `rx.checkbox` ligado a `selecionados`; existentes não têm checkbox. Implementar `toggle_codigo` e `selecionar_todos_novos`. Verificação: marcar/desmarcar atualiza `selecionados`; "selecionar todos" marca só os novos; existentes nunca selecionáveis.

## 6. Chamada importar-projetos

- [x] 6.1 Implementar o evento `importar`: `POST /provedores/{id}/importar-projetos` com body `{ codigos: <selecionados> }` e `Authorization: Bearer`; tratar 401 central. Verificação: envia exatamente os códigos selecionados; backend cria só inexistentes (confirmado no E2E do backend).

## 7. Loading / error / success

- [x] 7.1 Controlar `loading_descoberta`/`loading_importacao` (spinners + botões desabilitados, impedindo duplo clique) e o botão "Importar" desabilitado quando `selecionados` vazio. Verificação: durante cada chamada o botão correspondente fica desabilitado; importar indisponível sem seleção.
- [x] 7.2 Montar o `feedback` de sucesso (ex.: "N criados, M ignorados") a partir de `criados`/`ignorados`, sem expor `diagnostico`/dados técnicos. Verificação: feedback legível; nenhum dado técnico bruto na UI.

## 8. Atualização após importação

- [x] 8.1 Após importação bem-sucedida, redescobrir (novo `descobrir`) para refletir os importados como existentes e limpar `selecionados`. Verificação: código importado passa a aparecer como "Já existe" e sai da seleção.

## 9. Controle admin/leitura

- [x] 9.1 Exibir a ação "Descobrir projetos" e todos os controles de importação apenas sob `rx.cond(AuthState.is_admin, ...)`. Verificação: ação e controles condicionados a `AuthState.is_admin`; fluxo admin validado; validação autenticada com usuário `role=leitura` adiada para a task 11.2/change futura; autorização real permanece no backend.

## 10. Validação local

- [x] 10.1 Compilar o app Reflex (`reflex compile --dry`) após as alterações e revisar que não há import de `costguard` nem dependência do protótipo externo. Verificação: compilação sem erros; nenhuma referência ao pacote externo.
- [x] 10.2 Validar a change com `openspec validate frontend-descoberta-projetos-aws --strict`. Verificação: validação passa sem erros.

## 11. E2E

- [x] 11.1 (E2E admin, validado) Com um provedor AWS/Mock elegível (`tag_alocacao_projeto=PRJ`): abrir o modal, descobrir (existentes vs novos corretos), selecionar os novos, importar, ver o feedback (criados/ignorados) e confirmar que a redescoberta mostra os importados como existentes. Verificação: fluxo admin completo funciona na UI; sem regressão nos fluxos existentes de provedores. [Evidências: modal abre; loading OK; existentes com "Já existe" e sem checkbox; novo com "Novo" + checkbox; selecionar-todos-os-novos e contador OK; importar desabilitado sem seleção; importação cria o projeto (persistido no Xano, visível em /projetos); feedback de sucesso; seleção limpa; modal segue aberto; redescoberta automática; item importado vira "Já existe" e perde o checkbox.]
- [x] 11.2 Registrar o adiamento do E2E com `role=leitura` para uma change futura. Nesta change foi validado o fluxo administrativo; a ocultação da ação "Descobrir projetos" para usuários de leitura permanece implementada por `rx.cond(AuthState.is_admin, ...)`, porém o E2E autenticado com usuário `role=leitura` não foi executado e será validado separadamente. Verificação: adiamento explicitamente documentado, sem afirmar que o E2E de leitura passou.
