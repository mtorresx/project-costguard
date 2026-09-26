query redefinir_senha verb=POST {
  api_group = "auth"

  input {
    // Token recebido por e-mail e a nova senha
    text token filters=trim
  
    text nova_senha filters=trim
  }

  stack {
    // Mensagem de erro
    var $erro_generico {
      value = {
        mensagem: "Link inválido, expirado ou já utilizado"
      }
    }
  
    // Busca o token na tabela de recuperação
    db.get recuperacao_senha {
      field_name = "token_hash"
      field_value = $input.token
    } as $token_encontrado
  
    // Token não existe
    conditional {
      if ($token_encontrado == null) {
        return {
          value = $erro_generico
        }
      }
    }
  
    // Token já foi usado
    conditional {
      if ($token_encontrado.usado) {
        return {
          value = $erro_generico
        }
      }
    }
  
    // tempo atual pra comparar expiração
    var $agora {
      value = "now"
        |transform_timestamp:"+0 seconds":"UTC"
    }
  
    // Token expirado
    conditional {
      if ($token_encontrado.expira_em < $agora) {
        return {
          value = $erro_generico
        }
      }
    }
  
    db.edit usuarios {
      field_name = "id"
      field_value = $token_encontrado.usuarios_id
      data = {senha_hash: $input.nova_senha}
    } as $usuario_atualizado
  
    // Marca o token como usado
    db.edit recuperacao_senha {
      field_name = "id"
      field_value = $token_encontrado.id
      data = {usado: true}
    } as $token_atualizado
  
    var $sucesso {
      value = {mensagem: "Senha redefinida com sucesso"}
    }
  
    return {
      value = $sucesso
    }
  }

  response = $sucesso
  guid = "0EfUmwEPxl-g8E5OXZGtY0tY6JE"
}