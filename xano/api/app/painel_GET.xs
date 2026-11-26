// Painel agregado: uma única leitura
// para Início, Projetos e Alertas, por causa do limite de requisições do plano
// Xano. Mesmo conteúdo dos três endpoints individuais.
query painel verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
    // Mês opcional (AAAA-MM) do resumo de consumo. Vazio = mês corrente.
    text mes? filters=trim
  }

  stack {
    // P2-10: usuário desativado (ou removido) perde também o acesso às leituras.
    db.get usuarios {
      field_name = "id"
      field_value = $auth.id
    } as $usuario_sessao

    precondition ($usuario_sessao != null && $usuario_sessao.status == "ativo") {
      error_type = "unauthorized"
      error = "Token inválido ou expirado"
    }

    function.run "costguard/resumo_consumo" {
      input = {mes: $input.mes}
    } as $resumo

    function.run "costguard/lista_alertas" {
      input = {}
    } as $alertas

    function.run "costguard/recursos_nao_classificados" {
      input = {}
    } as $nao_classificados

    var $resposta {
      value = {
        resumo                    : $resumo
        alertas                   : $alertas
        recursos_nao_classificados: $nao_classificados
      }
    }
  }

  response = $resposta
  guid = "jtr6o8YEMNyAZ5R9CX7Xr4L0yPA"
}
