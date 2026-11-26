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
    // AWS Tag Key da cost allocation tag (ex.: "Projeto"). Opcional, não é segredo.
    text tag_alocacao_projeto? filters=trim
    // AWS Tag Key de equipe (ex.: "EQP"). Opcional, não é segredo.
    text tag_alocacao_equipe? filters=trim
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

    // P2-12: trocar a credencial (chave ou secret) ou a conta invalida o
    // último teste de conexão. O provedor volta a "pendente" até um novo teste, e a
    // sincronização (que exige "ok") não usa a credencial nova sem validação.
    // Provedor inativo continua inativo.
    var $credencial_mudou {
      value = $secret_enviado
        || ($input.aws_access_key_id != null && $input.aws_access_key_id != $provedor_alvo.aws_access_key_id)
        || ($input.identificador_conta != null && $input.identificador_conta != $provedor_alvo.identificador_conta)
    }

    var $novo_status { value = $provedor_alvo.status }
    conditional {
      if ($credencial_mudou && $provedor_alvo.status != "inativo") {
        var.update $novo_status { value = "pendente" }
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
        tag_alocacao_projeto: ($input.tag_alocacao_projeto != null) ? $input.tag_alocacao_projeto : $provedor_alvo.tag_alocacao_projeto
        tag_alocacao_equipe: ($input.tag_alocacao_equipe != null) ? $input.tag_alocacao_equipe : $provedor_alvo.tag_alocacao_equipe
        status             : $novo_status
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
        tag_alocacao_projeto: $provedor_atualizado.tag_alocacao_projeto
        tag_alocacao_equipe: $provedor_atualizado.tag_alocacao_equipe
        status             : $provedor_atualizado.status
      }
    }
  }

  response = $resposta
  guid = "IEa_Qv3m-G1_iefzgSy3fRSpvy4"
}
