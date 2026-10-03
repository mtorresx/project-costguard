## Context

Ver `proposal.md` — Why para a motivação. Esta change é a primeira fatia vertical do CostGuard e conecta o frontend Reflex a um backend Xano **criado do zero**.

Decisão de estratégia: o workspace Xano atual não possui dados a preservar e será completamente limpo. O backend de autenticação anterior (criado antes do OpenSpec) **não** é reaproveitado. Esta change define a baseline mínima necessária para autenticação.

Baseline mínima do backend (único escopo backend desta change):

- `xano/table/usuarios.xs` — tabela com `auth = true` e os campos `username` (único), `senha_hash` (tipo `password`), `role` (∈ {admin, leitura}), `status` (∈ {ativo, inativo}), `nome`, `email`.
- `xano/api/auth/auth.xs` — api_group `auth`.
- `xano/api/auth/login_POST.xs` — `POST /login`, entrada `{username, password}`, emite token.
- `xano/api/auth/me_GET.xs` — `GET /me`, saída mínima `{username, role}`.

Frontend Reflex: praticamente no template inicial. `rxconfig.py` usa `app_name="projetoImpacta"` com plugins Radix/Tailwind. `reflex==0.9.12`; `httpx` disponível no ambiente.

Restrições que moldam a abordagem: frontend exclusivamente Reflex; autorização real somente no Xano; nenhum segredo versionado; documentação atual do Reflex consultada via Agent Skills; comportamento do Xano confirmado via Developer MCP quando houver dúvida.

## Goals / Non-Goals

**Goals:**

- Criar a baseline mínima do backend Xano para autenticação (tabela `usuarios` + api_group `auth` + `login` + `me`), já com o contrato padronizado.
- Definir onde e como o token vive no frontend Reflex e como é reenviado nas requisições autenticadas.
- Definir o tratamento consistente de HTTP 401 no frontend.
- Definir a estrutura mínima de páginas Reflex (login + área protegida) e o mecanismo de proteção/redirecionamento.
- Manter a fronteira: frontend não é mecanismo de segurança.

**Non-Goals (nível de design):**

- Não reaproveitar nem migrar o backend legado; ele é descartado com a limpeza do workspace.
- Não incluir gestão de usuários (`criar_usuario`, `editar_usuario`, desativação) — feature futura.
- Não incluir recuperação/redefinição de senha, nem o domínio de custos.
- Não criar mecanismo automático de bootstrap do primeiro admin.
- Não definir refresh token, "lembrar-me" persistente entre reinícios, nem expiração deslizante.
- Não desenhar telas além de login e uma área autenticada mínima para exercitar o fluxo.

## Decisions

### D1 — Backend criado do zero como baseline mínima

A autenticação é construída a partir de um workspace Xano vazio. A baseline contém exatamente os quatro artefatos listados em Context. A lógica dos endpoints (login validado no backend, emissão/validação de token, `/me` resolvendo identidade a partir do token) usa primitivas nativas do Xano (`security.check_password`, `security.create_auth_token`) e a tabela `usuarios` com `auth = true`; não depende de funções, addons ou outras tabelas. Alternativa descartada: preservar/reaproveitar o backend existente — contraria a decisão aprovada de baseline limpa.

### D2 — Estado de sessão no Reflex via `rx.State`

A sessão (token, `username`, `role`, flag de autenticado) será mantida em um State de autenticação do Reflex. Decisão coerente com "frontend exclusivamente Reflex". A API concreta de State/eventos/vars foi confirmada via Reflex Agent Skills (reflex-docs) para `reflex==0.9.12`.

### D3 — Persistência do token via `rx.SessionStorage` (decisão fechada)

O token e os dados de sessão são mantidos em `rx.SessionStorage` do Reflex. Conforme a documentação oficial (Browser Storage / Client Storage — Reflex), `rx.SessionStorage` sobrevive ao recarregamento e à restauração de página, mas é limpo quando a aba/navegador é fechado, e fica isolado à aba em que foi criado. Isso corresponde exatamente ao requisito de sessão: *reload mantém a sessão; fechar e reabrir o navegador não precisa manter*.

Alternativas descartadas:
- `rx.LocalStorage`: persiste indefinidamente entre sessões do navegador, excedendo o comportamento desejado.
- `rx.Cookie` de sessão: atenderia (cookie sem `max_age` expira ao fechar o navegador), mas `rx.SessionStorage` expressa a intenção de forma direta e mantém o token fora do envio automático em cada requisição HTTP.
- Token apenas em memória do State: perderia a sessão a cada reload, quebrando o requisito.

