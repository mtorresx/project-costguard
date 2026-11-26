## MODIFIED Requirements

### Requirement: Consulta ao AWS Cost Explorer

O sistema SHALL obter os custos chamando a API do Cost Explorer (`GetCostAndUsage`), autenticada com AWS SigV4, usando a credencial do provedor decifrada apenas no backend. O **destino** e os **componentes da assinatura dependentes do destino** SHALL ser resolvidos a partir do provedor: quando `usar_mock = false`, `POST https://ce.us-east-1.amazonaws.com/`, assinatura com host `ce.us-east-1.amazonaws.com` e canonical URI `/` (endpoint AWS real, comportamento atual inalterado); quando `usar_mock = true`, `POST {base_normalizada}/aws/{identificador_conta}/ce/`, assinatura com host `<URL-DO-SIMULADOR>` e canonical URI `/aws/{identificador_conta}/ce/` (AWS Mock Simulator), onde `{identificador_conta}` é o Account ID do próprio provedor e `{base_normalizada}` deriva de `MOCK_BASE_URL` (configuração de ambiente, apenas no backend, não hardcoded, com barra final normalizada para não gerar barra dupla). A assinatura SHALL ser sempre coerente com o host e o canonical URI efetivamente usados na requisição; o sistema MUST NOT assinar com o host AWS real e enviar ao Mock. Em ambos os casos, a requisição SHALL usar `Content-Type: application/x-amz-json-1.1`, `X-Amz-Target: AWSInsightsIndexService.GetCostAndUsage`, a mesma implementação de SigV4 (uma única, reutilizada, com `service=ce` e `region=us-east-1`) e o corpo conceitual:

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
- **THEN** o backend chama `POST {base_normalizada}/aws/<conta>/ce/`, reutilizando a mesma implementação de SigV4, porém assinando com host `<URL-DO-SIMULADOR>` e canonical URI `/aws/<conta>/ce/`, coerentes com o destino

#### Scenario: Resposta paginada é consolidada

- **WHEN** a resposta inclui `NextPageToken`
- **THEN** o backend busca as páginas seguintes e só conclui a coleta como sucesso após processar todas
