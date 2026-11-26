## Por quê

Bug registrado na Change `frontend-detalhamento-projeto` (follow-up 9.9): `PATCH /projetos/{id}` com `{"budget": 0}` responde HTTP 200, mas não grava o zero; o orçamento anterior permanece. Com isso, o admin não consegue remover o orçamento de um projeto pela interface.

Causa confirmada em 2026-10-27 com uma variante temporária do endpoint que só devolvia o que recebeu (sem gravar): no XanoScript, `0 == null` é verdadeiro, e um campo `decimal` opcional ausente também chega como `0`. A expressão `($input.budget != null) ? $input.budget : $projeto_alvo.budget` trata o zero como "não enviado". Comparação estrita (`=== null`) e `has` também não distinguem os dois casos. Um campo `text` opcional distingue: ausente chega como `""` e o número `0` chega como `"0"`.

## O que muda

- `POST /projetos`: mesmo problema na criação (encontrado em 2026-11-03 ao recriar os projetos): orçamento 0 era recusado com "deve ser maior ou igual a zero". O campo passa a ser texto obrigatório com as mesmas regras.

- `PATCH /projetos/{id}`: o campo `budget` passa a ser recebido como texto e convertido no backend. Ausente ou vazio mantém o orçamento atual; `0` grava zero; valor negativo ou não numérico responde HTTP 400. O contrato com o frontend não muda (o frontend continua enviando número JSON).

## Capabilities

### Modified Capabilities

- `projetos`: "Edição de projeto restrita a admin" ganha o cenário de orçamento zero e de campo ausente.

## Impacto

- **Xano:** `xano/api/app/editar_projeto_PATCH.xs` e `xano/api/app/criar_projeto_POST.xs`.
- **Reflex:** nenhum.

## Fora do escopo

- Outros endpoints com campos numéricos opcionais (nenhum outro PATCH com decimal opcional foi encontrado).