O logout e a reação a 401 descartam a sessão limpando as vars de SessionStorage.

### D4 — Cliente HTTP e envio do token

As chamadas ao Xano (`login`, `/me`) partem do backend do Reflex (event handlers) usando `httpx` (já disponível no ambiente). O token é enviado no cabeçalho `Authorization: Bearer <token>`. Alternativa descartada: adicionar uma biblioteca de cliente nova — desnecessário e contra a regra de não introduzir dependências sem justificativa.

### D5 — Base URL do Xano por configuração, sem segredo versionado

A URL base do backend Xano é lida de variável de ambiente, não fixada em código versionado. O token de autenticação é dado do usuário em runtime, não um segredo de build; ainda assim não deve ser logado. Nenhuma credencial de serviço entra no frontend, e nenhuma credencial de teste é versionada.

### D6 — Rotas e proteção por verificação no carregamento (decisão fechada)

Rotas desta change:
- `/login` — página pública de login.
- `/` — área autenticada mínima protegida (não é o dashboard definitivo).

A página `/` verifica a sessão no carregamento (padrão `on_load` do Reflex) e redireciona para `/login` quando não houver sessão autenticada. A validação real do token ocorre no Xano, não no cliente. A proteção do frontend é apenas navegação/UX.

### D7 — Tratamento centralizado de 401

Um ponto único no frontend interpreta respostas HTTP 401 do Xano: descarta a sessão local e trata o usuário como não autenticado (encaminhando ao login). Evita espalhar tratamento de 401 por cada chamada.

### D8 — Validação da sessão via `/me`

Após o login e ao (re)carregar a aplicação com token presente, o frontend chama `/me` para confirmar a validade do token e obter `username` e `role` atuais do backend, em vez de confiar apenas em dados embutidos no token. Mantém o backend como fonte de verdade da identidade.

### D9 — Contrato padronizado `username`/`password`/`role` desde a origem (decisão fechada)

O contrato de autenticação usa `username`, `password` e `role` no frontend e na API Xano, definidos **na criação** da baseline — não há renomeação de legado, pois o backend nasce do zero.

- Tabela `usuarios`: coluna de identificação `username`; senha persistida como `senha_hash` do tipo `password` (credencial com hash; nunca renomeada para `password` — o contrato usa `password` apenas como chave de input).
- `POST /login`: entrada `{username, password}`; compara `password` com `senha_hash` via `security.check_password`; emite token via `security.create_auth_token`.
- `GET /me`: saída mínima `{username, role}` (pode incluir campos adicionais como `nome`).

### D10 — Gestão de usuários é feature futura; primeiro admin é procedimento de ambiente

`criar_usuario`, `editar_usuario` e a desativação de usuários **não** fazem parte desta change; pertencem a uma futura change de gestão de usuários. Como a baseline nasce sem usuários e não há bootstrap automático nesta change, o primeiro usuário admin é cadastrado **manualmente no painel Xano**, apenas para desenvolvimento e testes, após a baseline existir. Isso é procedimento de ambiente, não funcionalidade do produto, e nenhuma credencial de teste é versionada.

## Risks / Trade-offs

- **Token em `rx.SessionStorage` (D3) é acessível a scripts no navegador (risco de XSS)** → Mitigação: não é mecanismo de segurança do sistema; a autorização real é no Xano e o token expira (expiração definida no `login`). `SessionStorage` some ao fechar o navegador, reduzindo a janela de exposição. Não versionar segredos, não logar o `password` nem o token. Endurecimento adicional (cookies HttpOnly, CSRF) fica fora desta fatia.
- **Baseline sem usuários exige cadastro manual do primeiro admin (D10)** → Mitigação: procedimento de ambiente documentado; sem bootstrap automático e sem credenciais versionadas. Os testes funcionais dependem desse admin existir no workspace.
- **APIs concretas do Reflex 0.9.12** → Mitigação: `rx.SessionStorage`, `on_load`/`rx.redirect`, handlers async e `httpx` confirmados via documentação oficial. O design fixa o comportamento, não a assinatura exata.
- **Verificação funcional depende do Xano remoto** → os testes de `login`/`/me` e o E2E exigem a baseline sincronizada ao workspace e o admin manual; ficam pendentes até a sincronização (fora do escopo desta etapa de Review).

## Open Questions

Nenhuma. A estratégia de baseline limpa está aprovada; o escopo backend é `usuarios` + api_group `auth` + `login` + `me`; gestão de usuários é feature futura; o primeiro admin é cadastro manual de ambiente; `senha_hash` permanece tipo `password`.
