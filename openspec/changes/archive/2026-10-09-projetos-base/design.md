## Context

Ver `proposal.md` — Why. Esta change implementa a fatia vertical de Projetos: tabela + endpoints no Xano e a página `/projetos` em Reflex consumindo dados reais.

Estado atual relevante:

- **Autenticação (capability `autenticacao`, baseline limpa)**: tabela `usuarios` (`username`, `senha_hash` tipo `password`, `role` ∈ {admin, leitura}, `status`); `login_POST` emite JWT via `security.create_auth_token` (extras com `username`/`role`); `me_GET` (`auth = "usuarios"`) retorna `{username, role}`. O padrão de endpoint protegido é: `auth = "usuarios"`, `db.get usuarios` por `$auth.id`, `precondition` de role para escrita.
- **Frontend (`interface-frontend`)**: `/projetos` existe como apresentação/mock (`projetoImpacta/pages/projetos.py`), dentro do app shell, protegida por `on_load=AuthState.require_auth`. `AuthState` expõe `token`, `username`, `role`, `is_admin`, e trata 401 via `handle_unauthenticated`. `config.py` fornece `XANO_BASE_URL` por env.
- **Xano `app`**: o api_group `app` foi removido na baseline limpa; será recriado por esta change para hospedar as rotas de Projetos.

## Goals / Non-Goals

**Goals:**
- Criar a tabela `projetos` e os cinco endpoints (listar, detalhe, criar, editar, desativar) com auth/admin no backend.
- Ligar a página `/projetos` aos dados reais, com controles de escrita só para admin.
- Reusar o padrão de autenticação/401 existente, sem alterá-lo.

**Non-Goals (design):**
- Sem cálculo de custo/consumo, sem alertas, sem equipes/recursos/provedores.
- Sem DELETE físico — desativação é mudança de `status`.
- Sem novos conceitos de domínio além dos campos aprovados.

## Decisions

### D1 — Schema da tabela `projetos`

```xs
table projetos {
  auth = false
  schema {
    int id
    text nome filters=trim
    text codigo filters=trim|upper
    decimal budget
    enum status?=ativo {
      values = ["ativo", "inativo"]
    }
    timestamp criado_em?=now {
      visibility = "private"
    }
  }
  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "criado_em", op: "desc"}]}
    {type: "btree|unique", field: [{name: "codigo", op: "asc"}]}
  ]
}
```

- `codigo` com filtro `upper` e índice `btree|unique` garante unicidade e a convenção de maiúsculas da tag (`PRJ_<codigo>`).
- `budget` é `decimal`; a regra `>= 0` é validada nos endpoints (precondition), já que o tipo em si não impõe o mínimo.
- `status` enum com default `ativo`.

### D2 — API group e rotas

As rotas vivem no api_group `app` (recriado), seguindo o padrão dos endpoints de auth. Contrato proposto:

| Método | Rota | Auth | Autorização | Entrada | Saída (sucesso) |
|---|---|---|---|---|---|
| GET | `/projetos` | sim | autenticado | — | lista de `{id, nome, codigo, budget, status}` |
| GET | `/projetos/{id}` (ou `detalhe_projeto` por `id`) | sim | autenticado | `id` | `{id, nome, codigo, budget, status}` |
| POST | `/projetos` (criar) | sim | admin | `{nome, codigo, budget}` | projeto criado |
| PATCH | `/projetos/{id}` (editar) | sim | admin | `{id, nome?, budget?}` | projeto atualizado |
| POST | `/projetos/{id}/desativar` (desativar) | sim | admin | `{id}` | projeto com `status = inativo` |

Observações:
- A escolha exata do verbo/caminho de cada rota segue a convenção do projeto (os endpoints da baseline anterior usavam `listar_projetos_GET`, `detalhe_projeto_GET`, `criar_projeto_POST`, `editar_projeto_PATCH`, `desativar_projeto_POST`). Esta change pode reusar esses nomes.
- `codigo` não é editável na edição (preserva a identidade da tag); apenas `nome` e `budget` mudam. Decisão registrada; se o grupo quiser permitir editar `codigo`, revalidar unicidade.

### D3 — Autenticação e autorização no backend (padrão existente)

Cada endpoint usa `auth = "usuarios"`. Para escrita, o padrão é:

```
db.get usuarios { field_name = "id" field_value = $auth.id } as $usuario_logado
precondition ($usuario_logado != null) { error_type = "unauthorized" ... }
precondition ($usuario_logado.role == "admin") { error_type = "accessdenied" ... }
```

Leitura exige apenas sessão válida (o `auth = "usuarios"` já garante 401 sem token). A autorização real é sempre no backend; o frontend nunca decide acesso.

### D4 — Validações de escrita

- `nome` e `codigo` obrigatórios (não vazios) via precondition.
- `budget` obrigatório e `>= 0` via precondition (`$input.budget != null && $input.budget >= 0`).
- Unicidade de `codigo`: `db.get projetos` por `codigo` antes de criar; se existir, erro de validação. O índice único é a garantia final.
- Desativar: `db.edit projetos` apenas `status = "inativo"`; sem DELETE.

### D5 — Integração Reflex

Um estado dedicado da página (seguindo o padrão de `AuthState`): carrega a lista no `on_load` (ou após `require_auth`), enviando `Authorization: Bearer <token>`; em 401, delega ao tratamento central (`AuthState.handle_unauthenticated`). Os controles de criar/editar/desativar são renderizados sob `rx.cond(AuthState.is_admin, ...)` — ocultação é só UX. O design dos cards incorporado é preservado; o `custo_atual`/percentual exibidos hoje são mock e permanecem como apresentação (fora do escopo de custos), ou são omitidos — a decisão de exibição fica para a implementação sem alterar o contrato.

### D6 — Base URL e verificação

As chamadas usam `XANO_BASE_URL` (env) via `config.py`, apontando para a base do api_group `app`. Testes funcionais exigem a tabela/endpoints sincronizados ao Xano e o admin de teste — executados na etapa de apply quando o backend estiver disponível.

## Risks / Trade-offs

- **Base URL por api_group**: auth (`/login`, `/me`) e projetos (`/projetos`) podem estar em api_groups diferentes (`auth` vs `app`), com bases distintas. Mitigação: definir a(s) base(s) por env; a implementação confirma se usa uma base única ou uma por grupo. Registrado como ponto de atenção.
- **Validação de `budget >= 0` depende de precondition** (não do tipo). Mitigação: precondition explícita em criar e editar.
- **Edição de `codigo`**: desabilitada por decisão (D2) para preservar a tag; se mudar, revalidar unicidade.

## Open Questions

- **Base(s) de API no frontend**: usar uma única `XANO_BASE_URL` para auth e app, ou uma base por api_group? Não bloqueia a modelagem; afeta apenas a configuração de ambiente no apply. Decidir ao integrar a página, confirmando como os api_groups `auth` e `app` ficam expostos no Xano.
