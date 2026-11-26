// Moldura HTML comum dos e-mails do CostGuard (alerta de orçamento e recursos sem
// equipe): cabeçalho escuro com "CostGuard" em TEXTO e acento #14b8a6, corpo
// claro, botão "Abrir projeto no CostGuard" e rodapé "Alerta manual enviado pelo
// CostGuard".
//
// Compatibilidade com clientes de e-mail: layout só em tabelas, CSS INLINE,
// largura máxima de 600 px, atributos entre aspas simples. Sem imagem, SVG, fonte
// externa, @import, JavaScript nem bloco <style>.
//
// Segurança: `titulo` e `link` são escapados AQUI (costguard/escapar_html);
// `conteudo_html` JÁ É HTML seguro (montado pelo chamador só com texto escapado,
// números formatados e rótulos fixos) e entra sem alteração. O link é o do
// projeto, validado pelo chamador (https + host + /projetos/<id>); o escape não o
// altera (não há & < > " ' nele).
//
// Defesa em profundidade: o `link` é aparado e só vira botão se começar com
// "https://" (e tiver algo depois). Qualquer outro valor (vazio, http://,
// javascript:, data: etc.) NÃO gera o botão: o e-mail sai sem ele, sem erro.
function "costguard/email_html_layout" {
  input {
    text titulo?
    text conteudo_html?
    text link?
  }

  stack {
    function.run "costguard/escapar_html" {
      input = {texto: ($input.titulo ?? "")}
    } as $titulo_html

    var $link_limpo { value = (($input.link ?? "")|trim) }
    var $link_prefixo { value = $link_limpo|substr:0:8 }
    var $link_ok { value = (($link_limpo|strlen) > 8 && $link_prefixo == "https://") }

    function.run "costguard/escapar_html" {
      input = {texto: $link_limpo}
    } as $link_html

    var $html { value = "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>CostGuard</title></head><body style='margin:0;padding:0;background-color:#f3f4f6;'>" }
    var.update $html { value = $html ~ "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='width:100%;background-color:#f3f4f6;'><tr><td align='center' style='padding:24px 12px;'>" }
    var.update $html { value = $html ~ "<table role='presentation' width='600' cellpadding='0' cellspacing='0' border='0' style='width:100%;max-width:600px;background-color:#ffffff;border:1px solid #e5e7eb;'>" }

    // Cabeçalho escuro (texto, sem imagem).
    var.update $html { value = $html ~ "<tr><td style='background-color:#0f172a;padding:20px 24px;border-bottom:4px solid #14b8a6;font-family:Arial,Helvetica,sans-serif;font-size:22px;line-height:28px;font-weight:bold;color:#ffffff;'>Cost<span style='color:#14b8a6;'>Guard</span></td></tr>" }

    // Corpo claro: título, conteúdo e botão.
    var.update $html { value = $html ~ "<tr><td style='padding:24px;font-family:Arial,Helvetica,sans-serif;color:#111827;'><h1 style='margin:0 0 16px 0;font-size:20px;line-height:26px;color:#111827;'>" ~ $titulo_html ~ "</h1>" }
    var.update $html { value = $html ~ ($input.conteudo_html ?? "") }

    // Botão: só com link https:// válido; sem ele, o corpo fecha sem o botão.
    var $botao_html { value = "" }

    conditional {
      if ($link_ok == true) {
        var.update $botao_html { value = "<table role='presentation' cellpadding='0' cellspacing='0' border='0' style='margin-top:24px;'><tr><td align='center' bgcolor='#14b8a6' style='background-color:#14b8a6;border-radius:6px;'><a href='" ~ $link_html ~ "' style='display:inline-block;padding:12px 24px;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:20px;font-weight:bold;color:#042f2e;text-decoration:none;'>Abrir projeto no CostGuard</a></td></tr></table>" }
      }
    }

    var.update $html { value = $html ~ $botao_html ~ "</td></tr>" }

    // Rodapé.
    var.update $html { value = $html ~ "<tr><td style='padding:16px 24px;background-color:#f9fafb;border-top:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:18px;color:#6b7280;'>Alerta manual enviado pelo CostGuard</td></tr>" }
    var.update $html { value = $html ~ "</table></td></tr></table></body></html>" }
  }

  response = $html
}
