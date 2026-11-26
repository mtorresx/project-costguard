## Por quê

O escopo inicial do CostGuard inclui importação de recursos e custos, identificação de recursos sem classificação e geração de alertas (`docs/project-overview.md`, seções 5 e 6; `docs/domain-model.md`, seção 11). Hoje:

- os endpoints de importação existem no Xano (`sincronizar-recursos`, `classificar-custos-equipe`), mas nenhuma tela permite executá-los: a importação só acontece por chamada direta à API;
- a página `/alertas` mostra dados fictícios ("Demonstração — sem backend") e não existe tabela nem regra de alertas no backend;
- recursos "Não classificados" (sem projeto válido) ficam gravados no inventário, mas não aparecem em nenhuma tela;
- falhas de sincronização do inventário só aparecem na resposta da chamada e não ficam registradas.

## O que muda

- **Sincronização pela interface (decisão do usuário em 2026-10-27: botão manual, sem agendamento):** em `/provedores`, o admin aciona "Sincronizar agora" em um provedor conectado. O frontend executa em sequência: inventário de recursos → custos por equipe → avaliação de alertas, mostrando o resultado de cada etapa.
- **Registro das execuções de inventário:** nova tabela `coletas_inventario`; `POST /provedores/{id}/sincronizar-recursos` passa a gravar uma linha ao final de cada execução (sucesso ou erro), sem outra mudança de comportamento.
- **Alertas (backend):** nova tabela `alertas` e endpoints:
  - `POST /alertas/avaliar` (admin): avalia as condições atuais e cria, atualiza ou resolve automaticamente os alertas; aceita `simular = true` para devolver as ações sem gravar;
  - `GET /alertas` (autenticado): lista os alertas;
  - `POST /alertas/{id}/resolver` (admin): resolução manual.
- **Tipos de alerta** (domínio): orçamento (70% atenção, 90% aviso, 100% excedido, sobre `custos_equipe` do mês corrente em USD), recursos não classificados (por provedor) e falha de importação (inventário, custos por equipe ou conexão do provedor).
- **Recursos não classificados:** novo endpoint `GET /recursos-nao-classificados` (autenticado).
- **Frontend `/alertas`:** dados reais, design adaptado da referência (KPIs, lista com nível e tempo relativo, filtro abertos/resolvidos, resolução para admin) e seção de recursos não classificados.

## Capabilities

### New Capabilities

- `alertas`: tabela, avaliação, deduplicação, resolução e leitura de alertas; página `/alertas`.
- `sincronizacao-provedor`: ação de sincronização manual por provedor na interface.

### Modified Capabilities

- `inventario-recursos`: a sincronização passa a registrar cada execução em `coletas_inventario`; novo requisito de leitura dos recursos não classificados.

## Impacto

- **Xano:** tabelas novas `alertas` e `coletas_inventario`; endpoints novos `alertas/avaliar`, `alertas` (GET), `alertas/{id}/resolver`, `recursos-nao-classificados`; `sincronizar_recursos_provedor_POST.xs` ganha um `db.add` ao final.
- **Reflex:** `pages/alertas.py` (reescrita), novo `pages/alertas_state.py`, `pages/provedores.py` e novo `pages/sincronizacao_state.py`; `on_load` em `projetoImpacta.py`.
- **Dependências:** nenhuma nova.

## Fora do escopo

- Agendamento automático da importação (pendência registrada; exige refatorar a lógica dos endpoints em funções).
- Execução de `coletar-custos` e `classificar-custos` (por projeto) pela interface: o consumo exibido vem de `custos_equipe`.
- Regras de alerta configuráveis, webhook, e-mail e notificações externas (presentes no frontend de referência, mas fora da documentação do projeto).
- Alerta por recurso individual (o alerta é agregado por provedor; a lista detalhada fica na página).
