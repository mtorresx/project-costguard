## Context

Ver `proposal.md` — Why. O CostGuard já possui coleta base de custos AWS implementada em
`xano/api/app/coletar_custos_provedor_POST.xs`: autorização admin, elegibilidade do
provedor (`tipo = aws`, `status = ok`), decifra JWE (`A256KW` + `A256CBC-HS512`) do segredo
só em memória, assinatura SigV4 do Cost Explorer (`service=ce`, `region=us-east-1`), chamada
`GetCostAndUsage` com `Granularity=DAILY`, `Metrics=[UnblendedCost]`, `GroupBy=[{DIMENSION,
SERVICE}]`, paginação por `NextPageToken`, normalização em memória, persistência atômica
(upsert só após todas as páginas) e registro de estado em `coletas_custo`.

Esta change reaproveita integralmente esse fluxo, mudando apenas o `GroupBy` (adicionando a
dimensão de tag), o mapeamento da resposta (do valor da tag para o projeto) e o destino de
persistência (nova tabela `custos_projeto`, sem tocar em `custos`).

Restrição-chave do Cost Explorer confirmada na documentação AWS: tags são sempre pares
Key=Value. `GroupBy` com `Type=TAG` exige uma **Key** específica (ex.: `Key=Environment`), e
`Filter.Tags` tem a forma `{ Key, Values[] }`. Não existe agrupamento por "prefixo de tag".

## Goals / Non-Goals

**Goals:**

- Permitir responder "quanto o projeto X consumiu em um dia/período?" a partir de tags AWS.
- Reutilizar o fluxo SigV4/JWE/paginação já validado, sem regressão na coleta base.
- Preservar a tabela `custos` e sua coleta validada sem alteração semântica.
- Tratar todos os casos de borda de forma não silenciosa e rastreável.
- Manter a solução read-only na AWS.

**Non-Goals (nível de design):**

- Não há interface Reflex nesta change (consumo/visualização fica para change futura).
- Não há cálculo de budget x custo, alertas ou dashboard.
- Não há suporte a `EQP_` nem a múltiplas tags simultâneas de equipe.
- Não há agendamento; a execução é disparada manualmente por um admin.

## Decisions

### D1 — Convenção de tag: Key = finalidade, Value = `codigo` (DECISÃO CONFIRMADA)

**Decisão confirmada pelo usuário (convenção oficial):** a tag de alocação de projeto é um
par Key/Value em que a **Key identifica a finalidade da tag** e o **Value é diretamente o
`projetos.codigo`**. Não há prefixo embutido no Value.

- `Key`  = `provedores.tag_alocacao_projeto` (Key padrão/recomendada do CostGuard = `PRJ`).
- `Value` = `projetos.codigo` (ex.: `PAGAMENTOS`).
- Correspondência: `provedores.tag_alocacao_projeto = PRJ` e `projetos.codigo = PAGAMENTOS`
  → tag AWS `PRJ = PAGAMENTOS`.
- No Cost Explorer, `GroupBy {Type: TAG, Key}` retorna o grupo com `Keys[0] = "PRJ$PAGAMENTOS"`
  (formato `"<Key>$<Value>"`). O código extrai `PAGAMENTOS` removendo exatamente o prefixo
  `"<tag_alocacao_projeto>$"` e compara diretamente com `projetos.codigo`.
- O `GroupBy` usa essa Tag **Key** (`tag_alocacao_projeto`).

**Genérico, não hardcoded:** `PRJ` é apenas a Key recomendada. O algoritmo MUST NOT fazer
hardcode de `PRJ`, MUST NOT exigir prefixo `PRJ_` no Value e MUST NOT remover `PRJ_` do Value.
Um cliente com outra convenção (ex.: `tag_alocacao_projeto = Project`) funciona sem alteração
de código: `Project$PAGAMENTOS` → `PAGAMENTOS`.

**Convenção anterior (substituída):** inicialmente havia-se adotado Key padronizada (ex.:
`Projeto`) com Value `PRJ_<codigo>` (ex.: `PRJ_PAGAMENTOS`), exigindo `starts_with "PRJ_"` e
remoção do prefixo. Essa convenção foi **substituída** pela convenção oficial acima; nenhuma
referência a `PRJ_<codigo>` como Value permanece válida.

**Justificativa:**

- O Cost Explorer agrupa por uma única Key via `GroupBy {Type: TAG, Key}`. Uma consulta
  agrupada retorna todos os projetos de uma vez (um grupo por Value), eficiente e com
  paginação única.
- Com o Value sendo diretamente o `codigo`, a correspondência é uma comparação direta com
  `projetos.codigo`, sem parsing de prefixo — mais simples e sem acoplamento a `PRJ`.
