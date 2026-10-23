## 0. Documentação de domínio

- [ ] 0.1 Atualizar `docs/domain-model.md` (seções Equipe, Recurso Cloud/Reatribuição e Registro de Custo) para deixar claro: o inventário representa a atribuição **atual** do recurso; o custo por equipe usa a dimensão **histórica** de tag retornada pelo Cost Explorer para o período; o custo histórico nunca é reclassificado usando a equipe atual do inventário; substituir "o consumo das equipes é derivado dos recursos atribuídos a elas" por redação coerente com essa regra; registrar a ativação das Tag Keys de projeto e de equipe como Cost Allocation Tags como pré-condição operacional na AWS real. Verificação: texto revisado; nenhuma frase sugere atribuir custo histórico pelo inventário.

## 1. Confirmações técnicas (Xano Developer MCP)

- [ ] 1.1 Confirmar no Xano Developer MCP: semântica de `NULL` em índice único, sintaxe de tratamento de erro (`try_catch`) e forma de remoção em lote por condição (`db.del`/equivalente). Verificação: resultado registrado; se alguma premissa do design (D2, D8) não se confirmar, interromper e levar a decisão ao usuário antes de prosseguir.

## 2. Schema — custos_equipe

- [ ] 2.1 Criar `xano/table/custos_equipe.xs` com `id`, `provedor_id` (FK), `projeto_id` (FK), `equipe_id` (FK nullable), `codigo_equipe` (text, `trim|upper`), `data`, `metrica` (enum `unblended`), `valor`, `moeda` (default `USD`), `estimado`, `sync_id` (private), `coletado_em` (private); índice único `(provedor_id, projeto_id, codigo_equipe, data, metrica)`, btree `(projeto_id, data desc)` e btree `(provedor_id, data)`. Verificação: validação do XanoScript sem erros; índices e FKs presentes.

## 3. Schema — coletas_custos_equipe

- [ ] 3.1 Criar `xano/table/coletas_custos_equipe.xs` com `id`, `provedor_id` (FK), `sync_id` (private), `intervalo_inicio`, `intervalo_fim`, `status` (`sucesso|erro`), `registros_gravados`, `registros_removidos`, `nao_alocados`, `tags_sem_projeto`, `projetos_inativos`, `sem_responsavel`, `equipes_criadas`, `aviso`, `mensagem`, `executado_em`; btree `(provedor_id, executado_em desc)`. Verificação: validação sem erros.

## 4. Endpoint de classificação — autorização e pré-condições

- [ ] 4.1 Criar `xano/api/app/classificar_custos_equipe_provedor_POST.xs` (`POST provedores/{id}/classificar-custos-equipe`, `api_group = app`, `auth = usuarios`) com: admin-only; provedor existe, `tipo = aws`, `status = ok`, credencial presente, `tag_alocacao_projeto` preenchida; `MOCK_BASE_URL` obrigatória só com `usar_mock = true`; intervalo padrão de 30 dias e `data_inicio < data_fim`. Todas as rejeições antes de decifrar o segredo ou chamar a AWS. Verificação: leitura → `accessdenied`; sem token → 401; inexistente → `notfound`; demais → `inputerror`.

## 5. Consulta ao Cost Explorer e paginação

- [ ] 5.1 Resolver a Key de equipe efetiva (`tag_alocacao_equipe` ou fallback `EQP`) e montar `GetCostAndUsage` `DAILY`, `UnblendedCost`, `GroupBy [TAG projeto, TAG equipe]`, sem `SERVICE`, reutilizando o mesmo trecho de SigV4 e de destino real/Mock de `classificar_custos_provedor_POST.xs`. Verificação: corpo enviado conforme D1; nenhum literal `PRJ` e apenas o fallback `EQP` no código.
- [ ] 5.2 Paginar por `NextPageToken` acumulando em memória; falha de página ou limite de iterações com token pendente → `erro`, sem persistência. Verificação: janela de mais de 60 dias no Mock gera mais de uma página e é consolidada.

## 6. Normalização, resolução e agregação

- [ ] 6.1 Extrair valores de projeto e equipe pelos prefixos exatos, aplicar `trim|upper`, tratar vazio após `trim`; resolver projeto (vazio → `nao_alocados`; inexistente → `tags_sem_projeto`; inativo → `projetos_inativos`) com cache por código. Verificação: contadores corretos para cada caso no E2E.
- [ ] 6.2 Resolver equipe para projeto ativo: vazio → "Sem responsável" (`equipe_id = null`, `codigo_equipe = ""`); existente → reutilizar; inexistente → criar `nome = codigo`, `auto_gerada = true`, rebuscando em caso de colisão no índice único; contar `equipes_criadas`. Verificação: nenhuma equipe fictícia criada; segunda execução → `equipes_criadas = 0`.
- [ ] 6.3 Agregar em memória por `(projeto_id, codigo_equipe, data)` somando `valor`; `Unit` diferentes na mesma chave → `erro` sanitizado, sem persistência e sem reconciliação; `moeda` = `Unit` da AWS, com fallback `USD` só quando ausente. Verificação: variantes de caixa/espaço do mesmo código no mesmo dia geram um único registro com a soma; revisão de código confirma que não há soma de unidades distintas nem conversão.

