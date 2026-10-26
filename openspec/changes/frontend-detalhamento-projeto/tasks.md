## 1. Confirmações antes do Apply

- [ ] 1.1 Confirmar com a documentação do Reflex 0.9.12 a leitura do parâmetro de rota dinâmica (`self.projeto_id`), a sua disponibilidade em `on_load` e o comportamento de `add_page(..., on_load=[...])`. Verificação: nota registrada no design com a fonte consultada. Observação: a página pública de rotas dinâmicas retornou 404 na consulta web; a confirmação deve usar a documentação instalada no ambiente ou outra fonte oficial.
- [ ] 1.2 Confirmar com a documentação do Reflex 0.9.12 como interromper a propagação de clique em botões dentro de um card clicável (risco R2). Verificação: escolha registrada no design (D2) ou troca para `rx.link`.
- [ ] 1.3 Confirmar com o Xano Developer MCP o formato do corpo de erro de `inputerror` (campo `message`) (risco R4). Verificação: formato confirmado ou mensagem genérica adotada como padrão.
- [ ] 1.4 Confirmar com o usuário as decisões pendentes R1 (atualidade dos custos), R3 (fuso horário) e R7 (projeto inativo). Verificação: respostas registradas no design.

## 2. Estado Reflex

- [ ] 2.1 Criar `projetoImpacta/pages/projeto_detalhe_state.py` com `ProjetoDetalheState`: `projeto_id` (rota), `projeto`, `nao_encontrado`, `loading`, `error_message`, período (`periodo_inicio`, `periodo_fim` em texto), métricas formatadas, `moeda`, lista de equipes com custo, grupos de recursos, `equipes_recolhidas`, aviso de sem responsável. Seguir o padrão de `ProjetosState` (`httpx`, `get_xano_app_base_url()`, `AuthState`). Verificação: o módulo importa sem erro e o estado compila.
- [ ] 2.2 Implementar a lógica de janela MTD (UTC) em função pura, testável: primeiro dia do mês e dia seguinte à data atual. Verificação: teste unitário cobre meio de mês, primeiro dia do mês e virada de ano.
- [ ] 2.3 Implementar a regra de moeda e orçamento (D5): `moeda` nula, diferente de USD, `budget = 0` e estouro de orçamento. Verificação: teste unitário cobre os quatro casos sem zero substituto.
- [ ] 2.4 Implementar a regra de nome do recurso a partir do ARN (último segmento após `/` ou `:`, ou ARN inteiro). Verificação: teste unitário com ARNs com `/`, com `:` e sem separador.

## 3. Carregamento e erros

- [ ] 3.1 Implementar `carregar` com `GET /projetos/{id}` e tratamento de 401 (`AuthState.handle_unauthenticated`), 404 e erro de rede. Parâmetro não inteiro positivo não chama o backend. Verificação: cada caminho mostra o estado esperado.
- [ ] 3.2 Implementar a consulta de `custos-equipe` com a janela MTD e tratamento de 401, `inputerror` (mensagem do backend ou genérica) e rede. Verificação: consulta envia `data_inicio` e `data_fim` corretos; erro de moedas mostra mensagem sem valores somados.
- [ ] 3.3 Implementar as consultas de `recursos` e `equipes` com erros independentes do bloco de custos. Verificação: falha em `recursos` não esconde as métricas.

## 4. Página e componentes

- [ ] 4.1 Criar `projetoImpacta/pages/projeto_detalhe.py` com `projeto_detalhe_page()`, portando do frontend de referência o cabeçalho, o breadcrumb, `_kpi_card_detalhe`, o bloco de equipes (`_barra_equipe`), o bloco de recursos (`_grupo_recursos`), o aviso de sem responsável e os estados vazios. Preservar estilos e tokens de `theme`. Verificação: página renderiza com dados de teste sem erro.
- [ ] 4.2 Ajustar a grade de KPIs para duas colunas, sem terceiro card (D6). Verificação: exatamente dois cards de métrica.
- [ ] 4.3 Remover da tela os blocos de custo por provedor, projeção, variação e coluna de valor por recurso. Verificação: nenhum desses textos ou colunas aparece na página.
- [ ] 4.4 Renderizar "Notificar DevOps" desabilitado, sem `on_click`. Verificação: botão visível e desabilitado; nenhum handler associado.
- [ ] 4.5 Implementar a exportação CSV com o módulo `csv` e `rx.download`, para "Exportar Dados" e "Exportar CSV". Verificação: arquivo tem as colunas definidas; campos com vírgula são escapados.

## 5. Rota e navegação

- [ ] 5.1 Registrar `/projetos/[projeto_id]` em `projetoImpacta/projetoImpacta.py` com `on_load=[AuthState.require_auth, ProjetoDetalheState.carregar]`. Verificação: a rota existe e a proteção de sessão é aplicada.
- [ ] 5.2 Ajustar o card de `projetoImpacta/pages/projetos.py` para mostrar "Ver detalhamento" e navegar ao detalhamento, sem que Editar e Desativar disparem a navegação (D2). Verificação: clique no card navega; clique em Editar abre o formulário sem navegar.

## 6. Validação local

- [ ] 6.1 Compilar o app Reflex com a versão do projeto (`reflex==0.9.12`) e revisar que não há import de `costguard`. Verificação: compilação sem erros e sem referência ao pacote externo.
- [ ] 6.2 Validar a change com `openspec validate frontend-detalhamento-projeto --strict`. Verificação: validação passa sem erros.

## 7. E2E

- [ ] 7.1 E2E admin com projeto 4 (PAGAMENTOS): abrir `/projetos`, clicar no card, conferir período, métricas, equipes com custo, recursos agrupados, aviso de sem responsável e botão desabilitado. Comparar os totais com a resposta de `GET /projetos/4/custos-equipe` para a mesma janela MTD. Verificação: valores da tela batem com a resposta do backend.
- [ ] 7.2 E2E admin com projeto sem registros no mês: confirmar o estado "Sem custos classificados" sem valores fictícios. Verificação: tela sem "US$ 0.00" calculado como custo e sem orçamento restante.
- [ ] 7.3 E2E de exportação CSV: conferir cabeçalho, linhas e ausência de colunas de valor. Verificação: arquivo baixado corresponde aos recursos ativos exibidos.
- [ ] 7.4 E2E de rota inválida e de projeto inexistente (`/projetos/abc`, `/projetos/999999`). Verificação: "Projeto não encontrado" sem erro de servidor.
- [ ] 7.5 E2E de sessão: acesso sem login redireciona a `/login`; token inválido gera redirecionamento após 401. Verificação: comportamento conforme a capability `autenticacao`.
- [ ] 7.6 E2E com usuário `role = leitura` **ativo**. Se não houver conta de leitura ativa, registrar o adiamento explicitamente, sem afirmar que o teste passou. Verificação: resultado registrado no relatório de validação.

## 8. Relatório e entrega

- [ ] 8.1 Registrar os comandos executados, saídas relevantes e resultado de cada etapa de validação. Verificação: relatório anexado ao fim do Apply, com o que não foi executado e o motivo.
- [ ] 8.2 Informar ao usuário os arquivos alterados e o `git add` sugerido, sem executar Git. Verificação: lista de arquivos de staging entregue para o usuário executar.
