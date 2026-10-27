## Por quê

A página `/projetos` mostra apenas o orçamento mensal de cada projeto. Para saber quanto do orçamento já foi consumido no mês, o usuário precisa abrir o detalhamento de cada projeto. O frontend de referência (`C:\frontend-costguard`, branch `development-fernando-alertas`) já tem esse indicador no card da listagem (custo do mês, percentual e barra), mas depende de campos que o backend não fornece.

Esta change traz o consumo MTD real para os cards de `/projetos`, preservando o visual da referência, a partir de um endpoint agregado no backend. O valor mostrado no card deve ser o mesmo da tela de detalhamento para a mesma janela.

## O que muda

- **Backend (Xano):** novo endpoint `GET /projetos-resumo-consumo-mtd`, somente leitura, para qualquer usuário autenticado. Retorna, em uma única chamada, todos os dados necessários aos cards: dados do projeto, custo classificado no mês corrente, moeda, última data com custo, percentual do orçamento e faixa de consumo.
- **Fonte do consumo:** a tabela `custos_equipe`, com o mesmo critério de `total_projeto` de `GET /projetos/{id}/custos-equipe` (todas as equipes mais "Sem responsável"). A comparação feita com os dados reais em 2026-10-26 (projetos 4 e 10, janela 2026-10-01 a 2026-10-27) confirmou que `custos_equipe` e o endpoint de detalhe coincidem e que `custos_projeto` difere apenas por arredondamento (até 0,00002 por dia).
- **Janela MTD:** calculada pelo backend em `America/Sao_Paulo`: do primeiro dia do mês até amanhã (exclusivo), a mesma regra do detalhamento.
- **Faixas de consumo** (definidas pelo domínio): `< 70%` normal, `>= 70% e < 90%` atenção, `>= 90% e < 100%` crítico, `>= 100%` estourado. A faixa é calculada sobre o valor bruto, nunca sobre o valor arredondado.
- **Frontend (Reflex), `/projetos`:** os cards passam a mostrar "Custo classificado (MTD)", "Último custo classificado: DD/MM/AAAA", percentual utilizado e barra colorida pela faixa, seguindo o layout do card da referência.
- **Estados explícitos**, sem valor fabricado: orçamento não definido, sem registros no mês, moeda incompatível com o orçamento em USD, custos em moedas diferentes, custo zero real, crédito (valor negativo) e endpoint de consumo indisponível.
- Projetos inativos continuam na listagem, com status "Inativo" e o custo classificado existente.
- `GET /projetos` e os demais endpoints existentes permanecem intocados.

## Capabilities

### New Capabilities

- `consumo-projetos`: endpoint agregado `GET /projetos-resumo-consumo-mtd` com o consumo MTD de todos os projetos, a partir de `custos_equipe`, com regras de janela, moeda, arredondamento, faixa e estados de custo.
- `frontend-consumo-projetos`: apresentação do consumo MTD nos cards de `/projetos`, com faixas coloridas, estados explícitos e comportamento quando o endpoint de consumo falha.

### Modified Capabilities

Nenhuma. O requisito "Página /projetos com dados reais" da capability `projetos` continua válido sem alteração: a listagem segue exibindo os projetos reais, com controles de escrita apenas para admin e tratamento de 401.

## Impacto

- **Xano:** um endpoint novo em `xano/api/app/`. Nenhuma tabela, índice, classificador ou endpoint existente é alterado. Nenhuma escrita em banco.
- **Reflex:** `projetoImpacta/pages/projetos.py` e `projetoImpacta/pages/projetos_state.py`. A tela de detalhamento (`/projetos/[projeto_id]`) não muda.
- **Dependências:** nenhuma nova.

## Fora do escopo

- Alertas: tabela, geração, deduplicação, resolução e notificações.
- Variação em relação ao mês anterior.
- Projeção de fim de mês.
- Configurações e slider de limite de alerta.
- Custo por provedor.
- Correção de `custos_projeto` (ausência de reconciliação e sobrescrita de duplicatas): fica para change própria, se necessário.
- Bug conhecido do `PATCH /projetos/{id}` com `budget = 0`.
- Notificar DevOps.
- Dashboard principal.
- Execução de classificadores ou coletas.
- Conversão de moeda; orçamento por equipe; orçamento trimestral ou anual.

## Característica observada dos dados

Em 2026-10-26, os projetos 4 e 10 têm custo registrado até 2026-10-19. Isso é registrado como característica dos dados atuais, não como bug. Por esse motivo, o card mostra a última data com custo e não afirma que o dado está atualizado ou completo até uma data.
