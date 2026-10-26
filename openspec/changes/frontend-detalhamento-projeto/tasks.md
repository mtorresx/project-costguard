## 1. Confirmações antes do Apply

- [x] 1.1 Confirmar a API de rota dinâmica, `projeto_id` e `on_load` no Reflex 0.9.12. Verificação: confirmado na fonte instalada (`reflex/state.py`: `setup_dynamic_args`, `DynamicRouteVar`, `hydrate_and_load`; `reflex/app.py`: `add_page(on_load=...)`). Documentação web de rotas dinâmicas retornou 404; a confirmação de runtime fica para o E2E (7.1).
- [x] 1.2 Confirmar a propagação de clique. Verificação: `stop_propagation` confirmado em `reflex_base/event/__init__.py` (linha 412), como propriedade de `EventHandler`/`EventSpec`. Escolha registrada no design (D2). Validação visual no E2E (7.1).
- [ ] 1.3 Confirmar com o Xano Developer MCP o formato do corpo de `inputerror` (campo `message`) (risco R4). Verificação: formato confirmado antes de qualquer tratamento específico de `inputerror`. Até lá, vale o fallback genérico já definido. Pendente: a ferramenta Xano Developer MCP não está disponível nesta sessão. Limitação registrada: fallback genérico adotado; nenhum parsing específico de `inputerror` implementado, pois o contrato não foi confirmado.
- [x] 1.4 Decisões de produto registradas: R1 aceito (rótulo "Custo classificado"), R3 resolvido (`America/Sao_Paulo`), R7 resolvido (projeto inativo acessível, com status "Inativo"). Verificação: proposal, design e spec atualizados.
- [x] 1.5 Confirmar `rx.download(url=None, filename=None, data=None, mime_type=None)` e `rx.redirect(path, *, is_external=False, popup=False, replace=False)` no Reflex 0.9.12. Verificação: assinaturas lidas em `reflex_base/event/__init__.py` (linhas 1556 e 1811); registrado no design.

## 1A. Dependência de fuso (aprovação pendente)

- [x] 1A.1 Aprovar a inclusão de `tzdata` em `requirements.txt`. Motivo: `zoneinfo.ZoneInfo("America/Sao_Paulo")` falha no Windows sem o banco de fusos (verificado: `ZoneInfoNotFoundError`, `tzdata` ausente). Verificação: aprovação explícita do usuário antes de editar `requirements.txt`. _Evidência: aprovado; `tzdata==2026.5` em requirements.txt e instalado no .venv; `ZoneInfo('America/Sao_Paulo')` resolve._

## 2. Estado Reflex

- [x] 2.1 Criar `projetoImpacta/pages/projeto_detalhe_state.py` com `ProjetoDetalheState`: `projeto_id` (rota), `projeto`, `nao_encontrado`, `loading`, `error_message`, período (`periodo_inicio`, `periodo_fim` em texto), métricas formatadas, `moeda`, lista de equipes com custo, grupos de recursos, `equipes_recolhidas`, aviso de sem responsável. Seguir o padrão de `ProjetosState` (`httpx`, `get_xano_app_base_url()`, `AuthState`). Verificação: o módulo importa sem erro e o estado compila. _Evidência: `projetoImpacta/pages/projeto_detalhe_state.py` criado; `reflex compile --dry` concluiu sem erro._
- [x] 2.2 Implementar a lógica de janela MTD em função pura, testável, usando `America/Sao_Paulo`: primeiro dia do mês e dia seguinte à data atual. Verificação: teste unitário cobre meio de mês, primeiro dia do mês, virada de ano e a virada UTC (02:00 UTC de 01/11 resulta em janela de outubro). Depende de 1A.1. _Evidência: `janela_mtd` em America/Sao_Paulo; checagens em script de scratchpad cobrem meio de mês, dia 1, virada de ano e virada UTC (02:00 UTC de 01/11 gera janela de outubro)._
- [x] 2.3 Implementar a regra de moeda e orçamento (D5): `moeda` nula, diferente de USD, `budget = 0` e estouro de orçamento. Verificação: teste unitário cobre os quatro casos sem zero substituto. _Evidência: `_preencher_custos` cobre moeda nula, moeda diferente de USD, budget zero e estouro; checagens passaram._
- [x] 2.4 Implementar a regra de nome do recurso a partir do ARN (último segmento após `/` ou `:`, ou ARN inteiro). Verificação: teste unitário com ARNs com `/`, com `:` e sem separador. _Evidência: `nome_recurso` cobre ARN com `/`, com `:` e sem separador; checagens passaram._

