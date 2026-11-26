// Trava técnica de exclusão mútua.
// O índice único em `nome` garante, no próprio banco, que só uma requisição
// por vez segura a trava. Sem dados de negócio; linhas duram cerca de 1 s.
table travas {
  auth = false

  schema {
    int id
    text nome filters=trim
    // Instante (ms) da aquisição. A trava não expira sozinha: é removida pelo
    // finally da requisição que a criou. Uma linha que sobre após falha do
    // servidor bloqueia edições e desativações de usuários até ser removida.
    int adquirida_em
    timestamp criado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree|unique", field: [{name: "nome", op: "asc"}]}
  ]
}
