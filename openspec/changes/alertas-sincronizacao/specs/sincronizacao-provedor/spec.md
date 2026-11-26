## ADDED Requirements

### Requirement: Sincronização manual por provedor

A página `/provedores` SHALL oferecer ao admin, para cada provedor com `status = ok`, a ação "Sincronizar agora", que executa em sequência: sincronização do inventário de recursos, classificação de custos por equipe e avaliação de alertas. A segunda etapa SHALL ser executada mesmo que a primeira falhe. A ação MUST NOT estar disponível para usuário leitura nem para provedor sem conexão; a autorização real permanece no backend.

#### Scenario: Admin sincroniza um provedor conectado

- **WHEN** o admin aciona "Sincronizar agora" em um provedor com status `ok`
- **THEN** as três etapas são executadas em ordem e o resultado de cada uma é exibido

#### Scenario: Provedor sem conexão

- **WHEN** o provedor não está com status `ok`
- **THEN** a ação não é oferecida

### Requirement: Resultado da sincronização não silencioso

O frontend SHALL exibir, por etapa, sucesso com os principais contadores, aviso devolvido pelo backend ou erro com mensagem sanitizada. Uma falha MUST NOT ser omitida nem apresentada como sucesso. HTTP 401 em qualquer etapa SHALL encerrar a sessão pelo tratamento central. Durante a execução, a ação SHALL ficar indisponível para evitar disparo duplicado.

#### Scenario: Falha no inventário

- **WHEN** a etapa de inventário retorna `status = erro` ou HTTP de erro
- **THEN** a etapa é exibida como falha com a mensagem do backend, a etapa de custos é executada e a avaliação de alertas registra a falha

#### Scenario: Aviso de tag de equipe

- **WHEN** a classificação de custos por equipe retorna `aviso`
- **THEN** o aviso é exibido junto ao resultado da etapa
