## Purpose

Comportamento observável da interface Reflex do CostGuard para o fluxo de descoberta e importação
de projetos AWS a partir de um provedor, consumindo os endpoints já existentes
(`POST /provedores/{id}/descobrir-projetos` e `POST /provedores/{id}/importar-projetos`). Define a
apresentação de resultados (existentes vs novos), a seleção dos novos, a importação com feedback,
a atualização após importação, os estados de loading/erro/sucesso e a restrição admin-only como
UX sobre a autorização que permanece no backend — preservando o design e os componentes já
consolidados, sem alterar nenhum contrato de backend.

## ADDED Requirements

### Requirement: Ação de descoberta disponível por provedor AWS (admin-only)

A interface SHALL oferecer, na página de provedores, uma ação para iniciar a descoberta de
projetos de um provedor AWS. A ação SHALL ser exibida apenas quando o usuário tiver papel admin
(`AuthState.is_admin`); para usuário `leitura`, a ação e os controles de importação MUST NOT ser
apresentados. Essa ocultação é apenas UX — a autorização real permanece no backend, que rejeita
descoberta/importação de não-admin. A ação SHALL preservar o design e os componentes existentes
(ex.: `rx.dialog`, `app_shell`, `pill`, elementos de tabela), sem nova página nem redesenho.

#### Scenario: Admin vê a ação de descoberta

- **WHEN** um admin acessa a página de provedores
- **THEN** cada provedor AWS apresenta a ação "Descobrir projetos"

#### Scenario: Usuário leitura não vê a ação

- **WHEN** um usuário com papel leitura acessa a página de provedores
- **THEN** a ação de descobrir e os controles de importação não são apresentados
- **AND** essa ocultação é apenas UX; a autorização real permanece no backend

### Requirement: Descoberta consome o endpoint e exibe os resultados

A interface SHALL, ao acionar a descoberta, chamar `POST /provedores/{id}/descobrir-projetos`
com o token da sessão (`Authorization: Bearer`), e exibir os itens de `descobertos` (cada um com
`codigo`, `existente`, `projeto_id`). Durante a chamada, a interface SHALL exibir um estado de
carregamento e MUST NOT permitir disparo duplicado simultâneo. Uma resposta HTTP 401 SHALL ser
tratada pelo mecanismo central de sessão existente (limpar sessão e redirecionar ao login).

#### Scenario: Descoberta exibe a lista retornada

- **WHEN** um admin aciona a descoberta de um provedor e o backend responde com `descobertos`
- **THEN** a interface exibe cada código descoberto, indicando se é existente ou novo

#### Scenario: Carregamento durante a descoberta

- **WHEN** a descoberta está em andamento
- **THEN** a interface mostra um indicador de carregamento e impede um novo disparo simultâneo

#### Scenario: 401 na descoberta

- **WHEN** a chamada de descoberta recebe HTTP 401
- **THEN** a interface limpa a sessão e redireciona ao login, conforme o tratamento central existente

### Requirement: Distinção visual entre projetos existentes e novos

A interface SHALL distinguir visualmente os projetos descobertos que já existem
(`existente = true`) dos que são novos (`existente = false`). Projetos existentes MUST NOT ser
selecionáveis para importação e SHALL ser identificados como já existentes. Projetos novos SHALL
ser selecionáveis individualmente para importação.

#### Scenario: Existente é identificado e não selecionável

- **WHEN** a lista de descobertos contém um item com `existente = true`
- **THEN** ele é marcado como já existente e não pode ser selecionado para importação

#### Scenario: Novo é selecionável

- **WHEN** a lista de descobertos contém um item com `existente = false`
- **THEN** ele pode ser selecionado individualmente para importação

### Requirement: Seleção dos projetos novos

A interface SHALL permitir selecionar e desmarcar individualmente cada projeto novo, e SHALL
oferecer uma ação para selecionar todos os novos de uma vez. A ação de importar SHALL considerar
apenas os códigos novos efetivamente selecionados. Quando nenhum novo estiver selecionado, a
interface SHALL impedir o disparo da importação (ex.: ação desabilitada).

#### Scenario: Selecionar todos os novos

- **WHEN** o admin aciona "selecionar todos os novos"
- **THEN** todos os itens novos ficam selecionados e os existentes permanecem não selecionáveis

#### Scenario: Importação exige ao menos um novo selecionado

- **WHEN** nenhum projeto novo está selecionado
- **THEN** a ação de importar fica indisponível

### Requirement: Importação consome o endpoint com os selecionados

A interface SHALL, ao importar, chamar `POST /provedores/{id}/importar-projetos` com o token da
sessão e um corpo contendo os `codigos` dos novos selecionados. Durante a chamada, a interface
SHALL exibir carregamento e MUST NOT permitir submissão duplicada (duplo clique). Uma resposta
HTTP 401 SHALL ser tratada pelo mecanismo central de sessão existente.

#### Scenario: Importa os selecionados

- **WHEN** o admin confirma a importação com um ou mais códigos novos selecionados
- **THEN** a interface chama o endpoint de importação com exatamente esses códigos

#### Scenario: Submissão duplicada é impedida

- **WHEN** a importação já está em andamento
- **THEN** a interface impede um segundo disparo até a conclusão

### Requirement: Feedback de resultado e atualização após importação

A interface SHALL, após uma importação bem-sucedida, apresentar um feedback informando quantos
projetos foram criados e, quando houver, os ignorados (ex.: já existentes). Em seguida, a
interface SHALL atualizar o estado para refletir os novos como existentes — redescobrindo a lista
(nova chamada de descoberta) ou atualizando a lista de projetos — de modo que os códigos
importados deixem de aparecer como novos selecionáveis.

#### Scenario: Feedback de criados e ignorados

- **WHEN** a importação conclui com sucesso
- **THEN** a interface informa a quantidade de criados e, se houver, os ignorados

#### Scenario: Lista reflete os importados como existentes

- **WHEN** a importação de um código novo conclui com sucesso
- **THEN** uma nova descoberta (ou atualização de lista) passa a apresentar esse código como existente, não mais como novo selecionável

### Requirement: Erros sanitizados na interface

A interface MUST NOT exibir ao usuário o diagnóstico técnico bruto do backend (ex.: o objeto
`diagnostico`, status HTTP cru, `RequestId`). Em caso de falha (rede, erro do backend, ou
`status = "erro"` na descoberta), a interface SHALL exibir uma mensagem clara e sanitizada,
preservando a mensagem sanitizada vinda do backend quando disponível, sem travar a página.

#### Scenario: Falha de descoberta mostra mensagem sanitizada

- **WHEN** a descoberta falha (erro de rede ou backend retorna `status = "erro"`)
- **THEN** a interface exibe uma mensagem clara e sanitizada, sem mostrar o `diagnostico` técnico bruto

#### Scenario: Falha de importação mostra mensagem sanitizada

- **WHEN** a importação falha
- **THEN** a interface exibe uma mensagem clara e sanitizada, sem expor dados técnicos crus
