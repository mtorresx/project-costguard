query "projetos/{id}/custos-equipe" verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "projetos"
    }
    // Intervalo opcional: início inclusivo, fim exclusivo.
    text data_inicio? filters=trim
    text data_fim? filters=trim
  }

  stack {
    // Qualquer usuário autenticado pode ler (auth garante 401 sem token).
    // Somente leitura: nunca dispara coleta nem escrita.
    db.get projetos {
      field_name = "id"
      field_value = $input.id
    } as $projeto

    precondition ($projeto != null) {
      error_type = "notfound"
      error = "Projeto não encontrado"
    }

    // Mesmo intervalo padrão da classificação: últimos 30 dias até ontem.
    var $agora_ts { value = now|to_int }
    var $inicio_ts { value = $agora_ts - 2592000000 }
    var $hoje { value = $agora_ts|format_timestamp:"Y-m-d":"UTC" }
    var $ha_30_dias { value = $inicio_ts|format_timestamp:"Y-m-d":"UTC" }

    var $inicio {
      value = ($input.data_inicio != null && $input.data_inicio != "") ? $input.data_inicio : $ha_30_dias
    }
    var $fim {
      value = ($input.data_fim != null && $input.data_fim != "") ? $input.data_fim : $hoje
    }

    precondition ($inicio < $fim) {
      error_type = "inputerror"
      error = "Intervalo inválido: data_inicio deve ser anterior a data_fim"
    }

    // Todas as linhas do projeto no intervalo, de todos os provedores.
    db.query custos_equipe {
      where = $db.custos_equipe.projeto_id == $input.id && $db.custos_equipe.data >= $inicio && $db.custos_equipe.data < $fim
      return = {type: "list"}
    } as $linhas

    // Moedas distintas ANTES de somar: nunca somar moedas diferentes.
    var $moedas { value = {} }
    foreach ($linhas) {
      each as $l {
        var $moeda_linha { value = $l.moeda }
        var.update $moedas { value = $moedas|set:$moeda_linha:true }
      }
    }

    precondition (($moedas|count) <= 1) {
      error_type = "inputerror"
      error = "Os custos do intervalo estão em moedas diferentes e não podem ser agregados."
    }

    var $moeda { value = null }
    conditional {
      if (($linhas|count) > 0) {
        var $primeira_linha { value = $linhas|first }
        var.update $moeda { value = $primeira_linha.moeda }
      }
    }

    // Totais por equipe (chave = equipe_id) e "Sem responsável".
    var $totais { value = {} }
    var $codigos_linha { value = {} }
    var $total_sem_responsavel { value = 0 }

    foreach ($linhas) {
      each as $l {
        conditional {
          if ($l.equipe_id == null || $l.codigo_equipe == "") {
            var.update $total_sem_responsavel { value = $total_sem_responsavel + $l.valor }
          }
          else {
            var $k { value = $l.equipe_id|to_text }
            var $acumulado { value = $totais|get:$k:0 }
            var.update $totais { value = $totais|set:$k:($acumulado + $l.valor) }
            var.update $codigos_linha { value = $codigos_linha|set:$k:$l.codigo_equipe }
          }
        }
      }
    }

    // Equipes do projeto ordenadas por código; inclui só as com custo.
    db.query equipes {
      where = $db.equipes.projeto_id == $input.id
      sort = {codigo: "asc"}
      return = {type: "list"}
    } as $equipes_projeto

    var $lista_equipes { value = [] }
    var $vistas { value = {} }
    var $total_equipes { value = 0 }

    foreach ($equipes_projeto) {
      each as $eq {
        var $ke { value = $eq.id|to_text }
        conditional {
          if ($totais|has:$ke) {
            var $total_eq { value = $totais|get:$ke:0 }
            var.update $lista_equipes {
              value = $lista_equipes|push:{
                equipe_id: $eq.id
                codigo   : $eq.codigo
                nome     : $eq.nome
                total    : $total_eq
              }
            }
            var.update $total_equipes { value = $total_equipes + $total_eq }
            var.update $vistas { value = $vistas|set:$ke:true }
          }
        }
      }
    }

    // Defensivo: linhas cuja equipe não foi encontrada continuam no total.
    foreach ($linhas) {
      each as $l {
        conditional {
          if ($l.equipe_id != null && $l.codigo_equipe != "") {
            var $kl { value = $l.equipe_id|to_text }
            conditional {
              if (($vistas|has:$kl) == false) {
                var $total_orfa { value = $totais|get:$kl:0 }
                var.update $lista_equipes {
                  value = $lista_equipes|push:{
                    equipe_id: $l.equipe_id
                    codigo   : $codigos_linha|get:$kl:""
                    nome     : $codigos_linha|get:$kl:""
                    total    : $total_orfa
                  }
                }
                var.update $total_equipes { value = $total_equipes + $total_orfa }
                var.update $vistas { value = $vistas|set:$kl:true }
              }
            }
          }
        }
      }
    }

    var $resposta {
      value = {
        projeto_id     : $projeto.id
        intervalo      : {inicio: $inicio, fim: $fim}
        moeda          : $moeda
        equipes        : $lista_equipes
        sem_responsavel: {total: $total_sem_responsavel}
        total_projeto  : $total_equipes + $total_sem_responsavel
      }
    }
  }

  response = $resposta
}
