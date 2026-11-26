## ADDED Requirements

### Requirement: Entidade Alerta

O sistema SHALL manter alertas com `tipo` (`orcamento`, `nao_classificado`, `importacao`), `nivel` (`atencao`, `critico`, `estourado`, `erro`), `mensagem`, `detalhe`, `chave` de condição, referência opcional a projeto e provedor, `condicao_ativa`, estado de resolução (`resolvido`, `resolucao` `manual`/`automatica`, `resolvido_em`, `resolvido_por`) e datas de criação e atualização. Alertas MUST NOT ser excluídos.

#### Scenario: Alerta criado

- **WHEN** a avaliação detecta uma condição nova
- **THEN** é gravado um alerta aberto (`resolvido = false`, `condicao_ativa = true`) com tipo, nível, mensagem e referências

### Requirement: Avaliação de alertas restrita a admin

`POST /alertas/avaliar` SHALL exigir admin ativo (HTTP 401 sem token, HTTP 403 para os demais). A avaliação SHALL ler o estado atual e reconciliar a tabela `alertas` conforme as regras desta capability. Com `simular = true`, SHALL devolver as ações que seriam executadas (`criar`, `atualizar`, `resolver`) e MUST NOT gravar.

#### Scenario: Simulação não grava

- **WHEN** um admin chama a avaliação com `simular = true`
- **THEN** a resposta lista as ações previstas e a tabela `alertas` permanece inalterada

#### Scenario: Usuário leitura

- **WHEN** um usuário leitura chama a avaliação
- **THEN** o backend responde HTTP 403

### Requirement: Alerta de orçamento por faixa

Para cada projeto ativo com `budget > 0` e custos do mês corrente exclusivamente em USD, a avaliação SHALL calcular o percentual bruto do custo MTD de `custos_equipe` sobre o orçamento e SHALL manter um alerta para a faixa mais alta atingida: `atencao` (≥ 70%), `critico` (≥ 90%, exibido como "Aviso") e `estourado` (≥ 100%, exibido como "Orçamento excedido"). Projetos abaixo de 70%, sem orçamento, inativos ou com moeda diferente de USD MUST NOT gerar alerta de orçamento.

#### Scenario: Projeto atinge 70%

- **WHEN** o custo MTD de um projeto atinge 75% do orçamento e não há episódio ativo para essa faixa no mês
- **THEN** é criado um alerta `orcamento` de nível `atencao`

#### Scenario: Escalada de faixa

- **WHEN** o projeto com alerta de `atencao` aberto passa a 92%
- **THEN** é criado um alerta de nível `critico` e o de `atencao` é resolvido automaticamente

#### Scenario: Sem repetição

- **WHEN** a avaliação é executada várias vezes com o projeto na mesma faixa
- **THEN** nenhum alerta adicional é criado

### Requirement: Alerta de recursos não classificados

A avaliação SHALL manter, por provedor não inativo, um alerta `nao_classificado` de nível `atencao` enquanto houver pelo menos um recurso ativo sem projeto válido, com a quantidade de recursos na mensagem. Quando a quantidade mudar, a mensagem SHALL ser atualizada sem criar novo alerta.

#### Scenario: Recursos sem projeto

- **WHEN** um provedor possui 3 recursos ativos sem projeto
- **THEN** existe um alerta aberto informando 3 recursos não classificados nesse provedor

#### Scenario: Todos classificados

- **WHEN** o provedor deixa de ter recursos sem projeto
- **THEN** o alerta é resolvido automaticamente

### Requirement: Alerta de falha de importação

A avaliação SHALL manter um alerta `importacao` de nível `erro` por provedor não inativo para cada fonte em falha: última execução de inventário com erro, última execução de custos por equipe com erro e provedor com `status = erro`. A mensagem SHALL identificar o provedor e a fonte e MUST NOT conter segredos. Quando a execução seguinte da mesma fonte tiver sucesso, o alerta SHALL ser resolvido automaticamente.

