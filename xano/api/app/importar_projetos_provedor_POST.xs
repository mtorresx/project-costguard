query "provedores/{id}/importar-projetos" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
    // Lista de códigos selecionados pelo admin (não reconsulta a AWS).
    text[] codigos
  }

  stack {
    // ============================================================
    // 1) Autorização: importação é operação administrativa (backend).
    // ============================================================
    db.get usuarios {
      field_name = "id"
      field_value = $auth.id
    } as $usuario_logado

    precondition ($usuario_logado != null) {
      error_type = "unauthorized"
      error = "Token inválido ou expirado"
    }

    precondition ($usuario_logado.status == "ativo" && $usuario_logado.role == "admin") {
      error_type = "accessdenied"
      error = "Acesso negado"
    }

    // ============================================================
    // A) Pré-condições do provedor (contexto da importação).
    // ============================================================
    db.get provedores {
      field_name = "id"
      field_value = $input.id
    } as $provedor

    precondition ($provedor != null) {
      error_type = "notfound"
      error = "Provedor não encontrado"
    }

    precondition ($provedor.tipo == "aws") {
      error_type = "inputerror"
      error = "Tipo de provedor não suportado (apenas 'aws')"
    }

    // ============================================================
    // B) Normalizar (trim+upper), remover vazios e deduplicar a lista recebida.
    //    NÃO reconsulta a AWS — trabalha só com a lista do admin.
    // ============================================================
    var $codigos_norm { value = [] }

    foreach (($input.codigos ?? [])) {
      each as $codigo_bruto {
        var $codigo { value = ($codigo_bruto|trim)|to_upper }
        conditional {
          if ($codigo != "") {
            var $ja_tem { value = false }
            foreach ($codigos_norm) {
              each as $c {
                conditional {
                  if ($c == $codigo) {
                    var.update $ja_tem { value = true }
                  }
                }
              }
            }
            conditional {
              if ($ja_tem == false) {
                var.update $codigos_norm { value = $codigos_norm|push:$codigo }
              }
            }
          }
        }
      }
    }

    // ============================================================
    // C) Para cada código: existe → ignorado; não existe → cria mínimo.
    //    Nunca duplica, nunca reativa (índice unique de projetos.codigo é a
    //    barreira final).
    // ============================================================
    var $criados { value = [] }
    var $ignorados { value = [] }

    foreach ($codigos_norm) {
      each as $codigo {
        db.query projetos {
          where = $db.projetos.codigo == $codigo
          return = {type: "single"}
        } as $existente

        conditional {
          if ($existente != null) {
            // Já existe: não altera, não reativa; registra como ignorado.
            var.update $ignorados {
              value = $ignorados|push:{
                codigo    : $codigo
                motivo    : "ja_existe"
                projeto_id: $existente.id
              }
            }
          }
          else {
            // Cria projeto mínimo. Não inventar orçamento (budget = 0).
            db.add projetos {
              data = {
                nome  : $codigo
                codigo: $codigo
                budget: 0
                status: "ativo"
              }
            } as $novo

            var.update $criados {
              value = $criados|push:{
                codigo    : $codigo
                projeto_id: $novo.id
              }
            }
          }
        }
      }
    }

    var $resposta {
      value = {
        provedor_id: $provedor.id
        criados    : $criados
        ignorados  : $ignorados
      }
    }
  }

  response = $resposta
  guid = "58SFOqtDGSo6_B9zxO8txqhYyQs"
}
