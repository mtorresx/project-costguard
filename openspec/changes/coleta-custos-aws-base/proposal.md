## Why

O CostGuard já cadastra provedores AWS, cifra credenciais via JWE e testa a conexão (SigV4 + STS `GetCallerIdentity`). O próximo passo do domínio é **obter custos reais** da AWS: sem custos importados, nenhuma consolidação por projeto, comparação com orçamento ou alerta pode existir (ver `docs/domain-model.md` — Registro de Custo). Esta change entrega a **primeira fatia de coleta de custos AWS** — consultar o AWS Cost Explorer (`GetCostAndUsage`) a partir de um provedor AWS ativo e conectado, persistir os custos no backend e registrar o estado da coleta — mantendo o escopo mínimo do MVP acadêmico.

## What Changes

- **Backend Xano (novo)**: duas tabelas — `custos` (custos coletados, granularidade diária, por serviço, em USD) e `coletas_custo` (estado de cada execução de coleta por provedor) — e um endpoint administrativo de coleta no api_group `app` já existente.
- **Coleta a partir de provedor ativo**: a coleta só é permitida para um provedor `tipo = aws` com `status = ok`. Provedor `inativo`/`erro`/`pendente` é rejeitado antes de qualquer chamada à AWS.
- **Consulta ao AWS Cost Explorer via SigV4**: o backend decifra a credencial (JWE, só em memória, imediatamente antes de assinar), monta SigV4 (service `ce`, region `us-east-1`) e chama `GetCostAndUsage` (POST) com granularidade `DAILY`, métrica `UnblendedCost` (USD) e agrupamento por `SERVICE`, tratando `NextPageToken` (paginação).
- **Persistência idempotente**: cada registro de custo é único por (provedor, data, serviço, métrica). Reexecutar a coleta para o mesmo período **atualiza** os valores (upsert), sem duplicar linhas.
- **Intervalo de consulta definido**: a coleta recebe `data_inicio` e `data_fim` (fim exclusivo, como a AWS exige); quando omitidos, usa um intervalo padrão simples do MVP (os últimos N dias até ontem).
- **Estado mínimo da coleta**: `coletas_custo` registra provedor de origem, intervalo, `status` (`sucesso`/`erro`), momento da última coleta e uma `mensagem` sanitizada em caso de erro.
- **Falha nunca silenciosa**: erro da AWS (ou falha parcial de paginação) resulta em `status = erro` com mensagem sanitizada; o backend retorna indicação explícita de falha.
- **Autorização no backend**: a coleta é operação **administrativa** (`role = admin`). O usuário `leitura` não executa coleta. (A consulta/visualização dos dados já coletados por `leitura` fica para uma change posterior — ver Fora do escopo.)
- **Segredo nunca exposto**: AWS Secret Access Key, `PROV_ENC_KEY`, Authorization SigV4, signing keys e o JWE decifrado **nunca** são retornados nem registrados em log; diagnóstico limitado a status HTTP, `Error.Code`, `Error.Message` sanitizada e `RequestId`.

## Capabilities

### New Capabilities

- `coleta-custos`: Coleta base de custos AWS do CostGuard — a entidade `custos` (custo diário por serviço, em USD, vinculado ao provedor de origem) e `coletas_custo` (estado da execução), e a operação administrativa que consulta o AWS Cost Explorer (`GetCostAndUsage` via SigV4) a partir de um provedor AWS `ok`, persiste os custos de forma idempotente por período e registra sucesso/erro, com autorização validada no backend e sem jamais expor segredos.

### Modified Capabilities

<!-- Nenhum requisito das capabilities `provedores`, `autenticacao`, `interface-frontend` ou `projetos` é alterado. Esta change consome a credencial e o status do provedor existentes, sem mudar seus contratos. -->

## Impact

- **Backend Xano (novo — escopo desta change)**:
  - `xano/table/custos.xs` — custos coletados (idempotentes por provedor+data+serviço+métrica).
  - `xano/table/coletas_custo.xs` — estado de cada execução de coleta.
  - `xano/api/app/coletar_custos_provedor_POST.xs` — endpoint administrativo de coleta (SigV4 → Cost Explorer).
  - Reuso de `$env.PROV_ENC_KEY` e do padrão SigV4 já existentes (nenhuma nova variável de ambiente).
- **Preservado sem alteração**: tabela `provedores`, endpoints de provedores, autenticação, `projetos`, frontend Reflex.

### Fora do escopo

- Inventário completo de recursos AWS; `GetCostAndUsageWithResources`.
- Classificação por tags `PRJ_`/`EQP_`; criação automática de equipes; consolidação de custos por projeto.
- Alertas 70/90/100; dashboard final de custos.
- Suporte a Azure, GCP ou Oracle (apenas AWS).
- Automação agendada (cron/task); a coleta é manual/administrativa nesta fase.
- Alteração de budget; otimização ou recomendação de custos.
- Frontend/página de consulta dos custos coletados (a visualização por `leitura` será uma change posterior); esta change entrega backend de coleta.
