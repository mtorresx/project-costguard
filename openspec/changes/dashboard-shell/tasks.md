## 1. Implementação

- [x] 1.1 `components/contador_state.py` e indicador de alertas no shell (topo e menu). _Evidência (2026-10-27): compilação ok; E2E: após carregar `/`, o topo mostra "Sem alertas abertos", coerente com 0 alertas abertos em `GET /alertas`._
- [x] 1.2 `home_state.py` com funções puras e `home.py` com o dashboard. _Evidência: `unit_frontend.py`: soma do custo (ok/moeda mista/sem registros/budget 0), projetos inativos fora, ordenação, limite de 5, barra limitada a 100, textos de faixa e período — parte dos 55/55._
- [x] 1.3 Shell sem itens de demonstração; "Minha conta" e ajuda atualizadas. _Evidência: busca por "demonstração", "webhook", "auto_tagging", "apresentação/mock" e `_status_multicloud` em `projetoImpacta/` sem ocorrências; E2E "Minha conta" sem webhook nem limite e com as faixas 70/90/100._
- [x] 1.4 Limite de requisições (design D6, encontrado no E2E). _Evidência: 1ª rodada do E2E: `/projetos/10/equipes` recebeu HTTP 429 ao navegar do dashboard para o detalhe. Implementado `cliente_xano` com nova tentativa (3, 5 e 8 s) e usado por todos os estados; `require_auth` mantém a sessão em 429 persistente. Testes unitários do transporte: 429→200 (2 chamadas), 200 direto, 429 persistente (4 chamadas), 401 sem nova tentativa. E2E repetido: o 429 foi repetido automaticamente e a página de detalhe carregou com dados._

## 2. Verificação

- [x] 2.1 E2E admin em `/`. _Evidência: `e2e.py`: custo "US$ 1,613.18" = soma dos `custo_mtd` com `custo_status = ok` do resumo real; período 01/10/2026 a 27/10/2026; 6 projetos ativos; consumo de INFRAESTRUTURA com 0.3% e faixa "Normal"; "Nenhum alerta aberto." coerente; sem números fictícios; clique no projeto abre o detalhe com o mesmo custo; regressão de `/projetos` com todos os projetos reais. Captura `shots/dashboard.png`._
- [x] 2.2 E2E de falha de um bloco (proxy local). _Evidência: `GET /alertas` com HTTP 500 injetado → "Não foi possível carregar os alertas." e os blocos de custo e consumo continuam. Captura `shots/dash_falha_alertas.png`._
- [x] 2.3 `openspec validate dashboard-shell --strict`. _Evidência: "Change 'dashboard-shell' is valid"._

## 3. Observações de execução do E2E

- O E2E apontou a app para um proxy local trocando temporariamente a linha `XANO_APP_BASE_URL` do `.env` (não versionado); a variável de ambiente do processo não tem precedência sobre o `.env`. Restaurado byte a byte (SHA-256 `e4908344…3a11` antes e depois).
- Resultado final: 39/39 verificações; nenhuma escrita real (a única escrita repassada foi a criação com username duplicado, recusada com 400); usuários e alertas idênticos antes e depois; sem erros de console.

## 4. Revisão Codex (2026-10-27)

- [x] 4.1 Achado 6 (IMPORTANTE) — 429 persistente na validação de sessão em silêncio. _Tratado: `AuthState.validacao_pendente` e aviso no shell; limpo na próxima validação bem-sucedida. Compilação ok. O caminho "429 em todas as tentativas" verificado por revisão e pelo teste unitário do transporte (429 persistente devolve 429 após 4 chamadas)._
- [x] 4.2 Observação do revisor "tarefas de dashboard-shell abertas": a revisão foi feita antes do registro das evidências; as tarefas foram atualizadas com a execução registrada acima.
