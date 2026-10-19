## 0. Convenção de domínio (confirmada — não bloqueante)

Decisão D1 confirmada pelo usuário (convenção oficial), sem pendências: a **Tag Key**
(`provedores.tag_alocacao_projeto`, recomendada `PRJ`) identifica a finalidade da tag e o
**Tag Value** é diretamente o `projetos.codigo`. O `GroupBy` do Cost Explorer usa essa Tag
Key e retorna o grupo no formato `"<Key>$<Value>"` (ex.: `PRJ$PAGAMENTOS`). O código extrai o
Value removendo exatamente `"<Key>$"` e compara diretamente com `projetos.codigo` (ex.:
`PRJ$PAGAMENTOS` → `PAGAMENTOS`). NÃO há hardcode de `PRJ` nem tratamento de prefixo `PRJ_` no
Value. As tasks abaixo implementam essa convenção.

## 1. Schema Xano — tabelas e campo

- [x] 1.1 Adicionar campo opcional `tag_alocacao_projeto` (text) à tabela `provedores` em `xano/table/provedores.xs`, sem marcar como sensível/privado (é a Key da tag, não um segredo). Verificação: schema sincronizado via Xano CLI e campo visível na definição da tabela.
- [x] 1.2 Criar tabela `custos_projeto` em `xano/table/custos_projeto.xs` com os campos de D2 (`id`, `provedor_id` FK, `projeto_id` FK, `data`, `servico`, `metrica` enum=`unblended`, `valor`, `moeda`=`USD`, `estimado`, `coletado_em` private) e índice único `(provedor_id, projeto_id, data, servico, metrica)` mais índice de leitura `(projeto_id, data desc)`. Verificação: tabela criada no workspace, índice único presente, FK apontando para `provedores` e `projetos`.
- [x] 1.3 Criar tabela `coletas_classificacao` em `xano/table/coletas_classificacao.xs` com os campos de D6 (`id`, `provedor_id` FK, `intervalo_inicio`, `intervalo_fim`, `status` enum `sucesso`/`erro`, `registros_gravados`, `nao_alocados`, `tags_sem_projeto`, `projetos_inativos`, `mensagem`, `executado_em`). Verificação: tabela criada no workspace com os enums e defaults esperados.

## 2. Provedores — persistir a Key da tag de alocação

- [x] 2.1 Atualizar `criar_provedor_POST.xs` e `editar_provedor_PATCH.xs` para aceitar e persistir `tag_alocacao_projeto` (opcional), preservando as regras existentes (admin, sem expor segredo). Verificação: criar/editar provedor com e sem o campo retorna o provedor sem o segredo e com o valor persistido quando informado.
- [x] 2.2 Garantir que `listar_provedores_GET.xs` e `detalhe_provedor_GET.xs` retornem `tag_alocacao_projeto` como metadado (não é segredo), mantendo a exclusão do `aws_secret_cifrado`. Verificação: respostas de leitura incluem a Key e nunca o segredo.

## 3. Endpoint de classificação (reuso do fluxo base)

- [x] 3.1 Criar `xano/api/app/classificar_custos_provedor_POST.xs` (verb POST, path `provedores/{id}/classificar-custos`, auth `usuarios`) partindo de `coletar_custos_provedor_POST.xs` como molde. Verificação: endpoint existe e responde 401 sem token.
- [x] 3.2 Implementar autorização admin e pré-condições: provedor existe, `tipo = aws`, `status = ok`, credencial presente e `tag_alocacao_projeto` definido; cada falha retorna erro explícito ANTES de qualquer chamada à AWS. Verificação: role leitura → accessdenied; provedor sem Key → inputerror; provedor inativo → inputerror; provedor inexistente → notfound; nenhuma chamada à AWS nesses casos.
- [x] 3.3 Decifrar o segredo via JWE (`A256KW`/`A256CBC-HS512`) só em memória, idêntico ao base, e resolver o intervalo (`Start` inclusivo / `End` exclusivo; default últimos 30 dias). Verificação: intervalo informado é respeitado; omitido usa `hoje−30d`..`hoje`.
- [x] 3.4 Montar `GetCostAndUsage` com `GroupBy = [ {Type: TAG, Key: <tag_alocacao_projeto>}, {Type: DIMENSION, Key: SERVICE} ]`, `Granularity=DAILY`, `Metrics=[UnblendedCost]`, assinar SigV4 (ce/us-east-1) e paginar por `NextPageToken` acumulando todas as páginas em memória sem persistir. Verificação: com resposta multi-página, todas as páginas são buscadas antes de qualquer gravação.

