## Contexto

- Consumo do mês: a fonte oficial é `custos_equipe` (mesma do card de `/projetos` e do detalhe), na janela MTD em `America/Sao_Paulo` (dia 1 até amanhã, exclusivo), com as faixas `atencao` (≥ 70%), `critico` (≥ 90%) e `estourado` (≥ 100%) já usadas por `GET /projetos-resumo-consumo-mtd`.
- Inventário: `recursos.projeto_id` nulo com `ativo = true` é "Não classificado". O Xano grava a chave estrangeira nula como `0`, então os filtros de banco usam `projeto_id == null || projeto_id == 0` (confirmado na homologação).
- Execuções de custos por equipe já ficam em `coletas_custos_equipe`; inventário não registra execução.
- Plano Free do Xano: 10 requisições a cada 20 s por cliente. A sequência de sincronização faz 3 chamadas e uma recarga.

## Decisões

### D1. Avaliação explícita em vez de gatilhos espalhados

Toda a regra de alertas fica em um único endpoint, `POST /alertas/avaliar`, que lê o estado atual (projetos, `custos_equipe`, recursos, últimas execuções, status dos provedores) e reconcilia a tabela `alertas`. Os endpoints de importação existentes não geram alertas diretamente. Motivo: uma única regra testável, sem tocar a lógica das importações já homologadas. O frontend chama a avaliação ao final de cada sincronização; o admin também pode acioná-la em `/alertas`.

### D2. Condição, chave e episódio

Cada condição detectada tem uma `chave` determinística:

| Tipo | Chave | Condição | Nível |
|---|---|---|---|
| `orcamento` | `orcamento_{projeto}_{AAAAMM}_{faixa}` | faixa atual do projeto no mês = faixa | `atencao` / `critico` / `estourado` |
| `nao_classificado` | `nao_classificado_{provedor}` | ≥ 1 recurso ativo sem projeto no provedor | `atencao` |
| `importacao` | `importacao_inventario_{provedor}` | última execução de inventário com erro | `erro` |
| `importacao` | `importacao_custos_{provedor}` | última execução de custos por equipe com erro | `erro` |
| `importacao` | `importacao_conexao_{provedor}` | provedor com `status = erro` | `erro` |

Um alerta representa um **episódio** da condição (`condicao_ativa = true` enquanto ela persiste):

- condição presente e sem episódio ativo → cria alerta;
- condição presente e episódio ativo → não cria outro (sem repetição contínua); atualiza `mensagem`/`detalhe` se mudaram (ex.: quantidade de recursos);
- episódio ativo cuja condição sumiu → `condicao_ativa = false` e, se ainda aberto, resolução automática (`resolucao = automatica`).

Resolver manualmente não encerra o episódio: a condição continua conhecida e não gera novo alerta enquanto persistir. Assim cumpre-se "alertas de orçamento não devem ser repetidos continuamente" e "a faixa gera aviso apenas quando alcançada".

Orçamento usa apenas a faixa mais alta atingida: ao passar de 70% para 90%, o alerta de atenção é resolvido automaticamente e o de aviso é criado. Na virada do mês, a chave muda e os episódios do mês anterior são encerrados.

### D3. Regras de orçamento

Somente projetos `ativo` com `budget > 0` e custos exclusivamente em USD no mês. Projetos com moeda diferente ou mista não geram alerta de orçamento (não é possível comparar sem conversão, fora do escopo). A faixa usa o percentual bruto.

### D4. Simulação

`simular = true` executa toda a avaliação e devolve as ações (`criar`, `atualizar`, `resolver`) sem gravar. Permite verificar a regra em produção sem alterar dados.

### D5. Registro de execuções de inventário

Tabela `coletas_inventario` (`provedor_id`, `status`, `recursos_encontrados`, `projetos_desconhecidos`, `mensagem`, `executado_em`). O endpoint de sincronização grava a linha imediatamente antes de montar a resposta; falhas de pré-condição (provedor sem conexão, sem tag) continuam respondendo HTTP 400 e não geram linha, pois a interface já as exibe e o provedor com erro de conexão gera alerta próprio.

### D6. Sequência de sincronização no frontend

`SincronizacaoState.sincronizar(provedor_id)`: (1) `sincronizar-recursos`; (2) `classificar-custos-equipe`, executado mesmo se (1) falhar, porque são fontes independentes; (3) `alertas/avaliar`. Cada etapa mostra sucesso, aviso ou erro sanitizado (`mensagem` do backend). Pausa de ~2 s entre chamadas por causa do limite do plano. HTTP 401 encerra a sessão. Só admin vê o botão; o backend continua sendo a barreira.

### D7. Leitura

`GET /alertas` devolve todos os alertas abertos e os 500 resolvidos mais recentes (achado 5 da revisão: contagens de abertos completas), com nomes de projeto e provedor resolvidos no backend. `GET /recursos-nao-classificados` devolve os recursos ativos sem projeto com provedor, ARN, serviço, região e valor de tag encontrado. Ambos para qualquer usuário autenticado (leitura de informação, como os demais GETs).

## Riscos

- **R1:** avaliações simultâneas podem criar alerta duplicado para a mesma chave (sem índice único, porque episódios encerrados mantêm a chave). Tratado (achado 4 da revisão): ao final de cada avaliação real, episódios ativos duplicados são encerrados, mantendo o de menor `id`. O duplicado continua no histórico como resolvido automaticamente.
- **R2:** a avaliação real grava em produção. Os testes desta change usam `simular = true`; a execução real fica para a homologação ou autorização explícita.
- **R3:** a sincronização real chama a AWS (ou o Mock) e grava inventário e custos; não é executada em teste sem autorização. A interface é testada com um proxy local que intercepta as chamadas.