- A finalidade da tag passa a ser carregada pela **Key** (`PRJ` para projeto; futuramente
  `EQP` para equipe), não por um prefixo no Value.

**Equipes (fora de escopo, apenas conceitual):** a convenção futura para equipes será Key
`EQP`, Value = código da equipe (ex.: `EQP = BACKEND`). Esta change NÃO implementa
classificação de equipes.

**Esta decisão NÃO deve ser alterada silenciosamente.** Está confirmada pelo usuário e toda a
modelagem (entidade `custos_projeto`, estratégia de consulta em D4 e tasks) assume esta
convenção. Afeta também o contrato de `projetos` (ver delta de `projetos`).

### D2 — Nova tabela `custos_projeto`, sem alterar `custos`

Criar `custos_projeto` em vez de alterar `custos`. A tabela `custos` representa custo por
provedor/dia/serviço e sua coleta está validada e idempotente; adicionar `projeto_id` a ela
mudaria a chave natural `(provedor_id, data, servico, metrica)` e a semântica (um mesmo
dia/serviço pode se dividir entre projetos), quebrando a coleta base. Separar as duas
preserva a coleta validada e deixa a classificação evoluir de forma independente.

Estrutura proposta de `custos_projeto` (a avaliar e confirmar na implementação):

- `id`
- `provedor_id` (FK `provedores`)
- `projeto_id` (FK `projetos`)
- `data` (date, dia do custo)
- `servico` (text, dimensão SERVICE)
- `metrica` (enum, `unblended` no MVP — espelha `custos`)
- `valor` (decimal)
- `moeda` (text, `USD` no MVP)
- `estimado` (bool)
- `coletado_em` (timestamp, private)

Índice único conceitual: `(provedor_id, projeto_id, data, servico, metrica)`.

**Observação de design sobre o índice:** manter `servico` na chave única é desejável para
reaproveitar o mesmo detalhamento por serviço da coleta base e permitir o breakdown por
serviço dentro do projeto. O `GroupBy` do Cost Explorer aceita até dois níveis, então a
consulta usa `GroupBy = [ {TAG, <Key>}, {DIMENSION, SERVICE} ]`, retornando valor por
tag×serviço×dia — exatamente a granularidade da chave. Isso é o melhor desenho para esta
change; não é necessário granularidade por recurso (fora de escopo).

### D3 — Novo campo no provedor em vez de constante global

Armazenar a Key da tag de alocação em `provedores.tag_alocacao_projeto` (opcional). Cada
provedor/conta AWS pode usar uma convenção de Key diferente; prender a Key a uma constante
global impediria contas distintas. Sem o campo preenchido, a classificação é rejeitada antes
de qualquer chamada à AWS (ver spec `classificacao-custos`).

### D4 — Estratégia de consulta: uma consulta agrupada por tag×serviço, por período

Reaproveitar o endpoint base como molde e criar
`provedores/{id}/classificar-custos` (POST, admin). Fluxo:

1. Autorização admin + elegibilidade do provedor (`aws`, `status = ok`) + exigir
   `tag_alocacao_projeto` definido. Falha ⇒ erro antes de chamar a AWS.
2. Decifrar o segredo JWE só em memória (idêntico ao base).
3. Resolver intervalo (`Start` inclusivo / `End` exclusivo; default: últimos 30 dias).
4. Montar `GetCostAndUsage` com
   `GroupBy = [ {Type: TAG, Key: <tag_alocacao_projeto>}, {Type: DIMENSION, Key: SERVICE} ]`.
5. Assinar SigV4 e paginar por `NextPageToken`, acumulando todas as páginas em memória
   (sem persistir — igual ao base).
6. Normalizar: para cada `ResultsByTime` (dia + `Estimated`) e cada `Groups`:
   - `Keys[0]` = `"<tag_alocacao_projeto>$<Value>"` (ex.: `PRJ$PAGAMENTOS`; ou `PRJ$`
     quando o recurso não tem valor para a tag);
   - `Keys[1]` = serviço;
   - valor/moeda de `UnblendedCost`.
7. Resolver projeto: remover exatamente o prefixo `"<tag_alocacao_projeto>$"` de `Keys[0]`
   para obter o Value. Se o Value for vazio ⇒ não alocado. Caso contrário, o Value é
   diretamente o `codigo` (normalizar para maiúsculas, coerente com `projetos.codigo` que é
   `upper`) e comparar diretamente com `projetos.codigo`. Buscar projeto ativo. NÃO há
   tratamento de prefixo `PRJ_` no Value.
8. Upsert em `custos_projeto` apenas para custos cujo projeto existe e está `ativo`;
   contabilizar os casos de borda (não alocado, tag sem projeto, projeto inativo) em
   contadores do resultado.
