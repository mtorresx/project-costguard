## Context

Ver `proposal.md` — Why. Esta change implementa a fatia vertical de Provedores (configuração base AWS): tabela + endpoints no Xano e a página `/provedores` em Reflex consumindo dados reais.

Estado atual relevante (verificado no repositório):

- **Autenticação (`autenticacao`)**: tabela `usuarios` (`username`, `senha_hash` tipo `password`, `role` ∈ {admin, leitura}, `status`); `login_POST` emite JWT via `security.create_auth_token` (extras com `usuario_id`/`username`/`role`); `me_GET` (`auth = "usuarios"`) retorna `{username, nome, role}`.
- **Projetos (`projetos`)**: padrão de endpoint protegido já consolidado no api_group `app`. Para escrita: `auth = "usuarios"`, `db.get usuarios` por `$auth.id`, `precondition ($usuario_logado != null)` (unauthorized) e `precondition ($usuario_logado.role == "admin")` (accessdenied). Leitura exige apenas sessão (`auth = "usuarios"` garante 401 sem token). As respostas são montadas por `var $resposta` explícito, retornando só os campos desejados. Desativação lógica via `db.edit ... status = "inativo"` (sem DELETE). Validações por `precondition`.
- **api_group `app`**: já existe (`xano/api/app/app.xs`, canonical `costguard-app`) e hospeda as rotas de Projetos. As rotas de Provedores serão adicionadas a este mesmo grupo (conforme pedido).
- **Frontend (`interface-frontend` / `projetos`)**: `/provedores` existe como apresentação/mock (`projetoImpacta/pages/provedores.py`), dentro do app shell, protegida por `on_load=AuthState.require_auth`. O padrão de página com dados reais já existe em `projetos.py` + `projetos_state.py`: um `rx.State` dedicado envia `Authorization: Bearer <token>`, trata 401 via `AuthState.handle_unauthenticated`, e os controles de escrita ficam sob `rx.cond(AuthState.is_admin, ...)`. `config.py` expõe `XANO_APP_BASE_URL` (env) via `get_xano_app_base_url()`.
- **Documentação Xano (verificada via Xano Developer MCP)**: `security.encrypt`/`security.decrypt` (ex.: `aes-256-cbc`) com `key`/`iv` em `$env`; campos de tabela aceitam `visibility = "private"`; inputs e campos aceitam `sensitive = true` (mascara em logs); `api.request` permite chamadas HTTP de saída (para a AWS). O tipo `password` é hash unidirecional — inadequado aqui, pois o segredo precisa ser recuperado para chamar a AWS no teste de conexão.

## Goals / Non-Goals

**Goals:**
- Criar a tabela `provedores` e os seis endpoints (listar, detalhe, criar, editar, desativar, testar conexão) com auth/admin no backend, no api_group `app`.
- Armazenar o `secret_access_key` de forma protegida e nunca retorná-lo ao frontend.
- Executar o teste de conexão AWS no backend (chamada somente leitura) e refletir o resultado em `status`.
- Ligar a página `/provedores` aos dados reais, com controles de escrita/teste só para admin, reusando o padrão de `projetos_state.py`.

**Non-Goals (design):**
- Sem importação de recursos/custos, Cost Explorer, classificação por tags, equipes, alertas ou dashboard.
- Sem suporte a Azure/GCP/Oracle (apenas AWS).
- Sem DELETE físico — desativação é mudança de `status`.
- Sem rotação automática de credenciais e sem gestão de múltiplas credenciais por provedor.

## Decisions

### D1 — Schema da tabela `provedores` (proposto)

```xs
table provedores {
  auth = false

  schema {
    int id
    text apelido filters=trim
    enum tipo?=aws {
      values = ["aws"]
    }
    text identificador_conta filters=trim
    enum tipo_credencial?=aws_access_key {
      values = ["aws_access_key"]
    }
    // Parte pública da credencial AWS (não é segredo).
    text aws_access_key_id? filters=trim {
      sensitive = true
    }
    // Segredo cifrado (ver D4). Nunca retornado; privado por padrão.
    text aws_secret_cifrado? {
      sensitive = true
      visibility = "private"
    }
    enum status?=pendente {
      values = ["pendente", "ok", "erro", "inativo"]
    }
    timestamp criado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree", field: [{name: "criado_em", op: "desc"}]}
  ]
}
```

