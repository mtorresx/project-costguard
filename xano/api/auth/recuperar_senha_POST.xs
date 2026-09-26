query recuperar_senha verb=POST {
  api_group = "auth"

  input {
    email email filters=trim|lower
  }

  stack {
    var $mensagem_padrao {
      value = {
        mensagem: "Se o e-mail existe no sistema, um link de recuperação foi enviado"
      }
    }
  
    db.get usuarios {
      field_name = "email"
      field_value = $input.email
    } as $usuario_encontrado
  
    conditional {
      if ($usuario_encontrado == null) {
        return {
          value = $mensagem_padrao
        }
      }
    }
  
    // Gera um UUID pra usar como token de recuperação
    security.create_uuid as $token_uuid
  
    var $expira_em {
      value = "now"
        |transform_timestamp:"+1 hour":"UTC"
    }
  
    db.add recuperacao_senha {
      data = {
        usuarios_id: $usuario_encontrado.id
        token_hash : $token_uuid
        expira_em  : $expira_em
        usado      : false
        created_at : "now"
      }
    } as $recuperacao_criada
  
    var $link_recuperacao {
      value = "https://seu-dominio.com/redefinir-senha?token=" ~ $token_uuid
    }
  
    debug.log {
      value = {
        acao        : "envio_email_recuperacao"
        destinatario: $usuario_encontrado.email
        link        : $link_recuperacao
        token       : $token_uuid
      }
    }
  
    return {
      value = $mensagem_padrao
    }
  }

  response = $mensagem_padrao
  guid = "X0wUG-bRtqKzHvdFV7H09JxwEhc"
}