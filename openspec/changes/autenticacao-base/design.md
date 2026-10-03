## Context

Ver `proposal.md` — Why para a motivação. Esta change é a primeira fatia vertical do CostGuard e conecta o frontend Reflex ao backend Xano para o fluxo de autenticação.

Estado atual relevante (confrontado com a documentação do projeto):

- **Backend Xano — existente e reaproveitável, com padronização de nomes autorizada nesta change**:
  - `xano/api/auth/login_POST.xs`: hoje recebe `usuario` e `senha`; será padronizado para `username` e `password`. Busca o usuário, rejeita se `status != "ativo"`, compara o password com `security.check_password` contra `senha_hash`, e emite JWT via `security.create_auth_token` (tabela `usuarios`, `expiration = 28800` s = 8 h, `extras` com `usuario_id`, `usuario`, `role`). Mensagem de erro única "Usuário ou senha inválidos" (não permite enumeração).
  - `xano/api/auth/me_GET.xs`: `auth = "usuarios"`; resolve `$auth.id` e hoje retorna `{usuario, nome, role}`; será padronizado para expor `username` e `role`.
  - `xano/table/usuarios.xs`: campo `senha_hash` do tipo `password` (hashing automático confirmado via Xano Developer MCP); campo `usuario` (único) que pode ser renomeado para `username`; `email` único; `role` ∈ {admin, leitura}; `status` ∈ {ativo, inativo}.
- **Frontend Reflex — praticamente no template inicial**: `projetoImpacta/projetoImpacta.py` contém apenas a página "Welcome to Reflex". `rxconfig.py` usa `app_name="projetoImpacta"` com plugins Radix/Tailwind. `reflex==0.9.12`.

Restrições que moldam a abordagem: frontend exclusivamente Reflex; autorização real somente no Xano; nenhum segredo versionado; documentação atual do Reflex deve ser consultada via Agent Skills no momento da implementação; comportamento do Xano deve ser confirmado via Developer MCP quando houver dúvida.

## Goals / Non-Goals

**Goals:**

- Reaproveitar `login_POST` e `me_GET` existentes, confrontando-os com a spec antes de qualquer alteração.
- Definir onde e como o token vive no frontend Reflex e como é reenviado nas requisições autenticadas.
- Definir o tratamento consistente de HTTP 401 no frontend.
- Definir a estrutura mínima de páginas Reflex (login + área protegida) e o mecanismo de proteção/redirecionamento.
- Manter a fronteira: frontend não é mecanismo de segurança.

**Non-Goals (nível de design):**

- Não definir refresh token, "lembrar-me" persistente entre reinícios, nem expiração deslizante — o token do backend expira em 8 h e isso basta para esta fatia.
- Não desenhar telas além de login e uma área autenticada mínima para exercitar o fluxo.
- Não introduzir novos endpoints. A alteração de schema/endpoints Xano se limita à padronização de nomes de autenticação (D9); qualquer outra divergência descoberta no apply deve interromper e ser registrada.
- Não renomear campos ou artefatos além do necessário para padronizar a interface de autenticação.

## Decisions

### D1 — Reaproveitar os endpoints Xano existentes

`login_POST` e `me_GET` já cobrem a lógica dos requisitos da spec (login, emissão de token, `/me` com identidade e role, 401 para token ausente/inválido via `auth = "usuarios"`). Decisão: **não reimplementar a lógica**; reaproveitar e apenas padronizar os nomes do contrato (ver D9). Alternativa descartada: recriar endpoints "OpenSpec-first" — contraria a regra de não reimplementar código só por anteceder o OpenSpec.

### D2 — Estado de sessão no Reflex via `rx.State`

A sessão (token, `username`, `role`, flag de autenticado) será mantida em um State de autenticação do Reflex. Decisão coerente com "frontend exclusivamente Reflex". A API concreta de State/eventos/vars será confirmada via **Reflex Agent Skills (reflex-docs)** no apply, pois a versão fixada é `0.9.12`.

### D3 — Persistência do token via `rx.SessionStorage` (decisão fechada)

O token e os dados de sessão serão mantidos em `rx.SessionStorage` do Reflex. Conforme a documentação oficial (Browser Storage / Client Storage — Reflex), `rx.SessionStorage` sobrevive ao recarregamento e à restauração de página, mas é limpo quando a aba/navegador é fechado, e fica isolado à aba em que foi criado. Esse comportamento corresponde exatamente ao requisito de sessão desta change: *reload mantém a sessão; fechar e reabrir o navegador não precisa manter*.

Alternativas descartadas:
- `rx.LocalStorage`: persiste indefinidamente entre sessões do navegador, o que excede o comportamento desejado (a sessão sobreviveria ao fechamento do navegador).
- `rx.Cookie` de sessão: também atenderia (cookie sem `max_age` expira ao fechar o navegador), mas `rx.SessionStorage` expressa a intenção de forma direta, sem depender de configuração de expiração, e mantém o token fora do envio automático em cada requisição HTTP.
- Token apenas em memória do State: perderia a sessão a cada reload, quebrando o requisito.

O logout e a reação a 401 usarão `rx.remove_session_storage`/`rx.clear_session_storage` para descartar a sessão. As assinaturas exatas serão confirmadas via reflex-docs no apply; o comportamento (não a assinatura) está fixado aqui.

### D4 — Cliente HTTP e envio do token

As chamadas ao Xano (`login`, `/me` e futuras autenticadas) partirão do backend do Reflex (event handlers) usando um cliente HTTP já disponível no ambiente Python (ex.: `httpx`, que acompanha o stack do Reflex). O token será enviado no cabeçalho `Authorization: Bearer <token>` conforme o padrão do Xano. Confirmar via reflex-docs/Developer MCP no apply. Alternativa descartada: adicionar uma biblioteca de cliente nova — desnecessário e contra a regra de não introduzir dependências sem justificativa.