## 3. Carregamento e erros

- [ ] 3.1 Implementar `carregar` com `GET /projetos/{id}` e tratamento de 401 (`AuthState.handle_unauthenticated`), 404 e erro de rede. Parâmetro não inteiro positivo não chama o backend. Verificação: cada caminho mostra o estado esperado. Implementado; verificação em runtime pendente (depende de sessão autenticada, ver 7.x).
- [ ] 3.2 Implementar a consulta de `custos-equipe` com a janela MTD e tratamento de 401, `inputerror` (mensagem do backend ou genérica) e rede. Verificação: consulta envia `data_inicio` e `data_fim` corretos; erro de moedas mostra mensagem sem valores somados. Implementado; verificação em runtime pendente (ver 7.x).
- [ ] 3.3 Implementar as consultas de `recursos` e `equipes` com erros independentes do bloco de custos. Verificação: falha em `recursos` não esconde as métricas. Implementado; verificação em runtime pendente (ver 7.x).

## 4. Página e componentes

- [ ] 4.1 Criar `projetoImpacta/pages/projeto_detalhe.py` com `projeto_detalhe_page()`, portando do frontend de referência o cabeçalho, o breadcrumb, `_kpi_card_detalhe`, o bloco de equipes (`_barra_equipe`), o bloco de recursos (`_grupo_recursos`), o aviso de sem responsável e os estados vazios. O primeiro card de métrica usa o rótulo "Custo classificado (MTD)". Preservar estilos e tokens de `theme`. Verificação: página renderiza com dados de teste sem erro, e o rótulo aparece exatamente como especificado. Implementado; verificação visual pendente (ver 7.x).
- [x] 4.6 Mostrar o status do projeto no cabeçalho, com "Ativo" ou "Inativo" (D13), sem bloquear o conteúdo quando inativo. Verificação: projeto com `status = inativo` mostra "Inativo" e o detalhamento continua visível. _Evidência: `_badge_status` usa `status_texto` ('Ativo'/'Inativo') no cabeçalho._
- [x] 4.2 Ajustar a grade de KPIs para duas colunas, sem terceiro card (D6). Verificação: exatamente dois cards de métrica. _Evidência: grade com `columns="2"` e dois cards de métrica (`_card_custo`, `_card_orcamento`)._
- [x] 4.3 Remover da tela os blocos de custo por provedor, projeção, variação e coluna de valor por recurso. Verificação: nenhum desses textos ou colunas aparece na página. _Evidência: grep na página não encontra projeção, tendência nem custo por provedor; coluna de valor removida da tabela de recursos._
- [x] 4.4 Renderizar "Notificar DevOps" desabilitado, sem `on_click`. Verificação: botão visível e desabilitado; nenhum handler associado. _Evidência: botão com `disabled=True`, sem `on_click`._
- [x] 4.5 Implementar a exportação CSV com o módulo `csv` e `rx.download`, para "Exportar Dados" e "Exportar CSV". Verificação: arquivo tem as colunas definidas; campos com vírgula são escapados. _Evidência: `exportar_csv` testado: cabeçalho `Equipe,Recurso,ARN,Serviço,Região`, campos com vírgula escapados pelo módulo `csv`, sem coluna de valor._

