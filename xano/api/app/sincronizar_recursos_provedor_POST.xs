query "provedores/{id}/sincronizar-recursos" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
  }

  stack {
    // Autorização: sincronização manual é operação administrativa.
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

    // Lógica em function "costguard/sincronizar_inventario" (a mesma do ciclo
    // automático). Ela não lança erro de negócio; as respostas abaixo
    // preservam o contrato anterior deste endpoint.
    function.run "costguard/sincronizar_inventario" {
      input = {provedor_id: $input.id, origem: "manual"}
    } as $saida

    var $codigo_pre { value = "" }
    conditional {
      if ($saida.erro_pre != null) {
        var.update $codigo_pre { value = $saida.erro_pre.codigo }
      }
    }

    precondition ($codigo_pre != "nao_encontrado") {
      error_type = "notfound"
      error = "Provedor não encontrado"
    }

    precondition ($codigo_pre != "tipo") {
      error_type = "inputerror"
      error = "Tipo de provedor não suportado (apenas 'aws')"
    }

    precondition ($codigo_pre != "status") {
      error_type = "inputerror"
      error = "Provedor não está conectado (status != ok)"
    }

    precondition ($codigo_pre != "credencial") {
      error_type = "inputerror"
      error = "Credencial AWS ausente"
    }

    precondition ($saida.ocupado != true) {
      error_type = "inputerror"
      error = "Já existe uma sincronização de recursos em andamento para este provedor."
    }

    var $resposta { value = $saida.resultado }
  }

  response = $resposta
  guid = "rPpVEUwelIk9YgWq0JsnqA5CDZU"
}
