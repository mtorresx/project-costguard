// Validação e normalização do e-mail do DevOps de um projeto. Fonte única da regra: usada por criar projeto, editar
// projeto e pelo envio do alerta (que revalida o valor gravado antes de usá-lo).
//
// Regra: uma única caixa, em minúsculas, sem espaços, vírgula, ponto e vírgula,
// quebra de linha ou caractere de controle (a lista de caracteres aceitos é
// fechada), no máximo 254 caracteres. Vazio = sem destinatário (válido).
// Devolve: {vazio, valido, email}. `email` é "" quando vazio ou inválido.
function "costguard/normalizar_email_devops" {
  input {
    text email?
  }

  stack {
    var $bruto { value = (($input.email ?? "")|trim)|to_lower }
    var $tamanho { value = $bruto|strlen }
    var $vazio { value = ($tamanho == 0) }
    var $formato_ok { value = false }

    // `$` do regex aceita uma quebra de linha final; ela já foi removida pelo
    // trim acima, e quebras internas não pertencem à lista de caracteres aceitos.
    conditional {
      if ($vazio == false && $tamanho <= 254 && ("/^[a-z0-9_%+-]+([.][a-z0-9_%+-]+)*@([a-z0-9]([a-z0-9-]*[a-z0-9])?[.])+[a-z]{2,24}$/"|regex_matches:$bruto)) {
        var.update $formato_ok { value = true }
      }
    }

    var $resultado {
      value = {
        vazio : $vazio
        valido: ($vazio || $formato_ok)
        email : ($formato_ok) ? $bruto : ""
      }
    }
  }

  response = $resultado
}
