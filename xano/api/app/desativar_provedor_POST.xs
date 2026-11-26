query "provedores/{id}/desativar" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }
  }

  stack {
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

    db.get provedores {
      field_name = "id"
      field_value = $input.id
    } as $provedor_alvo

    precondition ($provedor_alvo != null) {
      error_type = "notfound"
      error = "Provedor não encontrado"
    }

    // Desativação lógica: altera status, sem DELETE físico.
    db.edit provedores {
      field_name = "id"
      field_value = $input.id
      data = {status: "inativo"}
    } as $provedor_desativado

    var $resposta {
      value = {
        id                 : $provedor_desativado.id
        apelido            : $provedor_desativado.apelido
        tipo               : $provedor_desativado.tipo
        identificador_conta: $provedor_desativado.identificador_conta
        tipo_credencial    : $provedor_desativado.tipo_credencial
        status             : $provedor_desativado.status
      }
    }
  }

  response = $resposta
  guid = "uM6-j9M1m9ooMAk0NTAkNXdrKGQ"
}
