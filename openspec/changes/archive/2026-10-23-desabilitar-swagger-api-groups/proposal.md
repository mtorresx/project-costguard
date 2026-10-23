## Why

A documentação Swagger/OpenAPI gerada automaticamente pelo Xano está exposta nos dois api_groups do
CostGuard. O grupo `auth` usa documentação privada protegida por um token que está versionado em
texto puro no repositório desde o commit inicial (o Xano exporta esse token em plain text no
`.xs`). O grupo `app` não declara configuração `swagger`, e a documentação XanoScript informa que,
nesse caso, a documentação é **pública e sem token**. Isso viola a regra do projeto de não versionar
tokens e expõe, sem necessidade, o mapa de rotas e inputs das APIs de negócio. O frontend Reflex não
consome a documentação Swagger, então ela pode ser desabilitada sem impacto funcional.

## What Changes

- Desabilitar a documentação Swagger/OpenAPI automática do api_group `auth`, substituindo
  `swagger = {token: "..."}` por `swagger = {active: false}`. O token versionado é removido do
  arquivo como consequência.
- Desabilitar a documentação Swagger/OpenAPI automática do api_group `app`, adicionando
  `swagger = {active: false}`.
- Nenhum endpoint é alterado ou desabilitado: o `active` dos api_groups permanece inalterado
  (default `true`) e nenhum contrato HTTP funcional muda (rotas, inputs, respostas, autenticação
  e autorização).
- Após a publicação, o token Swagger antigo deixa de ter utilidade, pois não há mais documentação a
  proteger.

Risco tratado: **baixo** para o token (protege apenas a documentação do grupo `auth`, não concede
acesso a endpoints; repositório privado) e **baixo a médio** para o grupo `app` (documentação
provavelmente pública, expondo rotas e inputs de negócio, sem expor dados ou credenciais).

Fora do escopo:

- Qualquer alteração de endpoints, tabelas, autenticação, autorização ou frontend.
- Reescrita do histórico Git para remover o token antigo (o token perde a utilidade após a
  publicação; operações de histórico são reservadas ao usuário).
- Correção do aviso pré-existente `Unknown operation ID 'review'` em `openspec/config.yaml`.
- Demais pendências técnicas identificadas no onboarding.

## Capabilities

### New Capabilities

- `documentacao-api`: política de exposição da documentação automática (Swagger/OpenAPI) dos
  api_groups do backend Xano — desabilitada em todos os grupos do CostGuard, sem afetar a
  disponibilidade dos endpoints.

### Modified Capabilities

(nenhuma — os contratos de `autenticacao`, `projetos`, `provedores` e demais capabilities não
mudam.)

## Impact

- Arquivos: `xano/api/auth/auth.xs`, `xano/api/app/app.xs`.
- Backend Xano: atualização de configuração dos dois api_groups na publicação; nenhum endpoint
  alterado.
- Frontend Reflex: nenhum impacto (não consome Swagger).
- Ferramentas externas que eventualmente dependessem da URL da documentação Swagger deixam de
  acessá-la (nenhuma conhecida no projeto).
