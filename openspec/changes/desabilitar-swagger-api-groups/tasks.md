## 1. Alterar api_group auth

- [x] 1.1 Em `xano/api/auth/auth.xs`, substituir `swagger = {token: "..."}` por `swagger = {active: false}`, sem alterar `canonical`, `guid` nem adicionar `active` de grupo. Verificação: o arquivo não contém mais token; diff mostra apenas a linha `swagger` alterada. **Feito: linha `swagger` substituída por `swagger = {active: false}`; `canonical`/`guid` intactos; sem `active` de grupo; diff 1 linha.**

## 2. Alterar api_group app

- [x] 2.1 Em `xano/api/app/app.xs`, adicionar `swagger = {active: false}`, sem alterar `canonical`, `description`, `guid` nem adicionar `active` de grupo. Verificação: diff mostra apenas a linha `swagger` adicionada. **Feito: `swagger = {active: false}` adicionado após `description`; demais linhas intactas; diff 1 linha (CRLF preservado).**

## 3. Validação local

- [x] 3.1 Executar `openspec validate desabilitar-swagger-api-groups --strict`. Verificação: validação aprovada. **Feito: "Change 'desabilitar-swagger-api-groups' is valid"; `openspec validate --specs --all` sem falhas.**
- [x] 3.2 Confirmar que nenhum arquivo versionado contém o token Swagger antigo e que `git status --short` lista apenas os dois `.xs` e a pasta da change. Verificação: busca pelo token sem ocorrências; status sem arquivos inesperados. **Feito: busca pelo token antigo no working tree (fora `.git`/`.venv`/`.web`) sem ocorrências; status lista apenas os dois `.xs` e a pasta da change.**

## 4. Dry-run Xano

- [x] 4.1 Executar `xano workspace push -d ./xano --dry-run --no-guids --no-fast` (saída com o token mascarado). Verificação: o preview lista somente os api_groups `auth` e `app` como atualização, sem criações, remoções ou outros objetos. **Feito: dry-run de referência antes da edição = "No changes to push"; após a edição = "API Groups ~2 updated" com `UPDATE api_group app` e `UPDATE api_group auth`, sem CREATE/DELETE nem outros objetos.**

## 5. Publicação no Xano

- [x] 5.1 Após aprovação explícita do usuário, executar `xano workspace push -d ./xano --no-guids --no-fast` (sem `--force`, `--sync` ou `--delete`). Verificação: push concluído sem erro, aplicando apenas os dois api_groups. O dry-run pós-publicação não deve apresentar alterações funcionais inesperadas. É aceita exclusivamente a divergência persistente do api_group `auth` causada pelo token Swagger mantido internamente pelo Xano mesmo com `swagger.active=false`. Nenhum token deve ser copiado para o repositório. **Feito: o CLI recusou a execução em ambiente não interativo sem `--force` (não autorizado); a publicação foi executada manualmente pelo usuário com o comando aprovado. Estado exportado pelo Xano: `app` = `swagger = {active: false}`; `auth` = `swagger = {active: false, token: <oculto, não versionado>}`. Dry-run pós-publicação: apenas `UPDATE api_group auth` (divergência aceita, documentada no design); nenhuma outra alteração. `auth.xs` local permanece sem token.**

## 6. Validação dos endpoints após publicação

- [x] 6.1 Validar `POST /login` (credenciais válidas emitem token), `GET /me` com o token (retorna `username`/`role`) e `GET /projetos` com o token (responde normalmente). Verificação: respostas equivalentes às anteriores à mudança. **Feito (credenciais E2E locais, sem exposição): `POST /login` → HTTP 200, token emitido, "Login realizado com sucesso"; `GET /me` → HTTP 200 com `username`, `nome`, `role`; `GET /projetos` → HTTP 200, lista com 7 projetos.**
- [x] 6.2 Validar que `GET /projetos` e `GET /me` sem token continuam respondendo HTTP 401. Verificação: 401 observado. **Feito: sem `Authorization`, `GET /me`, `GET /projetos` e `GET /provedores` → HTTP 401 `ERROR_CODE_UNAUTHORIZED`.**

## 7. Validação da indisponibilidade da documentação

- [x] 7.1 Confirmar no Xano (configurações dos api_groups `auth` e `app`) que a documentação Swagger está desabilitada e que o acesso à documentação, inclusive com o token antigo, não está disponível. Verificação: evidência registrada sem expor o token. **Feito: configuração exportada pelo Xano (`xano workspace pull` em diretório temporário fora do repositório, removido em seguida) mostra `swagger.active = false` em `auth` e `app`; os api_groups e endpoints seguem ativos (ver 6.1/6.2). Complementar: `/apispec:<canonical>` (json/yaml) → HTTP 404 sem especificação para `app` sem token e para `auth` sem token, com o token antigo e com o token atual do servidor (formato de URL não confirmado na documentação do Xano; evidência principal é a configuração exportada).**
