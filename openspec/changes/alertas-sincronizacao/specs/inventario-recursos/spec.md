## MODIFIED Requirements

### Requirement: Estado da sincronização e falhas não silenciosas

O sistema SHALL responder à sincronização com um resultado contendo, no mínimo: o provedor, o
`status` (`sucesso`/`erro`), contadores úteis à operação (ex.: recursos encontrados/ativos,
recursos desativados na reconciliação, equipes criadas, recursos sem responsável, projetos
desconhecidos) e uma mensagem sanitizada em caso de erro. A falha MUST NOT ser silenciosa. Em erro
(AWS, paginação, enumeração de regiões ou pré-condição), o sistema SHALL retornar indicação
explícita e sanitizada, sem reconciliar. Cada execução que passar das pré-condições SHALL ser
registrada em `coletas_inventario` com `provedor_id`, `status`, `recursos_encontrados`,
`projetos_desconhecidos`, mensagem sanitizada e `executado_em`.

#### Scenario: Sincronização bem-sucedida reporta contadores

- **WHEN** uma sincronização conclui com sucesso
- **THEN** o resultado informa `status = sucesso` e os contadores de inventário/reconciliação/equipes/sem-responsável/projetos-desconhecidos

#### Scenario: Erro reporta estado sanitizado

- **WHEN** a sincronização falha
- **THEN** o resultado informa `status = erro` com mensagem sanitizada, e nenhum recurso é desativado

#### Scenario: Execução registrada

- **WHEN** uma sincronização termina, com sucesso ou erro, após as pré-condições
- **THEN** uma linha é gravada em `coletas_inventario` com o status e a mensagem sanitizada

## ADDED Requirements

### Requirement: Leitura dos recursos não classificados

O sistema SHALL permitir que um usuário autenticado liste, por `GET /recursos-nao-classificados`, os recursos ativos sem projeto válido (`projeto_id = null`), com `id`, `provedor_id`, `provedor_nome`, `arn`, `servico`, `regiao` e `codigo_projeto_tag`. Sem token, SHALL responder HTTP 401.

#### Scenario: Listar não classificados

- **WHEN** um usuário autenticado solicita os recursos não classificados
- **THEN** recebe apenas recursos ativos com `projeto_id = null`
