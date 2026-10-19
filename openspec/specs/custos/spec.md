# custos Specification

## Purpose

Coleta base de custos AWS do CostGuard: as entidades `custos` (custo diário por serviço, em USD, vinculado ao provedor de origem) e `coletas_custo` (estado de cada execução), e a operação administrativa que consulta o AWS Cost Explorer (`GetCostAndUsage` via SigV4) a partir de um provedor AWS conectado, persiste os custos de forma idempotente por período e registra sucesso ou erro, com autorização validada no backend Xano e sem jamais expor segredos.

## Requirements

### Requirement: Entidade Custo coletado

O sistema SHALL persistir custos coletados com, no mínimo: referência ao provedor de origem, data do custo (granularidade diária), serviço AWS, métrica, valor, moeda e um indicador de valor estimado. O valor SHALL ser expresso em USD. A data SHALL representar um único dia (granularidade `DAILY`). O serviço SHALL identificar o serviço AWS ao qual o custo pertence (dimensão `SERVICE` do Cost Explorer). O indicador `estimado` SHALL refletir se o valor retornado pela AWS é estimado. Cada registro SHALL ser atribuível a exatamente um provedor de origem.

#### Scenario: Custo diário por serviço persistido

- **WHEN** uma coleta bem-sucedida processa um dia e um serviço com custo
- **THEN** passa a existir um registro com provedor de origem, data, serviço, métrica, valor em USD e o indicador `estimado`

#### Scenario: Custo vinculado ao provedor de origem

- **WHEN** um custo é persistido
- **THEN** ele referencia o provedor AWS a partir do qual foi coletado

### Requirement: Idempotência da coleta por período

O sistema SHALL garantir que reexecutar a coleta para o mesmo provedor e o mesmo período não crie registros de custo duplicados. Um registro de custo SHALL ser único pela combinação de provedor, data, serviço e métrica. Quando uma nova coleta (bem-sucedida em todas as páginas) retornar um valor para uma combinação já existente, o sistema SHALL atualizar o valor existente em vez de inserir um novo registro.

#### Scenario: Reexecução não duplica registros

- **WHEN** a coleta é executada duas vezes para o mesmo provedor e o mesmo período
- **THEN** não existem registros de custo duplicados para a mesma combinação de provedor, data, serviço e métrica

#### Scenario: Reexecução atualiza valor alterado

- **WHEN** a AWS retorna, numa segunda coleta, um valor diferente para um dia/serviço já coletado
- **THEN** o registro existente é atualizado com o novo valor, sem criar duplicata

### Requirement: Coleta restrita a admin

O sistema SHALL permitir executar a coleta de custos apenas a usuários autenticados com `role = admin`. A autorização SHALL ser validada no backend. O usuário com `role = leitura` MUST NOT conseguir executar a coleta.

#### Scenario: Admin executa coleta

- **WHEN** um admin solicita a coleta de custos de um provedor elegível
- **THEN** o backend executa a coleta

#### Scenario: Usuário leitura não executa coleta

- **WHEN** um usuário com role leitura tenta executar a coleta
- **THEN** o backend nega a operação com erro de autorização e nenhuma coleta é realizada

#### Scenario: Coleta sem autenticação

- **WHEN** uma requisição de coleta é feita sem token válido
- **THEN** o backend responde com HTTP 401

### Requirement: Coleta exige provedor AWS conectado

O sistema SHALL executar a coleta apenas para um provedor existente com `tipo = aws` e `status = ok`. Se o provedor não existir, não for AWS, ou estiver com `status` diferente de `ok` (`pendente`, `erro` ou `inativo`), o sistema MUST NOT chamar a AWS e SHALL rejeitar a operação com uma indicação explícita do motivo.

#### Scenario: Provedor conectado é aceito

- **WHEN** um admin solicita a coleta para um provedor `aws` com `status = ok`
- **THEN** o backend prossegue com a coleta

#### Scenario: Provedor inativo ou com erro é rejeitado

- **WHEN** um admin solicita a coleta para um provedor com `status` igual a `inativo`, `erro` ou `pendente`
- **THEN** o backend rejeita a operação sem chamar a AWS e informa o motivo

#### Scenario: Provedor inexistente

- **WHEN** um admin solicita a coleta para um `id` de provedor que não existe
- **THEN** o backend responde com erro de recurso não encontrado

### Requirement: Consulta ao AWS Cost Explorer

