"""Tela de entrada com o logotipo animado, exibida logo após o login.

Incorporada do frontend original de referência, com a transição
suavizada a pedido do usuário. O elemento de vídeo avisa quando a reprodução
termina ou falha; tarefas em segundo plano cuidam dos tempos e dos fades.

Sequência:
1. O login é aceito e `SplashState.mostrar_pos_login("/inicio")` monta o overlay, que entra
   com fade-in curto sobre a tela de login.
2. Assim que o overlay está opaco, a rota já troca para o painel **por baixo dele**: o painel
   carrega os dados enquanto o vídeo toca, e nada dele fica visível.
3. Quando o vídeo termina (ou falha, ou passa `MAX_MS`) e o painel está pronto,
   o último quadro e o fundo se dissolvem juntos, com leve aproximação do logotipo.

O overlay fica acima das rotas (`app.extra_app_wraps`, ver `projetoImpacta.py`) e sobrevive à
troca de rota. O vídeo só é montado após o login com animação habilitada.
"""

import asyncio

import reflex as rx
from reflex.event import no_args_event_spec
from reflex_components_core.el.elements.media import Video

from .. import theme as t

VIDEO_SRC = "/videos/logo-loading.mp4"

# Chave geral: desligada, o login vai direto ao painel, sem overlay e sem baixar o vídeo.
SPLASH_ATIVO = True

# O vídeo dura cerca de 7 s. O limite só evita prender o usuário se o vídeo nunca avisar.
MAX_MS = 11000
FADE_IN_MS = 350          # entrada do overlay sobre o login
LOGO_SAIDA_MS = 520       # fade + leve aproximação durante a revelação do painel
FADE_OUT_MS = 800         # dissolução final do overlay sobre o painel
REVELAR_APOS_MS = 300     # mínimo, após o painel avisar que carregou, antes de revelar
ESPERA_PAINEL_MS = 8000   # após o fim do vídeo sem aviso do painel: mostra "Continuar"
ESPERA_MAXIMA_MS = 60000  # depois disso a espera automática para (o botão continua disponível)

VIDEO_LARGURA = "min(480px, 90vw)"
# O fundo do painel e a máscara radial integram o vídeo ao overlay.
FUNDO = t.BG

# Esfumaça as bordas do quadro do vídeo (o fundo dele é quase igual ao do overlay, mas
# não idêntico): sem isso aparece um retângulo em volta do logotipo.
_BORDA_SUAVE = "radial-gradient(ellipse 46% 44% at 50% 50%, #000 62%, transparent 100%)"
_SEM_MOVIMENTO = {"@media (prefers-reduced-motion: reduce)": {"animation": "none", "transition": "none", "transform": "none"}}

# Scripts mínimos (rx.call_script, recurso nativo do Reflex):
# preferência "reduzir movimento" do sistema e bloqueio do Tab enquanto o overlay cobre a tela
# (sem ele, o foco de teclado alcançaria controles invisíveis por baixo).
_JS_REDUZIR = "window.matchMedia('(prefers-reduced-motion: reduce)').matches"
_JS_PRENDER_FOCO = (
    "window.__cgSplashTab = window.__cgSplashTab || function (e) {"
    " const splash = document.getElementById('cg-splash');"
    " if (e.key === 'Tab' && splash) { e.preventDefault(); (splash.querySelector('button') || splash).focus(); } };"
    "document.addEventListener('keydown', window.__cgSplashTab, true);"
    "document.getElementById('cg-splash')?.focus({preventScroll:true});"
)
_JS_SOLTAR_FOCO = "if (window.__cgSplashTab) { document.removeEventListener('keydown', window.__cgSplashTab, true); }"

# O navegador confirma o fim do fade antes de o servidor trocar a rota. Se a
# animação estiver desativada, o fundo já nasce opaco e a lista estará vazia.
_JS_COBERTURA = """(async () => {
    const splash = document.getElementById('cg-splash');
    if (!splash) return -1;
    await Promise.allSettled(splash.getAnimations().map(animation => animation.finished));
    return splash.isConnected ? Number(splash.dataset.execucao) : -1;
})()"""


