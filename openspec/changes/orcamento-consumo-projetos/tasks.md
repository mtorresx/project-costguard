## 1. Confirmações antes de implementar

- [ ] 1.1 Confirmar que o usuário criou e está na branch dedicada (sugestão: `feature/orcamento-consumo-projetos`) antes de qualquer edição de código. Verificação: `git branch --show-current` diferente de `main`.
- [ ] 1.2 Confirmar no Xano Developer MCP: (a) `format_timestamp` com fuso `America/Sao_Paulo`; (b) filtro de arredondamento com casas decimais; (c) se uma rota estática `projetos/resumo-consumo-mtd` convive com `projetos/{id}` (GET) sem ser capturada por ela; (d) filtro de `db.query` por intervalo de `date`. Verificação: confirmação registrada nesta tarefa. Se (a) ou (c) não forem confirmados, interromper e decidir com o usuário (design D3).
- [ ] 1.3 Confirmar com a skill `reflex-docs` e a versão instalada (`reflex==0.9.12`) o uso de `rx.progress` com `value` e `color_scheme` `green`, `yellow`, `orange` e `red`. Verificação: confirmação registrada nesta tarefa.

## 2. Backend: `GET /projetos/resumo-consumo-mtd`

- [ ] 2.1 Antes de publicar, capturar como linha de base (somente leitura) as respostas de `GET /projetos`, `GET /projetos/4`, `GET /projetos/10` e `GET /projetos/{4,10}/custos-equipe` na janela MTD, e as contagens de linhas de `custos_equipe`, `custos_projeto` e `custos`. Verificação: arquivo de linha de base no scratchpad, sem tokens nem credenciais.
- [ ] 2.2 Criar `xano/api/app/resumo_consumo_mtd_projetos_GET.xs` (`GET projetos/resumo-consumo-mtd`, `api_group = app`, `auth = usuarios`, sem input) com a janela MTD em `America/Sao_Paulo` (`data_inicio` primeiro dia do mês, `data_fim` amanhã, exclusivo). Verificação: parser do language server e dry-run do Xano CLI sem erros.
- [ ] 2.3 Implementar a agregação com uma consulta a `projetos` (ordem `criado_em desc`) e uma consulta a `custos_equipe` na janela, somando por projeto o valor bruto, as moedas distintas e a maior data, incluindo todas as equipes e "Sem responsável". Verificação: revisão do código contra o requisito "Fonte do custo MTD" e ausência de consulta por projeto.
- [ ] 2.4 Implementar `custo_status` (`ok`, `sem_registros`, `moeda_incompativel`, `moedas_mistas`), `ultima_data_com_custo`, percentual e faixa sobre valores brutos, e o arredondamento final (`custo_mtd` 2 casas, `percentual_usado` 1 casa), com `percentual_usado`/`faixa` nulos quando `budget` não for maior que zero ou `custo_status` não for `ok`. Verificação: revisão do código contra os requisitos "Estado do custo", "Arredondamento" e "Percentual e faixa de consumo".
- [ ] 2.5 Montar a resposta com `data_inicio`, `data_fim` e `projetos[]` contendo exatamente `id`, `nome`, `codigo`, `status`, `budget`, `custo_status`, `custo_mtd`, `moeda`, `ultima_data_com_custo`, `percentual_usado` e `faixa`. Verificação: revisão do código; nenhum `sync_id`, `coletado_em`, `provedor_id` ou credencial na resposta.
- [ ] 2.6 Publicar o endpoint no workspace com o Xano CLI, sem alterar outros documentos. Verificação: dry-run lista somente o endpoint novo; após publicar, a rota responde HTTP 200 com token.

## 3. Validação do backend (somente leitura)

