## 0. Correção documental (convenção de tags)

- [x] 0.1 Atualizar `docs/domain-model.md` para a convenção oficial atual: tag de projeto `PRJ=<codigo>` e tag de equipe `EQP=<codigo>` (Tag Key = finalidade, Tag Value = código), substituindo os formatos históricos `PRJ_PAGAMENTOS`/`EQP_BACKEND` quando descrevem a convenção vigente; deixar explícito que `PRJ$...`/`EQP$...` é a representação do Cost Explorer (GroupBy), não o formato da tag gravada no recurso. Verificação: nenhuma descrição da convenção vigente usa `PRJ_`/`EQP_`; distinção tag×Cost Explorer registrada.

## 1. Schema — equipes

- [x] 1.1 Criar tabela `equipes` em `xano/table/equipes.xs` com `id`, `nome`, `codigo` (trim|upper), `projeto_id` (FK `projetos`), `auto_gerada` (bool) e índice único `(projeto_id, codigo)`. Sem `budget`; sem `status` no MVP (ver design D4). Verificação: tabela válida (MCP/dry-run), índice único presente, FK para `projetos`.

## 2. Schema — recursos

- [x] 2.1 Criar tabela `recursos` em `xano/table/recursos.xs` com os campos de D5 (`id`, `provedor_id` FK, `arn`, `regiao`, `servico`, `projeto_id` FK nullable, `equipe_id` FK nullable, `codigo_projeto_tag`, `codigo_equipe_tag`, `sync_id`, `ultima_vista_em`, `ativo`, `criado_em`, `atualizado_em`) e índice único `(provedor_id, arn)` + índices de leitura por `projeto_id` e `equipe_id`. ARN íntegro (text). Verificação: tabela válida; índice único presente; FKs corretas.

## 3. Provedor — Tag Key de equipe

- [x] 3.1 Adicionar campo opcional `tag_alocacao_equipe` (text) à tabela `provedores` e aos endpoints `criar/editar/listar/detalhe` (aceitar/persistir/retornar; não é segredo; sem expor o secret). Verificação: criar/editar com e sem o campo; leitura inclui `tag_alocacao_equipe` e nunca o secret.

## 4. Estratégia regional

- [x] 4.1 Implementar a enumeração de regiões habilitadas via EC2 `DescribeRegions` (SigV4 reutilizado; read-only), com routing real/Mock por `usar_mock`. Verificação: lista de regiões obtida; falha de enumeração aborta a sync sem reconciliar.

## 5. Auth / pré-condições

- [x] 5.1 No endpoint de sincronização: autorização admin + pré-condições (provedor existe, `tipo=aws`, `status=ok`, credencial presente, `tag_alocacao_projeto` definido); cada falha retorna erro explícito ANTES de qualquer chamada externa; `tag_alocacao_equipe` opcional. Verificação: leitura → accessdenied; sem Tag Key projeto → inputerror; inativo/erro/pendente → inputerror; inexistente → notfound; 401 sem token.
- [x] 5.2 Proteção best-effort contra duplo disparo (NÃO lock atômico): campos `sincronizacao_recursos_em_andamento`/`_inicio`/`_id` no provedor; antes de chamadas externas, rejeitar com erro controlado sanitizado se marca ativa dentro da janela (15 min), permitir se órfã/expirada, adquirir a marca com o `sync_id`; liberar a marca no sucesso e em erro controlado, apenas se ainda pertencer a esta execução. Documentar a limitação no design. Verificação: execução com marca ativa → erro controlado; marca expirada → permite; marca liberada ao fim.

## 6. Chamada de inventário (GetResources)

- [x] 6.1 Criar `xano/api/app/sincronizar_recursos_provedor_POST.xs` chamando `GetResources` (Tagging API) por região, com `TagFilters` contendo **apenas** a Tag Key de projeto; SigV4 coerente ao destino (`service=tagging`, host `tagging.{region}.amazonaws.com`), read-only. Verificação: `TagFilters` só com a Key de projeto; nenhuma escrita na AWS.

## 7. Paginação

- [x] 7.1 Tratar `PaginationToken` por região, reassinando cada página, acumulando todos os recursos; só considerar a sync completa após a última página de todas as regiões. Verificação: resposta multi-página consolidada; execução parcial não dispara reconciliação.

