## 1. Decisões de segurança e pré-requisitos (gate antes do Apply)

- [ ] 1.1 Obter aprovação explícita do usuário para as decisões de segurança D4.1–D4.3 (mecanismo de cifra `security.encrypt`/`decrypt` com `key`/`iv` em `$env` do Xano; modelo de credencial = chave de acesso AWS somente leitura; variáveis de cifra criadas no Xano, nunca no `.env` do frontend ou no Git). Verificação: aprovação registrada antes de iniciar qualquer tarefa de implementação.
- [ ] 1.2 Criar no Xano as variáveis de ambiente `PROV_ENC_KEY` e `PROV_ENC_IV` (valores fora de Git/frontend). Verificação: variáveis existem no workspace Xano e não aparecem em nenhum arquivo versionado (busca por `PROV_ENC_` no repositório não retorna valores).

## 2. Backend Xano — tabela

- [ ] 2.1 Criar `xano/table/provedores.xs` conforme D1 (campos `id`, `apelido`, `tipo` enum=[aws], `identificador_conta`, `tipo_credencial` enum=[aws_access_key], `aws_access_key_id` sensitive, `aws_secret_cifrado` sensitive+private, `status` enum=[pendente,ok,erro,inativo], `criado_em` private). Verificação: `openspec`/Xano MCP valida a sintaxe XanoScript do arquivo sem erros.

## 3. Backend Xano — leitura

- [ ] 3.1 Criar `xano/api/app/listar_provedores_GET.xs` (`auth = "usuarios"`), retornando lista de `{id, apelido, tipo, identificador_conta, tipo_credencial, status}` via `var $resposta` explícito. Verificação: resposta não contém nenhum campo de segredo; sem token retorna 401.
- [ ] 3.2 Criar `xano/api/app/detalhe_provedor_GET.xs` (`auth = "usuarios"`), por `id`, retornando os mesmos metadados sem segredo; `id` inexistente → erro `notfound`. Verificação: resposta sem segredo; id inexistente retorna notfound.

## 4. Backend Xano — escrita (admin)

- [ ] 4.1 Criar `xano/api/app/criar_provedor_POST.xs` (admin via padrão D3): validar `apelido`/`identificador_conta` não vazios, `tipo == "aws"`, credencial completa; cifrar `aws_secret_access_key` com `security.encrypt` (`$env.PROV_ENC_KEY`/`$env.PROV_ENC_IV`) em `aws_secret_cifrado`; `status = "pendente"`; resposta sem segredo. Verificação: admin cria e recebe provedor sem segredo; leitura recebe accessdenied; `tipo` != aws e campos ausentes retornam inputerror.
- [ ] 4.2 Criar `xano/api/app/editar_provedor_PATCH.xs` (admin): atualizar `apelido`/`identificador_conta`; se `aws_secret_access_key` enviado, re-cifrar e substituir; se ausente, preservar `aws_secret_cifrado`; `tipo` não alterável para valor não suportado; resposta sem segredo. Verificação: edição sem segredo preserva o cifrado; edição com segredo substitui; leitura recebe accessdenied.
- [ ] 4.3 Criar `xano/api/app/desativar_provedor_POST.xs` (admin): `db.edit` apenas `status = "inativo"`, sem DELETE; resposta sem segredo. Verificação: status passa a inativo e o registro permanece; leitura recebe accessdenied.

## 5. Backend Xano — teste de conexão AWS (admin)

- [ ] 5.1 Confirmar na implementação o mecanismo da chamada AWS (D5/Q2): SigV4 nativo em XanoScript ou fallback (Lambda/conector), usando documentação do Xano via MCP. Verificação: decisão registrada e um caminho funcional selecionado antes de 5.2.
- [ ] 5.2 Criar `xano/api/app/testar_conexao_provedor_POST.xs` (admin): carregar provedor, validar `tipo = aws` e credencial salva, decifrar `aws_secret_cifrado`, chamar AWS STS `GetCallerIdentity` (somente leitura), atualizar `status` para `ok`/`erro` e retornar `{id, status, conectado, mensagem}` sem segredo; falha nunca silenciosa. Verificação: credencial válida → status ok; inválida → status erro com mensagem; leitura recebe accessdenied; segredo nunca na resposta nem em log.

## 6. Frontend Reflex — estado e integração

- [ ] 6.1 Criar `projetoImpacta/pages/provedores_state.py` (padrão `projetos_state.py`): `carregar` (GET `/provedores`, Bearer token, 401 → `AuthState.handle_unauthenticated`), ações de criar/editar/desativar/testar via `get_xano_app_base_url()`. Campo do segredo sempre vazio; na edição, vazio = não alterar. Verificação: `reflex compile` sem erros; chamadas usam `XANO_APP_BASE_URL`; nenhum segredo persistido no estado do cliente.
- [ ] 6.2 Reescrever `projetoImpacta/pages/provedores.py` para consumir o estado real: listar provedores com status, controles de cadastro/configuração/teste sob `rx.cond(AuthState.is_admin, ...)`, preservando o design incorporado; remover `_PROVEDORES_MOCK`. Verificação: página renderiza lista real; segredo nunca reexibido; leitura sem controles de escrita/teste.
- [ ] 6.3 Atualizar `projetoImpacta/projetoImpacta.py`: `on_load` de `/provedores` passa a `[AuthState.require_auth, ProvedoresState.carregar]`. Verificação: ao acessar `/provedores` autenticado, a lista real é carregada.

## 7. Verificação integrada

- [ ] 7.1 Sincronizar tabela/endpoints ao Xano e validar os fluxos fim a fim (admin cadastra → testa conexão → status reflete; leitura só consulta; 401 limpa sessão). Verificação: cenários da spec `provedores` observados manualmente contra o backend; confirmar que nenhuma resposta expõe o segredo (inspeção das respostas de listar/detalhe/criar/editar/testar).
- [ ] 7.2 Revisar que a change não alterou `usuarios`, `projetos` nem a autenticação, e que nenhum segredo foi versionado. Verificação: `git diff --stat` restrito aos arquivos previstos no Impact; busca por chaves/segredos no diff não retorna valores.
