## Contexto

Motivação e escopo: ver `proposal.md`. Requisitos: ver `specs/consumo-projetos/spec.md` e `specs/frontend-consumo-projetos/spec.md`.

Estado atual relevante:

- `GET /projetos` (`xano/api/app/listar_projetos_GET.xs`) devolve apenas as linhas de `projetos`, ordenadas por `criado_em desc`. É usado pela listagem, pela recarga após criar, editar e desativar, e não tem custo.
- `GET /projetos/{id}/custos-equipe` (`xano/api/app/listar_custos_equipe_projeto_GET.xs`) soma `custos_equipe` de um projeto em um intervalo e é a fonte do "Custo classificado (MTD)" da tela de detalhamento. Com moedas diferentes no intervalo, responde `inputerror`.
- A tela de detalhamento calcula a janela MTD no frontend (`janela_mtd` em `projeto_detalhe_state.py`, fuso `America/Sao_Paulo`) e formata valores com `formatar_valor`.
- `ProjetosState` (`projetoImpacta/pages/projetos_state.py`) carrega `GET /projetos` e normaliza para `Projeto` (`id`, `nome`, `codigo`, `budget`, `status`), usado também por `abrir_editar`.
- Comparação real feita em 2026-10-26 (somente leitura, Metadata API), janela 2026-10-01 a 2026-10-27:

| Projeto | `custos_projeto` | `custos_equipe` | endpoint de detalhe | linhas (projeto / equipe) |
|---|---|---|---|---|
| 4 PAGAMENTOS | 873,63815 | 873,63814 | 873,6381400000001 | 95 / 76 |
| 10 INFRAESTRUTURA | 739,54037 | 739,54037 | 739,5403699999999 | 95 / 38 |

Mesmas datas nas duas tabelas (2026-10-01 a 2026-10-19), somente `USD`, nenhuma duplicidade nas chaves lógicas. Diferenças diárias entre as tabelas de no máximo 0,00002, com sinais alternados, compatíveis com arredondamento.

## Objetivos / Não objetivos

**Objetivos:**

- Uma única chamada para montar os cards, com toda a regra de negócio (janela, soma, estados, percentual e faixa) no backend.
- Valor do card idêntico ao do detalhamento para a mesma janela.
- Nenhuma alteração em endpoints, tabelas ou telas existentes além de `/projetos`.

**Não objetivos:**

- Refatorar `GET /projetos/{id}/custos-equipe` para compartilhar a agregação com o novo endpoint.
- Corrigir `custos_projeto`.
- Mostrar o período MTD no cabeçalho da listagem.

## Decisões

### D1. Endpoint novo, e não extensão de `GET /projetos`

`GET /projetos/resumo-consumo-mtd` é um endpoint novo, completo para os cards.

- **Por quê:** `GET /projetos` é usado pela recarga do CRUD e pela spec `projetos`. Acrescentar uma agregação mensal a ele aumenta o custo de toda leitura de projetos e amplia o raio de regressão. O endpoint novo pode ser publicado, testado e abandonado sem afetar nada existente.
- **Alternativa descartada:** estender `GET /projetos` com campos de consumo. Menos uma rota, mas mudança de contrato em endpoint compartilhado.
- **Alternativa descartada:** o frontend chamar `custos-equipe` por projeto. Gera N+1 chamadas e coloca regra de negócio no frontend.

### D2. Fonte: `custos_equipe`

- **Por quê:** é a mesma fonte do detalhamento (requisito de consistência card × detalhe), é reconciliada por janela via `sync_id` e já inclui "Sem responsável". A comparação real confirmou equivalência com o endpoint de detalhe.
- **Alternativa descartada:** `custos_projeto`. Valores atuais equivalentes, mas sem reconciliação e com sobrescrita de duplicatas no classificador; não é a fonte do detalhe.

### D3. Janela MTD calculada no backend

O endpoint calcula `data_inicio` (primeiro dia do mês) e `data_fim` (amanhã, exclusivo) em `America/Sao_Paulo`, com o padrão já usado nos endpoints existentes (`now` em milissegundos, formatado com `format_timestamp`), mas com o fuso `America/Sao_Paulo` em vez de `UTC`. O suporte a esse fuso no `format_timestamp` deve ser confirmado no Xano Developer MCP antes da implementação (tarefa 1.2).

- **Por quê:** regra de negócio no backend; o frontend não precisa enviar datas e a chamada continua única.
- **Alternativa descartada:** o frontend enviar `data_inicio`/`data_fim` como no detalhamento. Funciona, mas deixa a definição da janela no cliente.
- **Se o fuso não for suportado:** interromper e decidir com o usuário (ex.: deslocamento fixo de −3h, válido porque o Brasil não tem horário de verão desde 2019). Não aplicar sem aprovação.

### D4. Agregação em memória com duas consultas

O endpoint faz uma consulta a `projetos` (ordenada por `criado_em desc`) e uma consulta a `custos_equipe` filtrada pela janela, para todos os projetos. A agregação por projeto (soma bruta, conjunto de moedas, maior data) é feita em memória, com mapas de chave `"k" ~ sha256(id)`, o mesmo padrão de `listar_custos_equipe_projeto_GET.xs`.

