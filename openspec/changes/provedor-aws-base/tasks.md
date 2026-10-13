## 1. Decisões de segurança e pré-requisitos (gate antes do Apply)

- [x] 1.1 Decisões de segurança D4 aprovadas pelo usuário com ajustes: (a) chave de cifra em `$env.PROV_ENC_KEY`, **sem IV fixo global** — AEAD/JWE preferencial ou IV aleatório por gravação; (b) credencial = chave de acesso AWS de IAM dedicada, nunca root, somente leitura/privilégio mínimo; (c) `status = ok` significa apenas "credencial autenticada". Verificação: aprovação registrada nesta change (proposal/design/spec atualizados).
- [x] 1.2 Mecanismo de cifra confirmado via Xano MCP: **JWE** escolhido. `jwe_encode`/`jwe_decode` com `key_algorithm = "A256KW"` e `content_algorithm = "A256CBC-HS512"`, chave de `$env.PROV_ENC_KEY`, IV/nonce gerenciado pelo próprio JWE. O `encrypt`/`decrypt` simétrico do Xano só oferece modos CBC com IV explícito (sem `aes-256-gcm` nativo), então o caminho JWE é o adotado. `aws_secret_iv` permanece no schema mas não é usado. Verificação: decisão registrada em design (D4/Q3); assinaturas dos filtros confirmadas na doc.
- [x] 1.3 Criada no Xano a variável de ambiente `PROV_ENC_KEY` (valor fora de Git/frontend); sem IV fixo global. Verificação: confirmada no E2E — cadastro de provedor e JWE funcionando com a chave do `$env`; busca por `PROV_ENC_` no repositório não retorna valores.

## 2. Backend Xano — tabela

- [x] 2.1 Criado `xano/table/provedores.xs` conforme D1 (`id`, `apelido`, `tipo` enum=[aws], `identificador_conta`, `tipo_credencial` enum=[aws_access_key], `aws_access_key_id` sensitive, `aws_secret_cifrado` sensitive+private, `aws_secret_iv` sensitive+private reservado, `status` enum=[pendente,ok,erro,inativo], `criado_em` private). Verificação: Xano MCP validou a sintaxe sem erros (`provedores.xs: Valid`).

## 3. Backend Xano — leitura

- [x] 3.1 Criado `xano/api/app/listar_provedores_GET.xs` (`auth = "usuarios"`), retornando lista de `{id, apelido, tipo, identificador_conta, tipo_credencial, status}` via `var $resposta` (map explícito). Verificação: resposta não inclui segredo/IV; sem token o `auth = "usuarios"` retorna 401. Validado pelo Xano MCP. (E2E ao vivo em 7.1.)
- [x] 3.2 Criado `xano/api/app/detalhe_provedor_GET.xs` (`auth = "usuarios"`), por `id`, retornando os metadados sem segredo; `id` inexistente → `notfound`. Verificação: resposta sem segredo; validado pelo Xano MCP. (E2E ao vivo em 7.1.)

## 4. Backend Xano — escrita (admin)

- [x] 4.1 Criado `xano/api/app/criar_provedor_POST.xs` (admin via padrão D3): valida `apelido`/`identificador_conta` não vazios, `tipo == "aws"`, credencial completa; protege `aws_secret_access_key` via `jwe_encode` (`$env.PROV_ENC_KEY`, A256KW/A256CBC-HS512); `status = "pendente"`; resposta sem segredo. Verificação: validado pelo Xano MCP; segredo marcado `sensitive`, nunca na resposta. (E2E ao vivo em 7.1.)
- [x] 4.2 Criado `xano/api/app/editar_provedor_PATCH.xs` (admin): atualiza `apelido`/`identificador_conta`/`aws_access_key_id` (ausente = preserva); se `aws_secret_access_key` enviado, re-protege via `jwe_encode` (novo token JWE) e substitui `aws_secret_cifrado`; se ausente, preserva o cifrado; resposta sem segredo. Verificação: validado pelo Xano MCP. (E2E ao vivo em 7.1.)
- [x] 4.3 Criado `xano/api/app/desativar_provedor_POST.xs` (admin): `db.edit` apenas `status = "inativo"`, sem DELETE; resposta sem segredo. Verificação: validado pelo Xano MCP. (E2E ao vivo em 7.1.)

