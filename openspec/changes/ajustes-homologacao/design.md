## Decisões

### D1. Parâmetro `mes` no resumo

`text mes?` (`AAAA-MM`), validado por `padrão|regex_matches:valor` (sintaxe confirmada na change `correcao-orcamento-zero`). Mês corrente em `America/Sao_Paulo` (`Y-m`) é calculado no backend:

- vazio ou igual ao corrente → janela atual (dia 1 até amanhã, exclusivo); `mes_corrente = true`;
- anterior → `data_inicio = AAAA-MM-01`, `data_fim` = dia 1 do mês seguinte (virada de ano tratada); `mes_corrente = false`;
- posterior → HTTP 400 "Mês futuro"; formato inválido → HTTP 400.

Comparação de meses por texto `AAAA-MM` (ordem lexicográfica = cronológica). O cálculo de faixa e percentual não muda: para um mês fechado, compara o custo do mês inteiro com o orçamento mensal atual do projeto (o sistema não guarda histórico de orçamento; o texto da tela indica "orçamento atual").

### D2. Estado de período compartilhado

`PeriodoState.mes` (`""` = mês atual) e a lista de opções (mês atual + 5 anteriores, calculada em `America/Sao_Paulo`). O seletor, ao mudar, grava o mês e dispara a recarga da página em que está. A escolha persiste ao navegar entre páginas na mesma sessão.

### D3. Detalhe do projeto

A janela do detalhe é calculada no frontend (como antes) a partir de `PeriodoState.mes`: mês corrente → até amanhã; mês fechado → dia 1 ao dia 1 do mês seguinte. "Custo classificado (MTD)" → "Custo classificado no mês"; "Orçamento restante" mantido, com a indicação "mês fechado" quando aplicável.

### D4. Ordenação dos cards de Projetos

Chave: ativos antes de inativos; maior `percentual_usado` primeiro (itens sem percentual depois); depois maior custo; depois nome. Ordenação feita no frontend sobre os itens do resumo.

### D5. Notificações temporárias

`rx.toast.success` para mensagens de sucesso em Usuários e Alertas (desaparecem sozinhas); erros continuam como aviso fixo até a próxima ação.

### D6. Desempenho dentro do limite do plano Xano

Medição (2026-11-03): chamadas individuais de 0,2 a 0,7 s; na navegação, a 11ª requisição em 20 s ficava na fila (até 17,5 s). Decisões:

- **Funções Xano compartilhadas** (`xano/function/costguard/`): a lógica de resumo, alertas, recursos não classificados, recursos e equipes do projeto foi movida sem alteração; os endpoints individuais só chamam a função (respostas comparadas antes e depois: idênticas).
- **Painéis:** `GET /painel?mes=` (resumo + alertas + não classificados) usado por Início, Projetos e Alertas — mesma URL, então uma única chamada atende as três páginas pelo cache; `GET /projetos/{id}/painel` (projeto + recursos + equipes) mais `custos-equipe` no detalhe (4 → 2 chamadas, em paralelo).
- **Transporte HTTP compartilhado** (`projetoImpacta/api.py`): pool de conexões reaproveitado; controle de vazão FIFO (10 por 20,5 s) que aguarda só o tempo até abrir vaga; cache de respostas 200 de GET por 60 s, por token e URL; qualquer POST/PATCH/DELETE limpa o cache; nova tentativa em 429 mantida; cabeçalho interno para leitura forçada (botão Atualizar do Início). Log opcional `COSTGUARD_LOG_HTTP=1` (método, caminho sem query, origem, fila, duração).
- **Painel com falha** (exceto 401): o frontend recorre às leituras individuais, mantendo os erros independentes por bloco.
- Projetos e Provedores mantêm a lista anterior na tela enquanto atualizam (spinner só na primeira carga).

Riscos: dados alterados por outro usuário podem aparecer com até 60 s de atraso (as escritas do próprio app limpam o cache; o botão Atualizar força a leitura). A validação de sessão (`/me`) também é reaproveitada por até 60 s: um usuário desativado é deslogado em até 60 s, enquanto as escritas continuam validadas no backend a cada chamada.