- **Por quê:** número fixo de consultas, independente da quantidade de projetos. O volume atual é pequeno (114 linhas de `custos_equipe` na janela de outubro, todos os projetos).
- **Alternativa descartada:** uma consulta a `custos_equipe` por projeto. N+1 no backend.

### D5. `custo_status` com `moedas_mistas`

O enum de `custo_status` é `ok`, `sem_registros`, `moeda_incompativel` e `moedas_mistas`.

- **Por quê:** o endpoint de detalhe trata moedas misturadas como erro do intervalo. Na listagem, um erro desse tipo não pode derrubar a resposta de todos os projetos, então o caso vira um estado por projeto. Separar de `moeda_incompativel` evita ambiguidade: com uma única moeda não-USD há valor para exibir; com moedas misturadas não há.

### D6. Arredondamento e faixa

A soma e o percentual são mantidos brutos durante o cálculo. A faixa é decidida sobre o percentual bruto. Só no momento de montar a resposta `custo_mtd` é arredondado para 2 casas e `percentual_usado` para 1 casa. O filtro de arredondamento do XanoScript deve ser confirmado na tarefa 1.2.

- **Por quê:** evita, por exemplo, 69,96% exibido como 70,0% ser classificado como atenção, e elimina ruído de ponto flutuante (873,6381400000001).

### D7. Frontend: chamada única com fallback

`ProjetosState.carregar` passa a chamar `GET /projetos/resumo-consumo-mtd`. Se essa chamada falhar (rede ou status diferente de 200 e 401), o estado faz uma segunda chamada a `GET /projetos` e marca todos os cards como "Consumo indisponível", com mensagem no topo. Não há junção entre as duas respostas: no modo normal só existe a primeira; no modo de falha só a segunda.

- **Por quê:** mantém a listagem e o CRUD funcionando quando só o consumo falha, sem exibir zero no lugar do consumo e sem join no frontend.
- **Alternativa descartada:** sem fallback (página inteira em erro). Pior para quem só precisa editar um projeto.

### D8. Apresentação pré-calculada no estado

O estado converte cada item da resposta em campos de exibição (texto do custo, texto da última data, texto do percentual, valor da barra limitado a 0–100, cor e rótulo da faixa, mensagem de estado), como a tela de detalhamento já faz. O componente só renderiza. A formatação de valores reutiliza `formatar_valor` de `projeto_detalhe_state.py`, para o card e o detalhe exibirem o mesmo texto.

O item continua contendo `id`, `nome`, `codigo`, `budget` e `status`, porque `abrir_editar` e `desativar` dependem desses campos.

- **Fronteira de regra:** o frontend não decide faixa nem percentual; apenas limita a largura da barra e escolhe textos e cores a partir dos valores recebidos.

### D9. Cores e componente da barra

A barra segue o card da referência (`rx.progress` com `color_scheme`), com o mapa `normal → green`, `atencao → yellow`, `critico → orange`, `estourado → red`. O rótulo textual da faixa acompanha o percentual. A posição e o tamanho exatos do rótulo ficam para a revisão visual manual.

## Riscos / Trade-offs

- [Fuso `America/Sao_Paulo` não suportado no `format_timestamp`] → confirmar na tarefa 1.2; se não suportado, interromper e decidir com o usuário (D3).
- [A rota `projetos/resumo-consumo-mtd` ser capturada por `projetos/{id}` no roteamento do Xano] → confirmar na tarefa 1.2 antes de criar o endpoint; se houver conflito, interromper e decidir com o usuário o caminho da rota, sem alterar `projetos/{id}`.
- [Lógica de soma duplicada entre o novo endpoint e `custos-equipe`] → tarefa de equivalência que compara, para todos os projetos, o custo bruto do resumo com o `total_projeto` do detalhe na mesma janela.
- [Card e detalhe com janelas diferentes perto da meia-noite, porque um usa o relógio do backend e o outro o do frontend] → ambos usam `America/Sao_Paulo`; a diferença só ocorre em chamadas separadas pela virada do dia. Aceito.
- [Dados com defasagem, ex.: último custo em 2026-10-19 em 2026-10-26] → o card mostra "Último custo classificado" e não afirma completude.
- [Crescimento de `custos_equipe`] → uma consulta filtrada por data usa o índice `(provedor_id, data)`; o volume de um mês é pequeno hoje. Reavaliar se crescer.
- [Fallback esconde problema do endpoint] → a mensagem "Não foi possível carregar o consumo dos projetos." é sempre exibida no modo de falha.
- [AuthState trata HTTP 429 como sessão expirada] → follow-up conhecido, fora desta change; a listagem só trata 401 explicitamente.

## Plano de implantação

1. Criar o endpoint em `xano/api/app/`, validar a sintaxe (parser do language server e dry-run do Xano CLI) e publicar no workspace.
2. Validar o endpoint por HTTP (somente leitura) antes de alterar o frontend.
3. Alterar o frontend.
4. Rollback: o frontend volta a usar `GET /projetos` (revertendo os arquivos da listagem); o endpoint novo pode permanecer publicado sem uso, pois não grava nada.
