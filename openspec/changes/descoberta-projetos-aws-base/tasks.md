## 1. Endpoint de descoberta (read-only)

- [ ] 1.1 Criar `xano/api/app/descobrir_projetos_provedor_POST.xs` (verb POST, path `provedores/{id}/descobrir-projetos`, auth `usuarios`). Verificação: endpoint existe e responde 401 sem token.
- [ ] 1.2 Autorização admin + pré-condições: provedor existe, `tipo = aws`, `status = ok`, credencial presente e `tag_alocacao_projeto` definido; cada falha retorna erro explícito ANTES de qualquer chamada à AWS/Mock. Verificação: role leitura → accessdenied; sem Tag Key → inputerror; provedor inativo/erro/pendente → inputerror; inexistente → notfound; nenhuma chamada externa nesses casos.
- [ ] 1.3 Resolver destino/assinatura reaproveitando o padrão consolidado: `$eh_mock`, `$sig_host`, `$canonical_uri`, `$sig_endpoint` por `usar_mock`, com normalização de `MOCK_BASE_URL` (barra final) e validação de presença no ramo Mock; decifrar o secret via JWE só em memória. Verificação: `usar_mock=false` usa endpoint/host/URI reais; `usar_mock=true` usa `{base}/aws/{conta}/ce/` e host do Mock; Mock sem `MOCK_BASE_URL` → erro sanitizado.
- [ ] 1.4 Chamar `GetTags` (`X-Amz-Target: AWSInsightsIndexService.GetTags`) com `TagKey = tag_alocacao_projeto` e `TimePeriod` válido (default últimos 30 dias), assinado via SigV4 coerente ao destino, read-only. Tratar `NextPageToken` consolidando todas as páginas. Verificação: resposta multi-página consolidada; falha de página → erro sanitizado sem lista parcial.
- [ ] 1.5 Normalizar/filtrar: para cada valor em `Tags[]`, aplicar `trim|upper`; ignorar vazio; deduplicar. Verificação: valores vazios ausentes; cada código aparece uma vez; normalização coerente com `projetos.codigo`.
- [ ] 1.6 Comparar com `projetos.codigo`: para cada código, `existente` (bool) e `projeto_id` (ou null), sem gravar nada. Verificação: existentes marcados com id correto; inexistentes com `existente=false`/`projeto_id=null`; nenhuma gravação.
- [ ] 1.7 Resposta: `{ provedor_id, tag_key, descobertos: [{codigo, existente, projeto_id}] }`, sem segredos/Authorization/JWE; diagnóstico de erro sanitizado (http_status, Error.Code, Error.Message, RequestId). Verificação: resposta no formato; nenhum dado sensível.

## 2. Endpoint de importação (grava apenas inexistentes)

- [ ] 2.1 Criar `xano/api/app/importar_projetos_provedor_POST.xs` (verb POST, path `provedores/{id}/importar-projetos`, auth `usuarios`), recebendo uma lista de códigos selecionados. Verificação: endpoint existe e responde 401 sem token.
- [ ] 2.2 Autorização admin + pré-condições do provedor (existe, `tipo = aws`). Verificação: role leitura → accessdenied; provedor inexistente → notfound.
- [ ] 2.3 Para cada código: normalizar `trim|upper`; ignorar vazio; consultar `projetos.codigo`; se existe → ignorar (não altera/reativa); se não existe → `db.add` com `nome = codigo`, `codigo`, `budget = 0`, `status = ativo`. Verificação: importa só inexistentes; existentes inalterados (inclusive status); vazios ignorados.
- [ ] 2.4 Não duplicar: confiar no índice único de `projetos.codigo` como barreira final; a verificação de existência é feita na importação (não confia em `existente` da descoberta). Verificação: reimportar o mesmo código não cria duplicata.
- [ ] 2.5 Resposta distinguindo `criados` e `ignorados` (com motivo: já existe / vazio), sem segredos. Verificação: contadores/listas rastreáveis; nenhum dado sensível.

## 3. Verificação e validação

- [ ] 3.1 Validar os XanoScript criados (MCP XanoScript quando disponível) e via `xano workspace push -d .\xano --dry-run` (sem push real). Verificação: validação sem erros; dry-run mostra apenas os dois endpoints novos, sem remoções nem alterações em outros objetos.
- [ ] 3.2 Validar a change com `openspec validate descoberta-projetos-aws-base --strict`. Verificação: validação passa sem erros.
- [ ] 3.3 (E2E, pós-aprovação) Com provedor Mock (`tag_alocacao_projeto = PRJ`) tendo tags `PRJ$PAGAMENTOS`, `PRJ$MARKETING`, `PRJ$INFRAESTRUTURA`, `PRJ$`: descobrir (lista correta, vazio ignorado, existentes marcados) e importar os inexistentes (criados com budget 0/ativo, sem duplicar), confirmando que a classificação passa a associá-los. Verificação: descoberta read-only correta; importação cria só inexistentes; fluxo real/Mock e classificação intactos.