## 4. Normalização e classificação por projeto

- [x] 4.1 Normalizar `ResultsByTime`/`Groups` extraindo `Keys[0]` (valor da tag), `Keys[1]` (serviço), `valor`, `moeda`, `data`, `estimado`. Verificação: itens normalizados contêm valor de tag, serviço, dia, valor, moeda e estimado.
- [x] 4.2 Resolver o projeto: remover exatamente o prefixo `"<tag_alocacao_projeto>$"` de `Keys[0]` para obter o Value; se Value vazio → não alocado; senão o Value é diretamente o `codigo` (normalizar para maiúsculas, comparar com `projetos.codigo`); buscar projeto `ativo`. Sem hardcode de `PRJ` e sem tratamento de prefixo `PRJ_` no Value. Verificação: `PRJ$PAGAMENTOS` resolve para projeto `codigo=PAGAMENTOS`; `Project$PAGAMENTOS` (Key `Project`) também; Value vazio não resolve projeto.
- [x] 4.3 Classificar casos de borda em contadores: Value ausente/vazio → `nao_alocados`; Value sem projeto → `tags_sem_projeto` (sem criar projeto); projeto `inativo` → `projetos_inativos`; nenhum custo subjacente é descartado. Verificação: contadores refletem cada caso e nenhum projeto é criado automaticamente.

## 5. Persistência atômica e idempotente

- [x] 5.1 Após sucesso de todas as páginas, fazer upsert em `custos_projeto` apenas para custos com projeto existente e `ativo`, pela chave natural `(provedor_id, projeto_id, data, servico, metrica)` (query → edit se existe, add se não). Verificação: reexecução no mesmo período não duplica; valor alterado na AWS atualiza o registro existente.
- [x] 5.2 Garantir atomicidade: se qualquer página falhar, não gravar nada em `custos_projeto`, registrar `coletas_classificacao` com `status = erro` e mensagem sanitizada, e manter intactos os registros anteriores. Verificação: simular falha de página → nenhuma gravação, estado `erro`, dados anteriores inalterados.
- [x] 5.3 Confirmar que a operação NÃO cria/edita/remove nada na tabela `custos` base. Verificação: executar classificação e comparar `custos` antes/depois — inalterada.

## 6. Detecção de tag de alocação inativa e estado da execução

- [x] 6.1 Detectar tag de alocação inativa/não propagada: se o `GroupBy TAG` não retornar a dimensão de tag esperada (grupos sem a chave de tag), tratar como erro sanitizado; opcionalmente usar `ce:ListCostAllocationTags` para confirmar status `Active` e produzir mensagem clara, sem ativar a tag. Verificação: cenário com tag inativa → `status = erro` sanitizado, sem modificar a AWS.
- [x] 6.2 Registrar `coletas_classificacao` ao final (sucesso ou erro) com intervalo, status, `registros_gravados`, contadores de borda, `mensagem` sanitizada e `executado_em`; a resposta MUST NOT conter segredo, Authorization SigV4, signing keys nem JWE decifrado. Verificação: inspecionar resposta e registro — contêm apenas dados seguros (http_status, Error.Code, Error.Message sanitizada, RequestId em erro).

## 7. Verificação de integração

- [x] 7.1 Executar a classificação ponta a ponta contra um provedor `aws` `status=ok` com `tag_alocacao_projeto` definido (ex.: `PRJ`) e a cost allocation tag ativada, cobrindo pelo menos um projeto existente/ativo (ex.: `PRJ$PAGAMENTOS`), um Value sem projeto (ex.: `PRJ$LEGADO`), um custo sem Value (ex.: `PRJ$`) e um projeto inativo. Verificação: `custos_projeto` recebe apenas os custos de projetos ativos existentes; os contadores de borda batem; `custos` permanece inalterada; nenhum segredo é exposto.
- [x] 7.2 Validar a change com `openspec validate classificacao-tags-aws-base --strict`. Verificação: validação passa sem erros.