9. Registrar estado em `coletas_classificacao` (ver D6) e responder sem segredos.

Alternativa descartada: uma consulta por projeto com `Filter.Tags`. Multiplicaria chamadas
cobradas e não traz benefício sobre o agrupamento único.

### D5 — Idempotência por upsert na chave natural

Mesma técnica da coleta base: `db.query` por `(provedor_id, projeto_id, data, servico,
metrica)`; se existe, `db.edit` (atualiza valor/moeda/estimado/coletado_em); senão `db.add`.
O índice único garante não duplicação. Persistência só após todas as páginas (atômico);
falha de página ⇒ nada gravado, estado `erro` sanitizado, dados anteriores intactos.

### D6 — Estado da classificação em tabela própria `coletas_classificacao`

Espelhar `coletas_custo`, acrescentando os contadores de borda. Campos propostos:
`id`, `provedor_id`, `intervalo_inicio`, `intervalo_fim`, `status` (`sucesso`/`erro`),
`registros_gravados`, `nao_alocados` (contagem de custo cujo Value da tag está ausente/vazio),
`tags_sem_projeto` (ex.: contagem de Values sem projeto correspondente), `projetos_inativos`
(ignorados), `mensagem` (sanitizada), `executado_em`. Usar tabela separada mantém a
semântica de `coletas_custo` (coleta base) intacta.

### D7 — Detecção de tag de alocação inativa/não propagada

Duas vias, nesta ordem de preferência:

1. **Inferência pela resposta** (sem permissão extra): se o `GroupBy TAG` não retorna a
   dimensão de tag esperada (todos os grupos sem a chave de tag, ou dimensão ausente),
   tratar como tag não ativa/não propagada ⇒ `status = erro` sanitizado.
2. **Verificação explícita** (opcional, custo de 1 permissão IAM): `ce:ListCostAllocationTags`
   para confirmar que a Key existe e está `Active` antes de consultar; `ce:GetTags` pode
   enumerar valores de tag para diagnóstico. Recomendado para mensagem de erro mais clara.

Em nenhum caso o CostGuard ativa a tag (restrição de escopo e de segurança).

## Risks / Trade-offs

- **Dependência da convenção de tag (D1)** → Resolvido: Key = finalidade
  (`tag_alocacao_projeto`, recomendada `PRJ`), Value = `projetos.codigo` diretamente.
  Mitigação residual: a Key correta precisa estar configurada no provedor (validada antes de
  chamar a AWS) e ativada como cost allocation tag.
- **Tag de alocação não ativada ⇒ grupos vazios** → Mitigação: D7 (inferência + opcional
  `ListCostAllocationTags`), erro sanitizado não silencioso, sem modificar a AWS.
- **Latência de propagação (até ~24h após ativar a tag)** → Mitigação: documentado como
  pré-condição operacional fora do controle do CostGuard; tratado como erro/estado, não como
  falha silenciosa.
- **Custo por chamada paginada do Cost Explorer** → Mitigação: uma consulta agrupada por
  período (não N por projeto); paginação só quando a AWS retorna `NextPageToken`.
- **Tag sem projeto / projeto inativo** → Mitigação: nunca cria projeto, nunca descarta o
  custo subjacente (permanece na coleta base), contabiliza de forma rastreável.
- **Divergência entre `custos` e `custos_projeto`** (somas podem diferir pois nem todo custo
  tem tag) → Trade-off aceito e esperado: o total não alocado é justamente o que falta
  taguear; fica rastreável no estado da execução.
- **Dupla verdade de granularidade** (serviço na chave) → Trade-off: aumenta linhas, mas
  mantém paridade com a coleta base e habilita breakdown por serviço sem recurso.

## Permissões IAM necessárias

- `ce:GetCostAndUsage` — já exigida pela coleta base; usada com `GroupBy TAG` nesta change.
- `ce:ListCostAllocationTags` — **opcional**, recomendada para D7 (detectar tag ausente/
  inativa com mensagem clara).
- `ce:GetTags` — **opcional**, apenas para diagnóstico/enumeração de valores de tag.

Todas são read-only. A credencial permanece de privilégio mínimo; o CostGuard não requer
permissão de escrita e não ativa cost allocation tags.

## Open Questions

- Não há decisão bloqueante. D1 está resolvida: Key = finalidade (`tag_alocacao_projeto`,
  recomendada `PRJ`), Value = `projetos.codigo` diretamente. A única questão deferível para a
  implementação, sem impacto nas specs nem na modelagem, é a via de detecção de tag inativa
  (D7): inferir pela resposta vazia ou confirmar explicitamente via `ce:ListCostAllocationTags`.
