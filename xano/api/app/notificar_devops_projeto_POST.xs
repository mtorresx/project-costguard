// Alerta de orçamento por e-mail ao DevOps do projeto.
//
// Envia UM e-mail, via API REST do Resend, ao `email_devops` JÁ CADASTRADO do
// projeto. O endpoint NÃO tem input de destinatário: qualquer campo extra do
// corpo é ignorado. QUALQUER usuário autenticado e ATIVO (admin ou leitura) pode
// acionar; criar/editar o e-mail do projeto continua só admin. Envio SOMENTE
// manual: nada no ciclo/sincronização chama este endpoint. Limite: 1 envio por
// projeto a cada 5 minutos (HTTP 429 depois), registrado só quando o Resend
// ACEITA o envio; o registro guarda QUANDO (devops_ultimo_envio_em) e QUEM
// (devops_ultimo_envio_por, id do usuário) na própria linha do projeto.
//
// Projeto INATIVO: HTTP 400 ("Este projeto está inativo; ..."), antes de qualquer
// trava, ficha ou envio (conferido de novo dentro da seção crítica).
//
// TETO DIÁRIO GLOBAL: no máximo 30 envios por dia civil (America/Sao_Paulo),
// somando TODOS os projetos. Constante no código (a lista de 30 fichas abaixo);
// não é configurável. Ao estourar: HTTP 429 com mensagem FIXA, sem número de
// segundos. Mecanismo: "fichas" na tabela `travas` já existente (sem tabela nova):
// linhas `devops_dia_<AAAA-MM-DD>_<n>`, n = 1..30, tomadas com db.add sob o
// índice único de `nome` (atômico: nunca existem mais de 30 fichas no dia, logo
// nunca mais de 30 envios aceitos, mesmo com dois projetos ao mesmo tempo). A
// ficha só fica CONSUMIDA quando o Resend ACEITA o envio; em qualquer outro
// desfecho (recusa, timeout, falha do alerta, exceção) é devolvida no finally.
// Crescimento: no máximo 30 linhas por dia; o script de limpeza do banco já
// apaga `travas` (sem rotina própria). Ficha órfã (queda do servidor entre
// tomar e devolver) fica consumida: erra para o lado seguro.
//
// ORDEM DAS CHECAGENS: 1) autenticação (401); 2) projeto existe (404); 3) projeto
// ativo (400); 4) tem e-mail (400); 5) e-mail configurado no servidor (500);
// 6) trava do projeto (429 "em andamento"); depois, já com a trava: 7) sessão,
// projeto, ativo e e-mail relidos; 8) limite de 5 min por projeto (429 com
// segundos); 9) teto diário (429 sem segundos); 10) conteúdo do alerta; 11) envio.
// O teto só é tocado depois das recusas 1 a 8 e a ficha é devolvida se o alerta
// não for aceito: chamada recusada nunca gasta o teto.
//
// Conteúdo do e-mail (HTML + texto puro, campos "html" e "text" do Resend):
// nome do projeto, mês de referência por extenso (pt-BR), orçamento, gasto no
// mês, percentual com barra de consumo, selo da NÍVEL/faixa (verde, amarelo,
// vermelho), quantidade de recursos sem equipe, nome (nunca o e-mail) de quem
// enviou e botão com o link do projeto. Valores em formato brasileiro ("US$
// 5.000,00", "12,5%") por funções, sem locale. Linha "Consumo do orçamento" sem
// faixa (sem percentual nem barra): orçamento zero ou nulo = "Orçamento não
// definido"; orçamento positivo sem custo em USD no mês = "Consumo indisponível
// (sem custo em USD no mês)". Layout,
// cabeçalho, botão e rodapé vêm de costguard/email_html_layout.
// Custo, percentual e nível vêm de costguard/resumo_consumo (mesma fonte e
// mesmas faixas 70/90/100 de GET /projetos/resumo-consumo-mtd).
// Nomenclatura do nível: a de /projetos (Normal, Atenção, Crítico, Estourado).
// DIVERGÊNCIA CONHECIDA: /inicio e /alertas chamam as mesmas faixas de Aviso
// (90%) e Excedido (100%); por isso o rótulo traz a faixa entre parênteses.
//
// Segurança:
//   - chave em $env.EMAIL_API_KEY e remetente em $env.EMAIL_FROM; sem uma das
//     duas, nada é enviado (a API nem é chamada). A base do link vem de
//     $env.COSTGUARD_APP_URL (https, sem barra final, no máximo 208 caracteres no
//     total; inválida, longa demais ou ausente cai
//     no padrão https://app.costguard.com.br);
//   - assunto "[CostGuard] Orçamento em alerta: PROJETO (faixa)", montado só com o
//     nome do projeto já sem CR/LF/tabulação, com \r e \n removidos do assunto
//     inteiro; nenhum cabeçalho dinâmico além do Authorization e da chave de
//     idempotência (só id e janela);
//   - TODO texto livre do banco (nome do projeto, nome de quem enviou) passa por
//     costguard/limpar_texto_linha (texto/assunto) e, no HTML, também por
//     costguard/escapar_html (& < > " '); os demais valores dinâmicos são
//     números formatados, rótulos fixos ou o id do projeto. O e-mail do usuário
//     NUNCA entra no corpo;
//   - o corpo/erro do Resend nunca é repassado, registrado ou devolvido;
//   - a resposta nunca traz o endereço completo: o ADMIN recebe a mensagem com o
//     endereço MASCARADO; os demais perfis recebem mensagem fixa, sem nenhuma
//     parte do endereço. A máscara é calculada ANTES da chamada ao Resend, para
//     que nenhuma exceção posterior ao envio vire erro (e convide a duplicata).
// Sem retentativa: uma única chamada ao Resend por requisição.
//
// Timeout ambíguo (RISCO ACEITO): se a chamada ao Resend estoura o tempo, o
// servidor NÃO sabe se o e-mail foi enviado. Nesse caso responde erro e NÃO
// consome o limite, então o admin pode tentar de novo e o destinatário pode
// receber DUPLICATA. Mitigação: o cabeçalho `Idempotency-Key`, derivado só do
// id do projeto e da janela de 5 minutos (sem nome nem e-mail), faz o Resend
// tratar repetições na mesma janela como o mesmo envio. NÃO VERIFICADO: se o
// Resend honra o cabeçalho neste endpoint (é inofensivo se for ignorado); e,
// se honra, como reage a uma repetição com conteúdo diferente (consumo mudou)
// ou depois de uma falha na mesma janela. Repetições que cruzam a virada da
// janela recebem outra chave: a mitigação é parcial.
query "projetos/{id}/notificar-devops" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "projetos"
    }
  }

  stack {
    // Autorização: qualquer usuário autenticado e ATIVO (admin ou leitura),
    // validado no backend. Usuário removido ou desativado perde o acesso (401).
    db.get usuarios {
      field_name = "id"
      field_value = $auth.id
    } as $usuario_logado

    precondition ($usuario_logado != null && $usuario_logado.status == "ativo") {
      error_type = "unauthorized"
      error = "Token inválido ou expirado"
    }

    db.get projetos {
      field_name = "id"
      field_value = $input.id
    } as $projeto_alvo

    precondition ($projeto_alvo != null) {
      error_type = "notfound"
      error = "Projeto não encontrado"
    }

    // Projeto inativo não é notificado: recusa ANTES de qualquer trava, ficha ou envio.
    precondition ($projeto_alvo.status == "ativo") {
      error_type = "inputerror"
      error = "Este projeto está inativo; não é possível notificar o DevOps."
    }

    // Destinatário: SOMENTE o e-mail gravado no projeto, revalidado.
    function.run "costguard/normalizar_email_devops" {
      input = {email: ($projeto_alvo.email_devops ?? "")}
    } as $email_pre

    precondition ($email_pre.vazio == false && $email_pre.valido == true) {
      error_type = "inputerror"
      error = "Este projeto não tem e-mail do DevOps cadastrado."
    }

    // Configuração do e-mail: sem chave ou remetente, NADA é enviado.
    var $email_chave { value = ($env.EMAIL_API_KEY ?? "") }
    var $email_from { value = ($env.EMAIL_FROM ?? "") }

    precondition ($email_chave != "" && $email_from != "") {
      error_type = "standard"
      error = "O envio de e-mail não está configurado no servidor."
    }

    // Base do link do projeto: $env.COSTGUARD_APP_URL, só se for https://host
    // (letras, dígitos, ponto, hífen, porta opcional; SEM barra final nem caminho).
    // Qualquer outro valor (ou ausente) usa o padrão. Fica antes da trava.
    // NÃO VERIFICADO no Xano: leitura de $env opcional e `substr` com início.
    var $app_url_bruto { value = (($env.COSTGUARD_APP_URL ?? "")|trim) }
    var $app_url { value = "https://app.costguard.com.br" }

    // O valor INTEIRO vira o href: por isso o tamanho total é limitado a 208
    // (8 do prefixo + 200 do host, a mesma janela do `substr`). Mais longo = padrão.
    conditional {
      if (($app_url_bruto|strlen) > 8 && ($app_url_bruto|strlen) <= 208) {
        var $app_url_prefixo { value = $app_url_bruto|substr:0:8 }
        var $app_url_host { value = $app_url_bruto|substr:8:200 }

        conditional {
          if ($app_url_prefixo == "https://" && ("/^[a-zA-Z0-9][a-zA-Z0-9.-]*(:[0-9]{1,5})?$/"|regex_matches:$app_url_host)) {
            var.update $app_url { value = $app_url_bruto }
          }
        }
      }
    }

    var $link_projeto { value = $app_url ~ "/projetos/" ~ ($input.id|to_text) }

    // ============================================================
    // Trava de exclusão mútua por projeto (tabela travas, índice único em
    // `nome`): torna atômico o par "conferir o limite + enviar + registrar" e
    // impede dois envios simultâneos do mesmo projeto. A trava é removida no
    // finally; uma trava órfã (> 2 min, bem acima do timeout do envio) é
    // removida na primeira tentativa da aquisição seguinte.
    // ============================================================
    var $trava_nome { value = "devops_projeto_" ~ ($input.id|to_text) }
    var $trava_id { value = null }
    var $trava_ocupada { value = false }

    foreach ([1, 2]) {
      each as $tentativa {
        conditional {
          if ($trava_id == null && $trava_ocupada == false) {
            try_catch {
              try {
                var $agora_trava { value = now|to_int }
                db.add travas {
                  data = {nome: $trava_nome, adquirida_em: $agora_trava}
                } as $nova_trava
                var.update $trava_id { value = $nova_trava.id }
              }
              catch {
                db.get travas {
                  field_name = "nome"
                  field_value = $trava_nome
                } as $trava_atual
                conditional {
                  if ($trava_atual != null) {
                    var $agora_cmp { value = now|to_int }
                    var $idade_trava { value = $agora_cmp - $trava_atual.adquirida_em }
                    conditional {
                      if ($idade_trava > 120000 && $tentativa == 1) {
                        db.del travas {
                          field_name = "id"
                          field_value = $trava_atual.id
                        }
                      }
                      else {
                        var.update $trava_ocupada { value = true }
                      }
                    }
                  }
                  else {
                    var.update $trava_ocupada { value = true }
                  }
                }
              }
            }
          }
        }
      }
    }

    precondition ($trava_id != null) {
      error_type = "toomanyrequests"
      error = "Já existe um envio em andamento para este projeto. Tente novamente em instantes."
    }

    // Seção crítica: não lança erro; registra o desfecho em variáveis, libera a
    // trava no finally e só depois responde.
    var $estado { value = "" }
    var $falha { value = false }
    var $segundos_restantes { value = 0 }
    var $mascarado { value = "" }
    var $eh_admin { value = false }
    var $registro_falhou { value = false }
    var $limite_ms { value = 300000 }

    // Ficha do teto diário: id da linha em `travas` (nulo = nenhuma tomada) e se o
    // Resend ACEITOU o envio (só então a ficha permanece consumida).
    var $ficha_id { value = null }
    var $ficha_aceita { value = false }
    var $ficha_ocupadas { value = 0 }
    var $ficha_liberacao_falhou { value = false }

    try_catch {
      try {
        // Releitura com a trava: sessão, projeto e destinatário atuais.
        db.get usuarios {
          field_name = "id"
          field_value = $auth.id
        } as $solicitante_atual

        // Só decide o TEXTO da resposta (admin vê o endereço mascarado); NÃO
        // restringe o envio: admin e leitura continuam podendo notificar.
        var.update $eh_admin { value = ($solicitante_atual != null) ? ($solicitante_atual.role == "admin") : false }

        db.get projetos {
          field_name = "id"
          field_value = $input.id
        } as $proj_atual

        conditional {
          if ($solicitante_atual == null || $solicitante_atual.status != "ativo") {
            var.update $estado { value = "sem_sessao" }
          }
          elseif ($proj_atual == null) {
            var.update $estado { value = "sem_projeto" }
          }
          elseif ($proj_atual.status != "ativo") {
            var.update $estado { value = "projeto_inativo" }
          }
        }

        var $email_gravado { value = ($proj_atual != null) ? ($proj_atual.email_devops ?? "") : "" }

        function.run "costguard/normalizar_email_devops" {
          input = {email: $email_gravado}
        } as $email_atual

        var $destino { value = $email_atual.email }

        conditional {
          if ($estado == "" && ($email_atual.vazio == true || $email_atual.valido == false)) {
            var.update $estado { value = "sem_destino" }
          }
        }

        // Limite: 1 envio por projeto a cada 5 minutos.
        var $agora_ms { value = now|to_int }
        var $ultimo_envio { value = ($proj_atual != null) ? ($proj_atual.devops_ultimo_envio_em ?? 0) : 0 }
        var $decorrido_ms { value = $agora_ms - $ultimo_envio }

        conditional {
          if ($estado == "" && $ultimo_envio > 0 && $decorrido_ms < $limite_ms) {
            // Relógio adiantado (decorrido negativo) nunca passa de 5 min.
            // Segundos = resto/1000 arredondado e depois LIMITADO a [1, 300]:
            // o limite não depende do comportamento exato de `round`.
            // NÃO VERIFICADO: o tipo devolvido por `/` e por `round:0` no Xano
            // (inteiro ou decimal) e o texto de `to_text` do inteiro.
            var $resto_ms { value = ($decorrido_ms < 0) ? $limite_ms : ($limite_ms - $decorrido_ms) }
            var.update $segundos_restantes { value = (($resto_ms / 1000)|round:0)|to_int }

            conditional {
              if ($segundos_restantes < 1) {
                var.update $segundos_restantes { value = 1 }
              }
              elseif ($segundos_restantes > 300) {
                var.update $segundos_restantes { value = 300 }
              }
            }

            var.update $estado { value = "limite" }
          }
        }

        // Teto diário GLOBAL: 30 envios por dia civil de America/Sao_Paulo, somando
        // todos os projetos. Só chega aqui quem passou por todas as recusas
        // anteriores (sessão, projeto, ativo, e-mail e limite de 5 min).
        // Dia civil: o instante menos 3 h (UTC-3), formatado em UTC. O Brasil não
        // tem horário de verão desde 2019, então America/Sao_Paulo = UTC-3 fixo.
        // Escolhido no lugar do nome de fuso em `format_timestamp` por simplicidade
        // e para o teto não depender de base de fusos. O fuso "America/Sao_Paulo"
        // com `format_timestamp` JÁ é usado em costguard/resumo_consumo e
        // costguard/avaliar_alertas; a dúvida real (NÃO VERIFICADO) é só o formato
        // "d/m/Y" sobre timestamp de tabela (usado no aviso de recursos). Se o Brasil
        // voltar ao horário de verão, o dia vira com 1 h de erro (o teto continua valendo).
        var $agora_brt_ms { value = $agora_ms - 10800000 }
        var $dia_civil { value = $agora_brt_ms|format_timestamp:"Y-m-d":"UTC" }

        // As 30 fichas do dia (o TETO é o tamanho desta lista). db.add falha no
        // índice único quando a ficha já existe; então tenta a próxima. Nenhuma
        // ficha livre = teto atingido. A ficha tomada só fica consumida se o
        // Resend aceitar (ver o finally).
        conditional {
          if ($estado == "") {
            foreach ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]) {
              each as $n_ficha {
                conditional {
                  if ($ficha_id == null) {
                    try_catch {
                      try {
                        db.add travas {
                          data = {nome: "devops_dia_" ~ $dia_civil ~ "_" ~ ($n_ficha|to_text), adquirida_em: $agora_ms}
                        } as $nova_ficha
                        var.update $ficha_id { value = $nova_ficha.id }
                      }
                      catch {
                        var.update $ficha_ocupadas { value = $ficha_ocupadas + 1 }
                      }
                    }
                  }
                }
              }
            }

            conditional {
              if ($ficha_id == null) {
                var.update $estado { value = "teto_diario" }
              }
            }
          }
        }

        conditional {
          if ($estado == "") {
            // Mesmas regras de consumo e faixas 70/90/100 do resto do sistema.
            function.run "costguard/resumo_consumo" {
              input = {mes: ""}
            } as $resumo

            var $item_resumo { value = null }
            foreach ($resumo.projetos) {
              each as $it {
                conditional {
                  if ($it.id == $input.id) {
                    var.update $item_resumo { value = $it }
                  }
                }
              }
            }

            conditional {
              if ($item_resumo == null) {
                var.update $estado { value = "falha_resumo" }
              }
              else {
                // Valores numéricos/enumerados do resumo: não vêm do usuário.
                // FORMATAÇÃO BRASILEIRA (sem locale): costguard/formatar_numero_br
                // recebe o valor já multiplicado (centavos ou décimos, inteiro) e
                // devolve "5.000,00" / "12,5"; o mês sai por extenso de
                // costguard/mes_extenso_pt_br ("novembro de 2026").
                var $mes_ref { value = $resumo.mes }

                function.run "costguard/mes_extenso_pt_br" {
                  input = {mes: $mes_ref}
                } as $mes_extenso

                // Defesa em profundidade: mesmo sendo texto de mapa fixo (ou vazio),
                // o mês passa por escapar_html antes de entrar no HTML; o texto puro
                // usa a versão sem escape.
                function.run "costguard/escapar_html" {
                  input = {texto: $mes_extenso}
                } as $mes_html

                // Orçamento zero (ou negativo): "Orçamento não definido".
                var $orcamento_txt { value = "Orçamento não definido" }

                conditional {
                  if ($item_resumo.budget > 0) {
                    var $orc_centavos { value = ((($item_resumo.budget ?? 0) * 100)|round:0)|to_int }

                    function.run "costguard/formatar_numero_br" {
                      input = {escalado: $orc_centavos, casas: 2}
                    } as $orc_fmt

                    var.update $orcamento_txt { value = "US$ " ~ $orc_fmt }
                  }
                }

                // Consumo do orçamento. O teste usa `faixa` (texto, só é nulo sem
                // custo em USD/orçamento) e NÃO o percentual: no XanoScript um
                // decimal 0 == null, então 0% seria confundido com "indisponível".
                // Sem faixa o percentual e a barra NÃO são calculados e a linha diz:
                // orçamento zero ou nulo = "Orçamento não definido"; orçamento
                // positivo (budget > 0) sem custo em USD no mês = "Consumo
                // indisponível (sem custo em USD no mês)".
                // A largura da barra (célula de tabela com width em %) é inteira e
                // LIMITADA a 0..100 (0% < p < 1% mostra 1% para a barra aparecer).
                var $pct_txt { value = "Orçamento não definido" }

                conditional {
                  if ($item_resumo.budget > 0) {
                    var.update $pct_txt { value = "Consumo indisponível (sem custo em USD no mês)" }
                  }
                }

                var $pct_largura { value = 0 }

                conditional {
                  if ($item_resumo.faixa != null) {
                    var $pct_decimos { value = ((($item_resumo.percentual_usado ?? 0) * 10)|round:0)|to_int }

                    function.run "costguard/formatar_numero_br" {
                      input = {escalado: $pct_decimos, casas: 1}
                    } as $pct_fmt

                    var.update $pct_txt { value = $pct_fmt ~ "%" }
                    var.update $pct_largura { value = (($item_resumo.percentual_usado ?? 0)|round:0)|to_int }

                    conditional {
                      if ($pct_largura < 1 && $pct_decimos > 0) {
                        var.update $pct_largura { value = 1 }
                      }
                      elseif ($pct_largura < 0) {
                        var.update $pct_largura { value = 0 }
                      }
                      elseif ($pct_largura > 100) {
                        var.update $pct_largura { value = 100 }
                      }
                    }
                  }
                }

                var $nivel_rotulo { value = "Indisponível (sem custo em USD no período ou orçamento zerado)" }

                // Selo da faixa: rótulo curto (assunto e selo), cor do texto/da
                // barra e cor de fundo do selo. Verde = normal, amarelo = atenção,
                // vermelho = crítico e estourado; cinza = indisponível.
                var $faixa_curta { value = "Indisponível" }
                var $cor_faixa { value = "#6b7280" }
                var $fundo_faixa { value = "#f3f4f6" }

                // Nível do alerta: rótulos de /projetos, com a faixa entre
                // parênteses (em /inicio e /alertas Crítico = Aviso e
                // Estourado = Excedido).
                conditional {
                  if ($item_resumo.faixa == "estourado") {
                    var.update $nivel_rotulo { value = "Estourado (100% ou mais do orçamento)" }
                    var.update $faixa_curta { value = "Estourado" }
                    var.update $cor_faixa { value = "#991b1b" }
                    var.update $fundo_faixa { value = "#fee2e2" }
                  }
                  elseif ($item_resumo.faixa == "critico") {
                    var.update $nivel_rotulo { value = "Crítico (a partir de 90% do orçamento)" }
                    var.update $faixa_curta { value = "Crítico" }
                    var.update $cor_faixa { value = "#dc2626" }
                    var.update $fundo_faixa { value = "#fee2e2" }
                  }
                  elseif ($item_resumo.faixa == "atencao") {
                    var.update $nivel_rotulo { value = "Atenção (a partir de 70% do orçamento)" }
                    var.update $faixa_curta { value = "Atenção" }
                    var.update $cor_faixa { value = "#b45309" }
                    var.update $fundo_faixa { value = "#fef3c7" }
                  }
                  elseif ($item_resumo.faixa == "normal") {
                    var.update $nivel_rotulo { value = "Normal (abaixo de 70% do orçamento)" }
                    var.update $faixa_curta { value = "Normal" }
                    var.update $cor_faixa { value = "#15803d" }
                    var.update $fundo_faixa { value = "#dcfce7" }
                  }
                }

                // Custo do mês (mesma fonte da listagem: custo_mtd do resumo).
                // O teste usa `custo_status` (texto) e NÃO o valor: decimal 0 == null.
                // Moeda diferente de USD ou moedas mistas nunca são somadas nem
                // convertidas: o e-mail diz "indisponível", sem inventar valor.
                var $custo_txt { value = "sem custo registrado no mês" }

                conditional {
                  if ($item_resumo.custo_status == "ok") {
                    var $custo_centavos { value = ((($item_resumo.custo_mtd ?? 0) * 100)|round:0)|to_int }

                    function.run "costguard/formatar_numero_br" {
                      input = {escalado: $custo_centavos, casas: 2}
                    } as $custo_fmt

                    var.update $custo_txt { value = "US$ " ~ $custo_fmt }
                  }
                  elseif ($item_resumo.custo_status == "moedas_mistas") {
                    var.update $custo_txt { value = "indisponível (moedas diferentes no mês)" }
                  }
                  elseif ($item_resumo.custo_status == "moeda_incompativel") {
                    var.update $custo_txt { value = "indisponível (custo em moeda diferente de USD)" }
                  }
                }

                // Recursos sem tag de equipe do projeto: recursos ATIVOS do
                // projeto sem equipe vinculada (equipe_id nulo ou 0, o Xano grava
                // a FK nula como 0) E sem valor em codigo_equipe_tag. É a mesma
                // regra do bloco "Recursos sem responsável" da tela do projeto.
                // Falha na consulta NÃO bloqueia o alerta: o e-mail diz "indisponível".
                var $qtd_sem_tag { value = 0 }
                var $sem_tag_ok { value = false }

                try_catch {
                  try {
                    db.query recursos {
                      where = $db.recursos.projeto_id == $input.id && $db.recursos.ativo == true && ($db.recursos.equipe_id == null || $db.recursos.equipe_id == 0)
                      return = {type: "list"}
                    } as $recursos_sem_equipe

                    foreach ($recursos_sem_equipe) {
                      each as $rs {
                        conditional {
                          if ((($rs.codigo_equipe_tag ?? "")|trim) == "") {
                            var.update $qtd_sem_tag { value = $qtd_sem_tag + 1 }
                          }
                        }
                      }
                    }

                    var.update $sem_tag_ok { value = true }
                  }
                  catch {
                    var.update $sem_tag_ok { value = false }
                  }
                }

                var $sem_tag_txt { value = ($sem_tag_ok == true) ? ($qtd_sem_tag|to_text) : "indisponível" }

                // Textos LIVRES vindos do banco: o nome do projeto e o nome de quem
                // acionou o envio (SÓ o nome, nunca o e-mail). Cada um passa por
                // costguard/limpar_texto_linha (sem CR/LF/tabulação, aparado, até 120
                // caracteres) = versão do TEXTO PURO e do assunto; e, só para o HTML,
                // por costguard/escapar_html (& < > " '). O HTML nunca usa a versão
                // "limpa" crua, e o texto puro nunca usa a escapada.
                function.run "costguard/limpar_texto_linha" {
                  input = {texto: ($proj_atual.nome ?? "")}
                } as $nome_limpo

                function.run "costguard/escapar_html" {
                  input = {texto: $nome_limpo}
                } as $nome_html

                function.run "costguard/limpar_texto_linha" {
                  input = {texto: ($solicitante_atual.nome ?? "")}
                } as $enviado_limpo

                conditional {
                  if ($enviado_limpo == "") {
                    var.update $enviado_limpo { value = "Usuário do CostGuard" }
                  }
                }

                function.run "costguard/escapar_html" {
                  input = {texto: $enviado_limpo}
                } as $enviado_html

                // Autoverificação do escape: com < ou > restante, nada é enviado.
                var $escapados_juntos { value = $nome_html ~ $enviado_html ~ $mes_html }

                conditional {
                  if ("/[<>]/"|regex_matches:$escapados_juntos) {
                    var.update $estado { value = "falha_conteudo" }
                  }
                }

                conditional {
                  if ($estado == "") {
                    // Assunto: "[CostGuard] Orçamento em alerta: PROJETO (faixa)". O nome
                    // já vem sem CR/LF/tabulação (limpar_texto_linha); o assunto inteiro
                    // ainda tem \r e \n removidos (cabeçalho nunca recebe quebra de linha).
                    var $assunto {
                      value = (("[CostGuard] Orçamento em alerta: " ~ $nome_limpo ~ " (" ~ $faixa_curta ~ ")")|replace:"\r":"")|replace:"\n":""
                    }

                    // Texto puro (sem escape HTML): campos de uma linha já sem CR/LF.
                    var $texto { value = "CostGuard - Alerta de orçamento\n\n" }
                    var.update $texto { value = $texto ~ "Projeto: " ~ $nome_limpo ~ "\n" }
                    var.update $texto { value = $texto ~ "Mês de referência: " ~ $mes_extenso ~ "\n" }
                    var.update $texto { value = $texto ~ "Orçamento: " ~ $orcamento_txt ~ "\n" }
                    var.update $texto { value = $texto ~ "Gasto no mês: " ~ $custo_txt ~ "\n" }
                    var.update $texto { value = $texto ~ "Consumo do orçamento: " ~ $pct_txt ~ "\n" }
                    var.update $texto { value = $texto ~ "Nível do alerta: " ~ $nivel_rotulo ~ "\n" }
                    var.update $texto { value = $texto ~ "Recursos sem equipe: " ~ $sem_tag_txt ~ "\n" }
                    var.update $texto { value = $texto ~ "Enviado por: " ~ $enviado_limpo ~ "\n\n" }
                    var.update $texto { value = $texto ~ "Abrir projeto no CostGuard: " ~ $link_projeto ~ "\n\n" }
                    var.update $texto { value = $texto ~ "Alerta manual enviado pelo CostGuard\n" }

                    // Selo da faixa (cores fixas por faixa; nenhum dado do usuário).
                    var $h_selo {
                      value = "<span style='display:inline-block;padding:3px 12px;border-radius:12px;background-color:" ~ $fundo_faixa ~ ";color:" ~ $cor_faixa ~ ";font-size:13px;font-weight:bold;'>" ~ $faixa_curta ~ "</span>"
                    }

                    // Barra de consumo: tabela de 1 linha com células de largura em %
                    // (preenchida + restante). Só existe com faixa; a largura já está
                    // limitada a 0..100. Sem faixa ("Orçamento não definido"): sem barra.
                    var $h_barra_linha { value = "" }

                    conditional {
                      if ($item_resumo.faixa != null) {
                        var $barra_resto { value = 100 - $pct_largura }
                        var $h_barra_celulas { value = "" }

                        conditional {
                          if ($pct_largura > 0) {
                            var.update $h_barra_celulas {
                              value = $h_barra_celulas ~ "<td width='" ~ ($pct_largura|to_text) ~ "%' bgcolor='" ~ $cor_faixa ~ "' style='width:" ~ ($pct_largura|to_text) ~ "%;background-color:" ~ $cor_faixa ~ ";height:10px;line-height:10px;font-size:1px;'>&nbsp;</td>"
                            }
                          }
                        }

                        conditional {
                          if ($barra_resto > 0) {
                            var.update $h_barra_celulas {
                              value = $h_barra_celulas ~ "<td width='" ~ ($barra_resto|to_text) ~ "%' bgcolor='#e5e7eb' style='width:" ~ ($barra_resto|to_text) ~ "%;background-color:#e5e7eb;height:10px;line-height:10px;font-size:1px;'>&nbsp;</td>"
                            }
                          }
                        }

                        var.update $h_barra_linha {
                          value = "<tr><td colspan='2' style='padding:4px 0 12px 0;'><table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='width:100%;'><tr>" ~ $h_barra_celulas ~ "</tr></table></td></tr>"
                        }
                      }
                    }

                    // Linhas da tabela de dados: o valor é HTML seguro (texto do banco
                    // já escapado, números formatados ou rótulos fixos).
                    function.run "costguard/email_html_linha" {
                      input = {rotulo: "Projeto", valor_html: $nome_html}
                    } as $h_projeto

                    function.run "costguard/email_html_linha" {
                      input = {rotulo: "Mês de referência", valor_html: $mes_html}
                    } as $h_mes

                    function.run "costguard/email_html_linha" {
                      input = {rotulo: "Orçamento", valor_html: $orcamento_txt}
                    } as $h_orcamento

                    function.run "costguard/email_html_linha" {
                      input = {rotulo: "Gasto no mês", valor_html: $custo_txt}
                    } as $h_gasto

                    function.run "costguard/email_html_linha" {
                      input = {rotulo: "Consumo do orçamento", valor_html: $pct_txt}
                    } as $h_consumo

                    function.run "costguard/email_html_linha" {
                      input = {rotulo: "Nível do alerta", valor_html: $h_selo}
                    } as $h_nivel

                    function.run "costguard/email_html_linha" {
                      input = {rotulo: "Recursos sem equipe", valor_html: $sem_tag_txt}
                    } as $h_sem_equipe

                    function.run "costguard/email_html_linha" {
                      input = {rotulo: "Enviado por", valor_html: $enviado_html}
                    } as $h_enviado

                    var $h_conteudo {
                      value = "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='width:100%;'>" ~ $h_projeto ~ $h_mes ~ $h_orcamento ~ $h_gasto ~ $h_consumo ~ $h_barra_linha ~ $h_nivel ~ $h_sem_equipe ~ $h_enviado ~ "</table>"
                    }

                    // Moldura comum (cabeçalho escuro, botão com o link do projeto e rodapé).
                    function.run "costguard/email_html_layout" {
                      input = {titulo: "Orçamento em alerta", conteudo_html: $h_conteudo, link: $link_projeto}
                    } as $html

                    var $corpo_email {
                      value = {
                        from   : $email_from
                        to     : [$destino]
                        subject: $assunto
                        html   : $html
                        text   : $texto
                      }
                    }

                    // Uma única chamada, timeout curto, sem retentativa. Exceção
                    // (rede/timeout) vale como falha; o corpo da resposta nunca
                    // é lido nem repassado.
                    //
                    // Idempotency-Key: só id do projeto + janela de 5 minutos
                    // (instante / 300000, inteiro). Sem nome nem e-mail.
                    // NÃO VERIFICADO: suporte do Resend e o filtro `floor`.
                    var $janela_idem { value = ($agora_ms / 300000)|floor }
                    var $idem_chave {
                      value = "devops-" ~ ($input.id|to_text) ~ "-" ~ (($janela_idem|to_int)|to_text)
                    }

                    // Máscara calculada ANTES do envio: se falhar, nada saiu ainda
                    // (o erro não vira "falha depois de enviar" nem convida a duplicata).
                    var.update $mascarado { value = (($destino|split:"@"|first)|substr:0:1) ~ "***@" ~ ($destino|split:"@"|last) }

                    var $envio_status { value = 0 }
                    try_catch {
                      try {
                        api.request {
                          url = "https://api.resend.com/emails"
                          method = "POST"
                          params = $corpo_email
                          headers = [
                            "Content-Type: application/json",
                            "Authorization: Bearer " ~ $email_chave,
                            "Idempotency-Key: " ~ $idem_chave,
                            "User-Agent: costguard-xano/1.0"
                          ]
                          timeout = 10
                        } as $resp_email
                        var.update $envio_status { value = ($resp_email.response.status ?? 0) }
                      }
                      catch {
                        var.update $envio_status { value = 0 }
                      }
                    }

                    conditional {
                      if ($envio_status >= 200 && $envio_status < 300) {
                        var.update $estado { value = "enviado" }
                        // Aceito: a ficha do teto diário fica consumida (o finally não a devolve).
                        var.update $ficha_aceita { value = true }

                        // O instante só é gravado depois de o Resend aceitar.
                        try_catch {
                          try {
                            var $instante_envio { value = now|to_int }
                            // Quando e quem (id do usuário da sessão, relido com a trava).
                            db.edit projetos {
                              field_name = "id"
                              field_value = $input.id
                              data = {devops_ultimo_envio_em: $instante_envio, devops_ultimo_envio_por: $solicitante_atual.id}
                            }
                          }
                          catch {
                            var.update $registro_falhou { value = true }
                          }
                        }
                      }
                      else {
                        var.update $estado { value = "falha_envio" }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
      catch {
        var.update $falha { value = true }
      }
      finally {
        db.del travas {
          field_name = "id"
          field_value = $trava_id
        }

        // Ficha do teto diário: devolvida quando o Resend NÃO aceitou (recusa,
        // timeout, falha do alerta, exceção ou recusa posterior à ficha). Se a
        // devolução falhar, a ficha fica consumida (lado seguro) e a resposta
        // não muda.
        conditional {
          if ($ficha_id != null && $ficha_aceita == false) {
            try_catch {
              try {
                db.del travas {
                  field_name = "id"
                  field_value = $ficha_id
                }
              }
              catch {
                var.update $ficha_liberacao_falhou { value = true }
              }
            }
          }
        }
      }
    }

    precondition ($falha == false) {
      error_type = "standard"
      error = "Não foi possível concluir o envio do alerta. Tente novamente em instantes."
    }

    precondition ($estado != "sem_sessao") {
      error_type = "unauthorized"
      error = "Token inválido ou expirado"
    }

    precondition ($estado != "sem_projeto") {
      error_type = "notfound"
      error = "Projeto não encontrado"
    }

    precondition ($estado != "projeto_inativo") {
      error_type = "inputerror"
      error = "Este projeto está inativo; não é possível notificar o DevOps."
    }

    precondition ($estado != "sem_destino") {
      error_type = "inputerror"
      error = "Este projeto não tem e-mail do DevOps cadastrado."
    }

    var $msg_limite {
      value = "Já foi enviado um alerta deste projeto há pouco. Aguarde " ~ ($segundos_restantes|to_text) ~ " segundos para enviar outro (limite: 1 envio a cada 5 minutos)."
    }

    precondition ($estado != "limite") {
      error_type = "toomanyrequests"
      error = $msg_limite
    }

    // Teto diário global atingido: mensagem FIXA, de propósito SEM número de
    // segundos (amanhã = virada do dia civil de São Paulo; o app não deve contar).
    precondition ($estado != "teto_diario") {
      error_type = "toomanyrequests"
      error = "Limite diário de notificações atingido; tente amanhã."
    }

    precondition ($estado != "falha_resumo" && $estado != "falha_conteudo") {
      error_type = "standard"
      error = "Não foi possível montar o alerta deste projeto. Tente novamente em instantes."
    }

    precondition ($estado != "falha_envio") {
      error_type = "standard"
      error = "Não foi possível enviar o e-mail agora. Tente novamente em instantes."
    }

    precondition ($estado == "enviado") {
      error_type = "standard"
      error = "Não foi possível concluir o envio do alerta. Tente novamente em instantes."
    }

    // Se o Resend aceitou mas a gravação do instante falhou, o envio é sucesso,
    // porém o limite não foi registrado: a mensagem avisa (sem erro HTTP).
    // Não admin: mensagem fixa, sem nenhuma parte do endereço. Admin: endereço mascarado.
    var $mensagem_final { value = "Alerta enviado ao DevOps do projeto." }

    conditional {
      if ($eh_admin == true) {
        var.update $mensagem_final { value = "Alerta enviado para " ~ $mascarado ~ "." }
      }
    }

    conditional {
      if ($registro_falhou) {
        var.update $mensagem_final {
          value = $mensagem_final ~ " Aviso: não foi possível registrar o limite de 5 minutos; um novo envio pode ser aceito agora."
        }
      }
    }

    var $resposta {
      value = {
        status  : "enviado"
        mensagem: $mensagem_final
      }
    }
  }

  response = $resposta
}
