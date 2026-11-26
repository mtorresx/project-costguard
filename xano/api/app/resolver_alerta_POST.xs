query "alertas/{id}/resolver" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    int id
  }

  stack {
    // Autorização: admin ativo (validada no backend).
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

    db.get alertas {
      field_name = "id"
      field_value = $input.id
    } as $alerta

    precondition ($alerta != null) {
      error_type = "notfound"
      error = "Alerta não encontrado."
    }

    precondition ($alerta.resolvido == false) {
      error_type = "inputerror"
      error = "Alerta já está resolvido."
    }

    // Resolução manual não encerra o episódio (condicao_ativa inalterada).
    db.edit alertas {
      field_name = "id"
      field_value = $input.id
      data = {
        resolvido    : true
        resolucao    : "manual"
        resolvido_em : now
        resolvido_por: $usuario_logado.id
        atualizado_em: now
      }
    } as $atualizado

    var $resposta {
      value = {
        id          : $atualizado.id
        resolvido   : $atualizado.resolvido
        resolucao   : $atualizado.resolucao
        resolvido_em: $atualizado.resolvido_em
      }
    }
  }

  response = $resposta
}
