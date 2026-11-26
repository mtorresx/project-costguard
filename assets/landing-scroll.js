// O conteúdo e a pose inicial vêm no HTML. Só a cena acompanha o scroll.
if (!customElements.get("cg-cena-scroll")) {
  const poses = {
    hero:       { inclinacao: 55, angulo: -43, distancia: 15 },
    sobre:      { inclinacao: 64, angulo: -32, distancia: 37 },
    tags:       { inclinacao: 59, angulo: -36, distancia: 34 },
    orcamento:  { inclinacao: 55, angulo: -41, distancia: 34 },
    alertas:    { inclinacao: 51, angulo: -46, distancia: 34 },
    provedores: { inclinacao: 65, angulo: -38, distancia: 39 },
    final:      { inclinacao: 51, angulo: -43, distancia: 10 },
  };
  const destaques = ["hero", "tags", "orcamento", "alertas"];

  function ligarAbas(pagina, cena, ampla, opcoes) {
    const abas = [...pagina.querySelectorAll("[data-provedor]")];
    const paineis = pagina.querySelectorAll("[data-servicos]");
    const camadas = cena.querySelectorAll(".cg-nivel");
    let atual = "aws";

    function sincronizar() {
      for (const aba of abas) {
        const ativa = aba.dataset.provedor === atual;
        const local = ampla.matches || cena.contains(aba) ? "cena" : "lista";
        aba.setAttribute("aria-controls", "painel-" + local + "-" + aba.dataset.provedor);
        aba.setAttribute("aria-selected", String(ativa));
        aba.tabIndex = ativa ? 0 : -1;
      }
      for (const painel of paineis) painel.hidden = painel.dataset.servicos !== atual;
      const grupo = cena.querySelectorAll("[data-provedor]");
      camadas.forEach((el, i) => el.toggleAttribute("data-ativa", grupo[i].dataset.provedor === atual));
    }
    function selecionar(aba) {
      atual = aba.dataset.provedor;
      cena.setAttribute("data-escolha", "");
      sincronizar();
    }
    pagina.addEventListener("click", e => {
      const aba = e.target.closest("[data-provedor]");
      if (aba) selecionar(aba);
    }, opcoes);
    pagina.addEventListener("keydown", e => {
      const aba = e.target.closest("[data-provedor]");
      if (!aba) return;
      const irmas = [...aba.parentElement.querySelectorAll("[data-provedor]")];
      const i = irmas.indexOf(aba), n = irmas.length;
      const destinos = { Home: 0, End: n - 1, ArrowDown: (i+1)%n, ArrowRight: (i+1)%n,
                         ArrowUp: (i+n-1)%n, ArrowLeft: (i+n-1)%n };
      if (!Object.hasOwn(destinos, e.key)) return;
      e.preventDefault();
      const proxima = irmas[destinos[e.key]];
      selecionar(proxima);
      proxima.focus({preventScroll: true});
    }, opcoes);
    ampla.addEventListener("change", sincronizar, opcoes);
    sincronizar();
  }

  customElements.define("cg-cena-scroll", class extends HTMLElement {
    connectedCallback() {
      const cena = this;
      const pagina = cena.closest(".cg-landing");
      const figura = cena.closest("figure");
      const movimento = matchMedia("(prefers-reduced-motion: no-preference)");
      const ampla = matchMedia("(min-width: 54.001rem) and (min-height: 38.001rem)");
      const controle = new AbortController();
      const opcoes = { signal: controle.signal };
      // Aguarda também as abas da seção que vem depois da figura no HTML.
      const prepararAbas = () => ligarAbas(pagina, cena, ampla, opcoes);
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", prepararAbas, opcoes);
      else prepararAbas();
      let quadro = 0, centros = [], passos = [], niveis = [], legendas = [];
      let medir = true, rolagem = true, pesoHero = 0, angulo = -43;
      let tempoHero = 0, anterior = 0;

      function agendar() {
        if (!quadro && !document.hidden && movimento.matches && ampla.matches) {
          quadro = requestAnimationFrame(atualizar);
        }
      }

      function atualizar(agora) {
        quadro = 0;
        if (medir) {
          // As seções já foram montadas, inclusive na navegação interna do Reflex.
          passos = [...pagina.querySelectorAll("[data-passo]")];
          niveis = [...cena.querySelectorAll(".cg-nivel")];
          legendas = [...figura.querySelectorAll(".cg-legendas span")];
          centros = passos.map(el => {
            const caixa = el.getBoundingClientRect();
            return caixa.top + caixa.height / 2 + pagina.scrollTop;
          });
          medir = false;
          rolagem = true;
        }
        if (rolagem) {
          const limite = Math.max(1, pagina.scrollHeight - pagina.clientHeight);
          const fracao = Math.max(0, Math.min(1, pagina.scrollTop / limite));
          const ponto = centros[0] + fracao * (centros.at(-1) - centros[0]);
          const fim = Math.max(1, centros.findIndex(centro => centro >= ponto - .01));
          const inicio = fim - 1;
          // Mantém cada pose legível no centro do trecho e interpola entre trechos.
          const t = Math.max(0, Math.min(1, ((ponto - centros[inicio]) /
            (centros[fim] - centros[inicio]) - .18) / .64));
          const mistura = t * t * (3 - 2 * t);
          const origem = passos[inicio].dataset.passo;
          const destino = passos[fim].dataset.passo;
          const a = poses[origem], b = poses[destino];
          const valor = nome => a[nome] + (b[nome] - a[nome]) * mistura;
          const peso = passo => (passo === origem ? 1 - mistura : 0) + (passo === destino ? mistura : 0);
          pesoHero = peso("hero");
          angulo = valor("angulo");
          cena.style.setProperty("--inclinacao", valor("inclinacao") + "deg");
          cena.style.setProperty("--distancia", valor("distancia") + "px");
          cena.style.setProperty("--roadmap", peso("provedores"));
          cena.style.setProperty("--retorno", peso("final"));
          niveis.forEach((el, i) => el.style.setProperty("--luz", peso(destaques[i]) + (i === 0 ? peso("provedores") : 0)));
          const atual = mistura < .5 ? inicio : fim;
          legendas.forEach((el, i) => el.style.setProperty("--peso", i === atual ? 1 : 0));
          rolagem = false;
        }
        if (anterior && pesoHero) tempoHero += Math.min(agora - anterior, 64);
        anterior = pesoHero ? agora : 0;
        const giro = pesoHero * 5 * Math.sin(tempoHero / 4800);
        cena.style.setProperty("--angulo", (angulo + giro).toFixed(3) + "deg");
        if (pesoHero) agendar();
      }

      const entradas = new IntersectionObserver(itens => {
        for (const item of itens) {
          if (!item.isIntersecting) continue;
          if (movimento.matches) item.target.classList.add("cg-entrada");
          entradas.unobserve(item.target);
        }
      }, { root: pagina, threshold: .15 });
      const tamanho = new ResizeObserver(() => { medir = true; agendar(); });
      tamanho.observe(pagina);
      tamanho.observe(pagina.querySelector("main"));
      // O parser pode encontrar a cena antes das seções seguintes no HTML inicial.
      const observar = () => pagina.querySelectorAll("[data-passo]:not(.cg-hero)").forEach(el => entradas.observe(el));
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", observar, opcoes);
      else observar();

      function preferencia() {
        cancelAnimationFrame(quadro);
        quadro = anterior = 0;
        pagina.toggleAttribute("data-pausada", document.hidden);
        if (!ampla.matches || !movimento.matches) {
          for (const nome of ["--inclinacao", "--distancia", "--roadmap", "--retorno", "--angulo"]) cena.style.removeProperty(nome);
          niveis.forEach(el => el.style.removeProperty("--luz"));
          legendas.forEach(el => el.style.removeProperty("--peso"));
        }
        medir = true;
        agendar();
      }
      pagina.addEventListener("scroll", () => { rolagem = true; agendar(); }, { ...opcoes, passive: true });
      document.addEventListener("visibilitychange", preferencia, opcoes);
      movimento.addEventListener("change", preferencia, opcoes);
      ampla.addEventListener("change", preferencia, opcoes);
      preferencia();
      this.encerrar = () => {
        controle.abort();
        cancelAnimationFrame(quadro);
        tamanho.disconnect();
        entradas.disconnect();
      };
    }

    disconnectedCallback() { this.encerrar?.(); }
  });
}
