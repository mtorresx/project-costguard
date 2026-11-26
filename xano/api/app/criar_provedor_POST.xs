query provedores verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    text apelido filters=trim
    text tipo filters=trim
    text identificador_conta filters=trim
    text aws_access_key_id filters=trim
    text aws_secret_access_key {
      sensitive = true
    }
    // AWS Tag Key da cost allocation tag (ex.: "Projeto"). Opcional, não é segredo.
    text tag_alocacao_projeto? filters=trim
    // AWS Tag Key de equipe (ex.: "EQP"). Opcional, não é segredo.
    text tag_alocacao_equipe? filters=trim
  }

  stack {
    // Autorização: operação de escrita exige admin (validada no backend).
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

    // Campos obrigatórios.
    precondition ($input.apelido != null && $input.apelido != "") {
      error_type = "inputerror"
      error = "Campo 'apelido' é obrigatório"
    }

    // Nesta fase, apenas AWS é suportado.
    precondition ($input.tipo == "aws") {
      error_type = "inputerror"
      error = "Tipo de provedor não suportado (apenas 'aws')"
    }

    precondition ($input.identificador_conta != null && $input.identificador_conta != "") {
      error_type = "inputerror"
      error = "Campo 'identificador_conta' é obrigatório"
    }

    // Credencial AWS completa (chave de acesso IAM dedicada, somente leitura).
    precondition ($input.aws_access_key_id != null && $input.aws_access_key_id != "") {
      error_type = "inputerror"
      error = "Campo 'aws_access_key_id' é obrigatório"
    }

    precondition ($input.aws_secret_access_key != null && $input.aws_secret_access_key != "") {
      error_type = "inputerror"
      error = "Campo 'aws_secret_access_key' é obrigatório"
    }

    // Protege o segredo via JWE (AEAD): nonce/IV gerenciado pelo JWE; chave só do env.
    // Nunca logar nem retornar o secret em claro.
    var $segredo_cifrado {
      value = $input.aws_secret_access_key|jwe_encode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"
    }

    db.add provedores {
      data = {
        apelido            : $input.apelido
        tipo               : "aws"
        identificador_conta: $input.identificador_conta
        tipo_credencial    : "aws_access_key"
        aws_access_key_id  : $input.aws_access_key_id
        aws_secret_cifrado : $segredo_cifrado
        tag_alocacao_projeto: ($input.tag_alocacao_projeto != null && $input.tag_alocacao_projeto != "") ? $input.tag_alocacao_projeto : "PRJ"
        tag_alocacao_equipe: ($input.tag_alocacao_equipe != null && $input.tag_alocacao_equipe != "") ? $input.tag_alocacao_equipe : "EQP"
        status             : "pendente"
      }
    } as $novo_provedor

    // Resposta sem segredo nem IV.
    var $resposta {
      value = {
        id                 : $novo_provedor.id
        apelido            : $novo_provedor.apelido
        tipo               : $novo_provedor.tipo
        identificador_conta: $novo_provedor.identificador_conta
        tipo_credencial    : $novo_provedor.tipo_credencial
        tag_alocacao_projeto: $novo_provedor.tag_alocacao_projeto
        tag_alocacao_equipe: $novo_provedor.tag_alocacao_equipe
        status             : $novo_provedor.status
      }
    }
  }

  response = $resposta
  guid = "2A28SpQu7TG2qmxE5vnEusCk0lw"
}