- `tipo` e `tipo_credencial` são `enum` restritos a um único valor nesta fase (`aws` / `aws_access_key`), tornando o suporte exclusivo a AWS uma garantia de schema além da precondition.
- `aws_access_key_id` é a parte **pública** da credencial. Não é segredo, mas marcada `sensitive = true` por precaução de log. Pode ser exibida (ex.: mascarada) sem violar a regra — a decisão de exibi-la ou não é tratada em D6.
- `aws_secret_cifrado` guarda o segredo **cifrado** (D4), com `visibility = "private"` (fica fora de retornos padrão) e `sensitive = true`. Nenhum endpoint o coloca na resposta.
- `status` inclui `pendente` (recém-criado, sem teste), `ok`, `erro` e `inativo` (desativação lógica).
- Diferente de `projetos`, não há índice único óbvio obrigatório; `identificador_conta` poderia repetir entre contas/credenciais, então não se impõe unicidade nesta fase (ponto aberto Q1).

### D2 — API group e rotas (contrato proposto)

As rotas vivem no api_group `app` já existente, seguindo o padrão de Projetos.

| Método | Rota | Auth | Autorização | Entrada | Saída (sucesso) |
|---|---|---|---|---|---|
| GET | `/provedores` | sim | autenticado | — | lista de `{id, apelido, tipo, identificador_conta, tipo_credencial, status}` |
| GET | `/provedores/{id}` | sim | autenticado | `id` | `{id, apelido, tipo, identificador_conta, tipo_credencial, status}` |
| POST | `/provedores` | sim | admin | `{apelido, tipo, identificador_conta, aws_access_key_id, aws_secret_access_key}` | provedor criado (sem segredo), `status = pendente` |
| PATCH | `/provedores/{id}` | sim | admin | `{id, apelido?, identificador_conta?, aws_access_key_id?, aws_secret_access_key?}` | provedor atualizado (sem segredo) |
| POST | `/provedores/{id}/desativar` | sim | admin | `{id}` | provedor com `status = inativo` |
| POST | `/provedores/{id}/testar-conexao` | sim | admin | `{id}` | `{id, status, conectado: bool, mensagem}` (sem segredo) |

Observações:
- **Nenhuma** resposta inclui `aws_secret_access_key`/`aws_secret_cifrado`. A resposta é sempre montada por `var $resposta` explícito (padrão de Projetos), nunca retornando a row inteira do banco.
- No PATCH, `aws_secret_access_key` é opcional: ausente preserva o segredo; presente substitui. `tipo` não é alterável para valor não suportado.
- Nomes de arquivo `.xs` seguem a convenção de Projetos: `listar_provedores_GET.xs`, `detalhe_provedor_GET.xs`, `criar_provedor_POST.xs`, `editar_provedor_PATCH.xs`, `desativar_provedor_POST.xs`, `testar_conexao_provedor_POST.xs`.

### D3 — Autenticação e autorização no backend (padrão existente)

Idêntico a Projetos. Leitura: `auth = "usuarios"`. Escrita (criar/editar/desativar/testar):

```
db.get usuarios { field_name = "id" field_value = $auth.id } as $usuario_logado
precondition ($usuario_logado != null)        { error_type = "unauthorized" ... }
precondition ($usuario_logado.role == "admin") { error_type = "accessdenied" ... }
```

A autorização real é sempre no backend; o frontend nunca decide acesso.

### D4 — Estratégia de credencial (DECISÃO DE SEGURANÇA — requer aprovação)

**Problema:** o `secret_access_key` precisa ser (a) nunca exposto ao frontend, (b) nunca hardcoded/versionado, e (c) **recuperável pelo backend** para chamar a AWS no teste de conexão. Isso descarta hash unidirecional (tipo `password`).

**Abordagem escolhida (proposta): cifra simétrica no backend.**
- Na criação/edição, o backend cifra o `aws_secret_access_key` recebido via `security.encrypt` (`aes-256-cbc`) usando `key`/`iv` lidos de **variáveis de ambiente do Xano** (`$env.PROV_ENC_KEY`, `$env.PROV_ENC_IV`), e grava o resultado em `aws_secret_cifrado`.
- No teste de conexão, o backend lê `aws_secret_cifrado`, decifra com `security.decrypt` e usa o segredo em memória apenas para a chamada à AWS. O segredo decifrado nunca é retornado nem logado.
- `aws_secret_cifrado` é `visibility = "private"`; nenhum endpoint o inclui na resposta.

**Alternativas consideradas:**
- *Tipo `password` (hash):* rejeitado — hash é irreversível; impossível reusar o segredo para chamar a AWS.
- *Guardar o segredo em texto puro na tabela:* rejeitado — viola a regra de não expor segredo e amplia o impacto de qualquer vazamento de dados.
- *Guardar o segredo apenas em `$env` (sem tabela):* rejeitado — não escala para múltiplos provedores e mistura dado de runtime com configuração; manteríamos só a chave de cifra em `$env`.

