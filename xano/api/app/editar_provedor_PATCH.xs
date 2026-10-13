query "provedores/{id}" verb=PATCH {
  api_group = "app"
  auth = "usuarios"

  input {
    int id {
      table = "provedores"
    }

    text apelido? filters=trim
    text identificador_conta? filters=trim
    text aws_access_key_id? filters=trim
    text aws_secret_access_key? {
      sensitive = true
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

    precondition ($usuario_logado.role == "admin") {
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

    // Se um novo secret foi enviado, re-protege via JWE (novo token/nonce).
    // Caso contrário, preserva o cifrado existente. O IV não é usado (caminho JWE).
    var $secret_enviado {
      value = ($input.aws_secret_access_key != null && $input.aws_secret_access_key != "")
    }

    var $segredo_cifrado {
      value = $provedor_alvo.aws_secret_cifrado
    }

    conditional {
      if ($secret_enviado) {
        var.update $segredo_cifrado {
          value = $input.aws_secret_access_key|jwe_encode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"
        }
      }
    }

    db.edit provedores {
      field_name = "id"
      field_value = $input.id
      data = {
        apelido            : ($input.apelido != null) ? $input.apelido : $provedor_alvo.apelido
        identificador_conta: ($input.identificador_conta != null) ? $input.identificador_conta : $provedor_alvo.identificador_conta
        aws_access_key_id  : ($input.aws_access_key_id != null) ? $input.aws_access_key_id : $provedor_alvo.aws_access_key_id
        aws_secret_cifrado : $segredo_cifrado
      }
    } as $provedor_atualizado

    // Resposta sem segredo nem IV.
    var $resposta {
      value = {
        id                 : $provedor_atualizado.id
        apelido            : $provedor_atualizado.apelido
        tipo               : $provedor_atualizado.tipo
        identificador_conta: $provedor_atualizado.identificador_conta
        tipo_credencial    : $provedor_atualizado.tipo_credencial
        status             : $provedor_atualizado.status
      }
    }
  }

  response = $resposta
  guid = "IEa_Qv3m-G1_iefzgSy3fRSpvy4"
}
