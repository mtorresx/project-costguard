// Uma linha "rótulo / valor" da tabela de dados de um e-mail HTML do CostGuard
// (layout em tabelas, CSS inline, sem imagem). CONTRATO DE SEGURANÇA:
//   - `rotulo` é texto simples (constante do chamador): escapado AQUI;
//   - `valor_html` JÁ É HTML seguro: o chamador passa só texto do banco depois de
//     costguard/escapar_html, números formatados ou rótulos fixos. Esta função NÃO
//     escapa `valor_html` (escaparia duas vezes) nem aceita tags vindas do usuário.
function "costguard/email_html_linha" {
  input {
    text rotulo?
    text valor_html?
  }

  stack {
    function.run "costguard/escapar_html" {
      input = {texto: ($input.rotulo ?? "")}
    } as $rotulo_html

    var $linha {
      value = "<tr><td style='padding:8px 0;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:20px;color:#6b7280;width:40%;vertical-align:top;'>" ~ $rotulo_html ~ "</td><td style='padding:8px 0;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:20px;color:#111827;font-weight:bold;vertical-align:top;'>" ~ ($input.valor_html ?? "") ~ "</td></tr>"
    }
  }

  response = $linha
}