**Pontos que precisam de aprovação explícita antes do Apply (ver "Decisões de segurança para aprovação"):**
1. Confirmar o uso de `security.encrypt`/`decrypt` com `key`/`iv` em `$env` do Xano como mecanismo de proteção do segredo (vs. outra abordagem que o grupo prefira).
2. Confirmar o modelo de credencial para o MVP: **chave de acesso AWS somente leitura** (`access_key_id` + `secret_access_key`). (A `docs/domain-model.md` exige apenas "somente as permissões necessárias"; a escolha entre chave de acesso IAM e, no futuro, IAM Role/AssumeRole é uma decisão de domínio.)
3. Confirmar que as variáveis de ambiente de cifra serão criadas **no Xano** (não no `.env` do frontend, nem no Git).

### D5 — Teste de conexão AWS (proposto)

O endpoint `POST /provedores/{id}/testar-conexao` executa, no backend:
1. Autoriza (admin) e carrega o provedor; valida que `tipo = aws` e que há credencial salva.
2. Decifra `aws_secret_cifrado` (D4).
3. Chama a AWS **STS `GetCallerIdentity`** (operação somente leitura, sem custo e sem exigir permissões além da identidade) via `api.request` sobre o endpoint STS, assinada com SigV4 usando `aws_access_key_id` + segredo decifrado.
4. Interpreta o resultado: HTTP 200 → credencial válida (`status = ok`); erro de autenticação/assinatura ou falha → `status = erro`.
5. Grava o `status` via `db.edit` e retorna `{id, status, conectado, mensagem}` — sem segredo. A falha é sempre reportada (não silenciosa).

**Risco técnico a validar no Apply:** a assinatura AWS SigV4 em XanoScript pode exigir cálculo de HMAC-SHA256 encadeado. Alternativas se SigV4 manual se mostrar inviável no Xano:
- usar uma Lambda/função AWS intermediária acionada por `api.request` (mantém o segredo no backend); ou
- usar um conector/integração AWS do Xano, se disponível no workspace.
Esta decisão de implementação é registrada aqui e confirmada na etapa de Apply (ponto aberto Q2); não altera o contrato de API nem as specs.

### D6 — Integração Reflex (proposto)

Novo `projetoImpacta/pages/provedores_state.py` espelhando `projetos_state.py`:
- `carregar` (on_load, após `require_auth`): GET `/provedores` com `Authorization: Bearer <token>`; 401 → `AuthState.handle_unauthenticated`.
- Formulário de cadastro/edição (admin): POST/PATCH `/provedores`. O campo do segredo aparece **sempre vazio** (nunca preenchido com valor salvo); na edição, enviar o segredo vazio significa "não alterar".
- Ação "Testar conexão" (admin): POST `/provedores/{id}/testar-conexao`, depois recarrega a lista para refletir o novo `status`.
- Controles de escrita/teste sob `rx.cond(AuthState.is_admin, ...)` (apenas UX).
- `projetoImpacta.py`: `on_load` de `/provedores` passa a `[AuthState.require_auth, ProvedoresState.carregar]` (como em `/projetos`).
- Base de URL: reusa `get_xano_app_base_url()` (`XANO_APP_BASE_URL`). Nenhum segredo em `config.py` nem no `.env` do frontend.
- O design/tabela incorporado é preservado; o `status` passa a vir do backend (hoje é mock).

## Risks / Trade-offs

- **SigV4 em XanoScript pode ser complexo** → mitigação: fallback para Lambda/conector AWS (D5); confirmado no Apply. Não afeta specs/contrato.
- **Chave de cifra única para todos os provedores** (`$env`) → se a chave vazar, todos os segredos ficam expostos. Mitigação: chave somente no Xano, fora de Git/frontend; rotação futura fora do escopo deste MVP.
- **`identificador_conta` sem unicidade** → pode haver provedores duplicados apontando para a mesma conta. Mitigação: aceitável no MVP; unicidade pode ser adicionada depois (Q1).
- **Credencial IAM estática** (vs. role temporária) → trade-off de simplicidade do MVP acadêmico; a exigência de domínio ("somente permissões necessárias") é atendida por uma policy read-only. Decisão em D4.2.

## Migration Plan

- Mudança aditiva: nova tabela e novos endpoints no api_group `app` já existente; nenhuma alteração em `usuarios`/`projetos`/autenticação. Rollback = remover a tabela/endpoints e reverter a página `/provedores` ao mock. Variáveis de ambiente de cifra criadas no Xano antes do primeiro cadastro real.

## Open Questions

- **Q1 — Unicidade de `identificador_conta`:** impor unicidade por conta AWS, ou permitir múltiplos provedores para a mesma conta? Não bloqueia o contrato; decidível depois. Proposta atual: sem unicidade no MVP.
- **Q2 — Mecanismo da chamada AWS no teste de conexão:** SigV4 nativo em XanoScript vs. Lambda/conector intermediário. Não altera specs nem contrato de API; confirmado na implementação (Apply) conforme o que o workspace Xano suportar.
