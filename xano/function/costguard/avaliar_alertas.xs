// Avaliação de alertas: lê o estado atual e reconcilia a tabela alertas
// Com simular=true devolve as ações previstas e não grava nada. Usada pelo
// endpoint alertas/avaliar, pelo ciclo automático do inventário e pela edição
// de orçamento. A autorização é de quem chama.
function "costguard/avaliar_alertas" {
  input {
    bool simular?=false
  }

  stack {
    var $simular { value = ($input.simular == true) }

    // Janela MTD em America/Sao_Paulo (mesma regra do resumo de consumo).
    var $agora_ts { value = now|to_int }
    var $amanha_ts { value = $agora_ts + 86400000 }
    var $data_inicio { value = $agora_ts|format_timestamp:"Y-m-01":"America/Sao_Paulo" }
    var $data_fim { value = $amanha_ts|format_timestamp:"Y-m-d":"America/Sao_Paulo" }
    var $periodo { value = $agora_ts|format_timestamp:"Ym":"America/Sao_Paulo" }

    // ============================================================
    // A) Condições atuais.
    // ============================================================
    var $conds { value = [] }

    // --- Orçamento (custos_equipe do mês, somente USD) ---
    db.query projetos {
      sort = {id: "asc"}
      return = {type: "list"}
    } as $lista_projetos

    db.query custos_equipe {
      where = $db.custos_equipe.data >= $data_inicio && $db.custos_equipe.data < $data_fim
      return = {type: "list"}
    } as $linhas

    // Chaves de mapa só com [0-9a-f_k] (um "|" na chave quebra has/set).
    var $somas { value = {} }
    var $nao_usd { value = {} }

    foreach ($linhas) {
      each as $l {
        var $kp { value = "k" ~ (($l.projeto_id|to_text)|sha256) }
        conditional {
          if (($l.moeda ?? "") != "USD") {
            var.update $nao_usd { value = $nao_usd|set:$kp:true }
          }
        }
        var $soma_atual { value = $somas|get:$kp:0 }
        var.update $somas { value = $somas|set:$kp:($soma_atual + $l.valor) }
      }
    }

    foreach ($lista_projetos) {
      each as $p {
        var $kp { value = "k" ~ (($p.id|to_text)|sha256) }
        var $elegivel { value = ($p.status == "ativo" && $p.budget > 0 && ($somas|has:$kp) && ($nao_usd|has:$kp) == false) }
        var $faixa { value = null }
        var $pct { value = 0 }
        var $soma { value = 0 }

        conditional {
          if ($elegivel) {
            var.update $soma { value = $somas|get:$kp:0 }
            var.update $pct { value = $soma / $p.budget * 100 }
          }
        }

        conditional {
          if ($elegivel && $pct >= 100) {
            var.update $faixa { value = "estourado" }
          }
          elseif ($elegivel && $pct >= 90) {
            var.update $faixa { value = "critico" }
          }
          elseif ($elegivel && $pct >= 70) {
            var.update $faixa { value = "atencao" }
          }
        }

        conditional {
          if ($faixa != null) {
            var $pct_txt { value = ($pct|round:1)|to_text }
            var $msg { value = "Projeto " ~ $p.nome ~ " (" ~ $p.codigo ~ ") atingiu " ~ $pct_txt ~ "% do orçamento mensal" }
            conditional {
              if ($faixa == "estourado") {
                var.update $msg { value = "Projeto " ~ $p.nome ~ " (" ~ $p.codigo ~ ") excedeu o orçamento mensal (" ~ $pct_txt ~ "%)" }
              }
            }
            var $cond {
              value = {
                chave      : "orcamento_" ~ ($p.id|to_text) ~ "_" ~ $periodo ~ "_" ~ $faixa
                tipo       : "orcamento"
                nivel      : $faixa
                mensagem   : $msg
                detalhe    : "Custo classificado no mês: US$ " ~ (($soma|round:2)|to_text) ~ " de US$ " ~ (($p.budget|round:2)|to_text) ~ "."
                projeto_id : $p.id
                provedor_id: null
              }
            }
            var.update $conds { value = $conds|push:$cond }
          }
        }
      }
    }

    // --- Provedores: não classificados e falhas de importação ---
    db.query provedores {
      sort = {id: "asc"}
      return = {type: "list"}
    } as $lista_provedores

    db.query recursos {
      where = $db.recursos.ativo == true && ($db.recursos.projeto_id == null || $db.recursos.projeto_id == 0)
      return = {type: "list"}
    } as $nao_classificados

    foreach ($lista_provedores) {
      each as $pv {
        conditional {
          if ($pv.status != "inativo") {
            var $pid_txt { value = $pv.id|to_text }

            // Recursos sem projeto válido neste provedor.
            var $qtd_nc { value = 0 }
            foreach ($nao_classificados) {
              each as $r {
                conditional {
                  if ($r.provedor_id == $pv.id) {
                    var.update $qtd_nc { value = $qtd_nc + 1 }
                  }
                }
              }
            }

            conditional {
              if ($qtd_nc > 0) {
                var $msg_nc { value = ($qtd_nc|to_text) ~ " recursos sem projeto válido no provedor " ~ $pv.apelido }
                conditional {
                  if ($qtd_nc == 1) {
                    var.update $msg_nc { value = "1 recurso sem projeto válido no provedor " ~ $pv.apelido }
                  }
                }
                var $cond_nc {
                  value = {
                    chave      : "nao_classificado_" ~ $pid_txt
                    tipo       : "nao_classificado"
                    nivel      : "atencao"
                    mensagem   : $msg_nc
                    detalhe    : "Corrija a tag de projeto (" ~ ($pv.tag_alocacao_projeto ?? "") ~ ") na origem. Enquanto isso, o custo desses recursos fica fora dos orçamentos."
                    projeto_id : null
                    provedor_id: $pv.id
                  }
                }
                var.update $conds { value = $conds|push:$cond_nc }
              }
            }

            // Última execução de inventário.
            db.query coletas_inventario {
              where = $db.coletas_inventario.provedor_id == $pv.id
              sort = {executado_em: "desc"}
              return = {type: "single"}
            } as $ultima_inv

            conditional {
              if ($ultima_inv != null && $ultima_inv.status == "erro") {
                var $cond_inv {
                  value = {
                    chave      : "importacao_inventario_" ~ $pid_txt
                    tipo       : "importacao"
                    nivel      : "erro"
                    mensagem   : "Falha na sincronização do inventário do provedor " ~ $pv.apelido
                    detalhe    : ($ultima_inv.mensagem ?? "Falha na sincronização de recursos") ~ "."
                    projeto_id : null
                    provedor_id: $pv.id
                  }
                }
                var.update $conds { value = $conds|push:$cond_inv }
              }
            }

            // Última execução de custos por equipe.
            db.query coletas_custos_equipe {
              where = $db.coletas_custos_equipe.provedor_id == $pv.id
              sort = {executado_em: "desc"}
              return = {type: "single"}
            } as $ultima_custos

            conditional {
              if ($ultima_custos != null && $ultima_custos.status == "erro") {
                var $cond_custos {
                  value = {
                    chave      : "importacao_custos_" ~ $pid_txt
                    tipo       : "importacao"
                    nivel      : "erro"
                    mensagem   : "Falha na importação de custos por equipe do provedor " ~ $pv.apelido
                    detalhe    : ($ultima_custos.mensagem ?? "Falha na classificação de custos por equipe") ~ "."
                    projeto_id : null
                    provedor_id: $pv.id
                  }
                }
                var.update $conds { value = $conds|push:$cond_custos }
              }
            }

            // Provedor com erro de conexão.
            conditional {
              if ($pv.status == "erro") {
                var $cond_con {
                  value = {
                    chave      : "importacao_conexao_" ~ $pid_txt
                    tipo       : "importacao"
                    nivel      : "erro"
                    mensagem   : "Provedor " ~ $pv.apelido ~ " com erro de conexão"
                    detalhe    : "Revise as credenciais e execute o teste de conexão em Provedores."
                    projeto_id : null
                    provedor_id: $pv.id
                  }
                }
                var.update $conds { value = $conds|push:$cond_con }
              }
            }
          }
        }
      }
    }

    // ============================================================
    // B) Reconciliação com os episódios ativos.
    // ============================================================
    db.query alertas {
      where = $db.alertas.condicao_ativa == true
      return = {type: "list"}
    } as $episodios

    var $chaves_atuais { value = {} }
    foreach ($conds) {
      each as $c {
        var $ck { value = $c.chave }
        var.update $chaves_atuais { value = $chaves_atuais|set:$ck:true }
      }
    }

    var $episodio_por_chave { value = {} }
    foreach ($episodios) {
      each as $e {
        var $ek { value = $e.chave }
        var.update $episodio_por_chave { value = $episodio_por_chave|set:$ek:$e }
      }
    }

    var $acoes_resolver { value = [] }
    var $acoes_criar { value = [] }
    var $acoes_atualizar { value = [] }

    // Condição encerrada: fim do episódio e resolução automática se aberto.
    foreach ($episodios) {
      each as $e {
        var $ek2 { value = $e.chave }
        conditional {
          if (($chaves_atuais|has:$ek2) == false) {
            var $acao_r { value = {id: $e.id, chave: $e.chave, estava_aberto: ($e.resolvido == false)} }
            var.update $acoes_resolver { value = $acoes_resolver|push:$acao_r }

            conditional {
              if ($simular == false && $e.resolvido == false) {
                db.edit alertas {
                  field_name = "id"
                  field_value = $e.id
                  data = {
                    condicao_ativa: false
                    resolvido     : true
                    resolucao     : "automatica"
                    resolvido_em  : now
                    atualizado_em : now
                  }
                } as $editado_r
              }
              elseif ($simular == false) {
                db.edit alertas {
                  field_name = "id"
                  field_value = $e.id
                  data = {condicao_ativa: false, atualizado_em: now}
                } as $editado_r2
              }
            }
          }
        }
      }
    }

    // Condição presente: cria episódio novo ou atualiza o texto do ativo.
    foreach ($conds) {
      each as $c {
        var $ck2 { value = $c.chave }
        conditional {
          if ($episodio_por_chave|has:$ck2) {
            var $atual { value = $episodio_por_chave|get:$ck2:null }
            conditional {
              if ($atual.mensagem != $c.mensagem || ($atual.detalhe ?? "") != $c.detalhe) {
                var $acao_a { value = {id: $atual.id, chave: $c.chave, mensagem: $c.mensagem} }
                var.update $acoes_atualizar { value = $acoes_atualizar|push:$acao_a }
                conditional {
                  if ($simular == false) {
                    db.edit alertas {
                      field_name = "id"
                      field_value = $atual.id
                      data = {mensagem: $c.mensagem, detalhe: $c.detalhe, atualizado_em: now}
                    } as $editado_a
                  }
                }
              }
            }
          }
          else {
            var.update $acoes_criar { value = $acoes_criar|push:$c }
            conditional {
              if ($simular == false) {
                db.add alertas {
                  data = {
                    tipo          : $c.tipo
                    nivel         : $c.nivel
                    mensagem      : $c.mensagem
                    detalhe       : $c.detalhe
                    chave         : $c.chave
                    projeto_id    : $c.projeto_id
                    provedor_id   : $c.provedor_id
                    condicao_ativa: true
                    resolvido     : false
                  }
                } as $novo_alerta
              }
            }
          }
        }
      }
    }

    // Avaliações simultâneas podem criar dois episódios ativos para a mesma
    // chave: mantém o de menor id e encerra os demais (alertas nunca são excluídos).
    var $duplicados { value = [] }
    conditional {
      if ($simular == false) {
        db.query alertas {
          where = $db.alertas.condicao_ativa == true
          sort = {id: "asc"}
          return = {type: "list"}
        } as $ativos_final

        var $vistos { value = {} }
        foreach ($ativos_final) {
          each as $af {
            var $afk { value = $af.chave }
            conditional {
              if ($vistos|has:$afk) {
                var.update $duplicados { value = $duplicados|push:$af.id }
                // Resolução manual existente é preservada (só encerra o episódio).
                conditional {
                  if ($af.resolvido == true) {
                    db.edit alertas {
                      field_name = "id"
                      field_value = $af.id
                      data = {condicao_ativa: false, atualizado_em: now}
                    } as $dup_encerrado_r
                  }
                  else {
                    db.edit alertas {
                      field_name = "id"
                      field_value = $af.id
                      data = {
                        condicao_ativa: false
                        resolvido     : true
                        resolucao     : "automatica"
                        resolvido_em  : now
                        atualizado_em : now
                      }
                    } as $dup_encerrado
                  }
                }
              }
              else {
                var.update $vistos { value = $vistos|set:$afk:true }
              }
            }
          }
        }
      }
    }

    var $resposta {
      value = {
        simular   : $simular
        periodo   : $periodo
        condicoes : ($conds|count)
        criar     : $acoes_criar
        atualizar : $acoes_atualizar
        resolver  : $acoes_resolver
        duplicados_encerrados: $duplicados
      }
    }
  }

  response = $resposta
}
