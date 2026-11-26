// Resumo de consumo MTD de todos os projetos, para os cards de /projetos.
// Fonte: custos_equipe, com o mesmo critério de total_projeto em
// projetos/{id}/custos-equipe (todas as equipes + "Sem responsável").
// Rota com um único segmento literal: "projetos/resumo-consumo-mtd" colidiria
// com "projetos/{id}" (curinga x literal na mesma posição e verbo).
query "projetos-resumo-consumo-mtd" verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
    // Mês opcional (AAAA-MM). Vazio = mês corrente até a data atual.
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

    // Lógica em function "costguard/resumo_consumo" (mesmo contrato).
    function.run "costguard/resumo_consumo" {
      input = {mes: $input.mes}
    } as $resultado
  }

  response = $resultado
  guid = "snoDSEBbHWmOEXDQ7QJTR6QtP54"
}