## 5. Rota e navegação

- [x] 5.1 Registrar `/projetos/[projeto_id]` em `projetoImpacta/projetoImpacta.py` com `on_load=[AuthState.require_auth, ProjetoDetalheState.carregar]`. Verificação: a rota existe e a proteção de sessão é aplicada. _Evidência: rota `/projetos/[projeto_id]` registrada com `on_load=[AuthState.require_auth, ProjetoDetalheState.carregar]`; compile ok._
- [x] 5.2 Ajustar o card de `projetoImpacta/pages/projetos.py` para mostrar "Ver detalhamento" e navegar ao detalhamento, sem que Editar e Desativar disparem a navegação (D2). Verificação: clique no card navega; clique em Editar abre o formulário sem navegar. _Evidência: card com `on_click=rx.redirect(...)` e 'Ver detalhamento'; Editar e Desativar com `.stop_propagation` (diff de 15 inserções e 2 remoções)._

## 6. Validação local

- [x] 6.1 Compilar o app Reflex com a versão do projeto (`reflex==0.9.12`) e revisar que não há import de `costguard`. Verificação: compilação sem erros e sem referência ao pacote externo. _Evidência: `reflex compile --dry` concluiu sem erro._
- [x] 6.2 Validar a change com `openspec validate frontend-detalhamento-projeto --strict`. Verificação: validação passa sem erros. _Evidência: `Change 'frontend-detalhamento-projeto' is valid`, exit 0._

## 7. E2E

- [ ] 7.1 E2E admin com projeto 4 (PAGAMENTOS): abrir `/projetos`, clicar no card, conferir período, métricas, equipes com custo, recursos agrupados, aviso de sem responsável e botão desabilitado. Comparar os totais com a resposta de `GET /projetos/4/custos-equipe` para a mesma janela MTD. Verificação: valores da tela batem com a resposta do backend. Não executado: exige sessão autenticada com credenciais; sem credenciais disponíveis nesta rodada.
- [ ] 7.2 E2E admin com projeto sem registros no mês: confirmar o estado "Sem custos classificados" sem valores fictícios. Verificação: tela sem "US$ 0.00" calculado como custo e sem orçamento restante. Não executado (mesmo motivo de 7.1).
- [ ] 7.3 E2E de exportação CSV: conferir cabeçalho, linhas e ausência de colunas de valor. Verificação: arquivo baixado corresponde aos recursos ativos exibidos. Não executado (mesmo motivo de 7.1).
- [ ] 7.4 E2E de rota inválida e de projeto inexistente (`/projetos/abc`, `/projetos/999999`). Verificação: "Projeto não encontrado" sem erro de servidor. Não executado (mesmo motivo de 7.1).
- [ ] 7.5 E2E de sessão: acesso sem login redireciona a `/login`; token inválido gera redirecionamento após 401. Verificação: comportamento conforme a capability `autenticacao`. Não executado (mesmo motivo de 7.1).
- [ ] 7.6 E2E de leitura com o usuário E2E `role = leitura`, hoje **inativo**. Procedimento: reativar temporariamente, testar o acesso de leitura (somente visualização, sem controles de escrita), e desativar novamente ao fechar o teste. **Nunca excluir** o usuário. Não executar antes do início do E2E. Verificação: acesso de leitura validado, usuário desativado de volta, e o resultado registrado no relatório (8.1). Não executado: usuário E2E de leitura permanece inativo; reativação só no fechamento do E2E.

## 8. Relatório e entrega

- [ ] 8.1 Registrar os comandos executados, saídas relevantes e resultado de cada etapa de validação. Verificação: relatório anexado ao fim do Apply, com o que não foi executado e o motivo. Parcial: validações executadas listadas na resposta; E2E pendente.
- [ ] 8.2 Informar ao usuário os arquivos alterados e o `git add` sugerido, sem executar Git. Verificação: lista de arquivos de staging entregue para o usuário executar.