O sistema SHALL obter os custos chamando a API do Cost Explorer (`GetCostAndUsage`), autenticada com AWS SigV4, usando a credencial do provedor decifrada apenas no backend. O **destino** e os **componentes da assinatura dependentes do destino** SHALL ser resolvidos a partir do provedor: quando `usar_mock = false`, `POST https://ce.us-east-1.amazonaws.com/`, assinatura com host `ce.us-east-1.amazonaws.com` e canonical URI `/` (endpoint AWS real, comportamento atual inalterado); quando `usar_mock = true`, `POST {base_normalizada}/aws/{identificador_conta}/ce/`, assinatura com host `aws-mock.costguard.com.br` e canonical URI `/aws/{identificador_conta}/ce/` (AWS Mock Simulator), onde `{identificador_conta}` é o Account ID do próprio provedor e `{base_normalizada}` deriva de `MOCK_BASE_URL` (configuração de ambiente, apenas no backend, não hardcoded, com barra final normalizada para não gerar barra dupla). A assinatura SHALL ser sempre coerente com o host e o canonical URI efetivamente usados na requisição; o sistema MUST NOT assinar com o host AWS real e enviar ao Mock. Em ambos os casos, a requisição SHALL usar `Content-Type: application/x-amz-json-1.1`, `X-Amz-Target: AWSInsightsIndexService.GetCostAndUsage`, a mesma implementação de SigV4 (uma única, reutilizada, com `service=ce` e `region=us-east-1`) e o corpo conceitual:

```json
{
  "TimePeriod": { "Start": "<YYYY-MM-DD>", "End": "<YYYY-MM-DD>" },
  "Granularity": "DAILY",
  "Metrics": ["UnblendedCost"],
  "GroupBy": [ { "Type": "DIMENSION", "Key": "SERVICE" } ]
}
```

O sistema SHALL mapear a resposta para os registros de custo da seguinte forma:

- `data` ← `ResultsByTime[].TimePeriod.Start`
- `estimado` ← `ResultsByTime[].Estimated`
- `servico` ← `Groups[].Keys[0]`
- `valor` ← `Groups[].Metrics.UnblendedCost.Amount`
- `moeda` ← `Groups[].Metrics.UnblendedCost.Unit`

O sistema SHALL tratar a paginação (`NextPageToken`), consultando todas as páginas antes de persistir qualquer registro (ver requisito de falha parcial). A parametrização do destino MUST NOT alterar o fluxo quando `usar_mock = false`: o endpoint, os headers e a assinatura permanecem exatamente os atuais.

#### Scenario: Coleta diária por serviço

- **WHEN** a coleta é executada para um intervalo válido
- **THEN** o backend consulta o Cost Explorer com granularidade diária, métrica `UnblendedCost` e agrupamento por serviço, persistindo o custo em USD de cada dia/serviço com o mapeamento definido

#### Scenario: Destino AWS real quando usar_mock é false

- **WHEN** a coleta é executada para um provedor com `usar_mock = false`
- **THEN** o backend chama `POST https://ce.us-east-1.amazonaws.com/` com os headers e a assinatura atuais (host `ce.us-east-1.amazonaws.com`, canonical URI `/`), sem qualquer referência ao Mock

#### Scenario: Destino Mock quando usar_mock é true

- **WHEN** a coleta é executada para um provedor com `usar_mock = true` e `identificador_conta = <conta>`
- **THEN** o backend chama `POST {base_normalizada}/aws/<conta>/ce/`, reutilizando a mesma implementação de SigV4, porém assinando com host `aws-mock.costguard.com.br` e canonical URI `/aws/<conta>/ce/`, coerentes com o destino

#### Scenario: Resposta paginada é consolidada

- **WHEN** a resposta inclui `NextPageToken`
- **THEN** o backend busca as páginas seguintes e só conclui a coleta como sucesso após processar todas

### Requirement: Pré-condições operacionais do Cost Explorer

O sistema SHALL depender de pré-condições operacionais da conta AWS que estão fora do controle do CostGuard e MUST NOT tentar provisioná-las. Especificamente: o AWS Cost Explorer SHALL estar habilitado previamente na conta (o CostGuard não habilita o Cost Explorer); os dados de custo podem levar aproximadamente 24h para começar a aparecer após a habilitação; cada requisição paginada da Cost Explorer API possui cobrança da AWS; a permissão IAM mínima exigida é `ce:GetCostAndUsage`; e, em AWS Organizations, políticas/configurações da management account podem impedir o acesso mesmo com a credencial IAM local adequada. Quando qualquer dessas pré-condições impedir a coleta, o sistema SHALL tratar como erro sanitizado (não silencioso) e registrar o estado em `coletas_custo`.

