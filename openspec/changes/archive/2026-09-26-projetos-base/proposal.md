## Why

A página `/projetos` do CostGuard foi incorporada na change `interface-frontend` apenas como apresentação, com dados mock e sem backend. Projeto é o principal agrupador financeiro do domínio (ver `docs/domain-model.md`): sem ele, nenhuma funcionalidade de custo/orçamento pode existir. Esta change entrega a **primeira fatia vertical funcional de Projetos** — tabela e endpoints no Xano e a página Reflex consumindo dados reais — mantendo o escopo mínimo do MVP acadêmico.

## What Changes

- **Backend Xano (novo)**: tabela `projetos` e os endpoints de Projetos no api_group `app` — listar, detalhe, criar, editar e desativar.
- **Autorização no backend**: todas as rotas exigem autenticação; as operações de escrita (criar/editar/desativar) exigem `role = admin`; leitura é permitida a qualquer usuário autenticado.
- **Regras de integridade**: `codigo` único; campos obrigatórios validados; `budget` decimal `>= 0`; desativação via `status` (sem DELETE físico).
- **Frontend Reflex**: substituir os dados mock de `/projetos` por dados reais do Xano — listar projetos; criar/editar/desativar para admin; usuário `leitura` vê a lista sem controles administrativos. Preserva o design incorporado, o `AuthState`, a sessão e o tratamento central de 401 existentes.

## Capabilities

### New Capabilities

- `projetos`: Gestão base de Projetos do CostGuard — entidade `projetos` (id, nome, codigo único, budget mensal em USD, status ativo/inativo), operações de leitura (listar, detalhe) para qualquer usuário autenticado e de escrita (criar, editar, desativar) restritas a admin, com validação de autenticação e autorização no backend; e a página `/projetos` em Reflex consumindo esses dados.

### Modified Capabilities

<!-- Nenhum requisito das capabilities `autenticacao` ou `interface-frontend` é alterado. Esta change preserva a autenticação e substitui o conteúdo mock da página `/projetos` por dados reais, sem mudar o contrato de autenticação. -->

## Impact

- **Backend Xano (novo — escopo desta change)**:
  - `xano/table/projetos.xs` — tabela de projetos.
  - `xano/api/app/app.xs` — api_group `app` (recriado na baseline limpa; contém as rotas de Projetos).
  - `xano/api/app/listar_projetos_GET.xs`, `detalhe_projeto_GET.xs`, `criar_projeto_POST.xs`, `editar_projeto_PATCH.xs`, `desativar_projeto_POST.xs`.
- **Frontend Reflex (escopo desta change)**:
  - `projetoImpacta/pages/projetos.py` — passa a consumir o Xano (listar/criar/editar/desativar), com controles de escrita condicionados a `AuthState.is_admin`.
  - Possível estado dedicado da página (ex.: `projetoImpacta/pages/projetos.py` ou um módulo de estado) seguindo o padrão de `AuthState` (envio de token, reação a 401). Definido no `design.md`.
- **Preservado sem alteração**: `projetoImpacta/state.py` (`AuthState`), autenticação, `config.py`.

### Fora do escopo

- Equipes, recursos, AWS, provedores, importação de custos, classificação por tags.
- Cálculo de consumo × orçamento, alertas 70/90/100, dashboard real de custos (o `custo_atual`/percentual exibidos hoje são mock e permanecem fora desta change).
- Exclusão física de projeto (apenas desativação via `status`).
- Recuperação de senha e qualquer alteração na autenticação existente.
