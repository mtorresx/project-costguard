## Why

O CostGuard já integra com a AWS real (cadastro de provedor, teste de conexão via STS,
coleta de custos via Cost Explorer com SigV4, classificação por tag). Existe agora um
**AWS Mock Simulator** externo e funcional (`https://aws-mock.costguard.com.br`) que
expõe o contrato do Cost Explorer (`GetCostAndUsage`, `GetTags`) por conta, permitindo
exercitar os fluxos reais (armazenamento JWE, assinatura SigV4, paginação, idempotência,
classificação) sem depender de uma conta AWS de verdade — inclusive para habilitar o E2E
ainda pendente da change `classificacao-tags-aws-base`.

Objetivo: permitir que um provedor AWS seja marcado como "usar Mock", direcionando as
chamadas do Cost Explorer para o endpoint do Mock, **sem alterar em nada o fluxo AWS real**
e sem criar uma arquitetura paralela.

## What Changes

- Novo campo booleano no provedor: **`usar_mock`** (default `false`). O provedor continua
  sendo `tipo = aws`; Mock é apenas uma característica daquele provedor.
- **`usar_mock = false`**: comportamento atual permanece **exatamente igual** (endpoint AWS
  real, STS no teste de conexão). Nada no caminho real depende do Mock.
- **`usar_mock = true`**: as chamadas ao Cost Explorer passam a usar
  `https://aws-mock.costguard.com.br/aws/{identificador_conta}/ce/`, reutilizando a mesma
  implementação de SigV4, coleta e (futuramente) classificação — apenas a **URL de destino**
  muda.
- **Teste de conexão** passa a ser condicional ao `usar_mock`:
  - real → STS `GetCallerIdentity` (inalterado);
  - mock → chamada leve ao Cost Explorer do Mock (`GetTags` ou `GetCostAndUsage` com
    intervalo mínimo) para validar endpoint + Account ID + contrato. **Não autentica
    criptograficamente** as credenciais (o Mock não valida SigV4) — limitação documentada.
- Suporte a **N provedores Mock**, cada um com seu próprio Account ID, Access Key, Secret e
  apelido. Nenhum Account ID/credencial/`base_url` global ou hardcoded.
- **Frontend Reflex**: um único checkbox "Usar ambiente AWS Mock" no modal de provedor, logo
  após o Account ID. Sem redesenho, sem nova página, sem poluir a UI. Access Key e Secret
  permanecem visíveis mesmo com Mock marcado.
- As credenciais Mock (fictícias) são cadastradas e cifradas pelo **mesmo** mecanismo JWE,
  decifradas só em memória — proposital, para exercitar o fluxo de segurança real.
- **BREAKING**: nenhum. `usar_mock` default `false` preserva todos os provedores e fluxos
  existentes.

Fora do escopo:

- Modificar o AWS Mock Simulator (é externo e já funcional).
- Arquivar `classificacao-tags-aws-base` (permanece aberta; o Mock apenas habilitará seu E2E).
- STS/validação criptográfica de credenciais no Mock.
- Qualquer alteração de defaults ou de comportamento do fluxo AWS real.

## Capabilities

### New Capabilities

- `integracao-mock`: característica opcional de provedor AWS que, quando ativada
  (`usar_mock = true`), direciona as chamadas do Cost Explorer ao AWS Mock Simulator por
  conta (`/aws/{identificador_conta}/ce/`), com teste de conexão sem STS, isolamento total do
  fluxo AWS real e as credenciais fictícias tratadas pelo mesmo mecanismo JWE/SigV4. Inclui as
  regras de isolamento, multi-conta e as limitações de validação documentadas.

### Modified Capabilities

- `provedores`: adicionar o campo `usar_mock` (boolean, default `false`) à entidade e aos
  fluxos de criação, edição, listagem e detalhe; adaptar o **teste de conexão** para não
  chamar STS quando `usar_mock = true`, usando o Cost Explorer do Mock. Segredo nunca
  retornado; JWE preservado.
- `custos`: a coleta de custos passa a resolver o **destino** (endpoint) a partir do provedor
  — endpoint AWS real quando `usar_mock = false`, endpoint do Mock quando `usar_mock = true` —
  mantendo `DAILY`, `UnblendedCost`, `SERVICE`, paginação, idempotência, persistência e
  tratamento de erros idênticos. A assinatura SigV4 e o restante do fluxo são reaproveitados.

## Impact

- **Backend Xano**:
  - Campo `usar_mock` em `provedores`.
  - `criar_provedor_POST`, `editar_provedor_PATCH`, `listar_provedores_GET`,
    `detalhe_provedor_GET`: aceitar/retornar `usar_mock`.
  - `testar_conexao_provedor_POST`: ramo Mock (sem STS).
  - `coletar_custos_provedor_POST` (e, quando arquivado, `classificar_custos_provedor_POST`):
    parametrizar a URL de destino conforme `usar_mock`, com a **menor alteração possível**.
  - Base URL do Mock como variável de ambiente (`MOCK_BASE_URL`), não hardcoded.
- **Frontend Reflex**: checkbox "Usar ambiente AWS Mock" no modal de provedor; eventual
  indicação discreta de Mock na listagem apenas se ajudar operacionalmente.
- **AWS real**: nenhum impacto — caminho inalterado e independente do Mock.
- **`classificacao-tags-aws-base`**: não arquivada; o Mock habilita seu E2E posteriormente.
- **Segurança**: credenciais Mock fictícias cadastradas/cifradas via JWE; credenciais reais
  nunca enviadas ao Mock; credenciais Mock nunca usadas em endpoint AWS real.
