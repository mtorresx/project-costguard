// Estado da configuração do Azure (custo somente leitura). Valida o FORMATO das
// credenciais antes de qualquer uso em URL ou corpo e diz DE ONDE vêm.
//
// ORDEM DAS CREDENCIAIS: 1) o cadastro feito pela tela (tabela `azure_conexao`,
// cifrado com JWE e `$env.PROV_ENC_KEY`); 2) como RESERVA, as variáveis de
// ambiente do Xano (AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
// AZURE_SUBSCRIPTION_ID). Se o cadastro da tela EXISTE mas não decifra (chave
// errada, dado corrompido) ou está fora do formato, o estado é
// "configuracao_invalida" com origem "tela": NÃO cai em silêncio nas variáveis.
// AZURE_COST_API_VERSION (opcional, padrão 2023-11-01, testada no Azure real com
// HTTP 200) vale para as duas origens.
//
// NENHUM SEGREDO é devolvido (nem decifrado, nem cifrado): só estado, origem, a
// versão da API (a versão não é segredo e já é pública na documentação) e dois dados
// de exibição que NÃO são segredo e ficam em texto simples no cadastro (nada é
// decifrado para obtê-los): `apelido` e `tenant_final` (últimos 4 caracteres do
// tenant). Quem precisa dos valores secretos (o sincronizar e o cadastro) decifra
// dentro do PRÓPRIO endpoint: o histórico de requisições do Xano guarda a RESPOSTA
// de funções.
// Segredos nunca entram como `input` de função pelo mesmo motivo.
//
// MÍNIMO NECESSÁRIO: esta função roda a cada GET /azure/custo (qualquer usuário
// autenticado). Com cadastro da tela ela decifra SOMENTE o `tenant_id_cifrado` (basta
// para detectar "não decifra" / PROV_ENC_KEY trocada) e valida só o GUID dele. O
// client_secret, o client_id e o subscription_id NÃO são decifrados aqui: o formato do
// segredo é validado no POST /azure/conexao e REVALIDADO no sincronizar, depois de
// decifrar dentro do endpoint (cadastro que decifra mal ou fora do formato lá vira
// "configuracao_invalida" no estado guardado; ver azure_custo_sincronizar_POST).
//
// estado:
//   "nao_configurado"      sem cadastro e alguma das 4 variáveis ausente ou vazia
//   "configuracao_invalida" cadastro/variáveis presentes, mas fora do formato (GUID,
//                          tamanho, versão) ou cadastro que não decifra
//   "ok"                   pronto para uso
// origem: "tela" (cadastro no banco) | "servidor" (variáveis) | null (nao_configurado)
// apelido: o guardado no cadastro da tela, se não vazio; senão o padrão "Azure" (também
//   para origem "servidor" e nao_configurado).
// tenant_final: o guardado (4 caracteres) quando a origem é "tela"; null caso contrário
//   (nada é derivado da variável AZURE_TENANT_ID). Com origem "tela" e estado
//   "configuracao_invalida" (ex.: não decifra) os dois guardados SÃO devolvidos mesmo
//   assim: não são segredo e mostram ao admin qual cadastro está quebrado.
function "costguard/azure_config_estado" {
  input {
  }

  stack {
    var $tenant { value = "" }
    var $client { value = "" }
    var $segredo { value = "" }
    var $assinatura { value = "" }
    var $origem { value = null }
    // false = cadastro da tela existe mas não decifrou.
    var $decifrou { value = true }
    // Dados de exibição (não são segredo). Padrão "Azure" e null fora do cadastro da tela.
    var $apelido_exibido { value = "Azure" }
    var $tenant_final { value = null }

    db.get azure_conexao {
      field_name = "chave"
      field_value = "azure"
    } as $cadastro

    conditional {
      if ($cadastro != null) {
        var.update $origem { value = "tela" }

        // Apelido e final do tenant: colunas em texto simples (nada é decifrado aqui).
        conditional {
          if (($cadastro.apelido ?? "") != "") {
            var.update $apelido_exibido { value = $cadastro.apelido }
          }
        }

        conditional {
          if (($cadastro.tenant_final ?? "") != "") {
            var.update $tenant_final { value = $cadastro.tenant_final }
          }
        }

        // Só o tenant é decifrado (ver "MÍNIMO NECESSÁRIO" acima): o segredo, o client_id
        // e a assinatura ficam cifrados.
        try_catch {
          try {
            var.update $tenant { value = (($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }
          }
          catch {
            var.update $decifrou { value = false }
          }
        }
      }
      else {
        // Reserva: variáveis do servidor.
        var.update $tenant { value = (($env.AZURE_TENANT_ID ?? "")|trim) }
        var.update $client { value = (($env.AZURE_CLIENT_ID ?? "")|trim) }
        var.update $segredo { value = (($env.AZURE_CLIENT_SECRET ?? "")|trim) }
        var.update $assinatura { value = (($env.AZURE_SUBSCRIPTION_ID ?? "")|trim) }
      }
    }

    var $versao_api { value = (($env.AZURE_COST_API_VERSION ?? "")|trim) }

    conditional {
      if ($versao_api == "") {
        var.update $versao_api { value = "2023-11-01" }
      }
    }

    // Presença das 4 variáveis: só vale para a origem do servidor (sem cadastro da tela).
    var $presentes { value = ($tenant != "" && $client != "" && $segredo != "" && $assinatura != "") }

    // GUID: 36 caracteres e formato 8-4-4-4-12 em hexadecimal. O tamanho é
    // conferido à parte porque o `$` do regex aceita uma quebra de linha final.
    var $tenant_ok { value = (($tenant|strlen) == 36 && ("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$tenant)) }
    var $client_ok { value = (($client|strlen) == 36 && ("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$client)) }
    var $assinatura_ok { value = (($assinatura|strlen) == 36 && ("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$assinatura)) }

    // Segredo: ASCII visível, sem espaço nem controle (viaja só no corpo).
    var $segredo_ok { value = (($segredo|strlen) >= 8 && ($segredo|strlen) <= 256 && ("/^[!-~]+$/"|regex_matches:$segredo)) }

    // Versão da API: AAAA-MM-DD, com sufixo opcional -preview (vai na URL).
    var $versao_ok { value = (($versao_api|strlen) <= 20 && ("/^[0-9]{4}-[0-9]{2}-[0-9]{2}(-preview)?$/"|regex_matches:$versao_api)) }

    var $estado { value = "ok" }

    // Cadastro da tela que não decifra: inválido, SEM cair nas variáveis do servidor.
    // Cadastro da tela que decifra: só o tenant (GUID) e a versão são conferidos aqui; os
    // demais campos do cadastro são conferidos no POST e no sincronizar (ver cabeçalho).
    // Sem cadastro, a ausência de qualquer das 4 variáveis é "nao_configurado" (origem null).
    conditional {
      if ($origem == "tela" && $decifrou == false) {
        var.update $estado { value = "configuracao_invalida" }
      }
      elseif ($origem == "tela") {
        conditional {
          if ($tenant_ok == false || $versao_ok == false) {
            var.update $estado { value = "configuracao_invalida" }
          }
        }
      }
      elseif ($presentes == false && $origem == null) {
        var.update $estado { value = "nao_configurado" }
      }
      elseif ($presentes == false || $tenant_ok == false || $client_ok == false || $assinatura_ok == false || $segredo_ok == false || $versao_ok == false) {
        var.update $estado { value = "configuracao_invalida" }
      }
    }

    // Variáveis presentes (origem do servidor) só contam como origem quando há algo configurado.
    conditional {
      if ($origem == null && $estado != "nao_configurado") {
        var.update $origem { value = "servidor" }
      }
    }

    var $resultado {
      value = {
        estado      : $estado
        origem      : $origem
        versao_api  : ($estado == "ok") ? $versao_api : ""
        apelido     : $apelido_exibido
        tenant_final: $tenant_final
      }
    }
  }

  response = $resultado
}
