// Escape de HTML para TODO texto vindo do banco que entra no corpo HTML de um
// e-mail. Função única e reutilizável: nenhum
// endpoint repete a lista de trocas.
//
// Troca, NESTA ORDEM: & primeiro (senão os & dos demais escapes seriam escapados
// de novo), depois < > " '. Aspas duplas e simples ficam seguras tanto em
// conteúdo de tag quanto em valor de atributo. Entrada nula ou ausente devolve "".
// Devolve texto (não objeto). Não limita tamanho nem remove quebras de linha:
// quem precisa de uma linha só chama costguard/limpar_texto_linha ANTES.
// NÃO VERIFICADO no Xano: função devolvendo texto simples; `replace` com "\"".
function "costguard/escapar_html" {
  input {
    text texto?
  }

  stack {
    var $bruto { value = ($input.texto ?? "") }
    var $escapado {
      value = (((($bruto|replace:"&":"&amp;")|replace:"<":"&lt;")|replace:">":"&gt;")|replace:"\"":"&quot;")|replace:"'":"&#39;"
    }
  }

  response = $escapado
}
