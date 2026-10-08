## Why

O CostGuard precisa de uma base de autenticação funcional antes que qualquer funcionalidade sensível (projetos, orçamento, provedores, custos) possa ser desenvolvida com segurança, pois a autorização real depende da identificação confiável do usuário no backend.

O workspace Xano atual não possui dados a preservar e será completamente limpo. O backend de autenticação criado antes da adoção do OpenSpec **não** será reaproveitado. Esta change estabelece a **primeira baseline limpa** do backend Xano — somente a infraestrutura mínima necessária para a autenticação base — e implementa a fatia mínima de frontend Reflex para o fluxo de login funcionar ponta a ponta. O objetivo é fixar o comportamento consolidado de autenticação e o ritmo de desenvolvimento OpenSpec a partir de um backend criado do zero, sem expandir o escopo do sistema.

## What Changes

- **Baseline mínima do backend Xano criada do zero** com a nomenclatura padronizada `username`, `password` e `role` desde a origem (sem renomeação de legado). A baseline contém exatamente: a tabela `usuarios`, o api_group `auth`, e os endpoints `login` e `me`.
- **Tabela `usuarios`** nasce com os campos `username`, `senha_hash` (tipo `password`), `role`, `status`, `nome` e `email`, com `auth = true`.
- **`POST /login`** valida credenciais `{ "username", "password" }` exclusivamente no backend e emite um token de autenticação no sucesso.
- **`GET /me`** identifica o usuário autenticado a partir do token e retorna no mínimo `{ "username", "role" }`.
- **Novo (frontend Reflex)**: página mínima de login (`/login`) que envia credenciais ao backend.
- **Novo (frontend Reflex)**: estado de sessão autenticada, armazenando e reutilizando o token nas requisições autenticadas.
- **Novo (frontend Reflex)**: obtenção do usuário autenticado via `/me` e disponibilização de `username` e `role` no estado.
- **Novo (frontend Reflex)**: tratamento de token ausente ou inválido, incluindo reação consistente a HTTP 401.
- **Novo (frontend Reflex)**: logout local da aplicação (descarte da sessão no cliente).
- **Novo (frontend Reflex)**: proteção mínima da área autenticada (`/`), com redirecionamento de usuário não autenticado para `/login`.

O frontend não é tratado como mecanismo de segurança. A validação de `password` e a autorização real permanecem no Xano.

## Capabilities

### New Capabilities

- `autenticacao`: Comportamento de autenticação do CostGuard ponta a ponta — login por username/password validado no backend Xano, emissão e validação de token, identificação do usuário autenticado (`/me`) com `username` e `role`, tratamento de token ausente/inválido e de HTTP 401, sessão autenticada no frontend Reflex, logout local, e proteção mínima com redirecionamento das páginas que exigem autenticação.

### Modified Capabilities

<!-- Nenhuma capability existente é modificada. openspec/specs/ está vazio; esta é a primeira change do projeto. -->

## Impact

- **Backend Xano — baseline limpa (único escopo backend desta change)**. O workspace será limpo; apenas estes artefatos são criados:
  - `xano/table/usuarios.xs` — tabela de usuários com `auth = true` e os campos `username` (único), `senha_hash` (tipo `password`), `role`, `status`, `nome`, `email`.
  - `xano/api/auth/auth.xs` — definição do api_group `auth`.
  - `xano/api/auth/login_POST.xs` — login e emissão de token (contrato `{username, password}`).
  - `xano/api/auth/me_GET.xs` — identificação do usuário autenticado (`{username, role}`).
- **Frontend Reflex (novo, escopo desta change)**:
  - `projetoImpacta/projetoImpacta.py` e módulos Reflex necessários (State de autenticação, página `/login`, área autenticada `/`, proteção de rotas). Estrutura e mecanismo de sessão definidos no `design.md`.
- **Configuração**: base URL do backend Xano no frontend, lida de ambiente, sem versionar segredos. Nenhuma credencial de teste é adicionada a arquivos versionados.
- **Bootstrap**: não há mecanismo automático de bootstrap. O primeiro usuário admin é cadastrado manualmente no painel Xano, apenas para desenvolvimento/testes, após a baseline existir — é procedimento de ambiente, não funcionalidade do produto.

### Fora do escopo desta change

- **Gestão de usuários (feature futura)**: `criar_usuario`, `editar_usuario`, `deletar_usuario`/desativação, administração de roles e política de complexidade de senha.
- **Recuperação/redefinição de senha.**
- **Domínio de custos**: projetos, orçamento, equipes, provedores, AWS/custos, recursos, importação, classificação, alertas, dashboard definitivo.
- **Artefatos descartados com a limpeza do workspace**: funções Quick Start, addons legados e artefatos de exemplo/IA.
