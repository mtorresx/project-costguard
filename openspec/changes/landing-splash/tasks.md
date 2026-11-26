## 1. Implementação

- [x] 1.1 Copiar `assets/videos/logo-loading.mp4` da referência (somente leitura na pasta original).
- [x] 1.2 `pages/landing.py` adaptada (conteúdo fiel ao produto, ilustração sem números, rodapé sem links inexistentes, redireciona sessão para `/inicio`).
- [x] 1.3 `components/splash.py` com a sequência suavizada (design D3) e `extra_app_wraps`.
- [x] 1.4 Rotas: `/` landing, `/inicio` painel; menu, logotipo, `load_me` e link "Voltar ao início" no login.

## 2. Verificação

- [x] 2.1 E2E: landing sem sessão; âncoras; 375 px sem rolagem horizontal; "Entrar" → `/login`; sem números fictícios.
- [x] 2.2 E2E: login recusado sem overlay; login aceito com overlay, painel invisível durante o vídeo, revelação em `/inicio` com dados; usuário com sessão em `/` → `/inicio`; segundo login toca de novo.
- [x] 2.3 Regressão das páginas autenticadas (E2E de ajustes) com o painel em `/inicio`.
- [x] 2.4 Revisão pontual do Codex. _1ª rodada: 1 BLOQUEANTE (revelação antes da navegação concluir) e 3 IMPORTANTES (aviso de vídeo de exibição antiga; reduzir movimento ainda tocava o vídeo; Tab alcançava controles por baixo). Tratados. 2ª rodada: 3 RESOLVIDOS; bloqueante mantido porque o limite de 8 s ainda revelava sem o painel pronto — tratado com o overlay que permanece e oferece "Continuar". Validação do caminho de demora com alteração temporária local (aviso do painel removido do `on_load` e espera de 500 ms), restaurada byte a byte (SHA-256 conferido): mensagem exibida, overlay opaco sem dissolver sozinho, foco no botão, "Continuar" fecha. E2E `e2e_landing.py` 16/16 (inclui Tab bloqueado e reduzir movimento sem overlay) e `e2e_regressao.py` 13/13._
- [x] 2.5 `openspec validate landing-splash --strict`.

## Evidências (2026-11-03)

- 2.1/2.2 — `e2e_landing.py` (scratchpad): 14/14. Landing pública em `/` sem Azure/GCP/Slack/projeções/números fictícios e sem criar conta; "Entrar" → `/login`; link "Voltar ao início" (`href="/"`); login recusado sem overlay e com a mensagem genérica; login aceito: overlay entra, rota já é `/inicio` com overlay opaco (amostras a cada 0,5 s), overlay é desmontado e o painel aparece com dados; do clique ao painel 9,3 s (≈2 s de login + 7 s de vídeo + transição); usuário com sessão em `/` → `/inicio`; após sair, o segundo login anima de novo; 375 px sem rolagem horizontal e "Entrar" visível; sem erros de página. Capturas `landing.png`, `landing_375.png`, `splash_6.png`, `splash_borda.png`, `pos_splash.png`.
- Ajuste visual: a borda do quadro do vídeo aparecia como um retângulo sutil em volta do logotipo (também na referência); trocada a máscara por um degradê radial — captura `splash_borda.png` sem o retângulo.
- 2.3 — regressão reescrita para ler os valores esperados da API (os dados foram recriados a pedido do usuário): `e2e_regressao.py` 13/13 (indicador de alertas, Outubro/2026 no Início, ordenação por consumo, detalhe com mês fechado/custo/equipes, Alertas, Usuários, Provedores, sem erros de página).
- 2.5 — "Change 'landing-splash' is valid".
- Confirmação final do Codex (2026-11-03): bloqueante RESOLVIDO, sem problemas novos, sem bloqueante remanescente; revisor não alterou arquivos. E2E final `e2e_landing.py` 16/16 (espera fixa de 3 s do caso "login recusado" trocada por espera pela mensagem, após uma falha de tempo causada pela fila do limite do Xano; isolado, o caso respondeu em 0,6 s) e `e2e_regressao.py` 13/13.