## 8. Parser de tags

- [x] 8.1 Para cada `ResourceTagMappingList[]`, extrair `ResourceARN`, `regiao`, `servico` (derivado do ARN), o valor da tag de projeto e, se houver, o da tag de equipe (sem filtrar por EQP). Verificação: itens normalizados contêm ARN íntegro, região, serviço e os valores crus de PRJ/EQP.

## 9. Resolução de projeto

- [x] 9.1 Normalizar valor de projeto (trim|upper) e resolver `projetos.codigo`: sem projeto → `projeto_id=null`/`equipe_id=null`, não cria nada, conta `projetos_desconhecidos`; projeto inativo → persiste com `projeto_id` inativo/`equipe_id=null`, não cria equipe, conta `projetos_inativos`. Verificação: cada caso reflete os contadores; nenhum projeto criado.

## 10. Criação/resolução de equipe

- [x] 10.1 Para projeto ativo com tag de equipe: normalizar (trim|upper), buscar `(projeto_id, codigo)`; existente → atribuir; inexistente → criar `auto_gerada=true` e atribuir; conta `equipes_criadas`. Verificação: reutiliza existente; cria só quando necessário; unicidade `(projeto_id, codigo)` respeitada.

## 11. Sem responsável

- [x] 11.1 Projeto ativo sem tag de equipe (ausente/vazia) → `equipe_id=null` ("Sem responsável"); nunca criar equipe fictícia; conta `sem_responsavel`. Verificação: recurso fica sem equipe; nenhuma equipe `SEM_RESPONSAVEL` é criada.

## 12. Upsert de recursos

- [x] 12.1 Upsert por `(provedor_id, arn)`: atualiza campos resolvidos + `sync_id`/`ultima_vista_em`/`ativo=true`; insere quando novo. Verificação: reexecução sem mudanças não duplica; mudança de tag reatribui projeto/equipe automaticamente.

## 13. Reconciliação

- [x] 13.1 Após sync completa e bem-sucedida, marcar `ativo=false` os recursos do provedor não vistos nesta execução (por `sync_id`), sem exclusão física; conta `recursos_desativados`. Verificação: recurso ausente vira inativo após sucesso; nada é desativado em falha parcial.

## 14. Erro / falha parcial

- [x] 14.1 Em falha (AWS, paginação, enumeração de regiões, pré-condição): `status=erro` sanitizado (http_status, Error.Code, Error.Message, RequestId), sem reconciliar, inventário anterior intacto; resposta nunca expõe secret/Authorization/JWE. Verificação: cenário de erro não desativa recursos e não vaza segredo.

## 15. Endpoints read-only

- [x] 15.1 Criar `GET /projetos/{id}/recursos` e `GET /projetos/{id}/equipes` (autenticado, read-only), permitindo distinguir recursos por equipe e os "Sem responsável" (`equipe_id=null`). Verificação: listagens retornam os dados do inventário; 401 sem token.

## 16. Validação

- [x] 16.1 Validar os XanoScript criados (MCP quando disponível) e via `xano workspace push -d .\xano --dry-run` (sem push real). Verificação: validação sem erros; dry-run mostra apenas os objetos desta change (2 tabelas novas, 1 campo em provedores, endpoints novos), sem remoções. [MCP validou 10/10 arquivos (3 warnings inócuos de db.edit/db.add sem `as`, padrão aceito); dry-run exit 0: +2 tabelas, ~1 tabela (ADD_FIELD), +3 endpoints, ~4 endpoints de provedor, 0 remoções.]
- [x] 16.2 Validar a change com `openspec validate inventario-recursos-equipes-aws-base --strict`. Verificação: validação passa sem erros.

## 17. Dependência Mock

