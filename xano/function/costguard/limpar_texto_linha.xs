// Limpeza de texto livre de UMA linha (nome de projeto, de usuário, de recurso
// etc.) antes de entrar no assunto, no texto puro ou, depois de
// costguard/escapar_html, no HTML de um e-mail.
//
// Troca CR, LF e tabulação por espaço (nada de quebra de linha: protege assunto
// e cabeçalhos), apara as pontas e limita a 120 caracteres. Entrada nula = "".
// Não escapa HTML: o texto puro não deve ter entidades; o HTML chama escapar_html.
//
// RISCO ACEITO / NÃO VERIFICADO (decisão do coordenador): só CR, LF e tabulação são
// tratados. Outros caracteres de controle (VT, FF, NUL), U+0085, U+2028, U+2029 e
// os de direção (U+202A a U+202E, U+2066 a U+2069) NÃO são removidos: não há
// precedente neste repositório de escape unicode em string nem de classe de regex
// equivalente em .xs, e a sintaxe não foi inventada. Consequência: o nome do
// projeto/usuário/recurso pode carregar esses caracteres no assunto e no corpo
// (efeito visual, por exemplo inversão de direção do texto). Não há injeção de
// cabeçalho: o envio é JSON para o Resend (campo `subject` de um objeto), e CR/LF
// já saem do assunto. O texto vem de usuário autenticado (admin cadastra projetos).
// Ampliar a limpeza exige confirmar no Xano real a sintaxe de escape unicode.
function "costguard/limpar_texto_linha" {
  input {
    text texto?
  }

  stack {
    var $limpo {
      value = ((($input.texto ?? "")|replace:"\r":" ")|replace:"\n":" ")|replace:"\t":" "
    }
    var.update $limpo { value = ($limpo|trim)|substr:0:120 }
  }

  response = $limpo
}
