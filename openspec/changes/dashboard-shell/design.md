## Decisões

### D1. Fontes e número de chamadas

`HomeState.carregar` faz três GETs em sequência: resumo de consumo, alertas e recursos não classificados. Com o `/me` do `require_auth`, são quatro requisições por carregamento, abaixo do limite de 10 em 20 s do plano Xano.

### D2. Custo classificado do mês

Soma de `custo_mtd` dos projetos com `custo_status = ok` (sempre USD). Projetos com `moeda_incompativel` ou `moedas_mistas` não entram na soma; quando existirem, o card informa quantos ficaram de fora. Sem nenhum projeto `ok`, o card mostra "Sem custos classificados no mês", sem "US$ 0.00" fabricado. O período exibido é o do resumo (`data_inicio` até a véspera de `data_fim`, que é exclusivo).

### D3. Maiores consumos

Projetos ativos com `percentual_usado` (orçamento > 0 e custo em USD), do maior para o menor, até 5, com barra e cor pela faixa do backend. Sem itens, mensagem explicando que não há projeto com orçamento e custo no mês.

### D4. Contador de alertas no shell

`ContadorAlertasState` (módulo próprio para evitar importação circular) guarda abertos e críticos abertos. É atualizado por `HomeState` e `AlertasState` após carregar `GET /alertas`. O shell não faz chamada própria; antes da primeira carga, nada é exibido. O valor pode ficar defasado até a próxima visita a essas páginas (aceito para não gastar requisições).

### D5. "Minha conta"

Mostra username, papel e o texto das faixas de alerta do domínio. Remove limite de alerta, webhook e auditoria contínua (não persistidos e fora da documentação).

### D6. Limite de requisições do plano Xano (HTTP 429)

Encontrado no E2E desta change: navegar do dashboard direto para o detalhe de um projeto soma mais de 10 requisições em 20 s e uma leitura recebeu HTTP 429; no pior caso, um 429 no `/me` de `require_auth` deslogava o usuário. Decisão: todos os estados usam `cliente_xano` (`projetoImpacta/api.py`), um cliente HTTP que repete a requisição após 429 (esperas de 3, 5 e 8 s). O 429 indica que o Xano recusou sem processar, então repetir não duplica escrita. Se o 429 persistir no `/me`, a sessão é mantida (o token não foi avaliado; cada chamada de dados continua validando o token no backend) e o shell exibe o aviso "Não foi possível validar a sessão agora" (achado 6 da revisão Codex: a falha de validação não pode ser silenciosa). Os helpers existentes de projetos, detalhe, provedores, descoberta e autenticação passam a usar o mesmo cliente, sem outra mudança de comportamento.
