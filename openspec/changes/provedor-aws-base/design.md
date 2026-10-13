## Context

Ver `proposal.md` — Why. Esta change implementa a fatia vertical de Provedores (configuração base AWS): tabela + endpoints no Xano e a página `/provedores` em Reflex consumindo dados reais.

Estado atual relevante (verificado no repositório):

- **Autenticação (`autenticacao`)**: tabela `usuarios` (`username`, `senha_hash` tipo `password`, `role` ∈ {admin, leitura}, `status`); `login_POST` emite JWT via `security.create_auth_token` (extras com `usuario_id`/`username`/`role`); `me_GET` (`auth = "usuarios"`) retorna `{username, nome, role}`.
- **Projetos (`projetos`)**: padrão de endpoint protegido já consolidado no api_group `app`. Para escrita: `auth = "usuarios"`, `db.get usuarios` por `$auth.id`, `precondition ($usuario_logado != null)` (unauthorized) e `precondition ($usuario_logado.role == "admin")` (accessdenied). Leitura exige apenas sessão (`auth = "usuarios"` garante 401 sem token). As respostas são montadas por `var $resposta` explícito, retornando só os campos desejados. Desativação lógica via `db.edit ... status = "inativo"` (sem DELETE). Validações por `precondition`.
- **api_group `app`**: já existe (`xano/api/app/app.xs`, canonical `costguard-app`) e hospeda as rotas de Projetos. As rotas de Provedores serão adicionadas a este mesmo grupo (conforme pedido).
- **Frontend (`interface-frontend` / `projetos`)**: `/provedores` existe como apresentação/mock (`projetoImpacta/pages/provedores.py`), dentro do app shell, protegida por `on_load=AuthState.require_auth`. O padrão de página com dados reais já existe em `projetos.py` + `projetos_state.py`: um `rx.State` dedicado envia `Authorization: Bearer <token>`, trata 401 via `AuthState.handle_unauthenticated`, e os controles de escrita ficam sob `rx.cond(AuthState.is_admin, ...)`. `config.py` expõe `XANO_APP_BASE_URL` (env) via `get_xano_app_base_url()`.
- **Documentação Xano (verificada via Xano Developer MCP e docs.xano.com)**: as funções **Encrypt Data**/**Decrypt Data** recebem `algorithm`, `key` e `initialization vector` (IV) **explícitos** — não há gerenciamento automático de nonce para o cifrador simétrico; existe `security.create_random_bytes` para gerar bytes aleatórios (IV por gravação); existe criptografia autenticada (AEAD) via **JWE** (`jwe_encode`/`jwe_decode`, com `KEY_ALGORITHM`/`CONTENT_ALGORITHM`), que gerencia o próprio IV internamente. Campos de tabela aceitam `visibility = "private"`; inputs e campos aceitam `sensitive = true` (mascara em logs); `api.request` permite chamadas HTTP de saída (para a AWS). O tipo `password` é hash unidirecional — inadequado aqui, pois o segredo precisa ser recuperado para chamar a AWS no teste de conexão. A lista exata de algoritmos aceitos pelo `encrypt` (ex.: disponibilidade de `aes-256-gcm`) será confirmada no Apply via Xano MCP.

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
    // IV/nonce aleatório desta gravação (ver D4). Único por gravação; privado.
    // Presente apenas quando o cifrador simétrico com IV explícito é usado
    // (não necessário se o segredo for protegido via JWE, que embute o IV).
    text aws_secret_iv? {
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
- `aws_secret_iv` guarda o **IV/nonce aleatório desta gravação** (D4), também `private` + `sensitive`. É único por gravação e nunca reutilizado; existe apenas no caminho de cifrador simétrico com IV explícito (dispensável no caminho JWE, que embute o IV no token).
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

### D4 — Estratégia de credencial (DECISÃO DE SEGURANÇA — aprovada com ajustes)

**Problema:** o `secret_access_key` precisa ser (a) nunca exposto ao frontend, (b) nunca hardcoded/versionado, e (c) **recuperável pelo backend** para chamar a AWS no teste de conexão. Isso descarta hash unidirecional (tipo `password`).

**Regra aprovada (obrigatória):** a chave de cifra permanece em `$env.PROV_ENC_KEY` (Xano), mas **NÃO** pode haver IV fixo global. Prefere-se criptografia autenticada (AEAD) com gerenciamento seguro de nonce/IV; se for necessário fornecer IV explicitamente, ele deve ser **aleatório por gravação**, armazenado junto ao ciphertext e nunca reutilizado.

**Abordagem escolhida: cifra autenticada no backend, com IV por gravação.**

- *Caminho preferencial (AEAD/JWE):* proteger o segredo via `jwe_encode` usando a chave de `$env.PROV_ENC_KEY`, gravando o token resultante em `aws_secret_cifrado`. O JWE gerencia o próprio IV/nonce internamente e provê autenticidade (integridade) além de confidencialidade; nesse caminho `aws_secret_iv` não é necessário. O teste de conexão decifra com `jwe_decode`.
- *Caminho alternativo (cifrador simétrico com IV explícito):* se, após confirmação na documentação do Xano, o JWE não for adequado ao caso, usar `security.encrypt`/`security.decrypt` com `key = $env.PROV_ENC_KEY` e um **IV aleatório gerado a cada gravação** via `security.create_random_bytes`. O IV é persistido em `aws_secret_iv` (privado) ao lado de `aws_secret_cifrado`; na edição que troca o segredo, gera-se um **novo** IV. Preferir um algoritmo com autenticação (ex.: `aes-256-gcm`) se o `encrypt` do Xano o oferecer; caso só CBC esteja disponível, manter o IV aleatório por gravação. **Em nenhum caso usar um IV fixo global.**
- Em ambos os caminhos, o segredo decifrado existe apenas em memória durante a chamada à AWS, nunca é retornado nem logado. `aws_secret_cifrado` e `aws_secret_iv` são `visibility = "private"`; nenhum endpoint os inclui na resposta.

**Decisão final (confirmada no Apply via Xano MCP):** escolhido o **caminho JWE (AEAD)**. O filtro `jwe_encode` do Xano gera um token com IV/nonce gerenciado internamente e autenticação (integridade), usando `key_algorithm = "A256KW"` e `content_algorithm = "A256CBC-HS512"` (AES-256-CBC + HMAC-SHA-512). A chave vem de `$env.PROV_ENC_KEY` (string ≥ 256 bits). Assinatura confirmada na doc: `"segredo"|jwe_encode:{headers}:"<key>":"A256KW":"A256CBC-HS512"` e `$token|jwe_decode:{}:"<key>":"A256KW":"A256CBC-HS512"`. Como o JWE embute o IV, **o campo `aws_secret_iv` não é usado** nesta implementação; ele permanece no schema como reservado/compatível (dispensável neste caminho), conforme já previsto no design. Isso satisfaz a regra aprovada: chave única em `$env`, sem IV fixo global, nonce gerenciado por gravação. O caminho simétrico `encrypt`/`decrypt` (que no Xano exige IV explícito — confirmado: só modos CBC como `aes-128/192/256-cbc`, sem GCM nativo) fica como alternativa não adotada.

**Alternativas consideradas:**
- *IV fixo global em `$env` (`PROV_ENC_IV`):* **rejeitado por decisão do usuário** — reutilizar um mesmo IV com a mesma chave em AES-CBC vaza informação entre ciphertexts e é prática insegura. Substituído por IV aleatório por gravação ou AEAD/JWE.
- *Tipo `password` (hash):* rejeitado — hash é irreversível; impossível reusar o segredo para chamar a AWS.
- *Guardar o segredo em texto puro na tabela:* rejeitado — viola a regra de não expor segredo e amplia o impacto de qualquer vazamento de dados.
- *Guardar o segredo apenas em `$env` (sem tabela):* rejeitado — não escala para múltiplos provedores e mistura dado de runtime com configuração; mantém-se só a chave de cifra em `$env`.

**Pré-requisitos aprovados (confirmados pelo usuário):**
1. Mecanismo de proteção = cifra no backend com chave em `$env.PROV_ENC_KEY`, **sem IV fixo global** (AEAD/JWE preferencial; senão IV aleatório por gravação em `aws_secret_iv`).
2. Modelo de credencial do MVP = **chave de acesso AWS** (`access_key_id` + `secret_access_key`) de uma **credencial IAM dedicada**, **nunca root**, com **privilégio mínimo/somente leitura**. IAM Role/AssumeRole com credenciais temporárias fica como evolução futura, fora desta change.
3. A chave de cifra é criada **no Xano** (`$env.PROV_ENC_KEY`), nunca no `.env` do frontend nem no Git.

### D5 — Teste de conexão AWS (proposto)

O endpoint `POST /provedores/{id}/testar-conexao` executa, no backend:
1. Autoriza (admin) e carrega o provedor; valida que `tipo = aws` e que há credencial salva.
2. Decifra `aws_secret_cifrado` (D4).
3. Chama a AWS **STS `GetCallerIdentity`** (operação somente leitura, sem custo e sem exigir permissões além da identidade) via `api.request` sobre o endpoint STS, assinada com SigV4 usando `aws_access_key_id` + segredo decifrado.
4. Interpreta o resultado: HTTP 200 → credencial válida (`status = ok`); erro de autenticação/assinatura ou falha → `status = erro`.
5. Grava o `status` via `db.edit` e retorna `{id, status, conectado, mensagem}` — sem segredo. A falha é sempre reportada (não silenciosa).

**Semântica aprovada de `status = ok`:** nesta change, `ok` significa **"credencial AWS autenticada com sucesso"** (a chamada STS `GetCallerIdentity` confirma que a chave é válida). Isso **não** afirma que todas as permissões futuras do CostGuard (Cost Explorer, listagem de recursos, tags) estão disponíveis. A validação específica dessas permissões ocorrerá na change responsável pela importação AWS, fora do escopo desta.

**Decisão confirmada no Apply (opção 1, aprovada pelo usuário):** **SigV4 manual** para STS `GetCallerIdentity`, implementado diretamente no endpoint `testar_conexao_provedor_POST.xs`. O Xano não possui conector STS nativo (apenas `cloud.aws.s3.*`, específico de S3), e optou-se por não introduzir bucket S3 nem Lambda/infra externa. Os primitivos necessários existem no XanoScript: `hmac_sha256:"key":true` (saída binária raw), `sha256`, `bin2hex`, `base64_encode`. Diretrizes de implementação:
- Escopo mínimo: assinar **somente** `GET https://sts.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15` (`service = sts`, `region = us-east-1`, host global). Sem abstração genérica; lógica isolada e legível para refatoração futura na integração AWS.
- Passos SigV4: (1) canonical request (método, URI, query, headers canônicos `host`+`x-amz-date`, signed headers, hash SHA-256 do payload vazio); (2) string to sign com escopo `<data>/us-east-1/sts/aws4_request`; (3) signing key derivada em 4 HMAC-SHA256 encadeados (`AWS4<secret>` → data → region → service → `aws4_request`), tudo em binário via `hmac_sha256:...:true`; (4) assinatura `hmac_sha256` sobre a string to sign, em hex (`bin2hex`); (5) header `Authorization: AWS4-HMAC-SHA256 Credential=.../SignedHeaders=.../Signature=...`.
- Segurança: o secret é decifrado (`jwe_decode`) **imediatamente antes** da assinatura, só em memória; nunca é logado, nunca retornado; não logar Access Key ID e secret juntos; nenhum material de assinatura volta ao frontend.
- Resultado: HTTP 200 do STS → `status = ok` ("credencial AWS autenticada com sucesso"); qualquer falha → `status = erro` com mensagem sanitizada. **Verificação real (E2E) fica pendente até o push e teste contra a AWS** — a implementação é marcada como concluída e a validação ao vivo como pendente.
Não altera o contrato de API nem as specs.

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
- **Chave de cifra única para todos os provedores** (`$env.PROV_ENC_KEY`) → se a chave vazar, todos os segredos ficam expostos. Mitigação: chave somente no Xano, fora de Git/frontend; IV aleatório por gravação (ou AEAD/JWE) limita a correlação entre ciphertexts mesmo com a mesma chave; rotação de chave futura fora do escopo deste MVP.
- **IV/nonce** → reutilizar IV com a mesma chave é inseguro. Mitigação (D4, aprovada): AEAD/JWE com nonce gerenciado, ou IV aleatório por gravação em `aws_secret_iv`; nunca IV fixo global.
- **`identificador_conta` sem unicidade** → pode haver provedores duplicados apontando para a mesma conta. Mitigação: aceitável no MVP; unicidade pode ser adicionada depois (Q1).
- **Credencial IAM estática** (vs. role temporária) → trade-off de simplicidade do MVP acadêmico; atendida por uma credencial IAM **dedicada** (nunca root) com policy **somente leitura**. IAM Role/AssumeRole fica como evolução futura (D4.2).
- **`status = ok` não garante permissões de importação** → `ok` significa apenas credencial autenticada (STS). Mitigação: semântica documentada em D5 e na spec; validação de Cost Explorer/recursos fica para a change de importação AWS.

## Migration Plan

- Mudança aditiva: nova tabela e novos endpoints no api_group `app` já existente; nenhuma alteração em `usuarios`/`projetos`/autenticação. Rollback = remover a tabela/endpoints e reverter a página `/provedores` ao mock. Variável de cifra (`$env.PROV_ENC_KEY`) criada no Xano antes do primeiro cadastro real.

## Open Questions

- **Q1 — Unicidade de `identificador_conta`:** impor unicidade por conta AWS, ou permitir múltiplos provedores para a mesma conta? Não bloqueia o contrato; decidível depois. Proposta atual: sem unicidade no MVP.
- **Q2 — Mecanismo da chamada AWS no teste de conexão:** RESOLVIDO (opção 1) — SigV4 manual para STS `GetCallerIdentity`, sem bucket S3 nem Lambda. Verificação E2E pendente até o push/teste contra a AWS.
- **Q3 — Mecanismo exato de cifra:** RESOLVIDO — JWE (`jwe_encode`/`jwe_decode`, `A256KW` + `A256CBC-HS512`, chave em `$env.PROV_ENC_KEY`, nonce gerenciado pelo JWE). `aws_secret_iv` permanece no schema mas não é usado neste caminho.
