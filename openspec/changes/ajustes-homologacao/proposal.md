## Por quê

Ajustes pedidos na homologação funcional (`AJUSTAR`, 2026-11-03):

- Com a virada do mês, o Início, os cards de Projetos e o detalhe do projeto passaram a mostrar o mês corrente (novembro), que ainda não tem custos importados; os dados de outubro existem, mas não podem ser vistos. O usuário percebeu as telas como "zeradas". Decisão do usuário: **seletor de mês**.
- Projetos devem ser ordenados pelo **maior consumo do orçamento** (decisão do usuário).
- "Exportar Dados" e "Exportar CSV" duplicados no detalhe do projeto: **remover os dois nesta V1** (decisão do usuário).
- A mensagem "Usuário criado." permanece na tela: deve **desaparecer sozinha**.
- Lentidão ao trazer as informações: **otimizar ao máximo** (pedido do usuário, 2026-11-03). Medição: cada chamada ao Xano leva 0,2–0,7 s; a lentidão vinha do limite do plano Free (10 requisições/20 s), que fazia requisições esperarem até 17,5 s, de chamadas em sequência e de conexões novas a cada chamada.
- Bug encontrado ao investigar a tela de Alertas vazia: o Xano grava chave estrangeira nula como `0`, e os filtros `projeto_id == null` de `GET /recursos-nao-classificados` e `POST /alertas/avaliar` nunca encontravam recursos não classificados (havia 4). Corrigido nesta rodada nos objetos da change `alertas-sincronizacao` (filtro aceita `null` ou `0`) e registrado lá.

## O que muda

- **Backend:** `GET /projetos-resumo-consumo-mtd` aceita o parâmetro opcional `mes` (`AAAA-MM`). Sem `mes` (ou com o mês corrente), mantém a janela do mês até a data atual. Com um mês anterior, usa o mês fechado (dia 1 até o dia 1 do mês seguinte, exclusivo). Mês futuro ou formato inválido → HTTP 400. A resposta passa a informar `mes` e `mes_corrente`.
- **Frontend:** seletor de mês (mês atual e os 5 anteriores) no Início, em Projetos e no detalhe do projeto, compartilhado entre as páginas. Rótulos passam de "MTD" para "no mês" e indicam se o mês está fechado ou em andamento; mensagens de ausência de custo deixam de dizer "até a data atual" para meses fechados.
- **Projetos:** ordenação por percentual do orçamento (maior primeiro); depois por custo; depois por nome; inativos ao final.
- **Detalhe:** remoção dos botões e da geração de CSV.
- **Desempenho:** funções Xano compartilhadas (resumo, alertas, recursos não classificados, recursos e equipes do projeto) com os endpoints individuais reduzidos a chamadas a essas funções (contratos idênticos); novos `GET /painel` e `GET /projetos/{id}/painel`; no frontend, leituras em paralelo, reaproveitamento de leituras por 60 s com descarte em qualquer escrita, controle de vazão no próprio app, conexões reaproveitadas e listas mantidas na tela durante a atualização.
- **Usuários e Alertas:** mensagens de sucesso como notificação temporária (`rx.toast`), que desaparece sozinha.

## Capabilities

### Modified Capabilities

- `consumo-projetos`: janela do resumo com mês selecionável.
- `frontend-consumo-projetos`: seletor de mês e ordenação dos cards.
- `frontend-detalhamento-projeto`: janela do mês selecionável; exportação CSV removida.
- Nova capability `painel-agregado`: painéis de leitura e regras de leitura do frontend dentro do limite do plano.
- `dashboard`: indicadores do mês selecionado.

## Impacto

- **Xano:** `xano/api/app/projetos_resumo_consumo_mtd_GET.xs`; novas funções em `xano/function/costguard/`; `listar_alertas_GET.xs`, `listar_recursos_nao_classificados_GET.xs`, `listar_recursos_projeto_GET.xs` e `listar_equipes_projeto_GET.xs` passam a chamar as funções; novos `painel_GET.xs` e `painel_projeto_GET.xs`.
- **Reflex:** novo `components/periodo_state.py`; `pages/home.py`, `pages/home_state.py`, `pages/projetos.py`, `pages/projetos_state.py`, `pages/projeto_detalhe.py`, `pages/projeto_detalhe_state.py`, `pages/usuarios.py`, `pages/usuarios_state.py`, `pages/alertas.py`, `pages/alertas_state.py`, `api.py`, `components/layout.py` (singular do indicador), `pages/provedores.py`.

## Dependência

A capability `dashboard` é criada pela change `dashboard-shell`, ainda não arquivada. Esta change deve ser arquivada depois dela.

## Fora do escopo

- Alertas de orçamento de meses passados (o orçamento e os alertas continuam sendo do mês corrente, conforme o domínio).
- Intervalos personalizados de datas.
