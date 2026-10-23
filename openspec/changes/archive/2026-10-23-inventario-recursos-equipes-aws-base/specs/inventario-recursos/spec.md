## Purpose

Inventário de recursos AWS do CostGuard: consulta read-only da Resource Groups Tagging API
(`GetResources`) por região habilitada da conta, filtrando pela Tag Key de projeto do provedor,
resolve para cada recurso o projeto (tag `PRJ`) e a equipe (tag `EQP`, criando-a automaticamente
quando necessário), trata o estado "Sem responsável" (projeto válido, sem equipe), persiste os
recursos por upsert e reconcilia os ausentes (desativa) apenas após uma sincronização completa e
bem-sucedida. Admin-only, autorização no backend, credenciais somente leitura e segredos jamais
expostos. Não calcula custo (escopo de change futura). A nuvem é a fonte da verdade da
classificação.

## ADDED Requirements

### Requirement: Entidade Recurso

O sistema SHALL persistir recursos inventariados com, no mínimo: `id`, `provedor_id` (origem),
`arn` (ARN completo e íntegro do recurso), `regiao`, `servico`, `projeto_id` (nullable),
`equipe_id` (nullable), o valor cru da tag de projeto, o valor cru da tag de equipe, um indicador
de presença no último inventário (`ultima_vista_em` e/ou `sync_id`) e `ativo` (booleano de
reconciliação). O ARN SHALL ser preservado integralmente. A unicidade de um recurso SHALL ser a
combinação `(provedor_id, arn)` — o mesmo ARN pertence a um provedor específico no modelo. O
sistema MUST NOT truncar nem reescrever o ARN.

#### Scenario: Recurso persistido com os campos do contrato

- **WHEN** o inventário processa um recurso retornado pela AWS
- **THEN** passa a existir um registro com `provedor_id`, `arn` íntegro, `regiao`, `servico`, `projeto_id`/`equipe_id` (possivelmente nulos), os valores crus das tags e o estado de presença/`ativo`

#### Scenario: Unicidade por provedor e ARN

- **WHEN** o mesmo `arn` é reprocessado para o mesmo `provedor_id` numa nova sincronização
- **THEN** o registro existente é atualizado (upsert), sem criar duplicata para `(provedor_id, arn)`

### Requirement: Sincronização restrita a admin

O sistema SHALL permitir executar a sincronização de recursos apenas a usuários autenticados com
`role = admin`, validando a autorização no backend. O usuário `leitura` MUST NOT conseguir
executar a sincronização. Uma requisição sem token válido SHALL receber HTTP 401.

#### Scenario: Admin executa a sincronização

- **WHEN** um admin solicita a sincronização de recursos de um provedor elegível
- **THEN** o backend executa a sincronização

#### Scenario: Usuário leitura não sincroniza

- **WHEN** um usuário com role leitura tenta sincronizar recursos
- **THEN** o backend nega a operação com erro de autorização e nada é consultado ou gravado

#### Scenario: Sincronização sem autenticação

- **WHEN** uma requisição de sincronização é feita sem token válido
- **THEN** o backend responde com HTTP 401

### Requirement: Sincronização exige provedor AWS conectado e Tag Key de projeto

O sistema SHALL executar a sincronização apenas para um provedor existente com `tipo = aws`,
`status = ok` e `tag_alocacao_projeto` definido. Se o provedor não existir, não for AWS, estiver
com `status` diferente de `ok`, ou não tiver a Tag Key de projeto definida, o sistema MUST NOT
chamar a AWS e SHALL rejeitar a operação com indicação explícita do motivo. A Tag Key de equipe
(`tag_alocacao_equipe`) SHALL ter valor efetivo resolvido com fallback padrão `EQP` quando o
provedor não a tiver definida (campo nulo/vazio, ex.: provedor legado), de modo que a ausência do
campo não force todos os recursos a "Sem responsável"; o estado "Sem responsável" decorre apenas da
ausência da tag de equipe no próprio recurso.

#### Scenario: Provedor elegível é aceito

- **WHEN** um admin solicita a sincronização para um provedor `aws` `status = ok` com `tag_alocacao_projeto` definido
- **THEN** o backend prossegue com a sincronização

#### Scenario: Provedor sem Tag Key de projeto é rejeitado

- **WHEN** o provedor não tem `tag_alocacao_projeto` definido
- **THEN** o backend rejeita a operação sem chamar a AWS e informa o motivo

#### Scenario: Provedor inativo, com erro, pendente ou inexistente

- **WHEN** o provedor tem `status` diferente de `ok`, não é `aws`, ou não existe
- **THEN** o backend rejeita a operação sem chamar a AWS (erro de validação ou recurso não encontrado, conforme o caso)

