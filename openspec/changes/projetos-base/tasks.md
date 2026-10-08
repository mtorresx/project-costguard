## 1. Tabela e contratos Xano

- [ ] 1.1 Criar `xano/table/projetos.xs` com o schema aprovado (D1): `id`, `nome` (text, trim), `codigo` (text, trim|upper, único), `budget` (decimal), `status` (enum ativo/inativo, default ativo), `criado_em`. Índice `btree|unique` em `codigo`. Verificação: schema conforme D1; XanoScript validado via Xano Developer MCP (ou doc oficial se o validador não estiver disponível).
- [ ] 1.2 Garantir o api_group `app` (`xano/api/app/app.xs`) para hospedar as rotas de Projetos. Verificação: api_group `app` existe e é o contêiner das rotas.
- [ ] 1.3 Confirmar a convenção de nomes/rotas (D2) e como o `XANO_BASE_URL` cobre o api_group `app` (Open Question do design). Verificação: decisão de base de API registrada antes da integração do frontend.

## 2. Endpoints de leitura

- [ ] 2.1 Criar `listar_projetos_GET.xs` (`auth = "usuarios"`): retorna a lista de projetos. Verificação: autenticado retorna lista; sem token retorna 401.
- [ ] 2.2 Criar `detalhe_projeto_GET.xs` (`auth = "usuarios"`, entrada `id`): retorna o projeto ou erro de não encontrado. Verificação: `id` existente retorna o projeto; inexistente retorna notfound; sem token 401.

## 3. Endpoints de escrita (admin) e validação

- [ ] 3.1 Criar `criar_projeto_POST.xs` (`auth = "usuarios"`, admin): valida `nome`/`codigo` não vazios, `budget >= 0`, e unicidade de `codigo`; cria com `status = ativo` (D3/D4). Verificação: admin cria projeto válido; leitura recebe accessdenied; faltando campos/`budget` inválido/`codigo` duplicado → erro de validação.
- [ ] 3.2 Criar `editar_projeto_PATCH.xs` (`auth = "usuarios"`, admin): edita `nome`/`budget` (mantém `codigo`), revalida `budget >= 0`. Verificação: admin edita; leitura recebe accessdenied.
- [ ] 3.3 Criar `desativar_projeto_POST.xs` (`auth = "usuarios"`, admin): define `status = inativo` sem DELETE físico. Verificação: admin desativa (status muda, registro persiste); leitura recebe accessdenied.
- [ ] 3.4 Validar os `.xs` dos cinco endpoints via Xano Developer MCP (ou doc oficial, se indisponível). Verificação: XanoScript válido; nenhuma operação fora do escopo de Projetos.

## 4. Integração da página Reflex

- [ ] 4.1 Implementar o estado da página de projetos (lista; envio de `Authorization: Bearer <token>`; reação a 401 delegando a `AuthState.handle_unauthenticated`), conforme D5. Verificação: `/projetos` carrega a lista real; 401 limpa a sessão e redireciona a `/login`.
- [ ] 4.2 Substituir os dados mock de `projetoImpacta/pages/projetos.py` pela lista real, preservando o design incorporado. Verificação: a página não usa mais `_PROJETOS_MOCK`; badge "Demonstração — sem backend" removido.
- [ ] 4.3 Adicionar controles de criar/editar/desativar sob `rx.cond(AuthState.is_admin, ...)`. Verificação: admin vê e usa os controles; usuário leitura vê a lista sem controles (ocultação só UX; backend continua autoritativo).

## 5. Verificação de ponta a ponta

- [ ] 5.1 `reflex compile --dry` sem erros. Verificação: compila com sucesso.
- [ ] 5.2 Fluxo admin: listar → criar (código inédito) → editar → desativar, observando as regras (código duplicado rejeitado; `budget >= 0`). Verificação: operações refletem no backend. Depende do Xano com a baseline sincronizada e o admin de teste; marcar pendente se indisponível.
- [ ] 5.3 Fluxo leitura: lista visível, sem controles; tentativa de escrita (se forçada) negada pelo backend. Verificação: conforme a spec.
- [ ] 5.4 Revisar `git diff` da change: alterações restritas a `xano/` (tabela + app + 5 endpoints) e `projetoImpacta/pages/projetos.py` (+ estado), sem segredos e sem tocar autenticação. Verificação: diff limpo e no escopo.
