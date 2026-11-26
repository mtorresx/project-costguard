## Por quê

O escopo inicial do CostGuard (`docs/project-overview.md`, seção 5) inclui o gerenciamento de usuários pelo administrador: não existe autocadastro, usuários são criados por um admin, desativados em vez de excluídos, e o sistema deve preservar pelo menos um administrador ativo. Hoje a página `/usuarios` exibe dados fictícios ("Demonstração — sem backend") e o Xano não tem nenhum endpoint de usuários.

Além disso, o levantamento encontrou duas falhas relacionadas ao ciclo de vida do usuário:

- `GET /me` responde HTTP 200 com `{erro: ...}` quando o usuário do token não existe, contrariando o requisito "Consulta sem token válido" (HTTP 401).
- Um usuário desativado continua com acesso até o token expirar (8 h): `GET /me` não confere `status`, e os endpoints de escrita conferem apenas `role`. Com a desativação passando a existir pela interface, isso passa a ser uma brecha real.

## O que muda

- **Backend (Xano), api_group `app`:**
  - `GET /usuarios` — lista de usuários (admin).
  - `POST /usuarios` — cria usuário com nome, username, e-mail, papel e **senha inicial definida pelo admin** (decisão do usuário em 2026-10-27; recuperação de senha por e-mail foi adiada).
  - `PATCH /usuarios/{id}` — edita nome, e-mail e papel.
  - `POST /usuarios/{id}/desativar` e `POST /usuarios/{id}/reativar` — desativação lógica e reativação.
  - `POST /usuarios/{id}/senha` — admin define nova senha para um usuário (substitui a representação anterior).
  - Regra de pelo menos um admin ativo aplicada no backend em rebaixamento e desativação; admin não pode desativar a si mesmo.
- **Backend, autenticação:** `GET /me` responde HTTP 401 quando o usuário do token não existe ou está inativo. Os endpoints de escrita existentes passam a exigir `status = ativo` além de `role = admin`.
- **Frontend (Reflex), `/usuarios`:** página com dados reais, adaptando o design da referência (frontend de referência, pages/usuarios.py): KPIs, busca, tabela com papel e status, formulário de criação, edição, definição de senha e desativação/reativação. Página restrita a admin; usuário leitura vê aviso de acesso restrito.

## Capabilities

### New Capabilities

- `usuarios`: gestão de usuários pelo administrador (backend e página `/usuarios`).

### Modified Capabilities

- `autenticacao`: "Identificação do usuário autenticado" passa a negar usuário inativo ou inexistente com HTTP 401; novo requisito de revogação de acesso de usuário desativado nas operações de escrita.

## Impacto

- **Xano:** tabela técnica `travas` (exclusão mútua da regra de pelo menos um admin ativo; necessidade comprovada no design D4); 6 endpoints novos em `xano/api/app/`; `xano/api/auth/me_GET.xs`; precondição de status adicionada aos endpoints de escrita existentes (`criar/editar/desativar projeto`, `criar/editar/desativar/testar provedor`, `descobrir/importar projetos`, `coletar/classificar custos`, `classificar custos equipe`, `sincronizar recursos`). Nenhuma tabela existente alterada.
- **Reflex:** `projetoImpacta/pages/usuarios.py` (reescrita) e novo `projetoImpacta/pages/usuarios_state.py`; registro de `on_load` em `projetoImpacta.py`.
- **Dependências:** nenhuma nova.

## Fora do escopo

- Recuperação e redefinição de senha por e-mail (adiada por decisão do usuário: sem provedor de e-mail configurado).
- Troca de senha pelo próprio usuário.
- Foto de perfil, papéis além de `admin`/`leitura`, exclusão física.
- Revogação imediata de tokens já emitidos nos endpoints somente leitura (ver design, risco R2).
