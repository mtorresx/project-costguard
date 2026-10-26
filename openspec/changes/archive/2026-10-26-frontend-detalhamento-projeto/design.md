## Contexto

A referência visual está em `C:\frontend-costguard\costguard\pages\projetos.py`: a função `projeto_detalhe_page()` (linha 935), o estado `ProjetosState` (linha 145) e os componentes auxiliares `_barra_equipe`, `_grupo_recursos`, `_kpi_card_detalhe`, `_breadcrumb_detalhe` e `_vazio`. A rota é registrada em `C:\frontend-costguard\costguard\costguard.py` (linhas 36–39) como `/projetos/[projeto_id]`.

Fatos confirmados no código:

- A referência consome `GET /projetos/{id}/detalhe`, que não existe no Xano (404). Por isso as seções aparecem vazias. Não há dados de exemplo no código atual. Os documentos `openspec/changes/detalhamento-projeto/design.md` e `proposal.md` da referência ainda descrevem dados de exemplo; essa é uma divergência documental registrada, e o código é a fonte para o comportamento atual da referência.
- No projeto principal, `GET /projetos/{id}` retorna só o projeto (`xano/api/app/detalhe_projeto_GET.xs`), sem custo.
- `GET /projetos/{id}/custos-equipe` agrega por janela de datas, todos os provedores, e retorna `moeda`, `equipes` (somente com custo), `sem_responsavel.total` e `total_projeto` (`xano/api/app/listar_custos_equipe_projeto_GET.xs`). Moedas diferentes geram `inputerror`. Intervalo sem registros retorna `moeda = null`.
- `GET /projetos/{id}/recursos` retorna metadados sem custo: `id`, `provedor_id`, `arn`, `regiao`, `servico`, `projeto_id`, `equipe_id`, `codigo_projeto_tag`, `codigo_equipe_tag`, `sem_responsavel`, `ativo`. **Não filtra `ativo`**, então a tela precisa filtrar. O `codigo_equipe_tag` é o valor cru da tag (spec `inventario-recursos`), não o código normalizado.
- `GET /projetos/{id}/equipes` retorna `id`, `nome`, `codigo`, `projeto_id`, `auto_gerada`, para todas as equipes do projeto.
- O projeto principal usa `reflex==0.9.12`. Na 0.9.12, `rx.redirect(path, *, is_external=False, popup=False, replace=False)` deve ser retornado pelo handler. `rx.download(url=None, filename=None, data=None, mime_type=None)` aceita `data` como `str`. Parâmetros de rota dinâmica viram variáveis do State (`DynamicRouteVar`), do tipo `str` quando não há lista.

## Decisões

### D1 — Rota, página e estado

- Rota `/projetos/[projeto_id]`, registrada em `projetoImpacta/projetoImpacta.py` com `add_page(..., on_load=[AuthState.require_auth, ProjetoDetalheState.carregar])`, o mesmo padrão já usado para `/projetos`.
- Página em `projetoImpacta/pages/projeto_detalhe.py` (`projeto_detalhe_page()`), e estado em `projetoImpacta/pages/projeto_detalhe_state.py` (`ProjetoDetalheState`).
- O estado é separado de `ProjetosState`, que continua responsável apenas pela lista e pelo formulário.
- O parâmetro da rota é lido como `self.projeto_id` (`str`). Se não for inteiro positivo, a página mostra "Projeto não encontrado" sem chamar o backend. A confirmação da API de rota dinâmica com a documentação será feita antes do Apply (ver tarefas).

### D2 — Navegação a partir de `/projetos`

- O card de `projetos.py` mantém o clique que abre o detalhamento (`rx.redirect(f"/projetos/{id}")`), como na referência, e o texto "Ver detalhamento".
- Os botões Editar e Desativar, visíveis só para admin, ficam dentro do card. Sem tratamento, o clique neles também dispararia a navegação. Eles devem interromper a propagação do evento com `.stop_propagation` no handler (`ProjetosState.abrir_editar(projeto).stop_propagation`). Confirmado na fonte instalada do Reflex 0.9.12 (ver seção "Confirmações Reflex"). Só o clique nos botões é interrompido; o restante do card continua navegando.

### D3 — Carregamento e erros

Ordem de carregamento em `carregar`:

