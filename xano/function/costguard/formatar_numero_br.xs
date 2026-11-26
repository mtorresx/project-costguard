// Formatação numérica brasileira (ponto nos milhares, vírgula nos decimais) SEM
// depender de locale. Trabalha com INTEIRO já escalado, por texto e aritmética
// simples:
//   - `escalado` = valor x 10^casas, arredondado pelo chamador (ex.: US$ 5000,00
//     entra como 500000 com casas = 2; 12,5% entra como 125 com casas = 1);
//   - `casas` = 1 ou 2 (casas decimais mostradas; mais que isso não é suportado);
//   - devolve só o número ("5.000,00", "12,5", "-3,40"); prefixo ("US$ ") e sufixo
//     ("%") ficam com o chamador.
// Suporta até 18 dígitos na parte inteira (5 grupos de milhares).
// Não usa `floor`, `mod` nem `%`: a parte decimal sai de `substr` com início
// variável (forma já usada em outros endpoints) e a divisão por potência de 10 é
// EXATA (o valor menos o resto), arredondada só por segurança contra decimal.
// NÃO VERIFICADO no Xano: função devolvendo texto simples; `to_int` de texto com
// zeros à esquerda ("05"/"000"); `to_text` de inteiro grande sem notação científica.
function "costguard/formatar_numero_br" {
  input {
    int escalado
    int casas
  }

  stack {
    var $negativo { value = ($input.escalado < 0) }
    var $absoluto { value = ($negativo == true) ? (0 - $input.escalado) : $input.escalado }
    var $digitos { value = $absoluto|to_text }
    var $minimo { value = $input.casas + 1 }

    // Zeros à esquerda até haver ao menos casas + 1 dígitos (0,05 = "005").
    foreach ([1, 2]) {
      each as $passo {
        conditional {
          if (($digitos|strlen) < $minimo) {
            var.update $digitos { value = "0" ~ $digitos }
          }
        }
      }
    }

    var $corte { value = ($digitos|strlen) - $input.casas }
    var $fracao_txt { value = "" }
    var $fracao_num { value = 0 }
    var $escala { value = 1 }

    conditional {
      if ($input.casas == 2) {
        var.update $escala { value = 100 }
        var.update $fracao_txt { value = $digitos|substr:$corte }
        var.update $fracao_num { value = $fracao_txt|to_int }
      }
      elseif ($input.casas == 1) {
        var.update $escala { value = 10 }
        var.update $fracao_txt { value = $digitos|substr:$corte }
        var.update $fracao_num { value = $fracao_txt|to_int }
      }
    }

    var $resto_num { value = ((($absoluto - $fracao_num) / $escala)|round:0)|to_int }
    var $resto_txt { value = $resto_num|to_text }
    var $agrupado { value = "" }

    // Milhares: tira os 3 últimos dígitos do inteiro, de cada vez (até 5 vezes).
    foreach ([1, 2, 3, 4, 5]) {
      each as $grupo {
        conditional {
          if (($resto_txt|strlen) > 3) {
            var $inicio_cauda { value = ($resto_txt|strlen) - 3 }
            var $cauda_txt { value = $resto_txt|substr:$inicio_cauda }
            var $cauda_num { value = $cauda_txt|to_int }
            var.update $agrupado { value = "." ~ $cauda_txt ~ $agrupado }
            var.update $resto_num { value = ((($resto_num - $cauda_num) / 1000)|round:0)|to_int }
            var.update $resto_txt { value = $resto_num|to_text }
          }
        }
      }
    }

    var $sinal { value = ($negativo == true) ? "-" : "" }
    var $saida { value = $sinal ~ $resto_txt ~ $agrupado }

    conditional {
      if ($input.casas == 2 || $input.casas == 1) {
        var.update $saida { value = $saida ~ "," ~ $fracao_txt }
      }
    }
  }

  response = $saida
}
