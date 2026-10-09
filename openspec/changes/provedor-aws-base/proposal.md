## Why

A página `/provedores` do CostGuard foi incorporada na change `interface-frontend` apenas como apresentação, com dados mock e sem backend. O Provedor Cloud é a origem de recursos, custos e tags do domínio (ver `docs/domain-model.md`): sem conectar uma conta cloud, nenhuma funcionalidade de importação, classificação ou orçamento pode existir. Esta change entrega a **configuração base de um provedor AWS** — tabela e endpoints no Xano e a página Reflex `/provedores` consumindo dados reais — permitindo cadastrar uma conta AWS com credencial somente leitura, testar a conexão e consultar o estado do provedor, mantendo o escopo mínimo do MVP acadêmico.

## What Changes

- **Backend Xano (novo)**: tabela `provedores` e os endpoints de Provedores no api_group `app` já existente — listar, detalhe, criar, editar, desativar e testar conexão.
- **Suporte inicial a AWS**: nesta fase o único `tipo` suportado é `aws`. A credencial é uma chave de acesso AWS **somente leitura** (`access_key_id` + `secret_access_key`).
- **Segredo nunca exposto**: o `secret_access_key` é armazenado de forma cifrada no backend (chave de cifra em variável de ambiente do Xano, nunca no código/Git) e **nunca** é retornado ao frontend em nenhum endpoint. Após salvo, o segredo não é reexibido; para trocá-lo o admin reenvia um novo valor.
- **Autorização no backend**: todas as rotas exigem autenticação; as operações de escrita (criar/editar/desativar/testar) exigem `role = admin`; leitura (listar/detalhe) é permitida a qualquer usuário autenticado. O usuário `leitura` nunca cria nem altera provedores.
- **Teste de conexão não silencioso**: o backend chama a AWS (STS `GetCallerIdentity`, somente leitura) usando a credencial salva, atualiza o `status` do provedor (`ok` quando a conexão é válida, `erro` quando falha) e retorna o resultado. Falha de conexão nunca é silenciosa.
- **Desativação lógica**: provedor é desativado via `status`, sem exclusão física.
- **Frontend Reflex**: substituir os dados mock de `/provedores` por dados reais do Xano — listar provedores; cadastrar/configurar e testar conexão para admin; exibir o status da conexão; usuário `leitura` apenas consulta. A credencial secreta salva nunca é reapresentada. Preserva o design incorporado, o `AuthState`, a sessão e o tratamento central de 401 existentes.

## Capabilities

### New Capabilities

- `provedores`: Configuração base de Provedores Cloud do CostGuard — entidade `provedores` (id, apelido, tipo, identificador da conta, tipo de credencial, credencial cifrada e nunca retornada, status), suporte inicial ao tipo AWS com credencial somente leitura, operações de leitura (listar, detalhe sem segredo) para qualquer usuário autenticado e de escrita (criar, editar, desativar, testar conexão) restritas a admin, teste de conexão AWS executado no backend que atualiza o status, com autenticação e autorização validadas no backend Xano; e a página `/provedores` em Reflex consumindo esses dados.

### Modified Capabilities

<!-- Nenhum requisito das capabilities `autenticacao`, `interface-frontend` ou `projetos` é alterado. Esta change preserva a autenticação e substitui o conteúdo mock da página `/provedores` por dados reais, sem mudar contratos existentes. -->

## Impact

- **Backend Xano (novo — escopo desta change)**:
  - `xano/table/provedores.xs` — tabela de provedores.
  - `xano/api/app/listar_provedores_GET.xs`, `detalhe_provedor_GET.xs`, `criar_provedor_POST.xs`, `editar_provedor_PATCH.xs`, `desativar_provedor_POST.xs`, `testar_conexao_provedor_POST.xs` — rotas no api_group `app` já existente.
  - Variáveis de ambiente do Xano para a chave/IV de cifra do segredo (não versionadas).
- **Frontend Reflex (escopo desta change)**:
  - `projetoImpacta/pages/provedores.py` — passa a consumir o Xano, com controles de escrita e teste de conexão condicionados a `AuthState.is_admin`.
  - Novo estado dedicado da página (ex.: `projetoImpacta/pages/provedores_state.py`) seguindo o padrão de `ProjetosState`/`AuthState` (envio de token, reação a 401).
  - `projetoImpacta/projetoImpacta.py` — `on_load` da rota `/provedores` passa a carregar a lista real (como já ocorre em `/projetos`).
- **Preservado sem alteração**: `projetoImpacta/state.py` (`AuthState`), autenticação, `config.py` (reusa `XANO_APP_BASE_URL`), tabelas/endpoints de `usuarios` e `projetos`.

### Fora do escopo

- Importação de recursos AWS; importação de custos; Cost Explorer completo.
- Classificação por tags `PRJ_`/`EQP_`; criação automática de equipes; consolidação de custos.
- Alertas; dashboard real de custos.
- Suporte a Azure, GCP ou Oracle (apenas AWS nesta fase).
- Exclusão física de provedor (apenas desativação via `status`).
- Qualquer alteração na autenticação, em `projetos` ou em `usuarios`.
