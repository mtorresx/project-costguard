// Lógica compartilhada: usada pelo
// endpoint listar_alertas_GET e pelos painéis agregados.
function "costguard/lista_alertas" {
  input {
  }

  stack {
    // Qualquer usuário autenticado pode ler (auth garante 401 sem token).
    // Todos os abertos (contagens completas) + os 500 resolvidos mais recentes.
    db.query alertas {
      where = $db.alertas.resolvido == false
      sort = {criado_em: "desc"}
      return = {type: "list"}
    } as $abertos

    db.query alertas {
      where = $db.alertas.resolvido == true
      sort = {criado_em: "desc"}
      return = {type: "list", paging: {page: 1, per_page: 500}}
    } as $pagina_resolvidos

    var $todos { value = $abertos|merge:$pagina_resolvidos.items }

    db.query projetos {
      return = {type: "list"}
    } as $lista_projetos

    db.query provedores {
      return = {type: "list"}
    } as $lista_provedores

    var $nome_projeto { value = {} }
    foreach ($lista_projetos) {
      each as $p {
        var $kp { value = "k" ~ ($p.id|to_text) }
        var.update $nome_projeto { value = $nome_projeto|set:$kp:$p.nome }
      }
    }

    var $nome_provedor { value = {} }
    foreach ($lista_provedores) {
      each as $pv {
        var $kv { value = "k" ~ ($pv.id|to_text) }
        var.update $nome_provedor { value = $nome_provedor|set:$kv:$pv.apelido }
      }
    }

    var $itens { value = [] }
    foreach ($todos) {
      each as $a {
        var $kap { value = "k" ~ (($a.projeto_id ?? 0)|to_text) }
        var $kav { value = "k" ~ (($a.provedor_id ?? 0)|to_text) }
        var $proj_nome { value = $nome_projeto|get:$kap:null }
        var $prov_nome { value = $nome_provedor|get:$kav:null }
        var $item {
          value = {
            id           : $a.id
            tipo         : $a.tipo
            nivel        : $a.nivel
            mensagem     : $a.mensagem
            detalhe      : $a.detalhe
            projeto_id   : $a.projeto_id
            projeto_nome : $proj_nome
            provedor_id  : $a.provedor_id
            provedor_nome: $prov_nome
            resolvido    : $a.resolvido
            resolucao    : $a.resolucao
            resolvido_em : $a.resolvido_em
            criado_em    : $a.criado_em
            atualizado_em: $a.atualizado_em
          }
        }
        var.update $itens { value = $itens|push:$item }
      }
    }
  }

  response = $itens
}
