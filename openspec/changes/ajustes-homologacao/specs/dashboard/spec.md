## ADDED Requirements

### Requirement: Seletor de mês no dashboard

O dashboard SHALL oferecer o mesmo seletor de mês de Projetos e do detalhe (mês atual e os 5 anteriores, escolha compartilhada entre as páginas). O custo classificado e os maiores consumos SHALL refletir o mês selecionado, obtidos do `resumo` de `GET /painel` com o parâmetro `mes` (uma chamada para custo, alertas e não classificados); alertas abertos e recursos não classificados continuam refletindo o estado atual. Para o mês atual sem custos, o card SHALL informar a ausência de custos no mês e sugerir selecionar um mês anterior ou sincronizar os provedores, sem chamada adicional ao backend.

#### Scenario: Mês anterior selecionado

- **WHEN** o usuário seleciona outubro de 2026
- **THEN** o card de custo e os maiores consumos mostram outubro inteiro e o período "01/10/2026 a 31/10/2026"

#### Scenario: Mês atual sem custos

- **WHEN** o mês atual ainda não tem custos classificados
- **THEN** o card informa a ausência de custos no mês e sugere sincronizar os provedores ou selecionar um mês anterior
