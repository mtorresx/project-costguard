// Aviso por e-mail ao DevOps do projeto com a lista de RECURSOS SEM EQUIPE.
// Irmão de notificar_devops_projeto_POST: mesma
// moldura de e-mail, mesmo destinatário (SÓ o `email_devops` já cadastrado; sem
// input de destinatário), mesmo Resend, mesmo teto diário, mesmas travas e erros.
//
// AUTORIZAÇÃO (decisão do usuário): QUALQUER usuário autenticado e ATIVO (admin
// ou leitura) pode acionar, como em notificar-devops; usuário removido ou
// desativado recebe 401. NÃO existe 403 por papel. O papel só decide o TEXTO da
// resposta: o ADMIN recebe `destinatario_mascarado` e a mensagem com o endereço
// MASCARADO; os demais recebem a mensagem fixa "Aviso de recursos sem equipe
// enviado ao DevOps do projeto." e NENHUMA parte do endereço (nem a chave
// `destinatario_mascarado`). `enviado` e `quantidade` vão para todos. Criar/editar
// o e-mail do projeto continua só admin. Risco aceito: o teto diário de 30
// envios é global e compartilhado, então qualquer perfil pode esgotá-lo.
//
// Lista os recursos ATIVOS do projeto SEM EQUIPE: equipe_id nulo ou 0 (o Xano
// grava a FK nula como 0) E sem valor em codigo_equipe_tag (a mesma definição do
// bloco "Recursos sem responsável" da tela e da contagem do e-mail de orçamento).
// Tabela com no máximo 50 linhas (nome, serviço, região e data em que o recurso
// apareceu) e depois "e mais N"; `quantidade` é o TOTAL (não só as 50). Sem custo
// por recurso. Ordenação determinística: id crescente (o id é sequencial e a data
// de aparição, `criado_em`, nunca muda: a ordem é a de descoberta).
//   - "nome": a tabela `recursos` NÃO tem coluna de nome; usa-se o último trecho
//     do ARN (depois de "/" e de ":"), ex.: instance/i-0abc vira "i-0abc". O ARN
//     completo (que traz o número da conta) não vai ao e-mail.
//   - "mês corrente": `recursos` é um inventário atual (ativo = true) e não tem
//     coluna de mês; é o mesmo critério da contagem do e-mail de orçamento. O mês
//     do e-mail é o mês civil de America/Sao_Paulo (UTC-3 fixo), por extenso.
//
// Limite PRÓPRIO de 1 envio por projeto a cada 5 minutos (independente do de
// orçamento): colunas anuláveis devops_recursos_ultimo_envio_em / _por em
// `projetos`, gravadas só depois de o Resend ACEITAR (2xx). TETO DIÁRIO
// COMPARTILHADO: as mesmas fichas `devops_dia_<AAAA-MM-DD>_<n>` (n = 1..30) da
// tabela `travas`; a ficha só fica consumida com o aceite do Resend e é devolvida
// no finally em qualquer outro desfecho.
//
// ORDEM DAS CHECAGENS: 1) autenticação e usuário ativo (401); 2) projeto existe
// (404); 3) projeto ativo (400); 4) tem e-mail (400); 5) e-mail configurado no
// servidor (500); 6) trava do projeto (429 "em andamento"); depois, já com a
// trava: 7) sessão, projeto, ativo e e-mail relidos; 8) limite de 5 min (429 com
// segundos); 9) ZERO recursos sem equipe (400, sem enviar e sem tocar no teto: a
// lista é lida ANTES de qualquer ficha); 10) teto diário (429 sem segundos);
// 11) conteúdo; 12) envio. Chamada recusada nunca gasta o teto nem o limite de
// 5 min.
//
// Segurança: igual ao endpoint de orçamento (chave em $env.EMAIL_API_KEY,
// remetente em $env.EMAIL_FROM, base do link em $env.COSTGUARD_APP_URL validada,
// corpo/erro do Resend nunca repassados, uma única chamada sem retentativa).
// TODO texto livre do banco (nome do projeto, nome de quem enviou, nome/serviço/
// região do recurso) passa por costguard/limpar_texto_linha e, no HTML, por
// costguard/escapar_html. O e-mail do usuário nunca entra no corpo. Este endpoint
// NÃO chama o Azure nem o resumo de consumo: só lê `recursos`.
//
// Timeout ambíguo (RISCO ACEITO, igual ao endpoint de orçamento): pode haver
// duplicata; a Idempotency-Key `devops-rec-<id>-<janela de 5 min>` (distinta da
// de orçamento) mitiga. NÃO VERIFICADO: se o Resend a honra.
query "projetos/{id}/notificar-recursos-sem-equipe" verb=POST {
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
    // `nome`), PRÓPRIA deste aviso (nome diferente da do orçamento): torna
    // atômico o par "conferir o limite + enviar + registrar". Removida no
    // finally; trava órfã (> 2 min) é removida na primeira tentativa seguinte.
    // ============================================================
    var $trava_nome { value = "devops_rec_projeto_" ~ ($input.id|to_text) }
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
    var $quantidade { value = 0 }
    var $maximo_linhas { value = 50 }

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

        // Limite PRÓPRIO: 1 envio deste aviso por projeto a cada 5 minutos.
        var $agora_ms { value = now|to_int }
        var $ultimo_envio { value = ($proj_atual != null) ? ($proj_atual.devops_recursos_ultimo_envio_em ?? 0) : 0 }
        var $decorrido_ms { value = $agora_ms - $ultimo_envio }

        conditional {
          if ($estado == "" && $ultimo_envio > 0 && $decorrido_ms < $limite_ms) {
            // Relógio adiantado (decorrido negativo) nunca passa de 5 min.
            // Segundos = resto/1000 arredondado e depois LIMITADO a [1, 300].
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

        // Lista dos recursos sem equipe, lida ANTES do teto diário: com zero
        // recursos a resposta é 400 sem tocar em nenhuma ficha. Uma única consulta
        // e um único laço: conta o TOTAL e monta as linhas das 50 primeiras
        // (id crescente). Cada campo livre (nome derivado do ARN, serviço, região)
        // passa por limpar_texto_linha (texto/assunto) e, no HTML, por escapar_html.
        // Falha na consulta = erro 500 genérico (a lista é o conteúdo do e-mail).
        var $h_linhas { value = "" }
        var $t_linhas { value = "" }
        var $escapados_juntos { value = "" }
        var $r_td { value = "padding:6px 8px;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;color:#111827;word-break:break-all;vertical-align:top;" }

        conditional {
          if ($estado == "") {
            db.query recursos {
              where = $db.recursos.projeto_id == $input.id && $db.recursos.ativo == true && ($db.recursos.equipe_id == null || $db.recursos.equipe_id == 0)
              sort = {id: "asc"}
              return = {type: "list"}
            } as $recursos_sem_equipe

            foreach ($recursos_sem_equipe) {
              each as $rs {
                conditional {
                  if ((($rs.codigo_equipe_tag ?? "")|trim) == "") {
                    var.update $quantidade { value = $quantidade + 1 }

                    conditional {
                      if ($quantidade <= $maximo_linhas) {
                        // Nome = último trecho do ARN (depois de "/" e de ":").
                        var $arn_bruto { value = ($rs.arn ?? "") }
                        var $arn_parte { value = ((($arn_bruto|split:"/")|last) ?? "") }
                        var $arn_nome { value = ((($arn_parte|split:":")|last) ?? "") }

                        function.run "costguard/limpar_texto_linha" {
                          input = {texto: $arn_nome}
                        } as $r_nome

                        conditional {
                          if ($r_nome == "") {
                            var.update $r_nome { value = "(sem identificador)" }
                          }
                        }

                        function.run "costguard/limpar_texto_linha" {
                          input = {texto: ($rs.servico ?? "")}
                        } as $r_servico

                        function.run "costguard/limpar_texto_linha" {
                          input = {texto: ($rs.regiao ?? "")}
                        } as $r_regiao

                        // Data em que o recurso apareceu: criado_em (ms), dia de São Paulo.
                        var $criado_ms { value = (($rs.criado_em ?? 0)|to_int) }
                        var $r_data { value = "-" }

                        conditional {
                          if ($criado_ms > 0) {
                            var.update $r_data { value = $criado_ms|format_timestamp:"d/m/Y":"America/Sao_Paulo" }
                          }
                        }

                        function.run "costguard/escapar_html" {
                          input = {texto: $r_nome}
                        } as $r_nome_html

                        // Defesa em profundidade: a data (d/m/Y ou "-") também é escapada no HTML.
                        function.run "costguard/escapar_html" {
                          input = {texto: $r_data}
                        } as $r_data_html

                        function.run "costguard/escapar_html" {
                          input = {texto: $r_servico}
                        } as $r_servico_html

                        function.run "costguard/escapar_html" {
                          input = {texto: $r_regiao}
                        } as $r_regiao_html

                        var.update $h_linhas {
                          value = $h_linhas ~ "<tr><td style='" ~ $r_td ~ "'>" ~ $r_nome_html ~ "</td><td style='" ~ $r_td ~ "'>" ~ $r_servico_html ~ "</td><td style='" ~ $r_td ~ "'>" ~ $r_regiao_html ~ "</td><td style='" ~ $r_td ~ "'>" ~ $r_data_html ~ "</td></tr>"
                        }
                        var.update $t_linhas { value = $t_linhas ~ "- " ~ $r_nome ~ " | " ~ $r_servico ~ " | " ~ $r_regiao ~ " | " ~ $r_data ~ "\n" }
                        var.update $escapados_juntos { value = $escapados_juntos ~ $r_nome_html ~ $r_servico_html ~ $r_regiao_html ~ $r_data_html }
                      }
                    }
                  }
                }
              }
            }

            conditional {
              if ($quantidade == 0) {
                var.update $estado { value = "sem_recursos" }
              }
            }
          }
        }

        // Teto diário GLOBAL e COMPARTILHADO com notificar-devops: 30 envios por dia
        // civil de America/Sao_Paulo, somando todos os projetos e os dois tipos de
        // aviso (mesmas fichas devops_dia_<data>_<n>). Só chega aqui quem passou por
        // todas as recusas anteriores (sessão, projeto, ativo, e-mail, limite
        // de 5 min e zero recursos). Dia civil: o instante menos 3 h (UTC-3),
        // formatado em UTC (sem horário de verão no Brasil desde 2019). O fuso
        // "America/Sao_Paulo" com `format_timestamp` JÁ é usado em
        // costguard/resumo_consumo e costguard/avaliar_alertas; a dúvida real (NÃO
        // VERIFICADO) é só o formato "d/m/Y" sobre timestamp de tabela (r_data).
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
            // Mês de referência: o mês civil de São Paulo (AAAA-MM do dia civil), por extenso.
            var $mes_ref { value = $dia_civil|substr:0:7 }

            function.run "costguard/mes_extenso_pt_br" {
              input = {mes: $mes_ref}
            } as $mes_extenso

            // Defesa em profundidade: o mês também passa por escapar_html no HTML.
            function.run "costguard/escapar_html" {
              input = {texto: $mes_extenso}
            } as $mes_html

            // Textos LIVRES do banco: nome do projeto e nome de quem acionou o envio
            // (SÓ o nome, nunca o e-mail). Texto puro/assunto: limpar_texto_linha;
            // HTML: limpar_texto_linha + escapar_html.
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

            // Autoverificação do escape (projeto, usuário e as linhas dos recursos):
            // com < ou > restante, nada é enviado.
            var.update $escapados_juntos { value = $escapados_juntos ~ $nome_html ~ $enviado_html ~ $mes_html }

            conditional {
              if ("/[<>]/"|regex_matches:$escapados_juntos) {
                var.update $estado { value = "falha_conteudo" }
              }
            }

            conditional {
              if ($estado == "") {
                // Assunto: "[CostGuard] Recursos sem equipe: PROJETO (N)", com \r e \n removidos.
                var $assunto {
                  value = (("[CostGuard] Recursos sem equipe: " ~ $nome_limpo ~ " (" ~ ($quantidade|to_text) ~ ")")|replace:"\r":"")|replace:"\n":""
                }

                // "e mais N": recursos além das 50 linhas da tabela.
                var $mais { value = $quantidade - $maximo_linhas }

                // Texto puro (sem escape HTML): campos de uma linha já sem CR/LF.
                var $texto { value = "CostGuard - Recursos sem equipe\n\n" }
                var.update $texto { value = $texto ~ "Projeto: " ~ $nome_limpo ~ "\n" }
                var.update $texto { value = $texto ~ "Mês de referência: " ~ $mes_extenso ~ "\n" }
                var.update $texto { value = $texto ~ "Recursos sem equipe: " ~ ($quantidade|to_text) ~ "\n" }
                var.update $texto { value = $texto ~ "Enviado por: " ~ $enviado_limpo ~ "\n\n" }
                var.update $texto { value = $texto ~ "Recursos (nome | serviço | região | apareceu em):\n" ~ $t_linhas }

                conditional {
                  if ($mais > 0) {
                    var.update $texto { value = $texto ~ "e mais " ~ ($mais|to_text) ~ " recursos\n" }
                  }
                }

                var.update $texto { value = $texto ~ "\nAbrir projeto no CostGuard: " ~ $link_projeto ~ "\n\n" }
                var.update $texto { value = $texto ~ "Alerta manual enviado pelo CostGuard\n" }

                // HTML: dados do projeto + tabela de recursos (até 50 linhas) + "e mais N".
                function.run "costguard/email_html_linha" {
                  input = {rotulo: "Projeto", valor_html: $nome_html}
                } as $h_projeto

                function.run "costguard/email_html_linha" {
                  input = {rotulo: "Mês de referência", valor_html: $mes_html}
                } as $h_mes

                function.run "costguard/email_html_linha" {
                  input = {rotulo: "Recursos sem equipe", valor_html: ($quantidade|to_text)}
                } as $h_quantidade

                function.run "costguard/email_html_linha" {
                  input = {rotulo: "Enviado por", valor_html: $enviado_html}
                } as $h_enviado

                var $h_th { value = "padding:6px 8px;background-color:#f3f4f6;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:16px;color:#374151;text-align:left;" }

                var $h_tabela {
                  value = "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='width:100%;margin-top:16px;border:1px solid #e5e7eb;'><tr><th style='" ~ $h_th ~ "'>Recurso</th><th style='" ~ $h_th ~ "'>Serviço</th><th style='" ~ $h_th ~ "'>Região</th><th style='" ~ $h_th ~ "'>Apareceu em</th></tr>" ~ $h_linhas ~ "</table>"
                }

                var $h_mais { value = "" }

                conditional {
                  if ($mais > 0) {
                    var.update $h_mais {
                      value = "<p style='margin:8px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;color:#6b7280;'>e mais " ~ ($mais|to_text) ~ " recursos</p>"
                    }
                  }
                }

                var $h_conteudo {
                  value = "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='width:100%;'>" ~ $h_projeto ~ $h_mes ~ $h_quantidade ~ $h_enviado ~ "</table>" ~ $h_tabela ~ $h_mais
                }

                // Moldura comum (cabeçalho escuro, botão com o link do projeto e rodapé).
                function.run "costguard/email_html_layout" {
                  input = {titulo: "Recursos sem equipe", conteudo_html: $h_conteudo, link: $link_projeto}
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
                // (instante / 300000, inteiro), com prefixo próprio deste aviso.
                // Sem nome nem e-mail. NÃO VERIFICADO: suporte do Resend e `floor`.
                var $janela_idem { value = ($agora_ms / 300000)|floor }
                var $idem_chave {
                  value = "devops-rec-" ~ ($input.id|to_text) ~ "-" ~ (($janela_idem|to_int)|to_text)
                }

                // Máscara calculada ANTES do envio: se falhar, nada saiu ainda.
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
                          data = {devops_recursos_ultimo_envio_em: $instante_envio, devops_recursos_ultimo_envio_por: $solicitante_atual.id}
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
      catch {
        var.update $falha { value = true }
      }
      finally {
        db.del travas {
          field_name = "id"
          field_value = $trava_id
        }

        // Ficha do teto diário: devolvida quando o Resend NÃO aceitou (recusa,
        // timeout, falha do conteúdo, exceção ou recusa posterior à ficha). Se a
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

    // Nenhum recurso sem equipe: nada foi enviado, nenhuma ficha tomada e o limite
    // de 5 min NÃO foi registrado.
    precondition ($estado != "sem_recursos") {
      error_type = "inputerror"
      error = "Nenhum recurso sem equipe neste projeto no mês."
    }

    // Teto diário global atingido: mensagem FIXA, de propósito SEM número de segundos.
    precondition ($estado != "teto_diario") {
      error_type = "toomanyrequests"
      error = "Limite diário de notificações atingido; tente amanhã."
    }

    precondition ($estado != "falha_conteudo") {
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

    // Não admin: mensagem fixa, sem nenhuma parte do endereço. Admin: endereço
    // MASCARADO. Se o Resend aceitou mas a gravação do instante falhou, o envio é
    // sucesso, porém o limite não foi registrado: a mensagem avisa (sem erro HTTP;
    // mesmo aviso do endpoint de orçamento).
    var $mensagem_final { value = "Aviso de recursos sem equipe enviado ao DevOps do projeto." }

    conditional {
      if ($eh_admin == true) {
        var.update $mensagem_final { value = "Aviso de recursos sem equipe enviado para " ~ $mascarado ~ "." }
      }
    }

    conditional {
      if ($registro_falhou) {
        var.update $mensagem_final {
          value = $mensagem_final ~ " Aviso: não foi possível registrar o limite de 5 minutos; um novo envio pode ser aceito agora."
        }
      }
    }

    // `destinatario_mascarado` SÓ na resposta do admin (a chave nem existe para os demais).
    var $resposta {
      value = {
        status    : "enviado"
        mensagem  : $mensagem_final
        enviado   : true
        quantidade: $quantidade
      }
    }

    conditional {
      if ($eh_admin == true) {
        var.update $resposta {
          value = {
            status                : "enviado"
            mensagem              : $mensagem_final
            enviado               : true
            destinatario_mascarado: $mascarado
            quantidade            : $quantidade
          }
        }
      }
    }
  }

  response = $resposta
}