## 5. Backend Xano — teste de conexão AWS (admin)

- [x] 5.1 Mecanismo da chamada AWS confirmado (D5/Q2): **SigV4 manual** para STS `GetCallerIdentity` (opção 1 aprovada pelo usuário). Xano não tem conector STS nativo (só `cloud.aws.s3.*`); primitivos SigV4 confirmados (`hmac_sha256:key:raw`, `sha256`, `bin2hex`, `format_timestamp`). Sem bucket S3, sem Lambda. Verificação: decisão registrada em design (D5/Q2).
- [x] 5.2 Criado `xano/api/app/testar_conexao_provedor_POST.xs` (admin): carrega provedor, valida `tipo = aws` e credencial salva, decifra o segredo via `jwe_decode` imediatamente antes de assinar, monta SigV4 (service=sts, region=us-east-1) e chama STS `GetCallerIdentity` por `api.request`, atualiza `status` para `ok`/`erro` e retorna `{id, status, conectado, mensagem}` sem segredo; falha nunca silenciosa; mensagem sanitizada. `ok` = credencial autenticada. Verificação: validado pelo Xano MCP (sintaxe) e verificação funcional real confirmada no E2E — SigV4 e STS `GetCallerIdentity` retornando sucesso, status `ok` (ver 7.1).

## 6. Frontend Reflex — estado e integração

- [x] 6.1 Criado `projetoImpacta/pages/provedores_state.py` (padrão `projetos_state.py`): `carregar` (GET `/provedores`, Bearer token, 401 → `AuthState.handle_unauthenticated`), ações criar/editar/desativar/testar via `get_xano_app_base_url()`. Campo do segredo começa vazio, é limpo após o envio e, na edição, vazio = não alterar. Verificação: `reflex compile --dry` sem erros; chamadas usam `XANO_APP_BASE_URL`; segredo não persistido além da submissão.
- [x] 6.2 Reescrito `projetoImpacta/pages/provedores.py` consumindo o estado real: lista provedores com status (pill), controles de novo/editar/testar/desativar sob `rx.cond(AuthState.is_admin, ...)`, preservando o design incorporado (tabela, pills, app_shell); `_PROVEDORES_MOCK` removido. Verificação: `reflex compile --dry` sem erros; segredo nunca reexibido; leitura sem controles de escrita/teste.
- [x] 6.3 Atualizado `projetoImpacta/projetoImpacta.py`: `on_load` de `/provedores` passa a `[AuthState.require_auth, ProvedoresState.carregar]`. Verificação: `reflex compile --dry` sem erros; rota compila com o novo on_load.

## 7. Verificação integrada

- [x] 7.1 Sincronizados tabela/endpoints ao Xano e validados os fluxos fim a fim. Verificação (E2E confirmado): cadastro de provedor funcionando; JWE funcionando; AWS SigV4 funcionando; STS `GetCallerIdentity` retornando sucesso; status `Conectado` (`ok`); edição sem novo Secret preserva a credencial; nenhuma resposta expõe o segredo. Inclui a verificação funcional real da assinatura SigV4 (5.2), antes pendente.
- [x] 7.2 Revisado que a change não alterou `usuarios`, `projetos` nem a autenticação, e que nenhum segredo foi versionado. Verificação: `git status`/diff restritos aos arquivos previstos no Impact; busca por `PROV_ENC_`/segredos nos arquivos versionáveis não retorna valores; `.xs` de auth/projetos inalterados (validação em lote confirmou os 19 arquivos).
