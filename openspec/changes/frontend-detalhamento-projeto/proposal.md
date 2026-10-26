## Por quê

A página `/projetos` lista os projetos com o orçamento, mas não mostra de onde vem o gasto do mês. O frontend de referência (`C:\frontend-costguard`, branch `development-fernando-alertas`) já tem a tela de detalhamento em `/projetos/[projeto_id]`, desenhada com custo por equipe, orçamento e inventário de recursos. Hoje essa tela depende de `GET /projetos/{id}/detalhe`, que não existe no backend, então suas seções aparecem vazias.

Esta change porta a tela de detalhamento para `C:\projetoImpacta` e a liga aos endpoints reais já existentes: `GET /projetos/{id}`, `GET /projetos/{id}/custos-equipe`, `GET /projetos/{id}/recursos` e `GET /projetos/{id}/equipes`. O objetivo não é desenhar uma tela nova. É preservar o design da referência e substituir apenas o que não tem dado real.

## O que muda

- Nova rota `/projetos/[projeto_id]` no projeto principal, com a mesma navegação da referência: clique no card de `/projetos` (ação "Ver detalhamento") abre o detalhamento.
- Cabeçalho com breadcrumb (Projetos → nome do projeto), nome, subtítulo e botão "Exportar Dados".
- Duas métricas, calculadas sobre o **mês corrente até a data atual (MTD)**, sem seletor de intervalo:
  - Custo atual (MTD), a partir de `custos-equipe`.
  - Orçamento restante, com percentual utilizado do orçamento mensal do projeto.
- Bloco "Custo por equipe", com as equipes que têm custo no mês (dados de `custos-equipe`).
- Bloco "Recursos detalhados por equipe", agrupado por equipe, expansível, com recursos reais do inventário (`recursos` + `equipes`). Sem colunas de valor ou tendência por recurso.
- Aviso "Recursos sem responsável" quando houver recursos ativos sem equipe, com o botão "Notificar DevOps" **visível e desabilitado**.
- Exportação CSV gerada no cliente, apenas com dados reais carregados na tela.

## Fora do escopo

- **Notificar DevOps funcional**: envio de e-mail, endpoint, destinatários e feedback de sucesso. Será uma change separada, no final. Nesta change o botão fica desabilitado, sem handler.
- **Custo por provedor**: não há backend real. O bloco é removido nesta integração.
- **Projeção final do mês** e **variação percentual / tendência**: não há cálculo correto com os endpoints atuais. Não são exibidos.
- **Terceiro KPI**: não é criado para preencher a grade.
- **Seletor de intervalo de datas**: a tela trabalha só com o mês corrente.
- **Comparação de orçamento com intervalo arbitrário**.
- **Custo por recurso**: `GET /projetos/{id}/recursos` não traz valor. A tela não mostra custo por recurso.
- **Qualquer backend novo, endpoint novo ou alteração em XanoScript**.
- **Botão "Sincronizar" ou "Classificar custos" pela UI**.
- **Alertas, regras de alerta e o follow-up de login inativo (HTTP 200 em vez de 401)**.
- **Alterações em `C:\frontend-costguard`**: é somente referência visual.

## Impacto

- **Frontend (Reflex, `projetoImpacta/`)**: novo módulo de página e de estado para o detalhamento, nova rota em `projetoImpacta.py`, ajuste no card de `pages/projetos.py` para navegar ao detalhamento sem disparar as ações de editar e desativar.
- **Backend (Xano)**: nenhum. Só leitura, sem escrita.
- **Dependências**: nenhuma nova. Usa `httpx`, `config.get_xano_app_base_url()` e `AuthState`, como no padrão atual.
- **Specs**: nova capability `frontend-detalhamento-projeto`. Não altera as capabilities consolidadas (`projetos`, `equipes`, `inventario-recursos`, `custos-equipe`).