- [x] 17.1 Registrar/abrir (em branch/repo separado do Mock, fora desta branch) a necessidade do Mock simular `GetResources` por região e a enumeração de regiões, conforme o contrato do design. Verificação: dependência documentada e comunicada; NÃO alterar o Mock nesta branch. [Entregue pelo usuário: Mock publicado com DescribeRegions (`/aws/{conta}/ec2/`) e GetResources (`/aws/{conta}/tagging/{region}/`), com paginação e múltiplas regiões, em https://<URL-DO-SIMULADOR>.]

## 18. E2E

- [x] 18.1 (E2E, pós-dependência do Mock) Com provedor Mock (`tag_alocacao_projeto=PRJ`, `tag_alocacao_equipe=EQP`) e recursos fictícios cobrindo: projeto+equipe, projeto sem equipe ("Sem responsável"), projeto desconhecido e projeto inativo; executar `sincronizar-recursos` e validar enumeração multi-região, paginação, resolução, criação automática de equipe, contadores, upsert idempotente e proteção best-effort. Verificação: inventário correto; sem regressão nos fluxos existentes. [COMPROVADO contra https://<URL-DO-SIMULADOR> (provedor Mock id=2, conta 123456789012): DescribeRegions=4 regiões (eu-west-1, sa-east-1, us-east-1, us-west-2); GetResources paginado 50/página; 1ª sync {regioes_consultadas:4, recursos_encontrados:170, recursos_ativos:170, equipes_criadas:6, sem_responsavel:5, projetos_desconhecidos:2, projetos_inativos:31}; equipes auto-criadas validadas (PAGAMENTOS: BACKEND/DADOS/DEVOPS/QA, auto_gerada=true); "Sem responsável" (equipe_id=null); projeto desconhecido (total_projetos permanece 7, nada criado); projeto inativo MARKETING (0 equipes criadas, projeto_id preservado, 31 recursos); idempotência: 2ª sync {equipes_criadas:0} e GET pós-sync confirma 4 equipes / 103 recursos em PAGAMENTOS (sem duplicar); proteção best-effort provada indiretamente (2ª sync aceita dentro da janela de 15min ⇒ marca liberada ao fim da 1ª); campos `_em_andamento`/`_inicio`/`_id` são `visibility=private`, não observáveis via API (correto).]

- [x] 18.2 (E2E, requer mutação manual do dataset do Mock pelo usuário) Validar reatribuição automática (mudar a tag `EQP` de um recurso de BACKEND→DADOS em PAGAMENTOS e reexecutar: o recurso deve passar a `equipe_id` da equipe DADOS sem duplicar nada) e reconciliação (remover um recurso do dataset e reexecutar: o recurso ausente deve virar `ativo=false`, contando em `recursos_desativados`, sem exclusão física). Verificação: reatribuição aplicada; recurso removido fica inativo após sync bem-sucedida. [REATRIBUIÇÃO COMPROVADA: usuário alterou no Mock a tag EQP do ARN `arn:aws:ec2:sa-east-1:123456789012:instance/i-0123456789abcdef0` (conta 123456789012) de BACKEND→DADOS; sync no provedor id=2 retornou {status:sucesso, regioes_consultadas:4, recursos_encontrados:170, recursos_ativos:170, recursos_desativados:0, equipes_criadas:0, sem_responsavel:5, projetos_desconhecidos:2, projetos_inativos:31}; GET /projetos/4/recursos → match_count=1 (mesmo registro id=37, sem duplicação), projeto_id=4, codigo_projeto_tag=PAGAMENTOS, codigo_equipe_tag=DADOS, equipe_id=6, ativo=true, regiao=sa-east-1, ARN íntegro; total de recursos de PAGAMENTOS permanece 103; equipes permanecem 4 (BACKEND/DADOS/DEVOPS/QA, nenhuma DADOS nova). RECONCILIAÇÃO COMPROVADA: usuário removeu do dataset do Mock o ARN `arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef1` (antes PRJ=PAGAMENTOS/EQP=BACKEND); nova sync no provedor id=2 retornou {status:sucesso, regioes_consultadas:4, recursos_encontrados:169 (caiu de 170), recursos_ativos:169, recursos_desativados:1, equipes_criadas:0}; GET /projetos/4/recursos → o ARN continua persistido como MESMO registro id=81 (match_count=1, sem DELETE físico), ativo true→false, projeto_id=4, codigo_projeto_tag=PAGAMENTOS, codigo_equipe_tag=BACKEND, ARN íntegro; total de recursos de PAGAMENTOS permanece 103 (102 ativos / 1 inativo), sem desativação em massa. REATRIBUIÇÃO E RECONCILIAÇÃO COMPROVADAS — 18.2 concluída.]