1. Se o `projeto_id` não for inteiro positivo, marca `nao_encontrado` e encerra.
2. `GET /projetos/{id}`. HTTP 401 → `AuthState.handle_unauthenticated`. HTTP 404 → `nao_encontrado`. Falha de rede ou outro erro → mensagem genérica. Sucesso → guarda `nome`, `codigo`, `budget`.
3. Em paralelo lógico (sequencial no código, com `yield` entre as etapas), `GET /projetos/{id}/custos-equipe` com a janela MTD (D4). HTTP 401 → login. HTTP 400 `inputerror` → mensagem do backend, se houver `message`; senão, mensagem genérica. Falha de rede → mensagem genérica.
4. `GET /projetos/{id}/recursos` e `GET /projetos/{id}/equipes`. Falha em qualquer um mostra mensagem própria no bloco de recursos. Falhas de custos e de recursos são independentes: uma não esconde a outra.

Nenhuma mensagem exibe corpo técnico cru, status HTTP ou `RequestId`.

### D4 — Janela MTD (fuso `America/Sao_Paulo`)

- `hoje` é a data atual no fuso `America/Sao_Paulo`. A interface usa esse fuso para determinar o mês; **a semântica do backend não muda** (o endpoint continua recebendo `data_inicio` inclusiva e `data_fim` exclusiva, em `YYYY-MM-DD`).
- `data_inicio = primeiro dia do mês de hoje (America/Sao_Paulo)`.
- `data_fim = hoje + 1 dia`, porque o endpoint trata `data_fim` como exclusivo e o dia de hoje precisa entrar no total.
- A janela é mostrada na tela como texto ("Período: 01/10/2026 a 26/10/2026"), com a data final de exibição sendo `hoje`.
- Não há seletor de intervalo.
- **Dependência**: o fuso é obtido com `zoneinfo.ZoneInfo("America/Sao_Paulo")`. No Windows, a biblioteca padrão não traz o banco de fusos, então `tzdata` é adicionado a `requirements.txt`. Essa inclusão é aprovação pendente (ver proposal). Não se usa deslocamento fixo de UTC-3, porque isso seria uma regra própria no lugar do fuso oficial.

### D5 — Moeda e orçamento

- `moeda = null` (sem registros no mês): os KPIs de custo e de orçamento **não mostram valores calculados**. A tela mostra "Sem custos classificados no mês até a data atual." Zero não é usado como substituto de custo desconhecido, e não se calcula orçamento restante com base em zero.
- `moeda` diferente de `USD`: o custo é mostrado com a moeda retornada, mas o orçamento restante e o percentual **não são calculados**, porque o orçamento do projeto é em USD e não há conversão. A tela mostra a mesma mensagem de sem comparação.
- `moeda = USD` e `budget > 0`: orçamento restante = `budget − custo_atual`, percentual = `custo_atual / budget × 100`, com uma casa decimal. Quando o valor restante fica negativo, é mostrado com sinal, sem arredondar para zero. A barra é limitada a 100%, e o texto mostra o percentual real.
- `budget = 0`: não há percentual. O bloco mostra "Sem orçamento definido" no lugar do percentual e do restante.

### D6 — KPIs

A grade passa de 3 para 2 colunas, com o mesmo estilo visual (`_kpi_card_detalhe`):

- Card 1, "Custo classificado (MTD)": valor formatado (`US$ 1,234.56`). O rótulo não afirma atualização até este instante, porque o endpoint não expõe a data da última classificação.
- Card 2, "Orçamento restante": valor restante, barra de progresso e texto "X% utilizado de US$ Y", como na referência.

Não há card de projeção, de variação nem de custo por provedor.

### D7 — Custo por equipe

- Fonte: `custos-equipe.equipes`. Lista só equipes com custo no mês, ordenada por `codigo` pelo backend.
- Cada item mostra nome (`nome` do backend), número de recursos, total e barra. Barra = fração do `total_projeto`, calculada no Python.
- Número de recursos não vem de `custos-equipe`. Vem da contagem de recursos ativos por equipe (D8). Equipe sem recurso ativo mostra o número de recursos como 0, que é contagem real, não custo.
- Sem equipes com custo: "Nenhum custo por equipe no mês até a data atual."
- Não exibe variação percentual.

### D8 — Recursos detalhados por equipe

