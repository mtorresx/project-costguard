## 1. Implementação

- [x] 1.1 `editar_projeto_PATCH.xs`: `text budget?` com as regras do design. _Evidência (2026-10-27): `$budget_enviado` por `strlen > 0` (não por `!= null`, porque `"0" == null` também pode ser verdadeiro no XanoScript); dry-run filtrado com somente `UPDATE query projetos/{id} PATCH`; publicado._

## 2. Verificação

- [x] 2.1 Variante temporária que devolve o valor calculado sem gravar. _Evidência: diagnóstico com variantes de eco (sem `db.edit`) no projeto 4/10: com `decimal budget?`, `0`, `0.0`, `"0"`, `null` e ausente chegam como `0` e `== null` verdadeiro; `=== null` e `has` não distinguem; com `text`, ausente → `""` e `0` → `"0"`. Variante da correção: `0` → grava 0; `12.5` → 12.5; ausente → mantém 250000; `null` → mantém; `"0.00"` → 0; `-1` → 400; `"abc"` → 400 "deve ser numérico". Versão real republicada a partir de `./xano` após cada variante._
- [x] 2.2 Versão real: `-1` e `"abc"` → 400 sem gravar; `GET /projetos` inalterado. _Evidência: ambos 400 com as mensagens esperadas; `GET /projetos` idêntico antes e depois._
- [x] 2.3 Gravação real de `budget = 0`. _Atualização (2026-11-03): gravação de orçamentos pela edição exercitada na recriação dos dados autorizada pelo usuário (`PATCH` 0 → 2000, 1400, 670, 480 e 1500, todos persistidos)._ Registro original: _Não executada: alteraria dados reais sem autorização. Risco: o `db.edit` com o valor calculado só foi verificado pela variante que devolve o valor. Recomendado na homologação: editar um projeto de teste para orçamento 0 e conferir o card._
- [x] 2.4 `openspec validate correcao-orcamento-zero --strict`. _Evidência: "Change 'correcao-orcamento-zero' is valid"._

## 3. Revisão Codex (2026-10-27)

- [x] 3.1 Achado 2 (BLOQUEANTE) — entrada não numérica começando por zero aceita. _Tratado: validação por expressão regular antes da conversão. Variante de teste da sintaxe: `padrão|regex_matches:valor` aceita `0`, `12.5`, `0.00` e recusa `0abc`, `1e3`, `-1` (sem sinal no padrão), `12.`; a ordem inversa sempre falso. Versão real (padrão com sinal opcional): `0abc`, `1e3`, `12.` → 400 "deve ser numérico"; `-1` → 400 "maior ou igual a zero"; `" "` (vazio após `trim`) → 200 mantendo os valores atuais (gravação sem mudança de valor); `GET /projetos` idêntico antes e depois._

## 4. Criação de projeto (2026-11-03)

- [x] 4.1 `criar_projeto_POST.xs` com `budget` texto obrigatório (regex, `>= 0`). _Evidência: encontrado ao recriar os projetos a pedido do usuário (5 criações com `budget = 0` → 400). Dry-run filtrado (somente `UPDATE query projetos POST`); publicado; `-1` → 400 "maior ou igual a zero"; `"abc"` → 400 "numérico"; ausente → 400 "obrigatório"; 5 projetos criados com `budget = 0` (200). Gravação de `budget = 0` comprovada por execução real (autorizada pelo usuário na recriação dos dados)._