### D5 — Base URL do Xano por configuração, sem segredo versionado

A URL base do backend Xano será lida de configuração/variável de ambiente, não fixada em código versionado. O token de autenticação é dado do usuário em runtime, não um segredo de build; ainda assim não deve ser logado. Nenhuma credencial de serviço entra no frontend.

### D6 — Rotas e proteção por verificação no carregamento (decisão fechada)

Rotas desta change:
- `/login` — página pública de login.
- `/` — área autenticada mínima protegida (não é o dashboard definitivo).

A página `/` verificará a sessão no carregamento (padrão `on_load` do Reflex) e redirecionará para `/login` quando não houver sessão autenticada. A validação real do token ocorre no Xano (via `/me` e nos endpoints `auth`), não no cliente. Assim a proteção do frontend é apenas navegação/UX. Confirmar a API de `on_load`/redirecionamento via reflex-docs no apply.

### D7 — Tratamento centralizado de 401

Um ponto único no frontend interpretará respostas HTTP 401 do Xano: descarta a sessão local e trata o usuário como não autenticado (encaminhando ao login). Evita espalhar tratamento de 401 por cada chamada.

### D8 — Validação da sessão via `/me`

Após o login e ao (re)carregar a aplicação com token presente, o frontend chamará `/me` para confirmar a validade do token e obter `username` e `role` atuais do backend, em vez de confiar apenas em dados embutidos no token. Mantém o backend como fonte de verdade da identidade.

### D9 — Padronização de nomenclatura `username`/`password`/`role` com renomeação da coluna (decisão fechada)

O contrato de autenticação passa a usar `username`, `password` e `role` no frontend e na API Xano. Decisão aprovada: **renomear a coluna `usuarios.usuario` para `username`** para consistência entre tabela, API e frontend. A coluna de senha `senha_hash` **não** é renomeada. Resultado alvo da tabela `usuarios`: `username`, `senha_hash`, `role` (além dos demais campos existentes).

Impacto mapeado por análise dos arquivos `xano/**/*.xs`, caminhos confirmados no workspace:
- `xano/table/usuarios.xs`: renomear o campo `usuario`→`username` e o índice `btree|unique` sobre `usuario`→`username`.
- `xano/api/auth/login_POST.xs`: inputs `usuario`→`username` e `senha`→`password`; `db.get ... field_name = "usuario"` → `"username"`; `text_password` de `security.check_password` lê o novo input; claims do JWT que referenciam o campo acompanham o novo nome.
- `xano/api/auth/me_GET.xs`: leitura `$usuario_atual.usuario` → `.username` e chave de resposta `usuario`→`username`.
- `xano/api/auth/criar_usuario_POST.xs`: input, `db.get field_name="usuario"`, `db.add {usuario: ...}` e a resposta `{usuario: ...}` passam a usar `username`.
- `xano/api/auth/editar_usuario_PATCH.xs`: a resposta expõe `$usuario_atualizado.usuario` → `.username`.

**Fora do impacto (confirmado por análise):** os endpoints `listar_projetos_GET`, `criar_projeto_POST`, `editar_projeto_PATCH`, `desativar_projeto_POST`, `deletar_usuario_DELETE` e `aws/costs_POST` usam apenas variáveis locais (`$usuario_logado`, `$usuario_alvo`) e o nome da tabela em `auth = "usuarios"`, **não** o campo `usuario`. Não serão alterados.

**Campo de senha:** permanece `password senha_hash` (tipo `password`, hashing automático). O nome interno `senha_hash` é mantido — o contrato externo usa `password` apenas como chave de input; a coluna continua sendo credencial protegida.

**Nota sobre `criar_usuario`/`editar_usuario`:** não implementam funcionalidade nova nesta change; são tocados apenas o necessário para acompanhar a renomeação do campo e não quebrarem. Nenhuma outra funcionalidade desses endpoints é alterada.

## Risks / Trade-offs

- **Token em `rx.SessionStorage` (D3) é acessível a scripts no navegador (risco de XSS)** → Mitigação: não é mecanismo de segurança do sistema; a autorização real é no Xano e o token expira em 8 h. `SessionStorage` some ao fechar o navegador, reduzindo a janela de exposição. Não versionar segredos, não logar o `password` nem o token, e manter Reflex como única stack de frontend reduz a superfície. Endurecimento adicional (cookies HttpOnly, CSRF) fica fora desta fatia e pode ser tratado em change futura, conforme decisão de manter o MVP simples.
- **Expiração de 8 h sem refresh (Non-Goal)** → Mitigação: o tratamento de 401 (D7) leva o usuário de volta ao login de forma limpa quando o token expira.
- **APIs concretas do Reflex 0.9.12 podem diferir do assumido (D2/D6)** → Mitigação: `rx.SessionStorage` e seus removedores estão confirmados na documentação oficial; `on_load`, event handlers e cliente HTTP serão confirmados via Reflex Agent Skills antes de implementar. O design fixa o comportamento, não a assinatura exata.
- **Renomear o campo `usuarios.usuario` amplia o número de arquivos tocados (D9)** → Mitigação: impacto mapeado e restrito a `usuarios.xs` e aos quatro endpoints de usuário/autenticação; endpoints de projetos/custos não são afetados. Validar cada `.xs` alterado via Xano Developer MCP.
- **Divergência entre o backend existente e a spec descoberta no apply** → Mitigação: pela regra do projeto, interromper e registrar a decisão em vez de improvisar alteração fora do escopo.

## Open Questions

Nenhuma. A última decisão pendente (renomear a coluna `usuarios.usuario` → `username`) foi aprovada e incorporada ao escopo (D9); `senha_hash` não é renomeado.
