## Context

Ver proposal.md — Why. Estado atual confirmado:

- `xano/api/auth/auth.xs`: `canonical = "hd-zNDLF"`, `swagger = {token: <valor versionado>}`.
- `xano/api/app/app.xs`: `canonical = "costguard-app"`, sem opção `swagger`.
- Documentação XanoScript do `api_group`: sem `swagger` → documentação pública e sem token;
  `swagger = {token: "..."}` → documentação privada (token armazenado em plain text e exportado
  no `.xs`); `swagger = {active: false}` → documentação desabilitada.
- O `active` de nível de grupo é outra opção (desabilita o grupo inteiro) e não deve ser usado.
- Dry-run de referência (`xano workspace push -d ./xano --dry-run --no-guids --no-fast`) antes da
  edição: "No changes to push" — local e workspace publicado estavam idênticos.
- O frontend Reflex não referencia Swagger.

## Goals / Non-Goals

**Goals:**

- Declarar explicitamente `swagger = {active: false}` nos dois api_groups.
- Publicar apenas essas duas alterações de configuração.

**Non-Goals:**

- Alterar `active` de grupo, `canonical`, `guid`, `description` ou qualquer endpoint/tabela.
- Reescrever histórico Git.

## Decisions

### D1 — Desabilitar a documentação em vez de mantê-la privada

Alternativas:

- **Remover a linha `swagger`**: rejeitada — o default do Xano é documentação pública.
- **Rotacionar o token e manter privada**: rejeitada — o Xano armazena e exporta o token em plain
  text; o próximo `pull` voltaria a versioná-lo.
- **Substituir por variável de ambiente**: rejeitada — a documentação do `api_group` não indica
  suporte a `$env` nessa opção.
- **`swagger = {active: false}`** (escolhida): elimina a superfície e o segredo; nenhum consumidor
  conhecido depende da documentação.

### D2 — Edição mínima dos `.xs`

Apenas a linha `swagger` é substituída (auth) ou adicionada (app). `canonical`, `description` e
`guid` permanecem inalterados para que o push atualize os grupos existentes, sem criar novos.

### D3 — Push restrito e sem writeback

O dry-run e o push usam `--no-guids` e `--no-fast` para não alterar arquivos locais
(writeback de GUIDs / `.xano/sync_state.json`). O push é parcial (padrão, sem `--sync` e sem
`--delete`), de modo que só os arquivos alterados são enviados. Saídas são mascaradas para não
exibir o token antigo.

## Risks / Trade-offs

- [O Xano trata `active: false` de `swagger` de forma diferente da documentada] → validar após a
  publicação que os endpoints respondem e que a documentação está indisponível; rollback abaixo.
- [Ferramenta externa não mapeada usa a URL da documentação] → nenhuma conhecida; se surgir,
  avaliar documentação privada fora do repositório em change própria.
- [Token antigo permanece no histórico Git do repositório privado] → perde utilidade após a
  publicação; reescrita de histórico não é necessária e é reservada ao usuário.
- [`xano workspace pull` futuro reintroduz configuração diferente] → a revisão de diff antes de
  commit deve confirmar `swagger = {active: false}`.

## Comportamento observado após a publicação

A publicação foi executada manualmente pelo usuário (o CLI exige confirmação interativa e o uso de
`--force` não foi autorizado). Estado exportado pelo Xano após a publicação:

- `app`: `swagger = {active: false}` — idêntico ao local (o Xano apenas exporta `description`
  como comentário, o que o CLI trata como equivalente).
- `auth`: `swagger = {active: false, token: <oculto>}` — o Xano **mantém internamente um token
  Swagger server-side no grupo `auth` mesmo com a documentação desabilitada**. Esse token é
  diferente do token antigo que estava versionado.

Consequências e regras decorrentes (decisão do usuário: aceitar o estado atual):

- O token atual do servidor **não foi versionado** e **não deve ser copiado** para
  `xano/api/auth/auth.xs`; o arquivo local permanece `swagger = {active: false}`.
- Por isso o dry-run pós-publicação apresenta de forma persistente `UPDATE api_group auth`. Essa
  divergência é aceita como estado interno/normalização do Xano e não representa alteração
  funcional.
- Um futuro `xano workspace pull` pode trazer esse token novamente para `auth.xs`. **Qualquer pull
  deve ser revisado antes de commit**, removendo o token se ele reaparecer.
- Enquanto `swagger.active = false`, o token não concede acesso à documentação (validado: acesso
  com o token antigo e com o token atual não retornou especificação).
- Se a documentação Swagger for reativada no futuro, essa configuração de segurança deve ser
  revista em change própria (o token interno voltaria a ser funcional).

## Migration Plan

1. Editar os dois `.xs`; validar a change com `openspec validate --strict`.
2. Dry-run: deve listar somente os dois api_groups como atualização.
3. Publicar (após aprovação do usuário) com o mesmo conjunto de flags, sem `--force`.
4. Validar endpoints (`/login`, `/me`, `GET /projetos`, 401 sem token) e indisponibilidade da
   documentação.

Rollback: restaurar no Xano (UI das configurações do api_group) a opção de documentação anterior,
ou republicar o `.xs` anterior. Não é necessário rollback de endpoints, pois não são alterados.
