## Decisão

`text budget?` no lugar de `decimal budget?`. Regras:

- `budget == ""` (ausente ou vazio) → mantém o valor atual;
- caso contrário, `$valor = $input.budget|to_decimal`;
- `$valor < 0` → HTTP 400 "Campo 'budget' deve ser maior ou igual a zero";
- texto fora do formato decimal `^-?[0-9]+([.][0-9]+)?$` → HTTP 400 "Campo 'budget' deve ser numérico", antes da conversão (achado bloqueante 2 da revisão Codex: a primeira versão aceitava `"0abc"`). No XanoScript o filtro é escrito `padrão|regex_matches:valor` (a ordem inversa sempre devolve falso, confirmado por variante).

## Verificação sem gravar dados reais

A correção do caminho de gravação só é comprovada gravando. Sem autorização, verifica-se: (a) variante temporária que devolve o valor que seria gravado para `0`, `12.5`, ausente, `-1`, `"abc"`, `"0abc"`, `"1e3"` e `"12."`; (b) a versão real responde 400 para `-1` e `"abc"` antes de gravar. O teste de gravação real fica para a homologação.