- Fontes: `recursos` (filtrado para `ativo = true` na tela) e `equipes` (para o nome por `equipe_id`).
- Justificativa do uso de `/equipes`: `custos-equipe` só lista equipes com custo, e `codigo_equipe_tag` é o valor cru da tag. Usar `equipe_id` com o nome de `/equipes` é a única forma de nomear de forma correta todas as equipes com recurso, inclusive as sem custo no mês. Este é o uso previsto em "necessidade real" do pedido.
- Grupos (regra aprovada após o E2E):
  - `equipe_id > 0`: grupo da equipe real, com nome de `/equipes`.
  - `equipe_id` ausente ou 0 e `codigo_equipe_tag` vazio: grupo "Sem responsável".
  - `equipe_id` ausente ou 0 e `codigo_equipe_tag` preenchido: grupo "Equipe não vinculada — <TAG>", um por tag. Não se mistura tag diferente, não se cria equipe no frontend e a inconsistência não é escondida.
  - Ordem: equipes reais por nome, depois "Equipe não vinculada", e "Sem responsável" por último.
  - Valor 0 nunca é tratado como equipe válida.
- Cada grupo mostra o nome da equipe e "N recursos", e é recolhível, como na referência (`_grupo_recursos`, com `equipes_recolhidas`).
- Colunas da tabela: **Recurso**, **Serviço** e **Região**. Não há coluna de valor nem de tendência.
- **Recurso**: último segmento do ARN (após o último `/` ou `:`). O ARN completo fica no `title` da célula (tooltip) e no CSV. Se o ARN não tiver separadores, mostra o ARN inteiro.
- **Serviço**: valor cru de `servico`. O ícone usa o mapeamento de `_ICONES_SERVICO` da referência, comparando sem diferenciar maiúsculas e minúsculas. Serviço não mapeado usa ícone genérico de nuvem.
- Sem recursos ativos: "Nenhum recurso registrado ainda."

### D9 — Recursos sem responsável

- **Critério de exibição**: o bloco aparece quando `GET /projetos/{id}/recursos` retorna ao menos um recurso com `ativo = true`, `equipe_id` ausente ou 0 e `codigo_equipe_tag` vazio. O custo **não** é usado como condição. Não se usa `custo > 0` para decidir se existem recursos sem responsável.
- O texto explica o risco de chargeback, como na referência.
- O custo sem responsável é informação financeira adicional, e aparece na linha "Custo acumulado sem responsável: US$ X" **somente quando `moeda` não é nula**, com o valor de `sem_responsavel.total` do backend, sem cálculo no frontend. Esse valor pode ser zero classificado; nesse caso a linha mostra `US$ 0.00`, porque é o valor confirmado pelo backend, não um substituto de dado desconhecido.
- Podem existir recursos sem responsável com custo zero, e custo sem responsável sem nenhum recurso listado de forma não associada. Não há associação de custo individual por recurso, então a tela não relaciona um valor a um recurso específico.
- O botão **"Notificar DevOps"** fica visível no mesmo local, com `disabled=True`, sem `on_click` e sem estado. Não há mensagem de sucesso.

### D10 — Exportação CSV

- "Exportar Dados" (cabeçalho) e "Exportar CSV" (bloco de recursos) geram o mesmo arquivo, a partir dos grupos carregados na tela.
- O arquivo é gerado com o módulo `csv` da biblioteca padrão (não por concatenação de texto), e retornado por `rx.download(data=..., filename=...)`.
- Colunas: `Equipe`, `Recurso`, `ARN`, `Serviço`, `Região`. Sem colunas de valor, tendência ou projeção.
- Nome do arquivo: `costguard-recursos-{codigo}.csv`, com `codigo` em minúsculas.
- Em `moeda = null` ou sem recursos, o botão continua disponível e gera o arquivo com o cabeçalho e as linhas existentes (se houver recursos). Não há dado fabricado.

### D11 — Formatação

Valores monetários são formatados em Python, dentro do estado, como strings `US$ 1,234.56`. Não se usa formatação de `Var` dentro do componente, para evitar depender do comportamento de formatação do Reflex. Isso segue a regra do projeto de mostrar duas casas e separador de milhar, sem abreviação.

### D13 — Projeto inativo

- A tela não bloqueia nem esconde o detalhamento de projeto inativo. O acesso segue a rota e a leitura permitidas pelo backend.
- O cabeçalho mostra o status do projeto com o rótulo "Inativo" quando `status = inativo`, e "Ativo" quando `status = ativo`, usando o mesmo componente de badge da listagem (`_status_badge`).

