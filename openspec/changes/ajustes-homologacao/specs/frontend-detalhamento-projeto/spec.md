## MODIFIED Requirements

### Requirement: Janela de custos do mês corrente

A página SHALL calcular a janela de custos usando o fuso `America/Sao_Paulo` e o mês selecionado no seletor de mês compartilhado (mês atual e os 5 anteriores; padrão: mês atual). Para o mês atual, `data_inicio` é o primeiro dia do mês e `data_fim` é o dia seguinte à data atual; para um mês anterior, `data_inicio` é o primeiro dia do mês e `data_fim` é o primeiro dia do mês seguinte; `data_fim` é sempre exclusivo. A semântica do backend não muda. A página MUST NOT oferecer intervalo livre de datas. A página SHALL exibir o período usado como texto. A página MUST NOT comparar o orçamento mensal com um intervalo diferente de um mês.

#### Scenario: Janela em meio ao mês

- **WHEN** a data atual em `America/Sao_Paulo` é 26/10/2026 e o mês atual está selecionado
- **THEN** a consulta usa `data_inicio = 2026-10-01` e `data_fim = 2026-10-27`, e a tela exibe o período "01/10/2026 a 26/10/2026"

#### Scenario: Primeiro dia do mês

- **WHEN** a data atual em `America/Sao_Paulo` é 01/11/2026 e o mês atual está selecionado
- **THEN** a consulta usa `data_inicio = 2026-11-01` e `data_fim = 2026-11-02`

#### Scenario: Virada de mês em UTC não altera a janela

- **WHEN** são 02:00 UTC de 01/11/2026, o que equivale a 31/10/2026 23:00 em `America/Sao_Paulo`
- **THEN** a consulta usa `data_inicio = 2026-10-01` e `data_fim = 2026-11-01`, porque o mês é o de São Paulo

#### Scenario: Mês anterior selecionado

- **WHEN** a data atual é 03/11/2026 e o usuário seleciona outubro de 2026
- **THEN** a consulta usa `data_inicio = 2026-10-01` e `data_fim = 2026-11-01`, e a tela exibe "01/10/2026 a 31/10/2026"

## REMOVED Requirements

### Requirement: Exportação CSV com dados reais

**Reason**: Decisão do usuário na homologação (2026-11-03): os botões "Exportar Dados" e "Exportar CSV" eram duplicados; a exportação sai da V1.
**Migration**: Nenhuma; a lista de recursos continua visível na página.