- [ ] 3.1 Validar com admin E2E: janela `data_inicio`/`data_fim` correta para a data do teste; todos os projetos de `GET /projetos` presentes, na mesma ordem; campos exatos. Verificação: script no scratchpad com resultado registrado nesta tarefa.
- [ ] 3.2 Validar os projetos conhecidos: projeto 4 (`budget = 0`) com `custo_status = "ok"`, `custo_mtd = 873.64` (ou o valor da data do teste), `percentual_usado = null` e `faixa = null`; projeto 10 (`budget = 250000`) com `custo_mtd` e `faixa = "normal"`; `ultima_data_com_custo` igual à maior data de `custos_equipe` lida pela Metadata API. Verificação: valores registrados nesta tarefa.
- [ ] 3.3 Validar equivalência com o detalhe: para cada projeto, `custo_mtd` igual ao `total_projeto` de `GET /projetos/{id}/custos-equipe` na mesma janela, arredondado para 2 casas. Verificação: script compara todos os projetos e reporta zero divergências.
- [ ] 3.4 Validar projetos sem registros e projetos inativos com os dados reais existentes. Verificação: `sem_registros` com campos nulos; inativos presentes com `status = "inativo"`.
- [ ] 3.5 Validar HTTP 401 sem token e com token inválido. Verificação: respostas registradas nesta tarefa.
- [ ] 3.6 Validar leitura com role leitura. Pré-requisito: o usuário reativar temporariamente o usuário E2E leitura (id 2), sem excluí-lo. Verificação: HTTP 200 com o mesmo conteúdo do admin. Se a reativação não for autorizada, registrar como não executado e o risco remanescente.
- [ ] 3.7 Validar ausência de efeitos colaterais: contagens de linhas de `custos_equipe`, `custos_projeto` e `custos` iguais à linha de base após várias chamadas ao endpoint. Verificação: comparação registrada nesta tarefa.
- [ ] 3.8 Regressão do backend: `GET /projetos`, `GET /projetos/{id}` e `GET /projetos/{id}/custos-equipe` idênticos à linha de base da tarefa 2.1. Verificação: comparação sem diferenças.
- [ ] 3.9 Estados sem dados reais (`moeda_incompativel`, `moedas_mistas`, custo zero real, crédito e as faixas `atencao`, `critico` e `estourado`): verificar por revisão da lógica contra os cenários da spec. Teste com dados só com autorização explícita do usuário (ex.: `budget` temporário em projeto de teste, nunca nos projetos 4 e 10). Verificação: registrar o que foi comprovado por execução e o que foi verificado apenas por revisão.

## 4. Frontend: estado da listagem

- [ ] 4.1 Em `projetos_state.py`, criar a função pura que converte um item do resumo em dados de exibição (texto do custo com `formatar_valor`, "Último custo classificado: DD/MM/AAAA", texto do percentual, valor da barra limitado a 0–100, cor e rótulo da faixa, mensagem de estado), mantendo `id`, `nome`, `codigo`, `budget` e `status`. Verificação: script no scratchpad cobre `ok` nas quatro faixas, `budget = 0`, `sem_registros`, `moeda_incompativel`, `moedas_mistas`, custo zero, crédito e data nula, com os textos exatos da spec.
- [ ] 4.2 Alterar `ProjetosState.carregar` para chamar `GET /projetos/resumo-consumo-mtd`; em 401, tratamento central; em outra falha, mensagem "Não foi possível carregar o consumo dos projetos." e fallback para `GET /projetos` com cards "Consumo indisponível"; se ambos falharem, mensagem existente "Não foi possível carregar os projetos.". Verificação: compilação sem erros e revisão contra o requisito "Endpoint de consumo indisponível".
- [ ] 4.3 Confirmar que `abrir_editar`, `salvar` e `desativar` continuam funcionando com o novo tipo de item e recarregam pelo endpoint de resumo. Verificação: revisão do código e regressão da seção 8.
- [ ] 4.4 Atualizar as docstrings de `projetos_state.py` e `projetos.py` que dizem que a listagem não exibe consumo. Verificação: nenhuma docstring contraditória.

## 5. Frontend: card de `/projetos`

