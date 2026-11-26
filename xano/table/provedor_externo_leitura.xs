// Último valor lido de um provedor EXTERNO somente leitura (hoje só o Azure:
// custo do mês corrente, tratado como custo NÃO ALOCADO). Uma linha por
// provedor + mês de referência (índice único).
//
// Por que tabela própria: `provedores` é por conta AWS com credencial cifrada
// (enum tipo só "aws") e as tabelas de custo são por projeto/equipe, em USD, e
// alimentam painel e orçamento. O Azure NÃO entra nesses números.
//
// NUNCA guarda: tenant, client id, client secret, assinatura, token, nem o corpo
// da resposta do Azure. As credenciais ficam só no cadastro cifrado da tela
// (tabela `azure_conexao`) ou, como reserva, nas variáveis de ambiente do Xano.
// Ao cadastrar/substituir/remover a conexão pela tela, TODAS as linhas do provedor
// "azure" são apagadas (a leitura guardada pertencia a outra credencial/assinatura).
//
// "Sem valor": `custo_mes_total` é ANULÁVEL (sem padrão), e uma linha nova sem
// valor grava null (nunca 0). Mas `db.edit` IGNORA null (e decimal 0 == null nas
// comparações), então numa linha já existente o custo antigo permanece na coluna
// mesmo depois de um sem_dados/sem_permissao. Por isso quem manda é `tem_valor`:
// só com tem_valor = true o custo é devolvido (ver costguard/azure_custo_estado).
table provedor_externo_leitura {
  auth = false

  schema {
    int id
    // "azure"
    text provedor filters=trim
    // Mês do valor, AAAA-MM (UTC).
    text mes_referencia filters=trim
    // Último valor lido com sucesso neste mês. Só vale quando tem_valor = true.
    // Anulável: null = nunca houve valor (linha criada só para guardar a tentativa).
    decimal custo_mes_total?
    text moeda?
    // Instante (ms) da última leitura BEM-SUCEDIDA do mês, com valor (ok) ou sem
    // consumo (sem_dados). Vale quando > 0; 0 = nenhuma leitura bem-sucedida
    // válida (nunca lida, ou sem_permissao/resposta_incompleta zeraram). Hora da
    // última leitura real (não há mais cache de 4 h). NÃO implica valor: quem diz
    // se há custo é tem_valor.
    int atualizado_em?=0
    // true só quando custo_mes_total/moeda guardam um valor válido (status ok).
    bool tem_valor?=false
    // Status da ÚLTIMA tentativa (conjunto fechado, nunca texto livre):
    // sem_leitura, ok, sem_dados, sem_permissao, indisponivel, resposta_incompleta.
    enum status?=sem_leitura {
      values = ["sem_leitura", "ok", "sem_dados", "sem_permissao", "indisponivel", "resposta_incompleta"]
    }
    // Resumo curto e genérico (sem IDs, sem segredo, sem corpo do Azure).
    text erro_resumo?
    // Instante (ms) da última tentativa de chamar o Azure. Gravado ANTES da
    // chamada; base do cooldown de 60 s entre tentativas (sucesso ou falha).
    int tentativa_em?=0
    // Instante (ms) até o qual NÃO se deve chamar o Azure (resposta 429).
    int bloqueado_ate?=0
    timestamp criado_em?=now {
      visibility = "private"
    }
  }

  index = [
    {type: "primary", field: [{name: "id"}]}
    {type: "btree|unique", field: [{name: "provedor", op: "asc"}, {name: "mes_referencia", op: "asc"}]}
  ]
}
