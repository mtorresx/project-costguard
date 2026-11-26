## Why

O backend de descoberta/importação de projetos AWS já está publicado e validado em E2E
(`descoberta-projetos`): `POST /provedores/{id}/descobrir-projetos` (read-only) e
`POST /provedores/{id}/importar-projetos` (cria só inexistentes). Hoje, porém, não há forma de
o admin usar esse fluxo pela interface — ele precisaria chamar os endpoints manualmente. Esta
change adiciona ao frontend Reflex o fluxo visual: a partir de um provedor AWS, descobrir os
projetos (valores de tag), distinguir existentes de novos, selecionar os novos e importá-los,
com feedback e atualização da lista.

A interface segue o design/UX já consolidado do CostGuard (tema, `app_shell`, `rx.dialog`,
`pill`, elementos de tabela), usando o material do frontend de referência apenas como
**referência visual** — não como contrato funcional, já que aquele protótipo usa contratos
antigos/divergentes do backend atual.

## What Changes

- Novo fluxo na página `/provedores`: por provedor AWS, uma ação **admin-only** "Descobrir
  projetos" abre um modal (`rx.dialog`, padrão já usado) que:
  - chama `POST /provedores/{id}/descobrir-projetos` e exibe os `descobertos`;
  - marca visualmente **existentes** (não selecionáveis) e **novos** (selecionáveis via checkbox);
  - oferece "Selecionar todos os novos";
  - com seleção, aciona `POST /provedores/{id}/importar-projetos` com os códigos escolhidos;
  - exibe loading, impede duplo clique, mostra feedback (criados/ignorados) e **redescobre** a
    lista após sucesso (os novos passam a aparecer como existentes).
- Novo estado Reflex para esse fluxo (no `ProvedoresState` existente ou em um state dedicado),
  seguindo o padrão atual (`AuthState`, `get_xano_app_base_url()`, tratamento de 401 central).
- Controles do fluxo visíveis apenas para admin (ocultação é UX; a autorização real é backend).
- Mensagens de erro sanitizadas (nunca expor `diagnostico` técnico bruto ao usuário).
- **BREAKING**: nenhum. Nenhuma alteração de backend, schema, autenticação ou dos fluxos
  existentes (criar/editar/testar/desativar provedor, CRUD de projetos).

Fora do escopo:

- Alterar o frontend de referência (somente referência) ou qualquer endpoint/lógica Xano.
- Alterar classificação, coleta, Mock, schemas, autenticação backend.
- Página nova dedicada (o fluxo vive dentro de `/provedores`).
- Edição de orçamento no fluxo de importação (projetos nascem com budget 0, conforme o backend;
  ajuste posterior pelo CRUD de projetos existente).

## Capabilities

### New Capabilities

- `frontend-descoberta-projetos`: comportamento observável da interface Reflex para descobrir e
  importar projetos AWS a partir de um provedor, consumindo os endpoints existentes, com
  distinção visual existentes/novos, seleção de novos, importação com feedback, atualização pós
  importação, estados de loading/erro/sucesso e restrição admin-only (UX sobre autorização
  backend). Não altera o contrato das capabilities de backend.

### Modified Capabilities

(nenhuma — a capability `interface-frontend` descreve tema/estrutura/preservação de auth e não
muda; este fluxo é um comportamento novo de UI, declarado como capability própria. A autenticação
e a autorização backend permanecem conforme `autenticacao` e `descoberta-projetos`.)

## Impact

- **Frontend Reflex** (`projetoImpacta/`):
  - `pages/provedores.py`: botão/ação "Descobrir projetos" por provedor (admin) + modal do fluxo.
  - `pages/provedores_state.py`: estado e eventos de descoberta/seleção/importação, ou um novo
    `pages/descoberta_state.py` dedicado (ver design).
  - Reuso de `components/layout.py` (app_shell), `components/pill.py`, `components/tabela.py`,
    `theme.py`, `AuthState` e `config.get_xano_app_base_url()`.
- **Backend/Xano, Mock, auth**: nenhuma alteração.
- **Referência visual**: o frontend de referência consultado apenas para padrões de UI; não
  alterado nem importado.
