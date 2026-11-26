// Estado guardado do custo do Azure (somente leitura, sem chamar o Azure).
// Usada pelo GET e pela resposta do POST de sincronização.
//
// Custo NÃO ALOCADO do mês corrente da assinatura Azure; NÃO se mistura aos
// custos AWS, projetos ou painel (outro provedor, outra moeda).
//
// status devolvido:
//   nao_configurado | configuracao_invalida   credenciais (ver função
//                                             costguard/azure_config_estado): cadastro
//                                             da tela primeiro, variáveis do servidor
//                                             como reserva
//   sem_leitura          configurado, mas nenhuma leitura feita ainda (também logo
//                        depois de trocar/remover a conexão: a leitura guardada é
//                        apagada, pois pertencia a outra credencial/assinatura)
//   desatualizado        o último valor guardado é de OUTRO mês (virou o mês):
//                        o custo NÃO é exibido como atual (custo null);
//                        mes_referencia traz o mês do valor antigo. Continua
//                        valendo sem o cache de 4 h: depende só da virada do mês
//   ok | sem_dados | sem_permissao | indisponivel | resposta_incompleta
//                        resultado da última tentativa no mês corrente
//   configuracao_invalida  também quando o sincronizar achou o cadastro da tela quebrado
//                        (não decifra ou fora do formato; a função de configuração só
//                        decifra o tenant): ver o bloco "Cadastro da tela quebrado" abaixo
//
// `origem`: de onde vêm as credenciais em uso ("tela" = cadastro no banco,
// "servidor" = variáveis de ambiente) ou null quando nao_configurado. NÃO é a
// `origem` do POST de sincronização (esta fica lá em `origem_credencial`). Nenhum
// segredo, ID ou token é devolvido.
//
// `apelido` e `tenant_final` (exibição, NÃO são segredo; vêm da função de configuração,
// que lê colunas em texto simples do cadastro, sem decifrar nada):
//   apelido       o guardado no cadastro da tela, se não vazio; senão "Azure" (também
//                 para origem "servidor" e nao_configurado). Nunca null.
//   tenant_final  últimos 4 caracteres do tenant guardados no cadastro da tela; null
//                 quando a origem é "servidor" ou nao_configurado.
// Com origem "tela" e configuracao_invalida, os dois guardados são devolvidos mesmo
// assim (indicam qual cadastro está quebrado). O POST de sincronização não os repassa.
//
// O custo (e a moeda) só são devolvidos quando a linha tem `tem_valor = true`
// (nunca por comparação com 0/null). `atualizado_em` é o instante da última
// leitura BEM-SUCEDIDA do mês, com ou sem valor (ok ou sem_dados; "sem_dados" =
// Azure respondeu, mas sem consumo no mês: NÃO é erro, custo e moeda null).
// Vale quando > 0 na linha. "indisponivel" mantém a última leitura bem-sucedida
// do mês e o `atualizado_em` dela. No mês anterior (desatualizado) nada disso é
// devolvido: nem custo nem `atualizado_em`, para a tela não mostrar hora de mês
// antigo como atual. Mês de referência em UTC (AAAA-MM).
//
// `proxima_leitura_em`: SEM cache de 4 h, reflete só o cooldown de 60 s
// (tentativa_em + 60 s, qualquer desfecho) e o bloqueio por 429 (bloqueado_ate),
// o maior dos dois; instante já passado vira null.
function "costguard/azure_custo_estado" {
  input {
  }

  stack {
    function.run "costguard/azure_config_estado" {
      input = {}
    } as $config

    var $agora_ms { value = now|to_int }
    var $mes_atual { value = $agora_ms|format_timestamp:"Y-m":"UTC" }
    var $cooldown_ms { value = 60000 }

    var $configurado { value = ($config.estado == "ok") }
    var $status { value = $config.estado }
    var $custo { value = null }
    var $moeda { value = null }
    var $atualizado_em { value = null }
    var $mes_ref { value = null }
    var $erro_resumo { value = null }
    var $proxima { value = null }
    // Texto FIXO do cadastro da tela quebrado. É o mesmo que o sincronizar grava em
    // erro_resumo (status "indisponivel", pois a coluna `status` é um enum fechado) quando
    // o cadastro não decifra ou está fora do formato; vira "configuracao_invalida" adiante.
    var $msg_cadastro { value = "O cadastro do Azure guardado no servidor não pôde ser lido. Cadastre a conexão novamente." }

    conditional {
      if ($config.estado == "configuracao_invalida") {
        conditional {
          if ($config.origem == "tela") {
            var.update $erro_resumo { value = $msg_cadastro }
          }
          else {
            var.update $erro_resumo { value = "As variáveis de ambiente do Azure no servidor estão em formato inválido." }
          }
        }
      }
      elseif ($config.estado == "ok") {
        db.query provedor_externo_leitura {
          where = $db.provedor_externo_leitura.provedor == "azure"
          sort = {mes_referencia: "desc"}
          return = {type: "list"}
        } as $linhas

        var $ultima { value = (($linhas|count) > 0) ? ($linhas|first) : null }

        conditional {
          if ($ultima == null) {
            var.update $status { value = "sem_leitura" }
          }
          elseif ($ultima.mes_referencia != $mes_atual) {
            // Virou o mês: o valor guardado é do mês anterior e não é "atual".
            var.update $status { value = "desatualizado" }
            var.update $mes_ref { value = $ultima.mes_referencia }
            var.update $erro_resumo { value = "O último valor guardado é de um mês anterior. Sincronize para ler o mês atual." }
          }
          else {
            var.update $status { value = $ultima.status }
            var.update $mes_ref { value = $ultima.mes_referencia }

            conditional {
              if (($ultima.erro_resumo ?? "") != "") {
                var.update $erro_resumo { value = $ultima.erro_resumo }
              }
            }

            conditional {
              if ($ultima.tem_valor == true) {
                var.update $custo { value = $ultima.custo_mes_total }
                var.update $moeda { value = $ultima.moeda }
              }
            }

            // Leitura bem-sucedida (com valor ou sem consumo): instante da leitura.
            conditional {
              if (($ultima.atualizado_em ?? 0) > 0) {
                var.update $atualizado_em { value = $ultima.atualizado_em }
              }
            }

            // Próxima leitura = o MAIOR entre o cooldown de 60 s após a última
            // tentativa (qualquer desfecho) e o bloqueio por 429. Sem cache de 4 h.
            conditional {
              if (($ultima.tentativa_em ?? 0) > 0) {
                var.update $proxima { value = $ultima.tentativa_em + $cooldown_ms }
              }
            }

            conditional {
              if (($ultima.bloqueado_ate ?? 0) > $agora_ms && ($proxima == null || $ultima.bloqueado_ate > $proxima)) {
                var.update $proxima { value = $ultima.bloqueado_ate }
              }
            }
          }
        }
      }
    }

    // Cadastro da tela quebrado, detectado pelo sincronizar (que decifra os quatro
    // campos dentro do endpoint): o par status "indisponivel" + texto fixo vira
    // "configuracao_invalida", sem custo, hora de leitura, mês nem próxima leitura.
    conditional {
      if ($status == "indisponivel" && $erro_resumo == $msg_cadastro) {
        var.update $status { value = "configuracao_invalida" }
        var.update $configurado { value = false }
        var.update $custo { value = null }
        var.update $moeda { value = null }
        var.update $atualizado_em { value = null }
        var.update $mes_ref { value = null }
        var.update $proxima { value = null }
      }
    }

    // Instante já passado não é "próxima leitura".
    conditional {
      if ($proxima != null && $proxima <= $agora_ms) {
        var.update $proxima { value = null }
      }
    }

    var $resultado {
      value = {
        provedor          : "azure"
        configurado       : $configurado
        status            : $status
        nao_alocado       : true
        custo_mes_total   : $custo
        moeda             : $moeda
        atualizado_em     : $atualizado_em
        mes_referencia    : $mes_ref
        erro_resumo       : $erro_resumo
        proxima_leitura_em: $proxima
        origem            : $config.origem
        apelido           : $config.apelido
        tenant_final      : $config.tenant_final
      }
    }
  }

  response = $resultado
}
