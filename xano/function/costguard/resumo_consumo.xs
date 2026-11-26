// Lógica compartilhada: usada pelo
// endpoint projetos_resumo_consumo_mtd_GET e pelos painéis agregados.
function "costguard/resumo_consumo" {
  input {
    text mes? filters=trim
  }

  stack {
    // Qualquer usuário autenticado pode ler (auth garante 401 sem token).
    // Somente leitura: nunca dispara coleta nem escrita.

    // Janela MTD em America/Sao_Paulo: início inclusivo no dia 1 do mês,
    // fim exclusivo = amanhã (sem horário de verão no fuso desde 2019).
    // Aritmética em variável própria antes do filtro (padrão de coletar-custos).
    var $agora_ts { value = now|to_int }
    var $amanha_ts { value = $agora_ts + 86400000 }
    var $data_inicio { value = $agora_ts|format_timestamp:"Y-m-01":"America/Sao_Paulo" }
    var $data_fim { value = $amanha_ts|format_timestamp:"Y-m-d":"America/Sao_Paulo" }

    // Mês selecionável.
    var $mes_atual { value = $agora_ts|format_timestamp:"Y-m":"America/Sao_Paulo" }
    var $mes_sel { value = (($input.mes ?? "")|strlen) > 0 ? $input.mes : $mes_atual }

    precondition ("/^[0-9]{4}-(0[1-9]|1[0-2])$/"|regex_matches:$mes_sel) {
      error_type = "inputerror"
      error = "Parâmetro 'mes' deve estar no formato AAAA-MM"
    }

    var $partes_sel { value = $mes_sel|split:"-" }
    var $ano_sel { value = ($partes_sel|first)|to_int }
    var $num_sel { value = ($partes_sel|last)|to_int }
    var $partes_atual { value = $mes_atual|split:"-" }
    var $chave_sel { value = $ano_sel * 12 + $num_sel }
    var $chave_atual { value = (($partes_atual|first)|to_int) * 12 + (($partes_atual|last)|to_int) }

    precondition ($chave_sel <= $chave_atual) {
      error_type = "inputerror"
      error = "Mês futuro não é permitido"
    }

    var $mes_corrente { value = ($chave_sel == $chave_atual) }

    conditional {
      if ($mes_corrente == false) {
        // Mês fechado: dia 1 até o dia 1 do mês seguinte (exclusivo).
        var $ano_fim { value = ($num_sel == 12) ? ($ano_sel + 1) : $ano_sel }
        var $num_fim { value = ($num_sel == 12) ? 1 : ($num_sel + 1) }
        var $num_fim_txt { value = ($num_fim < 10) ? ("0" ~ ($num_fim|to_text)) : ($num_fim|to_text) }
        var.update $data_inicio { value = $mes_sel ~ "-01" }
        var.update $data_fim { value = ($ano_fim|to_text) ~ "-" ~ $num_fim_txt ~ "-01" }
      }
    }

    // Duas consultas fixas, independentes da quantidade de projetos.
    db.query projetos {
      sort = {criado_em: "desc"}
      return = {type: "list"}
    } as $lista_projetos

    db.query custos_equipe {
      where = $db.custos_equipe.data >= $data_inicio && $db.custos_equipe.data < $data_fim
      return = {type: "list"}
    } as $linhas

    // Agregação em mapas planos (chaves internas seguras, não expostas).
    // A soma é feita por projeto E moeda: valores de moedas diferentes nunca
    // são somados entre si. Também registra moedas distintas, última moeda
    // vista e maior data por projeto.
    // Chaves só com [0-9a-f_k]: um "|" na chave é interpretado pelo Xano como
    // filtro em has/set e gera ERROR_FATAL "Invalid syntax" (confirmado por
    // execução em 2026-10-27).
    var $tem_registro { value = {} }
    var $somas_moeda { value = {} }
    var $pares_moeda { value = {} }
    var $qtd_moedas { value = {} }
    var $moeda_proj { value = {} }
    var $ultimas { value = {} }

    foreach ($linhas) {
      each as $l {
        var $kp { value = "k" ~ (($l.projeto_id|to_text)|sha256) }
        var $moeda_linha { value = ($l.moeda ?? "") }
        var $kpm { value = $kp ~ "_" ~ ($moeda_linha|sha256) }

        var.update $tem_registro { value = $tem_registro|set:$kp:true }

        var $soma_atual { value = $somas_moeda|get:$kpm:0 }
        var.update $somas_moeda { value = $somas_moeda|set:$kpm:($soma_atual + $l.valor) }

        conditional {
          if (($pares_moeda|has:$kpm) == false) {
            var.update $pares_moeda { value = $pares_moeda|set:$kpm:true }
            var $qtd_atual { value = $qtd_moedas|get:$kp:0 }
            var.update $qtd_moedas { value = $qtd_moedas|set:$kp:($qtd_atual + 1) }
            var.update $moeda_proj { value = $moeda_proj|set:$kp:$moeda_linha }
          }
        }

        var $ultima_atual { value = $ultimas|get:$kp:"" }
        conditional {
          if ($l.data > $ultima_atual) {
            var.update $ultimas { value = $ultimas|set:$kp:$l.data }
          }
        }
      }
    }

    // Um item por projeto (ativos e inativos), na ordem de GET /projetos.
    var $itens { value = [] }

    foreach ($lista_projetos) {
      each as $p {
        var $kp { value = "k" ~ (($p.id|to_text)|sha256) }
        var $soma { value = 0 }
        var $qtd { value = $qtd_moedas|get:$kp:0 }
        var $moeda_unica { value = $moeda_proj|get:$kp:null }
        var $kpu { value = $kp ~ "_" ~ (($moeda_unica ?? "")|sha256) }

        var $custo_status { value = "sem_registros" }
        var $custo_mtd { value = null }
        var $moeda { value = null }
        var $ultima { value = $ultimas|get:$kp:null }

        // Estado do custo. Moedas diferentes nunca são somadas nem convertidas.
        conditional {
          if (($tem_registro|has:$kp) == false) {
            var.update $custo_status { value = "sem_registros" }
          }
          elseif ($qtd > 1) {
            var.update $custo_status { value = "moedas_mistas" }
          }
          elseif ($moeda_unica != "USD") {
            var.update $custo_status { value = "moeda_incompativel" }
            var.update $soma { value = $somas_moeda|get:$kpu:0 }
            var.update $custo_mtd { value = $soma|round:2 }
            var.update $moeda { value = $moeda_unica }
          }
          else {
            var.update $custo_status { value = "ok" }
            var.update $soma { value = $somas_moeda|get:$kpu:0 }
            var.update $custo_mtd { value = $soma|round:2 }
            var.update $moeda { value = $moeda_unica }
          }
        }

        // Percentual e faixa só com custo em USD e orçamento definido.
        // A faixa usa o percentual bruto, nunca o arredondado.
        var $calcula { value = ($custo_status == "ok" && $p.budget > 0) }
        var $pct_bruto { value = 0 }
        var $percentual { value = null }
        var $faixa { value = null }

        conditional {
          if ($calcula) {
            var.update $pct_bruto { value = $soma / $p.budget * 100 }
            var.update $percentual { value = $pct_bruto|round:1 }
          }
        }

        conditional {
          if ($calcula && $pct_bruto >= 100) {
            var.update $faixa { value = "estourado" }
          }
          elseif ($calcula && $pct_bruto >= 90) {
            var.update $faixa { value = "critico" }
          }
          elseif ($calcula && $pct_bruto >= 70) {
            var.update $faixa { value = "atencao" }
          }
          elseif ($calcula) {
            var.update $faixa { value = "normal" }
          }
        }

        // Objeto montado em variável própria: objetos multi-linha não
        // podem ser argumento de filtro.
        var $item {
          value = {
            id                   : $p.id
            nome                 : $p.nome
            codigo               : $p.codigo
            status               : $p.status
            budget               : $p.budget
            custo_status         : $custo_status
            custo_mtd            : $custo_mtd
            moeda                : $moeda
            ultima_data_com_custo: $ultima
            percentual_usado     : $percentual
            faixa                : $faixa
          }
        }
        var.update $itens { value = $itens|push:$item }
      }
    }

    var $resposta {
      value = {
        data_inicio : $data_inicio
        data_fim    : $data_fim
        mes         : $mes_sel
        mes_corrente: $mes_corrente
        projetos    : $itens
      }
    }
  }

  response = $resposta
}