class SplashState(rx.State):
    visivel: bool = False
    mostrado: bool = False      # overlay já entrou (opaco)
    logo_saindo: bool = False   # logotipo sumindo
    saindo: bool = False        # overlay dissolvendo
    # "" | "tocando" | "concluindo"
    fase: str = ""
    destino: str = "/inicio"
    painel_pronto: bool = False  # o painel (/inicio) avisou que terminou de carregar
    demorando: bool = False      # painel ainda não avisou: overlay oferece "Continuar"
    # Numera cada exibição: tarefas de uma exibição antiga não agem sobre a atual.
    execucao: int = 0

    @rx.event
    def mostrar_pos_login(self, destino: str = "/inicio"):
        """Chamado após o login aceito: consulta a preferência de movimento e inicia."""
        self.destino = destino
        if not SPLASH_ATIVO:
            return rx.redirect(destino)
        return rx.call_script(_JS_REDUZIR, callback=SplashState.iniciar)

    @rx.event
    def iniciar(self, reduzir_movimento: bool):
        """Cobre a tela e toca o vídeo do começo; sem animação para quem pede menos movimento."""
        if reduzir_movimento is True:
            return rx.redirect(self.destino)
        self.execucao += 1
        self.visivel = True
        self.mostrado = False
        self.logo_saindo = False
        self.saindo = False
        self.painel_pronto = False
        self.demorando = False
        self.fase = "tocando"
        return SplashState.vigia(self.execucao)

    @rx.event
    def marcar_painel_pronto(self):
        """Último evento do on_load de /inicio: o painel montou e carregou os dados."""
        self.painel_pronto = True

    @rx.event(background=True)
    async def entrar(self, execucao: int):
        """O navegador terminou o fade desta exibição. A rota pode trocar."""
        async with self:
            if self.execucao != execucao or self.mostrado or not self.visivel:
                return
            self.mostrado = True
            destino = self.destino
        yield rx.redirect(destino)

    @rx.event(background=True)
    async def vigia(self, execucao: int):
        """Último recurso: se o vídeo nunca avisar que terminou, conclui após `MAX_MS`."""
        await asyncio.sleep(MAX_MS / 1000)
        async with self:
            if self.execucao != execucao or self.fase != "tocando":
                return
            self.fase = "concluindo"
        yield SplashState.concluir(execucao)

    @rx.event
    def video_terminou(self, execucao: int):
        """O vídeo desta exibição terminou (ou falhou); avisos de exibições antigas são ignorados."""
        if self.fase != "tocando" or execucao != self.execucao:
            return
        self.fase = "concluindo"
        return SplashState.concluir(self.execucao)

    @rx.event(background=True)
    async def concluir(self, execucao: int):
        """Espera o painel avisar que carregou e dissolve o logotipo junto com o overlay.

        Nunca revela a tela antes do aviso do painel. Se ele demorar, o overlay mostra uma
        mensagem e o botão "Continuar" (o usuário nunca fica preso) e a navegação é reenviada.
        """
        passos = 0
        while True:
            async with self:
                if self.execucao != execucao or self.saindo:
                    return  # outra exibição começou ou o usuário clicou em "Continuar"
                pronto = self.painel_pronto
                destino = self.destino
                if not pronto and passos * 50 >= ESPERA_PAINEL_MS and not self.demorando:
                    self.demorando = True
                    reenviar = True
                else:
                    reenviar = False
            if pronto:
                break
            if reenviar:
                yield rx.redirect(destino)
            if passos * 50 >= ESPERA_MAXIMA_MS:
                return  # aguarda o usuário clicar em "Continuar"
            passos += 1
            await asyncio.sleep(0.05)
        await asyncio.sleep(REVELAR_APOS_MS / 1000)
        async with self:
            if self.execucao != execucao or self.saindo:
                return
            self.logo_saindo = True
            self.saindo = True
        await asyncio.sleep(FADE_OUT_MS / 1000 + 0.05)
        async with self:
            if self.execucao != execucao:
                return
            self.visivel = False
            self.fase = ""
        yield rx.call_script(_JS_SOLTAR_FOCO)

    @rx.event(background=True)
    async def continuar(self):
        """Botão "Continuar" (painel demorando): fecha o overlay sobre a tela atual."""
        async with self:
            execucao = self.execucao
            self.logo_saindo = True
            self.saindo = True
        await asyncio.sleep(FADE_OUT_MS / 1000 + 0.05)
        async with self:
            if self.execucao != execucao:
                return
            self.visivel = False
            self.fase = ""
        yield rx.call_script(_JS_SOLTAR_FOCO)


class _VideoMarca(Video):
    """Expõe os eventos nativos de término e falha do MP4 ao Reflex."""

    on_ended: rx.EventHandler[no_args_event_spec]
    on_error: rx.EventHandler[no_args_event_spec]


def _overlay() -> rx.Component:
    return rx.box(
        _VideoMarca.create(
            src=VIDEO_SRC,
            auto_play=True,
            muted=True,
            loop=False,
            controls=False,
            plays_inline=True,
            aria_hidden="true",
            on_ended=SplashState.video_terminou(SplashState.execucao),
            on_error=SplashState.video_terminou(SplashState.execucao),
            style={
                "width": VIDEO_LARGURA,
                "aspect_ratio": "16 / 9",
                "object_fit": "contain",
                "pointer_events": "none",
                "mask_image": _BORDA_SUAVE,
                "opacity": rx.cond(SplashState.logo_saindo, "0", "1"),
                "transform": rx.cond(SplashState.logo_saindo, "scale(1.025)", "scale(1)"),
                "transition": f"opacity {LOGO_SAIDA_MS}ms ease-in-out, transform {LOGO_SAIDA_MS}ms ease-out",
                **_SEM_MOVIMENTO,
            },
        ),
        rx.cond(
            SplashState.demorando & ~SplashState.saindo,
            rx.vstack(
                rx.text("O painel está demorando mais que o esperado.", color=t.TEXT_MAIN, font_size="14px"),
                rx.button("Continuar", on_click=SplashState.continuar, auto_focus=True,
                          variant="soft", color_scheme="teal"),
                position="absolute",
                bottom="12%",
                align="center",
                spacing="3",
            ),
            rx.fragment(),
        ),
        id="cg-splash",
        custom_attrs={"data-execucao": SplashState.execucao},
        tab_index=-1,
        on_mount=[
            rx.call_script(_JS_PRENDER_FOCO),
            rx.call_script(_JS_COBERTURA, callback=SplashState.entrar),
        ],
        role="status",
        aria_label="Carregando o CostGuard",
        position="fixed",
        inset="0",
        z_index="100000",
        display="flex",
        align_items="center",
        justify_content="center",
        background=FUNDO,
        opacity=rx.cond(SplashState.saindo, "0", "1"),
        animation=f"cg-splash-entrada {FADE_IN_MS}ms ease-in-out",
        transition=f"opacity {FADE_OUT_MS}ms ease-in-out",
        style={
            "@keyframes cg-splash-entrada": {"from": {"opacity": 0}, "to": {"opacity": 1}},
            "outline": "none",
            **_SEM_MOVIMENTO,
        },
    )


def splash_overlay() -> rx.Component:
    if not SPLASH_ATIVO:
        return rx.fragment()
    return rx.cond(SplashState.visivel, _overlay())
