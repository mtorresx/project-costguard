// Conexão do Azure cadastrada PELA TELA (custo somente leitura). No máximo UMA
// linha: o campo `chave` vale sempre "azure" e tem índice único, então um segundo
// db.add falha no próprio banco (o endpoint ainda grava sob trava, em `travas`).
//
// Por que tabela NOVA e aditiva (menor risco): `provedores` é por conta AWS com
// credencial cifrada e alimenta a sincronização/inventário (enum tipo só "aws");
// `provedor_externo_leitura` é só o cache da leitura do Azure (sem credenciais) e
// é apagada/recriada ao trocar a conexão. Nenhuma tabela existente é alterada.
//
// Os QUATRO dados são guardados CIFRADOS com o mesmo mecanismo da credencial AWS
// (JWE: jwe_encode/jwe_decode com `$env.PROV_ENC_KEY`, A256KW + A256CBC-HS512): o
// IV/nonce vem embutido no JWE. Nada é guardado em claro: nem o segredo, nem
// tenant, client id ou assinatura (as únicas informações em texto simples são o
// apelido e os 4 últimos caracteres do tenant, que não são segredo; ver abaixo).
// Os dados cifrados nunca são devolvidos por API (visibility private)
// nem por função (a função de estado só devolve estado/origem; quem precisa do
// segredo decifra dentro do próprio endpoint). Sem cadastro, o sistema usa as
// variáveis AZURE_* do servidor como reserva.
table azure_conexao {
  auth = false

  schema {
    int id
    // Chave fixa "azure": garante UMA única conexão (índice único).
    text chave filters=trim
    // Directory (tenant) ID, GUID, cifrado (JWE).
    text tenant_id_cifrado? {
      sensitive = true
      visibility = "private"
    }
    // Application (client) ID, GUID, cifrado (JWE).
    text client_id_cifrado? {
      sensitive = true
      visibility = "private"
    }
    // Client secret, cifrado (JWE).
    text client_secret_cifrado? {
      sensitive = true
      visibility = "private"
    }
    // ID da assinatura (GUID), cifrado (JWE).
    text subscription_id_cifrado? {
      sensitive = true
      visibility = "private"
    }
    // Apelido da conexão (texto opcional de 1 a 60 caracteres, já limpo no POST) e os
    // ÚLTIMOS 4 caracteres do tenant ID. NÃO são segredo: ficam em texto simples (sem
    // `sensitive`, sem cifragem), para o GET /azure/custo exibi-los sem decifrar nada.
    // Vazio ("") = sem apelido (db.edit ignora null, então o POST grava "" para limpar).
    // `tenant_final` nunca guarda o ID inteiro: o POST grava só o final (4 caracteres).
    // Colunas aditivas e anuláveis.
    text apelido?
    text tenant_final?
    // Instante (ms) da última gravação e id do admin que a fez (inteiro simples, sem FK).
    int atualizado_em?=0 {
      visibility = "private"
    }
    int atualizado_por? {
      visibility = "private"
    }
    timestamp criado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree|unique", field: [{name: "chave", op: "asc"}]}
  ]
}