#### Scenario: Falha de custos por equipe

- **WHEN** a última execução de custos por equipe de um provedor terminou com erro
- **THEN** existe um alerta aberto de falha de importação para esse provedor e essa fonte

### Requirement: Episódios e resolução automática

Cada alerta SHALL representar um episódio de uma condição identificada por `chave`. Enquanto a condição persistir, a avaliação MUST NOT criar outro alerta para a mesma chave, mesmo que o alerta tenha sido resolvido manualmente. Quando a condição deixar de existir, a avaliação SHALL marcar `condicao_ativa = false` e, se o alerta estiver aberto, SHALL resolvê-lo com `resolucao = automatica`. Uma nova ocorrência posterior da condição SHALL gerar um novo alerta. Se avaliações simultâneas deixarem mais de um episódio ativo para a mesma chave, a avaliação SHALL manter o de menor `id` e encerrar os demais com resolução automática, sem excluí-los.

#### Scenario: Resolução manual não gera repetição

- **WHEN** um admin resolve um alerta cuja condição continua presente e a avaliação é executada
- **THEN** nenhum novo alerta é criado para a mesma chave

#### Scenario: Episódios duplicados por avaliações simultâneas

- **WHEN** duas avaliações simultâneas criam dois alertas ativos para a mesma chave
- **THEN** ao final de cada avaliação resta um único episódio ativo para a chave (o de menor `id`)

#### Scenario: Condição volta a ocorrer

- **WHEN** uma condição encerrada volta a ocorrer
- **THEN** a avaliação cria um novo alerta

### Requirement: Resolução manual restrita a admin

`POST /alertas/{id}/resolver` SHALL exigir admin ativo e SHALL marcar o alerta como resolvido com `resolucao = manual`, `resolvido_em` e `resolvido_por`. Alerta inexistente SHALL resultar em HTTP 404; alerta já resolvido SHALL ser recusado com HTTP 400.

#### Scenario: Admin resolve

- **WHEN** um admin resolve um alerta aberto
- **THEN** o alerta passa a resolvido e continua listado

### Requirement: Leitura de alertas

`GET /alertas` SHALL permitir a qualquer usuário autenticado listar todos os alertas abertos e os 500 resolvidos mais recentes, cada grupo do mais recente para o mais antigo, com `id`, `tipo`, `nivel`, `mensagem`, `detalhe`, `projeto_id`, `projeto_nome`, `provedor_id`, `provedor_nome`, `resolvido`, `resolucao`, `resolvido_em`, `criado_em` e `atualizado_em`. Sem token, SHALL responder HTTP 401.

#### Scenario: Listagem

- **WHEN** um usuário autenticado lista os alertas
- **THEN** recebe todos os alertas abertos e os resolvidos mais recentes, ordenados por `criado_em` decrescente em cada grupo, com os campos definidos

### Requirement: Página /alertas com dados reais

O frontend SHALL exibir em `/alertas` os alertas reais, sem dados fictícios, adaptando o design da referência: indicadores (alertas abertos, abertos críticos — `estourado`, `critico` ou `erro` — e disparados nas últimas 24 h), filtro entre abertos, resolvidos e todos, busca por texto, lista com ícone e cor por nível, rótulo do tipo, mensagem, detalhe, tempo relativo e estado de resolução. O admin SHALL ter as ações "Resolver" em alertas abertos e "Avaliar alertas agora". A página SHALL exibir também os recursos não classificados. Erros SHALL ser exibidos de forma sanitizada e independente por bloco; HTTP 401 SHALL seguir o tratamento central.

#### Scenario: Usuário leitura

- **WHEN** um usuário leitura acessa `/alertas`
- **THEN** vê os alertas e os recursos não classificados, sem as ações de resolver e avaliar

#### Scenario: Sem alertas

- **WHEN** não há alertas no filtro escolhido
- **THEN** a página mostra um estado vazio, sem valores fabricados