## 7. Persistência e reconciliação

- [ ] 7.1 Gerar `sync_id` (`""|uuid`) e fazer upsert de cada linha agregada pela chave única, gravando o `sync_id` atual. Proteger upserts e reconciliação com tratamento de erro, registrando `erro` sanitizado em falha. Verificação: reexecução da mesma janela sem mudanças não duplica.
- [ ] 7.2 Somente após fetch, normalização/agregação e todos os upserts concluídos, remover de `custos_equipe` apenas as linhas do mesmo provedor, com `data >= data_inicio` e `data < data_fim`, de projetos com `status = ativo` no momento da reconciliação e `sync_id` diferente do atual ou nulo; `registros_removidos` conta só essas linhas e é `0` quando a reconciliação não ocorre. Verificação: cenários de reconciliação do E2E (seção 10), incluindo os limites da janela (linhas em `data_inicio − 1` e em `data_fim` permanecem).

## 8. Aviso, estado e resposta

- [ ] 8.1 Calcular o `aviso` não bloqueante (há custo de projeto ativo e nenhum com equipe); registrar a execução em `coletas_custos_equipe`; responder com os contadores, `aviso`, `mensagem` e `diagnostico` sanitizado, sem `sync_id` nem segredos. Verificação: resposta conforme D11; nenhum segredo na resposta.

## 9. Endpoint de leitura

- [ ] 9.1 Criar `xano/api/app/listar_custos_equipe_projeto_GET.xs` (`GET projetos/{id}/custos-equipe`, autenticado): projeto existe; intervalo padrão de 30 dias e `data_inicio < data_fim`; verificar moedas distintas antes de somar (uma → `moeda`; nenhuma → `moeda = null` e totais zero; mais de uma → `inputerror`, sem somar nem converter); agregar por equipe entre provedores; separar "Sem responsável"; `total_projeto`; `equipes` ordenada por `codigo`; sem série diária, filtro por provedor ou serviço. Verificação: admin e leitura → 200; sem token → 401; inexistente → `notfound`; intervalo sem custos → `moeda = null`; totais conferem com a soma das linhas; caso de moedas mistas verificado por revisão de código (o Mock só retorna USD).

## 10. E2E com AWS Mock (provedor Mock com `PRJ`/`EQP`)

- [ ] 10.1 Executar a classificação e validar: PRJ + EQP válidos; PRJ sem EQP ("Sem responsável"); projeto desconhecido; projeto inativo (sem gravação e sem equipe criada); EQP novo em projeto ativo (equipe criada); equipe existente reutilizada; vários serviços somados na mesma equipe/dia; vários dias; custo sem PRJ (`nao_alocados`). Verificação: evidência das respostas e contagens registrada na task.
- [ ] 10.2 Reexecutar a mesma janela e validar idempotência (sem duplicatas, `equipes_criadas = 0`, `registros_removidos = 0`). Verificação: contagens idênticas.
- [ ] 10.3 Executar janela de mais de 60 dias e validar paginação consolidada. Verificação: resultado completo.
- [ ] 10.4 (Requer edição manual no Mock pelo usuário) Alterar a tag EQP de um recurso, reexecutar a janela e validar a reconciliação: a combinação antiga é removida, `registros_removidos > 0` e o total do projeto não duplica. Verificação: evidência registrada. Observação: o Mock reescreve todo o histórico ao editar a tag; isso valida a reconciliação, não a semântica temporal da AWS real.
- [ ] 10.5 (Requer edição manual no Mock pelo usuário) Criar variante de caixa/espaço de um código e validar a soma após normalização. Verificação: registro único com a soma.
- [ ] 10.6 Validar o aviso de Tag Key de equipe: janela em que nenhum custo de projeto ativo tem equipe (ou provedor com Key de equipe sem dados) → `sucesso` com `aviso`. Verificação: resposta e registro contêm o aviso.
- [ ] 10.7 Validar casos de erro: Mock offline ou conta inexistente → `erro` sanitizado e nenhuma linha alterada ou removida; intervalo inválido; usuário leitura no POST; sem token. Verificação: respostas e ausência de alteração em `custos_equipe`.
- [ ] 10.8 Validar o endpoint de leitura contra os dados gravados e conferir, por projeto e dia, Σ `custos_equipe` = Σ `custos_projeto` (após executar as duas classificações sobre a mesma janela). Verificação: totais conferem.

## 11. Regressão

- [ ] 11.1 Executar `classificar-custos`, `coletar-custos` e `sincronizar-recursos` e confirmar comportamento inalterado; confirmar que nenhum registro de `custos`, `custos_projeto` ou `recursos` foi alterado pela nova classificação. Verificação: respostas e contagens iguais às anteriores.

## 12. Limitações registradas

- [ ] 12.1 Registrar no resultado da verificação o que não foi testado: AWS real (paginação real com dois agrupamentos por TAG e ativação da Tag Key de equipe) e Key customizada (o Mock aceita apenas `PRJ`/`EQP`). Verificação: riscos remanescentes documentados.
