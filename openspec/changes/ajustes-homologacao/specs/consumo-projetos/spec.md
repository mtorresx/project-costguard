## MODIFIED Requirements

### Requirement: Janela MTD calculada no backend

O backend SHALL calcular a janela no fuso `America/Sao_Paulo`. Sem o parâmetro opcional `mes`, ou com `mes` igual ao mês corrente, `data_inicio` é o primeiro dia do mês corrente e `data_fim` é o dia seguinte à data atual, exclusivo. Com `mes` (`AAAA-MM`) anterior ao mês corrente, `data_inicio` é o primeiro dia desse mês e `data_fim` é o primeiro dia do mês seguinte, exclusivo. Um `mes` posterior ao corrente ou fora do formato SHALL ser recusado com HTTP 400. A resposta SHALL conter `data_inicio` e `data_fim` no formato `YYYY-MM-DD`, `mes` (`AAAA-MM`) e `mes_corrente` (booleano) no nível superior. Apenas registros com `data >= data_inicio` e `data < data_fim` SHALL ser considerados.

#### Scenario: Janela no meio do mês

- **WHEN** o endpoint é chamado sem `mes` em 2026-10-26 às 16h em `America/Sao_Paulo`
- **THEN** a resposta contém `data_inicio = "2026-10-01"`, `data_fim = "2026-10-27"`, `mes = "2026-10"` e `mes_corrente = true`

#### Scenario: Virada de dia em UTC antes de São Paulo

- **WHEN** o endpoint é chamado em 2026-10-31 às 22h em `America/Sao_Paulo` (já 2026-11-01 em UTC)
- **THEN** a resposta contém `data_inicio = "2026-10-01"` e `data_fim = "2026-11-01"`

#### Scenario: Primeiro dia do mês

- **WHEN** o endpoint é chamado em 2026-11-01 às 10h em `America/Sao_Paulo`
- **THEN** a resposta contém `data_inicio = "2026-11-01"` e `data_fim = "2026-11-02"`

#### Scenario: Mês anterior fechado

- **WHEN** o endpoint é chamado com `mes = "2026-10"` em novembro de 2026
- **THEN** a resposta contém `data_inicio = "2026-10-01"`, `data_fim = "2026-11-01"` e `mes_corrente = false`

#### Scenario: Virada de ano

- **WHEN** o endpoint é chamado com `mes = "2025-12"`
- **THEN** a resposta contém `data_inicio = "2025-12-01"` e `data_fim = "2026-01-01"`

#### Scenario: Mês futuro ou inválido

- **WHEN** o endpoint é chamado com um `mes` posterior ao corrente ou com `mes = "2026-13"`
- **THEN** o backend responde HTTP 400