### D12 — Acesso e autorização

- A tela é acessível a admin e leitura (todas as leituras usadas são de usuário autenticado). A ocultação de ações é apenas visual. Como o botão Notificar DevOps está desabilitado, não há ação para ocultar.
- A autorização real permanece no backend. O frontend não decide acesso aos dados.
- Nenhum token ou segredo é registrado em log ou exibido.

## Riscos e pontos em aberto

- **R1 — Atualidade dos custos (aceito)**: `custos-equipe` mostra apenas dias já classificados. O rótulo "Custo classificado (MTD)" evita afirmar atualização. Aceito nesta change, sem endpoint de status.
- **R2 — Propagação do clique (resolvido)**: `.stop_propagation` confirmado na fonte instalada do Reflex 0.9.12. Validação visual no E2E (tarefa 7.1).
- **R3 — Fuso (resolvido)**: mês e data em `America/Sao_Paulo`, com dependência `tzdata` pendente de aprovação.
- **R4 — Formato de erro do Xano (aberto)**: o campo `message` do `inputerror` ainda não foi confirmado. Enquanto isso, a tela usa mensagem genérica. Nenhum tratamento específico de `inputerror` será implementado antes da confirmação do contrato.
- **R8 — Inconsistência de backend (aberta, fora desta change)**: no E2E foram confirmados recursos ativos com `equipe_id = 0` (projeto 4: 5 recursos com tag vazia; projeto 6: 31 recursos, sendo 13 BACKEND, 14 WEB, 2 MARKETING e 2 com tag vazia), todos com `sem_responsavel = true` no backend. Há tag preenchida sem vínculo interno de equipe. O frontend apresenta esse estado como "Equipe não vinculada", sem esconder, mas a causa precisa de investigação no backend (rotina de sincronização/inventário). Nenhum backend foi alterado nesta change.
- **R9 — 429 no `AuthState` (follow-up, fora desta change)**: `AuthState.require_auth` interpreta qualquer resposta de `/me` diferente de 200 como sessão expirada. HTTP 429 do Xano limpa a sessão do usuário. Deve ser tratado separadamente em change futura.
- **R5 — Nome derivado do ARN**: o nome mostrado é um recorte do ARN, não um campo oficial. O ARN completo fica disponível no tooltip e no CSV para evitar ambiguidade.
- **R6 — Divergência documental da referência**: `openspec/changes/detalhamento-projeto` da referência descreve dados de exemplo que não existem mais no código. Esta change não copia esses documentos.
- **R7 — Projeto inativo (resolvido)**: a tela abre o detalhamento e mostra o status "Inativo" (D13).

## Confirmações Reflex (pré-Apply, fonte instalada: Reflex 0.9.12)

- **Rota dinâmica**: `[projeto_id]` vira variável do State (`DynamicRouteVar`, tipo `str` para parâmetro único). O registro é feito por `setup_dynamic_args` em `reflex/state.py`. Como o `router_data` é atualizado antes da execução dos `on_load`, `self.projeto_id` está disponível em `carregar`. A confirmação de runtime será feita no E2E (tarefa 7.1).
- **`on_load`**: `add_page(..., on_load=[...])` aceita lista de eventos (`EventType[()]`), como já usado em `projetoImpacta.py`.
- **`rx.redirect(path, *, is_external=False, popup=False, replace=False)`**: deve ser retornado pelo handler. Usado no clique do card e na desautorização 401 pelo `AuthState`.
- **Propagação de clique**: `EventActionsMixin.stop_propagation` (`reflex_base/event/__init__.py`, linha 412) é uma propriedade de `EventHandler` e `EventSpec`. Uso: `on_click=ProjetosState.abrir_editar(projeto).stop_propagation`.
- **`rx.download(url=None, filename=None, data=None, mime_type=None)`**: `data` aceita `str`, e `filename` define o nome do arquivo. Retornado pelo handler, como no CSV atual da referência.

## Não-objetivos técnicos

- Nenhum cache novo, nenhum armazenamento no navegador para dados de negócio.
- Nenhuma chamada de escrita (`POST`, `PATCH`, `DELETE`) a partir desta tela.
- Nenhuma dependência nova em `requirements.txt`.