#### Scenario: Cost Explorer indisponível é tratado como erro

- **WHEN** a coleta é executada e a AWS indica que o Cost Explorer não está habilitado ou o acesso é negado por política da organização
- **THEN** o backend registra `coletas_custo` com `status = erro` e mensagem sanitizada, sem tentar habilitar o Cost Explorer

### Requirement: Coleta atômica sem persistência parcial

O sistema MUST NOT persistir resultados de uma coleta enquanto a consulta a todas as páginas da AWS não tiver sido concluída com sucesso. O fluxo SHALL ser: consultar e acumular/normalizar todas as páginas em memória; somente após todas retornarem sucesso, executar os upserts na tabela `custos`. Se qualquer página falhar, o sistema MUST NOT alterar a tabela `custos` com um lote incompleto, SHALL registrar a execução em `coletas_custo` com `status = erro` e mensagem sanitizada, e os dados de coletas anteriores SHALL permanecer intactos.

#### Scenario: Falha em uma página não altera os custos

- **WHEN** uma coleta falha ao buscar uma das páginas da AWS
- **THEN** nenhum registro desta coleta é gravado ou atualizado na tabela `custos`
- **AND** `coletas_custo` registra `status = erro` com mensagem sanitizada
- **AND** os registros de custo de coletas anteriores permanecem inalterados

#### Scenario: Upserts só após todas as páginas

- **WHEN** a AWS retorna múltiplas páginas e todas são obtidas com sucesso
- **THEN** o backend executa os upserts apenas depois de acumular todas as páginas

### Requirement: Intervalo de consulta definido

O sistema SHALL aceitar um intervalo de consulta com data inicial (`Start`) inclusiva e data final (`End`) exclusiva, conforme a semântica do Cost Explorer. Quando o intervalo não for informado, o sistema SHALL usar o padrão determinístico do MVP: os últimos 30 dias completos até ontem, com `Start = hoje (UTC) − 30 dias` e `End = hoje (UTC)` (como `End` é exclusivo, o último dia coletado é ontem).

#### Scenario: Intervalo informado é respeitado

- **WHEN** um admin informa `data_inicio` e `data_fim`
- **THEN** a coleta consulta exatamente esse intervalo, com `Start` inclusivo e `End` exclusivo

#### Scenario: Intervalo padrão quando omitido

- **WHEN** um admin executa a coleta sem informar o intervalo
- **THEN** o backend usa `Start = hoje (UTC) − 30 dias` e `End = hoje (UTC)`, cobrindo os últimos 30 dias completos até ontem

### Requirement: Estado da coleta registrado

O sistema SHALL registrar o estado de cada execução de coleta, contendo no mínimo: o provedor de origem, o intervalo consultado, o resultado (`sucesso` ou `erro`), o momento da última coleta e, em caso de erro, uma mensagem sanitizada. A falha MUST NOT ser silenciosa.

#### Scenario: Coleta bem-sucedida registra estado

- **WHEN** uma coleta termina com sucesso
- **THEN** o estado registra `sucesso`, o intervalo consultado e o momento da coleta

#### Scenario: Coleta com erro registra estado sanitizado

- **WHEN** uma coleta falha (erro da AWS ou falha ao paginar)
- **THEN** o estado registra `erro`, o momento e uma mensagem sanitizada, e o backend retorna indicação explícita de falha

### Requirement: Segredos e material de assinatura nunca expostos

O sistema MUST NOT retornar nem registrar em log: a AWS Secret Access Key, a chave `PROV_ENC_KEY`, o header `Authorization` SigV4, as signing keys intermediárias ou o segredo JWE decifrado. O segredo SHALL ser decifrado apenas no backend, em memória, imediatamente antes da assinatura. Qualquer diagnóstico de erro SHALL limitar-se a: status HTTP, `Error.Code`, `Error.Message` sanitizada e `RequestId`.

#### Scenario: Resposta da coleta não contém segredo

- **WHEN** a coleta é executada (com sucesso ou erro)
- **THEN** a resposta não contém a Secret Access Key, `PROV_ENC_KEY`, o Authorization SigV4, signing keys nem o JWE decifrado

#### Scenario: Diagnóstico de erro é sanitizado

- **WHEN** a coleta falha e um diagnóstico é retornado
- **THEN** o diagnóstico contém no máximo status HTTP, `Error.Code`, `Error.Message` sanitizada e `RequestId`
