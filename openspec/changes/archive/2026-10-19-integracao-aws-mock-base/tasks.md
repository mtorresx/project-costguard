## 1. Schema e configuração

- [x] 1.1 Adicionar campo `usar_mock` (bool, default `false`) à tabela `provedores` em `xano/table/provedores.xs`, sem marcar como sensível/privado. Verificação: schema válido no MCP XanoScript e campo presente com default `false`.
- [x] 1.2 Definir a env var `MOCK_BASE_URL` no workspace Xano (ex.: `https://aws-mock.costguard.com.br`), **apenas no backend**, sem hardcode e nunca enviada ao frontend. Verificação: variável disponível via `$env.MOCK_BASE_URL` no backend; nenhum endpoint/retorno a expõe ao Reflex. [Confirmado: MOCK_BASE_URL configurada; E2E de teste de conexão e coleta Mock bem-sucedidos (dependem de `$env.MOCK_BASE_URL`); não-exposição ao frontend verificada por inspeção (lida só nos ramos usar_mock=true, nenhum endpoint a retorna).]

## 2. Provedor — persistir e expor usar_mock

- [x] 2.1 Atualizar `criar_provedor_POST.xs` e `editar_provedor_PATCH.xs` para aceitar e persistir `usar_mock` (opcional; default `false` na criação), preservando autorização admin, JWE e não exposição do segredo. Verificação: criar/editar com e sem `usar_mock` retorna o provedor (sem segredo) com o valor correto; criação sem o campo grava `false`.
- [x] 2.2 Atualizar `listar_provedores_GET.xs` e `detalhe_provedor_GET.xs` para retornar `usar_mock` como metadado, mantendo a exclusão do `aws_secret_cifrado`. Verificação: respostas de leitura incluem `usar_mock` e nunca o segredo.

## 3. Resolução de destino e assinatura SigV4 coerente

- [x] 3.1 Em `coletar_custos_provedor_POST.xs`, parametrizar (sem duplicar a implementação) os componentes da assinatura dependentes do destino: `$sig_host`, `$canonical_uri` e a URL de destino. `usar_mock = false` → host `ce.us-east-1.amazonaws.com`, canonical URI `/`, URL `https://ce.us-east-1.amazonaws.com/` (valores atuais, idênticos). `usar_mock = true` → host `aws-mock.costguard.com.br`, canonical URI `/aws/{identificador_conta}/ce/`, URL `{base_normalizada}/aws/{identificador_conta}/ce/`. A assinatura deve ser coerente com o host/URI efetivamente enviados. Verificação: com `usar_mock=false` o canonical request, headers e assinatura são idênticos aos atuais; com `usar_mock=true` a assinatura usa host e URI do Mock.
- [x] 3.2 Montar a URL do Mock normalizando `MOCK_BASE_URL` (remover barra final) para evitar barra dupla (`//aws/...`), funcionando com `https://host` e `https://host/`. Validar presença de `MOCK_BASE_URL` antes de montar; se ausente e `usar_mock=true`, retornar erro sanitizado sem chamar rede. Verificação: base com e sem barra final produzem `.../aws/<conta>/ce/`; Mock sem `MOCK_BASE_URL` → erro sanitizado; provedor real não lê a variável.

## 4. Teste de conexão condicional

- [x] 4.1 Em `testar_conexao_provedor_POST.xs`, ramificar por `usar_mock`: `false` mantém o fluxo STS atual inalterado. Verificação: provedor real continua testando via STS exatamente como hoje.
- [x] 4.2 Implementar o ramo Mock (`usar_mock=true`): sem STS, chamar o Cost Explorer do Mock com `X-Amz-Target: AWSInsightsIndexService.GetTags`, corpo com `TagKey = PRJ` e um `TimePeriod` válido, em `{base_normalizada}/aws/{identificador_conta}/ce/`, assinando via SigV4 coerente com o Mock (host `aws-mock.costguard.com.br`, canonical URI `/aws/{identificador_conta}/ce/`); decifrar o secret via JWE só em memória. HTTP 2xx no contrato → `status=ok` **mesmo com lista de Tags vazia**; não condicionar a custos/projetos. Account ID inexistente/resposta incompatível/Mock offline → `status=erro` sanitizado. Verificação: Account ID válido (tags vazias) → ok; inexistente/incompatível → erro; Mock offline → erro; nenhuma chamada a STS.
- [x] 4.3 Documentar (em comentário no endpoint e na resposta/doc) que o teste Mock valida endpoint + Account ID + contrato e NÃO autentica criptograficamente as credenciais (Mock não valida SigV4). Verificação: limitação registrada e visível; não ocultada.

## 5. Frontend Reflex

- [x] 5.1 Adicionar ao modal de provedor um checkbox "Usar ambiente AWS Mock" (ligado a `usar_mock`) logo após o Account ID, preservando o design atual, sem nova página nem redesenho. Verificação: checkbox aparece na posição correta; marcado/desmarcado reflete em `usar_mock` no submit.
- [x] 5.2 Garantir que com Mock marcado os campos Access Key e Secret permaneçam visíveis e o Account ID continue obrigatório; com desmarcado, o modal funciona exatamente como hoje. Verificação: comportamento visual conferido nos dois estados.
- [x] 5.3 (Opcional operacional) Exibir indicação discreta de Mock na listagem apenas se agregar valor; não poluir a UI. Verificação: se implementado, indicação discreta e única; caso contrário, nada é adicionado.

## 6. Retrocompatibilidade (testes)

- [x] 6.1 Teste: provedor pré-existente sem `usar_mock` é tratado como `false` e usa AWS real. Verificação: coleta/teste desse provedor não referenciam o Mock.
- [x] 6.2 Teste: criação/edição/teste/coleta de provedor AWS real continuam usando o endpoint real e o fluxo atual (STS no teste, `ce.us-east-1.amazonaws.com` na coleta). Verificação: endpoints/headers/assinatura idênticos aos atuais quando `usar_mock=false`.
- [x] 6.3 Teste: o Mock nunca altera silenciosamente um provedor real (nenhum caminho real lê `MOCK_BASE_URL` nem chama o domínio do Mock). Verificação: inspeção do fluxo real confirma ausência de referência ao Mock.

## 7. Verificação e validação

- [x] 7.1 Validar todos os arquivos XanoScript alterados pelo MCP XanoScript (quando disponível) e via `xano workspace push -d .\xano --dry-run` (sem push real). Verificação: validação sem erros; dry-run coerente com o escopo. [Nota: MCP XanoScript indisponível nesta sessão; validação feita pelo dry-run do servidor Xano, exit 0.]
- [x] 7.2 Validar a change com `openspec validate integracao-aws-mock-base --strict`. Verificação: validação passa sem erros.
- [x] 7.3 (E2E, pós-aprovação) Com provedores Mock cadastrados (AWS-DATA/DEV/HOMOLOG/PROD/SANDBOX) usando as credenciais fictícias do Mock e `tag_alocacao_projeto = PRJ`, exercitar teste de conexão e coleta via Mock; posteriormente habilitar o E2E da change `classificacao-tags-aws-base`. Verificação: coleta Mock popula `custos`; classificação (quando retomada) resolve `PRJ$<codigo>`; fluxo real intacto.