### Requirement: Proteção best-effort contra sincronização concorrente

O sistema SHALL evitar o duplo disparo acidental da sincronização de recursos do mesmo provedor na
operação normal, por meio de uma marca de estado no provedor (em andamento, início e identificador
da execução). Antes de iniciar o inventário, se já houver uma sincronização marcada como em
andamento para o provedor **e** essa marca ainda estiver dentro de uma janela de recuperação
razoável, o sistema SHALL rejeitar a nova execução com erro controlado e mensagem sanitizada ("Já
existe uma sincronização de recursos em andamento para este provedor."), MUST NOT iniciar o
inventário e MUST NOT liberar a marca da execução vigente. Se a marca estiver claramente
órfã/expirada (fora da janela), o sistema SHALL permitir a nova execução. O sistema SHALL limpar a
marca ao final, tanto no sucesso quanto nos caminhos de erro controlados, liberando apenas a marca
que pertence à própria execução. Esta proteção é **best-effort/operacional** e MUST NOT ser
interpretada como um lock atômico/transacional distribuído: há uma janela não atômica entre a
verificação e a aquisição; o endpoint é admin-only.

#### Scenario: Rejeita execução quando já há sincronização ativa

- **WHEN** um admin dispara a sincronização de um provedor cuja marca indica sincronização em andamento dentro da janela de recuperação
- **THEN** o backend rejeita com erro controlado e mensagem sanitizada, sem iniciar nova sincronização nem liberar a marca da execução vigente

#### Scenario: Permite execução quando a marca está órfã/expirada

- **WHEN** a marca de sincronização em andamento é mais antiga que a janela de recuperação (execução anterior interrompida)
- **THEN** o backend permite a nova execução, adquirindo a marca para si (recuperação best-effort por tempo)

#### Scenario: Marca é liberada no fim (sucesso e erro controlado)

- **WHEN** a sincronização termina (com sucesso ou com erro controlado)
- **THEN** o backend limpa a marca de em andamento, desde que ela ainda pertença a esta execução

### Requirement: Inventário consulta a Tagging API por região, sem filtrar por tag de equipe

O sistema SHALL obter o inventário chamando a Resource Groups Tagging API (`GetResources`),
autenticada com AWS SigV4 usando a credencial do provedor decifrada apenas no backend, de forma
read-only. A consulta SHALL usar `TagFilters` contendo **apenas** a Tag Key de projeto do provedor
(ex.: `[{ "Key": "PRJ" }]`) e MUST NOT filtrar simultaneamente pela Tag Key de equipe — filtrar
por equipe excluiria recursos com projeto e sem equipe, que são justamente os "Sem responsável".
A Tagging API é regional; o sistema SHALL consultar as regiões habilitadas da conta (ver requisito
de estratégia regional) e consolidar os resultados. O sistema MUST NOT ativar/alterar/remover tags
ou recursos na AWS.

#### Scenario: Filtra só pela Tag Key de projeto

- **WHEN** a sincronização consulta `GetResources`
- **THEN** o `TagFilters` contém apenas a Tag Key de projeto, de modo que recursos com projeto e sem equipe também retornem

#### Scenario: Somente leitura

- **WHEN** a sincronização é executada
- **THEN** o backend realiza apenas chamadas de leitura (`GetResources`/enumeração de regiões) e não modifica a conta AWS

### Requirement: Estratégia regional de inventário

O sistema SHALL tratar a regionalidade da Tagging API de forma explícita. No MVP, o sistema SHALL
enumerar as regiões habilitadas da conta (via EC2 `DescribeRegions`, somente leitura) e executar
`GetResources` em cada região habilitada, consolidando os recursos. O sistema MUST NOT assumir
silenciosamente uma única região (ex.: `us-east-1`) como se cobrisse toda a conta. A `regiao` de
cada recurso SHALL ser registrada. (O design documenta a alternativa de agregação por Resource
Explorer como evolução futura, fora do MVP.)

#### Scenario: Consulta todas as regiões habilitadas

- **WHEN** a sincronização é executada
- **THEN** o backend enumera as regiões habilitadas e consulta `GetResources` em cada uma, registrando a região de cada recurso

#### Scenario: Não assume região única

- **WHEN** a sincronização é executada
- **THEN** o backend não limita o inventário a uma única região fixa sem ter enumerado as regiões habilitadas

### Requirement: Paginação consolidada antes de reconciliar

O sistema SHALL tratar a paginação da Tagging API (`PaginationToken`), buscando todas as páginas de
cada região e consolidando os recursos. A sincronização só SHALL ser considerada **completa**
depois que todas as páginas de todas as regiões consultadas tiverem retornado com sucesso. O
sistema MUST NOT marcar recursos como desaparecidos (reconciliação) com base numa execução parcial
ou que falhou no meio.

#### Scenario: Todas as páginas antes de concluir

- **WHEN** a resposta inclui `PaginationToken`
- **THEN** o backend busca as páginas seguintes e só conclui a sincronização após processar todas

#### Scenario: Execução parcial não reconcilia

- **WHEN** a sincronização falha antes de consolidar todas as páginas/regiões
- **THEN** o backend não desativa nenhum recurso e preserva o estado anterior

### Requirement: Resolução de projeto por recurso

O sistema SHALL, para cada recurso retornado, localizar a tag de projeto (Tag Key =
`tag_alocacao_projeto`), normalizar seu valor em `trim`+maiúsculas e resolvê-lo contra
`projetos.codigo`. Quando o valor estiver ausente/vazio, ou não existir projeto correspondente, o
recurso SHALL ter `projeto_id = null` e `equipe_id = null`, e o sistema MUST NOT criar projeto nem
equipe. Quando o projeto existir mas estiver inativo, o sistema MUST NOT criar equipe; o recurso
SHALL ser persistido com `projeto_id` do projeto inativo e `equipe_id = null`, e a ocorrência SHALL
ser contabilizada de forma rastreável (o comportamento é documentado no design, não silencioso).

#### Scenario: Projeto resolvido

- **WHEN** um recurso tem `PRJ = PAGAMENTOS` e existe projeto ativo `codigo = PAGAMENTOS`
- **THEN** o recurso recebe `projeto_id` desse projeto

#### Scenario: Projeto desconhecido não cria nada

- **WHEN** um recurso tem um valor de projeto sem `projetos.codigo` correspondente
- **THEN** o recurso fica com `projeto_id = null` e `equipe_id = null`, sem criar projeto nem equipe, e a ocorrência é contabilizada

#### Scenario: Projeto inativo não gera equipe

- **WHEN** um recurso referencia um projeto existente porém inativo
- **THEN** nenhuma equipe é criada; o recurso é persistido com o `projeto_id` inativo e `equipe_id = null`, e a ocorrência é registrada

### Requirement: Resolução de equipe e estado "Sem responsável"

O sistema SHALL, para um recurso com projeto resolvido e ativo, localizar a tag de equipe usando a
Tag Key efetiva do provedor (`tag_alocacao_equipe`, com fallback padrão `EQP` quando o campo for
nulo/vazio). Quando a tag de equipe estiver
ausente ou vazia, o recurso SHALL ter `equipe_id = null`, significando **"Sem responsável"** — um
estado real do recurso. O sistema MUST NOT criar uma equipe fictícia (ex.: `SEM_RESPONSAVEL`) para
representar esse estado. Quando houver valor de equipe, o sistema SHALL normalizá-lo em
`trim`+maiúsculas, buscar equipe por `(projeto_id, codigo)` e, se não existir, criá-la
automaticamente (`auto_gerada = true`), atribuindo-a ao recurso.

#### Scenario: Recurso com equipe

- **WHEN** um recurso tem projeto ativo e `EQP = BACKEND`
- **THEN** o recurso é associado à equipe `BACKEND` daquele projeto (criada automaticamente se ainda não existir)

#### Scenario: Recurso sem responsável

- **WHEN** um recurso tem projeto ativo mas não tem tag de equipe (ausente ou vazia)
- **THEN** o recurso fica com `equipe_id = null` ("Sem responsável"), sem criar equipe fictícia

### Requirement: Reatribuição automática na próxima sincronização

O sistema SHALL tratar a nuvem como fonte da verdade da classificação: numa sincronização
seguinte, se as tags de um recurso mudarem (ex.: `EQP = BACKEND` → `EQP = DADOS`), a associação do
recurso SHALL ser atualizada automaticamente para refletir as novas tags. O sistema MUST NOT exigir
nem oferecer, nesta capability, correção manual da atribuição de projeto/equipe de um recurso
dentro do CostGuard.

#### Scenario: Mudança de tag reatribui o recurso

- **WHEN** um recurso antes com `EQP = BACKEND` passa a ter `EQP = DADOS` e é reinventariado
- **THEN** o recurso passa a ser associado à equipe `DADOS` do projeto, automaticamente

### Requirement: Persistência idempotente dos recursos (upsert)

O sistema SHALL persistir os recursos por upsert pela chave natural `(provedor_id, arn)`:
atualizando o registro existente (tags resolvidas, `regiao`, `servico`, `projeto_id`, `equipe_id`,
valores crus das tags, presença no inventário) ou inserindo quando novo. Reexecutar a
sincronização sem mudanças MUST NOT criar duplicatas.

#### Scenario: Reexecução não duplica

- **WHEN** a sincronização é executada duas vezes sem mudanças na conta
- **THEN** não há recursos duplicados para a mesma combinação `(provedor_id, arn)`

### Requirement: Reconciliação de recursos ausentes

O sistema SHALL marcar como inativos (`ativo = false`) os recursos de um provedor que **não**
apareceram na sincronização atual, **somente após** a sincronização ter sido concluída com sucesso
(todas as páginas de todas as regiões). O sistema SHALL identificar os recursos vistos na execução
atual (ex.: por `sync_id`/`ultima_vista_em` daquela execução) e reconciliar os demais do mesmo
provedor. O sistema MUST NOT desativar recursos quando a sincronização falhar antes de concluir. O
sistema MUST NOT excluir fisicamente os recursos ausentes nesta operação (desativação lógica).

#### Scenario: Recurso que sumiu é desativado após sync completa

- **WHEN** um recurso existia antes e não aparece numa sincronização completa e bem-sucedida
- **THEN** ele é marcado `ativo = false`, sem ser excluído fisicamente

#### Scenario: Falha não desativa nada

- **WHEN** a sincronização falha antes de concluir todas as páginas/regiões
- **THEN** nenhum recurso é desativado e o inventário anterior permanece intacto

### Requirement: Estado da sincronização e falhas não silenciosas

O sistema SHALL responder à sincronização com um resultado contendo, no mínimo: o provedor, o
`status` (`sucesso`/`erro`), contadores úteis à operação (ex.: recursos encontrados/ativos,
recursos desativados na reconciliação, equipes criadas, recursos sem responsável, projetos
desconhecidos) e uma mensagem sanitizada em caso de erro. A falha MUST NOT ser silenciosa. Em erro
(AWS, paginação, enumeração de regiões ou pré-condição), o sistema SHALL retornar indicação
explícita e sanitizada, sem reconciliar.

#### Scenario: Sincronização bem-sucedida reporta contadores

- **WHEN** uma sincronização conclui com sucesso
- **THEN** o resultado informa `status = sucesso` e os contadores de inventário/reconciliação/equipes/sem-responsável/projetos-desconhecidos

#### Scenario: Erro reporta estado sanitizado

- **WHEN** a sincronização falha
- **THEN** o resultado informa `status = erro` com mensagem sanitizada, e nenhum recurso é desativado

### Requirement: Leitura do inventário por projeto

O sistema SHALL permitir que um usuário autenticado liste os recursos de um projeto e as equipes
de um projeto, para habilitar o consumo do inventário. A leitura MUST NOT exigir role admin. A
listagem de recursos de um projeto SHALL permitir distinguir os recursos por equipe e os recursos
"Sem responsável" (`equipe_id = null`). Uma requisição sem token válido SHALL receber HTTP 401.

#### Scenario: Listar recursos de um projeto

- **WHEN** um usuário autenticado solicita os recursos de um projeto existente
- **THEN** o backend responde com os recursos do projeto, permitindo distinguir por equipe e os "Sem responsável"

#### Scenario: Leitura sem autenticação

- **WHEN** uma requisição de leitura do inventário é feita sem token válido
- **THEN** o backend responde com HTTP 401

### Requirement: Segredos e material de assinatura nunca expostos

O sistema MUST NOT retornar nem registrar em log a AWS Secret Access Key, a chave `PROV_ENC_KEY`,
o header `Authorization` SigV4, as signing keys ou o segredo JWE decifrado, em nenhuma das
operações. O segredo SHALL ser decifrado apenas no backend, em memória, imediatamente antes da
assinatura. Qualquer diagnóstico de erro SHALL limitar-se a status HTTP, `Error.Code`,
`Error.Message` sanitizada e `RequestId`. Credenciais SHALL ser somente leitura.

#### Scenario: Resposta da sincronização não contém segredo

- **WHEN** a sincronização é executada (com sucesso ou erro)
- **THEN** a resposta não contém a Secret Access Key, `PROV_ENC_KEY`, o Authorization SigV4, signing keys nem o JWE decifrado

#### Scenario: Diagnóstico de erro é sanitizado

- **WHEN** a sincronização falha e um diagnóstico é retornado
- **THEN** o diagnóstico contém no máximo status HTTP, `Error.Code`, `Error.Message` sanitizada e `RequestId`