- [ ] 5.1 Portar o layout do card da referência (`C:\frontend-costguard\costguard\pages\projetos.py`, `_projeto_card`): rótulo "Custo classificado (MTD)", valor, "Último custo classificado", linha de orçamento, percentual com rótulo da faixa e `rx.progress`, mantendo nome, `PRJ_<codigo>`, badge de status, controles de admin e "Ver detalhamento". Sem badge de variação. Verificação: compilação sem erros.
- [ ] 5.2 Renderizar os estados sem valor fabricado: "Sem orçamento definido", "Sem custos classificados no mês até a data atual.", moeda incompatível, moedas mistas e "Consumo indisponível", sem barra nem percentual nesses casos. Verificação: revisão contra o requisito "Estados de custo sem valor fabricado".
- [ ] 5.3 Exibir a mensagem de consumo indisponível no topo da página no modo de fallback. Verificação: revisão do código.

## 6. Validações técnicas

- [ ] 6.1 Compilar o app Reflex seguindo a skill `reflex-process-management`. Verificação: compilação sem erros nem warnings novos.
- [ ] 6.2 Rodar `openspec validate orcamento-consumo-projetos --strict`. Verificação: validação passa.
- [ ] 6.3 Rodar `git diff --stat` e `git status --short`. Verificação: somente `projetos.py`, `projetos_state.py`, o endpoint novo em `xano/api/app/` e os artefatos desta change aparecem.

## 7. E2E

- [ ] 7.1 E2E admin em `/projetos`: projeto 4 com "US$ 873.64" (ou o valor da data), "Sem orçamento definido" e "Último custo classificado"; projeto 10 com custo, percentual, rótulo "Normal" e barra verde. Verificação: tela observada e registrada nesta tarefa.
- [ ] 7.2 E2E de rede: uma chamada a `resumo-consumo-mtd` ao abrir a página e nenhuma a `custos-equipe`. Verificação: log do backend Reflex ou instrumentação temporária registrada e removida.
- [ ] 7.3 E2E card × detalhe: para os projetos 4, 10 e demais com custo, o valor do card é igual ao "Custo classificado (MTD)" do detalhe. Verificação: valores registrados nesta tarefa.
- [ ] 7.4 E2E de projetos sem registros e inativos. Verificação: estados conforme a spec.
- [ ] 7.5 E2E de falha controlada do endpoint de consumo, sem alterar dados nem endpoints no Xano (método combinado com o usuário). Verificação: mensagem no topo, cards "Consumo indisponível" e CRUD/navegação funcionando.
- [ ] 7.6 E2E com usuário leitura (depende da reativação da tarefa 3.6). Verificação: consumo visível e sem controles de escrita; ou registro de não execução e risco.

## 8. Regressão

- [ ] 8.1 Regressão do CRUD como admin: criar, editar e desativar projeto com recarga da listagem. Operações que gravam no Xano somente com autorização do usuário no momento do teste; sem autorização, validar apenas abertura e cancelamento do formulário e registrar. Verificação: registro nesta tarefa.
- [ ] 8.2 Regressão do detalhamento `/projetos/4` e `/projetos/10`: métricas, equipes, recursos e CSV iguais aos de antes da change. Verificação: comparação registrada nesta tarefa.
- [ ] 8.3 Regressão de sessão: login, logout e 401 redirecionando ao login. Verificação: registro nesta tarefa.

## 9. Revisão visual e encerramento

- [ ] 9.1 Subir a UI e solicitar revisão visual manual ao usuário. Verificação: aprovação explícita do usuário; sem ela, a tarefa não é marcada.
- [ ] 9.2 Aplicar ajustes da revisão visual, se houver, e repetir E2E e regressões afetados. Verificação: tarefas repetidas registradas.
- [ ] 9.3 Teste final pré-archive: repetir 3.3, 7.1, 7.3 e 8.2 na data do teste. Verificação: resultados registrados nesta tarefa, sem divergência entre spec, implementação e tarefas.
