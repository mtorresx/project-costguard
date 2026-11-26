// Mês de referência por extenso em pt-BR (ex.: "2026-11" vira "novembro de
// 2026"), por mapa fixo de 12 nomes: não depende de locale nem de filtro de
// data. Entrada fora do formato AAAA-MM (01 a 12) devolve texto VAZIO (nunca o
// texto cru), sem erro: nada vindo de fora do padrão chega ao e-mail por aqui.
function "costguard/mes_extenso_pt_br" {
  input {
    text mes?
  }

  stack {
    var $bruto { value = (($input.mes ?? "")|trim) }
    var $resultado { value = "" }

    conditional {
      if ("/^[0-9]{4}-(0[1-9]|1[0-2])$/"|regex_matches:$bruto) {
        var $partes { value = $bruto|split:"-" }
        var $ano { value = $partes|first }
        var $numero { value = ($partes|last)|to_int }
        var $nome { value = "" }

        conditional {
          if ($numero == 1) {
            var.update $nome { value = "janeiro" }
          }
          elseif ($numero == 2) {
            var.update $nome { value = "fevereiro" }
          }
          elseif ($numero == 3) {
            var.update $nome { value = "março" }
          }
          elseif ($numero == 4) {
            var.update $nome { value = "abril" }
          }
          elseif ($numero == 5) {
            var.update $nome { value = "maio" }
          }
          elseif ($numero == 6) {
            var.update $nome { value = "junho" }
          }
          elseif ($numero == 7) {
            var.update $nome { value = "julho" }
          }
          elseif ($numero == 8) {
            var.update $nome { value = "agosto" }
          }
          elseif ($numero == 9) {
            var.update $nome { value = "setembro" }
          }
          elseif ($numero == 10) {
            var.update $nome { value = "outubro" }
          }
          elseif ($numero == 11) {
            var.update $nome { value = "novembro" }
          }
          elseif ($numero == 12) {
            var.update $nome { value = "dezembro" }
          }
        }

        var.update $resultado { value = $nome ~ " de " ~ $ano }
      }
    }
  }

  response = $resultado
}
