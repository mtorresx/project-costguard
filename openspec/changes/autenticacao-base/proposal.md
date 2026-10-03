## Why

O CostGuard precisa de uma base de autenticação funcional antes que qualquer funcionalidade sensível (projetos, orçamento, provedores, custos) possa ser desenvolvida com segurança, pois a autorização real depende da identificação confiável do usuário no backend.

O backend Xano já possui uma implementação parcial de autenticação criada antes da adoção do OpenSpec. Esta change formaliza o comportamento existente como especificação e implementa apenas a fatia mínima de frontend Reflex necessária para o fluxo de login funcionar ponta a ponta. O objetivo é estabelecer o comportamento consolidado de autenticação e o ritmo de desenvolvimento OpenSpec sobre código real, sem expandir o escopo do sistema.

- **Padronização de nomenclatura do contrato de autenticação** para `username`, `password` e `role`, tanto no frontend Reflex quanto na API Xano. O corpo de login passa a ser `{ "username", "password" }` e a resposta de `/me` passa a ser `{ "username", "role" }`. **BREAKING** para consumidores do contrato atual (`usuario`/`senha`).
- **Ajuste autorizado do backend Xano** para padronizar a interface: renomear os inputs de `login_POST` (`usuario`→`username`, `senha`→`password`), o campo retornado por `me_GET` (`usuario`→`username`), e **renomear o campo `usuario` da tabela `usuarios` para `username`** (decisão aprovada, parte do escopo desta change), atualizando todas as referências afetadas. O campo de senha persistido permanece o campo seguro do tipo `password` do Xano e **NÃO é renomeado nesta change**: continua como `senha_hash` (credencial protegida com hash).
- **Formalização do login por username e password** validando credenciais exclusivamente no backend.
- **Formalização da emissão de token** de autenticação pelo Xano no login bem-sucedido.
- **Formalização do endpoint `/me`** (`me_GET`) para identificar o usuário autenticado e disponibilizar seu `username` e `role`.
- **Formalização da validação de token** e do tratamento consistente de respostas HTTP 401 pelo backend.
- **Novo (frontend Reflex)**: página mínima de login (`/login`) que envia credenciais ao backend.
- **Novo (frontend Reflex)**: estado de sessão autenticada, armazenando e reutilizando o token nas requisições autenticadas.
- **Novo (frontend Reflex)**: obtenção do usuário autenticado via `/me` e disponibilização de `username` e `role` no estado.
- **Novo (frontend Reflex)**: tratamento de token ausente ou inválido, incluindo reação consistente a HTTP 401.
- **Novo (frontend Reflex)**: logout local da aplicação (descarte da sessão no cliente).
- **Novo (frontend Reflex)**: proteção mínima da área autenticada (`/`), com redirecionamento de usuário não autenticado para `/login`.

O frontend não é tratado como mecanismo de segurança. A validação de `password` e a autorização real permanecem no Xano.

## Capabilities

### New Capabilities

- `autenticacao`: Comportamento de autenticação do CostGuard ponta a ponta — login por username/senha validado no backend Xano, emissão e validação de token, identificação do usuário autenticado (`/me`) com `username` e `role`, tratamento de token ausente/inválido e de HTTP 401, sessão autenticada no frontend Reflex, logout local, e proteção mínima com redirecionamento das páginas que exigem autenticação.

### Modified Capabilities

<!-- Nenhuma capability existente é modificada. openspec/specs/ está vazio; esta é a primeira change do projeto. -->

## Impact

- **Backend Xano — renomeação aprovada do campo `usuarios.usuario` → `username` e padronização do contrato (escopo desta change)**:
  - `xano/table/usuarios.xs` — renomear o campo `usuario` para `username` e o índice `btree|unique` correspondente. Campo `senha_hash` **não** é renomeado; permanece do tipo `password` (hashing automático confirmado).
  - `xano/api/auth/login_POST.xs` — inputs `usuario`/`senha` → `username`/`password`; `db.get field_name = "usuario"` → `"username"`; emissão de token (claims que referenciam o campo acompanham o novo nome).
  - `xano/api/auth/me_GET.xs` — leitura do campo (`.usuario` → `.username`) e chave de resposta `usuario` → `username`.
  - `xano/api/auth/criar_usuario_POST.xs` — input, `db.get field_name="usuario"`, `db.add {usuario: ...}` e resposta `{usuario: ...}` passam a usar `username`.
  - `xano/api/auth/editar_usuario_PATCH.xs` — resposta expõe `.usuario` → `.username`.
- **Backend Xano — não impactados (confirmado por análise)**: `listar_projetos_GET`, `criar_projeto_POST`, `editar_projeto_PATCH`, `desativar_projeto_POST`, `deletar_usuario_DELETE` e `aws/costs_POST` usam apenas variáveis locais (`$usuario_logado`/`$usuario_alvo`) e `auth = "usuarios"` (nome da tabela), **não** o campo `usuario`. Não serão alterados nesta change.
- **Frontend Reflex (novo, escopo desta change)**:
  - `projetoImpacta/projetoImpacta.py` e módulos Reflex necessários (State de autenticação, página `/login`, área autenticada `/`, proteção de rotas). Estrutura e mecanismo de sessão definidos no `design.md`.
- **Configuração**: base URL do backend Xano no frontend, sem versionar segredos.
- **Fora do escopo**: recuperação/redefinição de senha, política de complexidade de senha, CRUD de usuários, administração de roles, dashboard definitivo, e todo o domínio de custos (projetos, orçamento, equipes, provedores, AWS, recursos, importação, classificação, alertas). Renomeações fora do necessário para a autenticação não fazem parte desta change.
