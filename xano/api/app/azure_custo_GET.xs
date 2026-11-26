// Custo do mês corrente da assinatura Azure, como custo NÃO ALOCADO (provedor
// somente leitura). Devolve o ÚLTIMO estado guardado: NÃO chama o Azure. Qualquer
// usuário autenticado e ativo. Não entra no ciclo automático e não se mistura
// aos custos AWS/projetos/painel (card à parte). Sem credenciais: status
// "nao_configurado" e custo null (nunca 0). Nenhuma credencial (cadastro da tela
// ou variável de ambiente) é devolvida. Devolve também `origem` ("tela" |
// "servidor" | null): de onde vêm as credenciais em uso (cadastro da tela primeiro,
// variáveis do servidor como reserva).
query "azure/custo" verb=GET {
  api_group = "app"
  auth = "usuarios"

  input {
  }

  stack {
    db.get usuarios {
      field_name = "id"
      field_value = $auth.id
    } as $usuario_sessao

    precondition ($usuario_sessao != null && $usuario_sessao.status == "ativo") {
      error_type = "unauthorized"
      error = "Token inválido ou expirado"
    }

    function.run "costguard/azure_custo_estado" {
      input = {}
    } as $resposta
  }

  response = $resposta
}
