## Decisões

### D1. Rotas

`/` vira a landing pública (como na referência). O painel autenticado vai para `/inicio`; o item "Início" do menu e o logotipo apontam para `/inicio`. A landing, ao montar, leva quem tem token na sessão para `/inicio`, onde `require_auth` valida o token no backend.

### D2. Overlay acima das rotas

`app.extra_app_wraps[(3, "Splash")]` monta o overlay fora das páginas (recurso disponível no Reflex 0.9.12), para que ele sobreviva à troca de rota. Um `<video preload="auto">` invisível baixa o vídeo antecipadamente.

### D3. Sequência suavizada

1. `AuthState.load_me` (após `/me` com sucesso) retorna `SplashState.mostrar_pos_login("/inicio")`.
2. O overlay monta com opacidade 0 e entra com fade de 350 ms.
3. Opaco, a rota troca para `/inicio` por baixo dele: `require_auth` e `HomeState.carregar` rodam enquanto o vídeo toca (~7 s).
4. Fim do vídeo (`on_ended`), falha (`on_error`) ou limite de 11 s: o logotipo some (fade 450 ms + escala 1,06); garante-se que a troca de rota já ocorreu e que se passaram 300 ms; o overlay dissolve em 800 ms (`cubic-bezier(0.22, 1, 0.36, 1)`) com `pointer-events: none`; depois é desmontado.

Revisão do Codex (2026-11-03): a revelação passou a depender do aviso real do painel (`SplashState.marcar_painel_pronto`, último evento do `on_load` de `/inicio`), não do envio do redirecionamento; após 8 s sem aviso, o overlay permanece, mostra a demora, reenvia a navegação e oferece "Continuar" (foco automático), parando a espera automática em 60 s. `video_terminou` recebe a execução; "reduzir movimento" é lido do navegador por `rx.call_script` (vai direto ao painel); enquanto o overlay existe, o Tab é bloqueado e o foco removido (script mínimo via `rx.call_script`).

Cada exibição tem um número (`execucao`): tarefas de exibições anteriores não agem sobre a atual (logins consecutivos tocam do início). `SPLASH_ATIVO = False` desliga a animação (redirecionamento direto).

Diferença em relação à spec da referência: lá o usuário ficava em `/login` até o fim do vídeo; aqui a rota troca no início, sob o overlay opaco — o painel continua invisível até o fim, mas fica pronto, o que torna a revelação suave.

### D4. Conteúdo da landing

Somente fatos do produto: AWS, tags de projeto/equipe, orçamento mensal, alertas 70/90/100%, recursos sem classificação, falhas de importação, papéis admin/leitura, credenciais somente leitura. A ilustração do painel usa rótulos reais e barras sem valores, nas cores das faixas do domínio. Nenhuma chamada ao backend.
