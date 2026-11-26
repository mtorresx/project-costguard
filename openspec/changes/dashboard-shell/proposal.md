## Por quê

O escopo inicial inclui "visualização das informações em dashboard" (`docs/project-overview.md`, seção 5). A home autenticada (`/`) ainda mostra números fictícios ("US$ 24.720", "18 projetos", "2 alertas") marcados como ilustrativos, e o shell exibe itens de demonstração: o selo "Multi-Cloud (demonstração)" no topo e um modal de preferências com limite de alerta, webhook e auditoria contínua que não são persistidos nem fazem parte da documentação do projeto (as faixas de alerta são fixas pelo domínio: 70%, 90% e 100%).

Com projetos, usuários, alertas e recursos não classificados já servidos pelo backend, a home e o shell podem exibir apenas dados reais.

## O que muda

- **Home `/` como dashboard real:** indicadores de custo classificado no mês (soma dos projetos em USD), projetos ativos, alertas abertos e recursos não classificados; projetos com maior consumo do orçamento; alertas abertos mais recentes; atalhos para as páginas. Dados de `GET /projetos-resumo-consumo-mtd`, `GET /alertas` e `GET /recursos-nao-classificados` (três chamadas, por causa do limite de requisições do plano Xano). Cada bloco tem estado de erro próprio.
- **Shell:** o selo de demonstração dá lugar a um indicador de alertas abertos (atualizado quando a home ou `/alertas` carregam, sem chamada extra); o item "Alertas" do menu mostra a contagem; o modal de preferências vira "Minha conta" (usuário, papel e faixas de alerta do domínio), sem campos não persistidos; a ajuda descreve as páginas reais.
- **Limite de requisições (HTTP 429):** cliente HTTP compartilhado com nova tentativa automática, usado por todos os estados; 429 na validação de sessão não desloga mais o usuário (problema encontrado no E2E desta change).
- O requisito "Páginas de apresentação registradas" de `interface-frontend` deixa de prever páginas mock.

## Capabilities

### New Capabilities

- `dashboard`: home autenticada com indicadores reais.

### Modified Capabilities

- `interface-frontend`: páginas registradas passam a usar dados reais; shell sem itens de demonstração.

## Impacto

- **Reflex:** `pages/home.py` (reescrita), novo `pages/home_state.py`, novo `components/contador_state.py`, `components/layout.py`, `pages/alertas_state.py` (atualiza o contador), `projetoImpacta.py`, `api.py` (cliente com nova tentativa) e os helpers HTTP de `state.py`, `projetos_state.py`, `projeto_detalhe_state.py`, `provedores_state.py` e `descoberta_state.py` (somente a troca do cliente).
- **Xano:** nenhum.

## Fora do escopo

- Projeção de fim de mês, variação contra o mês anterior e custo por provedor (fora do escopo do projeto ou sem fonte confiável).
- Preferências por usuário persistidas.
- Navegação em telas pequenas (o shell atual oculta o menu abaixo de 768 px; inalterado).
