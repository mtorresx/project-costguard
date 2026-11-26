// Lógica compartilhada: usada pelo
// endpoint listar_recursos_nao_classificados_GET e pelos painéis agregados.
function "costguard/recursos_nao_classificados" {
  input {
  }

  stack {
    // Qualquer usuário autenticado pode ler (auth garante 401 sem token).
    // "Não classificado" = recurso ativo sem projeto válido. O Xano grava a
    // chave estrangeira nula como 0, por isso o filtro aceita null ou 0.
    db.query recursos {
      where = $db.recursos.ativo == true && ($db.recursos.projeto_id == null || $db.recursos.projeto_id == 0)
      sort = {provedor_id: "asc"}
      return = {type: "list"}
    } as $lista

    db.query provedores {
      return = {type: "list"}
    } as $lista_provedores

    var $nome_provedor { value = {} }
    foreach ($lista_provedores) {
      each as $pv {
        var $kv { value = "k" ~ ($pv.id|to_text) }
        var.update $nome_provedor { value = $nome_provedor|set:$kv:$pv.apelido }
      }
    }

    var $itens { value = [] }
    foreach ($lista) {
      each as $r {
        var $kr { value = "k" ~ ($r.provedor_id|to_text) }
        var $prov_nome { value = $nome_provedor|get:$kr:null }
        var $item {
          value = {
            id                : $r.id
            provedor_id       : $r.provedor_id
            provedor_nome     : $prov_nome
            arn               : $r.arn
            servico           : $r.servico
            regiao            : $r.regiao
            codigo_projeto_tag: $r.codigo_projeto_tag
            descoberto_em     : $r.criado_em
          }
        }
        var.update $itens { value = $itens|push:$item }
      }
    }
  }

  response = $itens
}
