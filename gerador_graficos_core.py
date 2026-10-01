"""
Gerador de gráficos: linha, barras, barras empilhadas e tabela a partir de uma
tabela qualquer (primeira coluna = categoria, demais = séries).

Segue a peça do Alerta de Pesquisa (graficos_pesquisa_core) e reaproveita o que
é dela: Montserrat, título centrado que quebra antes da logo, grade pontilhada,
barra com a ponta do valor arredondada, rodapé cinza. O que muda é que aqui o
dado é livre, então a geometria inteira é MEDIDA: cabeçalho, legenda e rodapé
dizem quanto ocupam e a área do gráfico fica com o que sobra.

Decisões que valem explicação:

- Um eixo de valor só. Duas medidas de escala diferente no mesmo gráfico (R$ e
  %) não entram: a série de percentual só existe na tabela.
- Barra sempre parte do zero. Linha pode ter o eixo apertado, por opção.
- A cor segue a série, não a posição na seleção: tirar uma série do gráfico não
  repinta as que ficaram. Série única usa a cor da marca.
- Série de dado usa a paleta de gráficos da casa, não marinho/vinho. A ordem foi
  conferida em teste de paleta (vizinhas separadas também em deuteranopia).
  Mostarda, verde e salmão ficam abaixo de 3:1 contra o branco, e por isso a
  legenda está sempre presente e o rótulo de valor vem ligado por padrão.

Sem Streamlit: dá pra gerar por script e conferir sem subir o app.
"""

import io
import math
import os
import re
import threading
import unicodedata

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Ellipse, PathPatch, Rectangle
from matplotlib.ticker import MaxNLocator

import graficos_pesquisa_core as gp
from graficos_pesquisa_core import (BRANCO, ESCALAS_EXPORT, GELO, MARINHO,
                                    SUBTEXTO, TINTA)

RAIZ = os.path.dirname(os.path.abspath(__file__))

VINHO = "#962E4D"
FILETE = "#E1E1E1"

# Variação: dois sentidos, duas cores da marca. Nem verde nem vermelho.
COR_SOBE = "#44597F"
COR_CAI = VINHO

# Série de contexto: cinza que recua atrás da série destacada.
CINZA_CONTEXTO = "#B9B8B2"

# Um matiz só, do claro ao escuro, para séries que são etapas ordenadas da
# mesma coisa. O quarto tom é a própria cor da marca.
RAMPA_VINHO = ("#E6BDC9", "#D08EA3", "#B55F7B", "#962E4D", "#6E1F37", "#4A1425")
RAMPA_MARINHO = ("#C3CFE2", "#96A8C7", "#6B82AB", "#44597F", "#192D4E", "#0E1B31")

ESQUEMAS = {
    "tons": "Tons de uma cor (até 3 etapas do mesmo valor)",
    "destaque": "Uma série em destaque, as outras em cinza",
    "categorias": "Uma cor por série (coisas diferentes)",
}

# Sem eixo de valor, a unidade vai escrita uma vez na área do gráfico.
NOTA_UNIDADE = {"R$ milhões": "Em R$ milhões", "R$ bilhões": "Em R$ bilhões",
                "R$": "Em R$"}

# Paleta de gráficos (arquivo de cores da casa), na ordem validada.
PALETA = ("#6091D8", "#D8445D", "#C9A63F", "#4FA882", "#A96FAB", "#E8876A")
MAX_SERIES = len(PALETA)

TIPOS = {
    "linha": "Linha",
    "variacao": "Variação",
    "tempo": "Linha do tempo",
    "barras": "Barras",
    "ranking": "Ranking",
    "dois": "Dois momentos",
    "execucao": "Previsto x realizado",
    "cem": "Participação (100%)",
    "empilhadas": "Composição (empilhadas)",
    "hemiciclo": "Hemiciclo",
    "mapa": "Mapa de UFs",
    "numero": "Número em destaque",
    "matriz": "Matriz",
    "tabela": "Tabela",
}

# Quantas colunas de valor cada tipo usa. Fora daqui, o tipo aceita várias.
UMA_SERIE = ("ranking", "variacao", "mapa", "hemiciclo", "numero", "tempo")
DUAS_SERIES = ("execucao", "dois")
# A altura da peça acompanha o conteúdo; o tamanho escolhido manda na largura.
ALTURA_LIVRE = ("tabela", "tempo", "matriz", "numero")

# Rótulos de valor que cada tipo aceita; o primeiro é o padrão.
ROTULOS = {
    "linha": {"ultimo": "Só o último ponto", "todos": "Todos os pontos",
              "nenhum": "Nenhum"},
    "barras": {"todos": "Em toda barra", "nenhum": "Nenhum"},
    "empilhadas": {"todos": "Partes e total", "total": "Só o total",
                   "nenhum": "Nenhum"},
}

IDENTIDADES = {
    "EixoGov": {"logo": os.path.join(RAIZ, "logo_eixo_gov_magenta.png"),
                "destaque": VINHO, "rampa": RAMPA_VINHO},
    "Eleições 2026": {"logo": gp.LOGO_PADRAO, "destaque": MARINHO,
                      "rampa": RAMPA_MARINHO},
}

# (prefixo, sufixo) do eixo e da célula de tabela.
UNIDADES = {
    "R$ milhões": ("R$ ", " mi"),
    "R$ bilhões": ("R$ ", " bi"),
    "R$": ("R$ ", ""),
    "%": ("", "%"),
    "Número": ("", ""),
}

TAMANHOS = {
    "Paisagem (850 × 600)": (850, 600),
    "Slide 16:9 (960 × 540)": (960, 540),
    "Quadrado (800 × 800)": (800, 800),
}

FORMATOS = gp.FORMATOS

# Geometria em px da peça a 1× (dpi 100, então 1 unidade de tela = 1 px).
MARGEM = 38
LOGO_LARGURA = 85
LOGO_TOPO = 33
TITULO_TOPO = 30
TITULO_CORPOS = (17, 16, 15, 14, 13, 12)
RESPIRO = 16

# Contorno na cor do fundo em volta do rótulo de valor: o número continua
# legível quando uma linha passa por trás dele.
def _halo(peca):
    cor = BRANCO if peca.fundo == "none" else peca.fundo
    return [patheffects.withStroke(linewidth=3, foreground=cor)]


# ── leitura dos números ──────────────────────────────────────────────────────

_VAZIOS = {"", "-", "–", "—", "nan", "none", "n/d", "nd"}


def ler_numero(valor) -> tuple[float | None, bool, bool]:
    """(número, tem asterisco, entendi).

    'R$ 1.308,8 mi*' -> (1308.8, True, True); '-' -> (None, False, True);
    'abc' -> (None, False, False).

    Formato brasileiro: vírgula é decimal e ponto é milhar. Ponto sozinho só é
    milhar quando separa grupos de três dígitos ('1.234'); '308.8' é decimal.
    """
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return (None, False, True) if math.isnan(valor) else (float(valor), False, True)
    texto = str(valor if valor is not None else "").strip()
    if texto.lower() in _VAZIOS:
        return None, False, True
    marca = "*" in texto
    limpo = texto.replace("−", "-")
    negativo = limpo.lstrip("R$ ").startswith("-") or (
        limpo.startswith("(") and limpo.rstrip("* ").endswith(")"))
    limpo = re.sub(r"[^0-9.,]", "", limpo)
    if not re.search(r"\d", limpo):
        return None, marca, False
    if "," in limpo and "." in limpo:
        if limpo.rfind(",") > limpo.rfind("."):
            limpo = limpo.replace(".", "").replace(",", ".")
        else:
            limpo = limpo.replace(",", "")
    elif "," in limpo:
        limpo = limpo.replace(",", ".") if limpo.count(",") == 1 else limpo.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", limpo):
        limpo = limpo.replace(".", "")
    try:
        numero = float(limpo)
    except ValueError:
        return None, marca, False
    return (-numero if negativo else numero), marca, True


def series_da_tabela(cabecalho: list[str], linhas: list[list]) -> tuple[list[str], list[dict], list[str]]:
    """Tabela de texto -> (categorias, séries, avisos).

    A primeira coluna é a categoria (ano, órgão, UF...). Linha sem categoria e
    sem valor é descartada. Célula que não é número nem vazio vira aviso, com
    linha e coluna, e entra como vazia: nada é adivinhado.
    """
    categorias, avisos = [], []
    nomes = [str(c).strip() for c in cabecalho[1:]]
    colunas = [{"nome": n, "valores": [], "marcas": [], "textos": [],
                "pct": False, "indice": i}
               for i, n in enumerate(nomes)]
    for linha in linhas:
        celulas = ["" if c is None else str(c).strip() for c in linha]
        celulas += [""] * (len(cabecalho) - len(celulas))
        if not any(c and c.lower() not in _VAZIOS for c in celulas):
            continue
        categorias.append(celulas[0])
        for coluna, celula in zip(colunas, celulas[1:]):
            numero, marca, ok = ler_numero(celula)
            if not ok:
                avisos.append(f'"{celula}" em {coluna["nome"]} / {celulas[0] or "sem categoria"}')
            coluna["valores"].append(numero)
            coluna["marcas"].append(marca)
            coluna["textos"].append(celula)
    return categorias, colunas, avisos


def serie_percentual(nome: str, numerador: dict, denominador: dict) -> dict:
    """Série numerador/denominador em %, só onde os dois existem. O asterisco
    de qualquer um dos dois acompanha o resultado."""
    valores, marcas = [], []
    for n, d, mn, md in zip(numerador["valores"], denominador["valores"],
                            numerador["marcas"], denominador["marcas"]):
        ok = n is not None and d not in (None, 0)
        valores.append(n / d * 100 if ok else None)
        marcas.append(bool(ok and (mn or md)))
    return {"nome": nome, "valores": valores, "marcas": marcas,
            "textos": [""] * len(valores), "pct": True, "indice": -1}


_TEMPO = re.compile(
    r"^(\d{4}|\d{1,2}/\d{2,4}|\d{4}-\d{2}|[1-4]º? ?(tri|sem|bim)\w*[ /]?\d{0,4}"
    r"|(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\w*[ ./-]*\d{0,4})$", re.I)


def sugerir_tipo(categorias: list[str], n_series: int) -> tuple[str, str, str]:
    """(tipo, orientação, motivo) para servir de ponto de partida.

    Regra, não modelo: categoria que é tempo pede linha; UF pede mapa; uma
    coluna só de valor pede ranking; várias pedem barra, deitada quando o nome
    é longo ou a lista é comprida.
    """
    cats = [c for c in categorias if c]
    if len(cats) >= 3 and all(_TEMPO.match(c.strip()) for c in cats):
        return "linha", "vertical", "a primeira coluna é tempo"
    if len(cats) >= 10 and sum(1 for c in cats if sigla_uf(c)) >= len(cats) * 0.9 \
            and n_series == 1:
        return "mapa", "vertical", "a primeira coluna são UFs"
    if n_series > MAX_SERIES:
        return "tabela", "vertical", f"são mais de {MAX_SERIES} séries"
    if n_series == 1:
        return "ranking", "horizontal", "há uma coluna de valor e a primeira não é tempo"
    if len(cats) > 7 or any(len(c) > 14 for c in cats):
        return "barras", "horizontal", "os nomes das categorias são longos ou muitos"
    return "barras", "vertical", "a primeira coluna são categorias, não tempo"


_ETAPAS = re.compile(r"ploa|\bloa\b|dota[cç][aã]o|autorizad|empenh|liquidad|\bpag[oa]s?\b|"
                     r"previst|realizad|executad|or[cç]ad", re.I)


def parecem_etapas(nomes: list[str]) -> bool:
    """As séries são etapas do mesmo dinheiro (PLOA, dotação, empenhado, pago)?
    Decide a cor de partida: etapa ordenada pede tons de uma cor só."""
    return len(nomes) >= 2 and all(_ETAPAS.search(n) for n in nomes)


def par_execucao(nomes: list[str]) -> tuple[str, str]:
    """(previsto, realizado) de partida para o gráfico Previsto x realizado."""
    def achar(padroes, reserva):
        for padrao in padroes:
            for nome in nomes:
                if re.search(padrao, nome, re.I):
                    return nome
        return reserva
    previsto = achar((r"dota[cç][aã]o atual", r"autorizad", r"dota[cç][aã]o", r"\bloa\b",
                      r"previst", r"or[cç]ad"), nomes[0])
    realizado = achar((r"\bpag[oa]s?\b", r"liquidad", r"empenh", r"executad",
                       r"realizad"), nomes[-1])
    return previsto, realizado


# ── formatação ───────────────────────────────────────────────────────────────

def fmt_num(valor: float, casas: int = 1) -> str:
    """1308.8 -> '1.308,8' (ponto de milhar e vírgula decimal)."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def _fmt_rotulo(valor: float, unidade: str, casas: int) -> str:
    """Rótulo sobre a marca: só o número, porque a unidade já está no eixo.
    Percentual é a exceção, o % faz parte do número."""
    return fmt_num(valor, casas) + ("%" if unidade == "%" else "")


def _fmt_celula(valor, marca: bool, pct: bool, unidade: str, casas: int) -> str:
    if valor is None:
        return "–"
    if pct:
        texto = fmt_num(valor, 1) + "%"
    else:
        prefixo, sufixo = UNIDADES.get(unidade, ("", ""))
        texto = f"{prefixo}{fmt_num(valor, casas)}{sufixo}"
    return texto + ("*" if marca else "")


def _casas_das_marcas(marcas) -> int:
    for casas in (0, 1, 2):
        if all(abs(m - round(m, casas)) < 1e-9 for m in marcas):
            return casas
    return 2


# ── peça: figura medida em px ────────────────────────────────────────────────

class _Peca:
    """Figura a dpi 100, endereçada em px a partir do canto superior esquerdo."""

    def __init__(self, largura: int, altura: int, fundo: str, familia: str):
        self.L, self.A = largura, altura
        self.fundo, self.familia = fundo, familia
        # Figure direto, sem pyplot. O pyplot guarda as figuras num registro
        # global numerado, e o Streamlit desenha em várias threads (a prévia
        # de um rerun começa com o download do rerun anterior ainda rodando):
        # duas threads pegavam o mesmo número e desenhavam na MESMA figura. A
        # prévia saía embaralhada e, quando uma delas salvava em SVG, a outra
        # perdia o canvas no meio da medida (AttributeError em get_renderer).
        self.fig = Figure(figsize=(largura / 100, altura / 100), dpi=100)
        FigureCanvasAgg(self.fig)
        self.fig.patch.set_facecolor(fundo)

    def texto(self, x, y, conteudo, **estilo):
        estilo.setdefault("fontfamily", self.familia)
        estilo.setdefault("va", "top")
        return self.fig.text(x / self.L, 1 - y / self.A, conteudo, **estilo)

    def medir(self, conteudo, corpo, peso="normal", entrelinha=1.2) -> tuple[float, float]:
        alvo = self.fig.text(0, 0, conteudo, fontfamily=self.familia,
                             fontsize=corpo, fontweight=peso, linespacing=entrelinha)
        caixa = alvo.get_window_extent(self.fig.canvas.get_renderer())
        alvo.remove()
        return caixa.width, caixa.height

    def quebrar(self, conteudo, corpo, largura, peso="normal") -> str:
        """Quebra por palavra até caber na largura, respeitando as quebras que
        já vieram no texto."""
        saida = []
        for paragrafo in str(conteudo).splitlines():
            atual = ""
            for palavra in paragrafo.split():
                teste = f"{atual} {palavra}".strip()
                if not atual or self.medir(teste, corpo, peso)[0] <= largura:
                    atual = teste
                else:
                    saida.append(atual)
                    atual = palavra
            saida.append(atual)
        return "\n".join(saida)

    def circulo(self, x, y, raio, cor, borda=None):
        self.fig.add_artist(Ellipse(
            (x / self.L, 1 - y / self.A), 2 * raio / self.L, 2 * raio / self.A,
            transform=self.fig.transFigure, facecolor=cor,
            edgecolor=borda or "none", linewidth=1.5 if borda else 0, zorder=3))

    def retangulo(self, x, y, largura, altura, cor):
        self.fig.add_artist(Rectangle(
            (x / self.L, 1 - (y + altura) / self.A), largura / self.L,
            altura / self.A, transform=self.fig.transFigure, facecolor=cor,
            edgecolor="none"))


def _logo_recortada(caminho: str):
    """A logo sem a margem transparente/branca. Mesmo recorte do gráfico do
    alerta (graficos_pesquisa_core._colocar_logo), que lá vem junto com o
    posicionamento e por isso não dá para chamar daqui."""
    if not caminho or not os.path.exists(caminho):
        return None
    try:
        imagem = plt.imread(caminho)
    except Exception:
        return None
    if imagem.ndim == 3:
        alpha = imagem[:, :, 3] > 0.02 if imagem.shape[2] >= 4 else True
        rgb = imagem[:, :, :3]
        limite_branco = 0.92 if rgb.max() <= 1.0 else 235
        visivel = alpha & (rgb.min(axis=2) < limite_branco)
        if visivel.any():
            ys, xs = visivel.nonzero()
            margem = max(4, round(max(xs.max() - xs.min(), ys.max() - ys.min()) * 0.04))
            imagem = imagem[max(0, ys.min() - margem):ys.max() + margem + 1,
                            max(0, xs.min() - margem):xs.max() + margem + 1]
    return imagem


def _moldura(peca: _Peca, titulo: str, subtitulo: str, rodape: str,
             caminho_logo: str, incluir_logo: bool) -> tuple[float, float]:
    """Desenha título, subtítulo, logo e rodapé. Devolve (topo, base) em px da
    faixa que sobra para o conteúdo.

    A logo reserva o espaço dela mesmo na versão sem logo: as duas peças saem
    no mesmo .zip e precisam ter a mesma quebra de título e a mesma geometria.
    """
    fig, L = peca.fig, peca.L
    logo = _logo_recortada(caminho_logo)
    logo_esq = L - MARGEM - LOGO_LARGURA
    logo_base = 0.0
    if logo is not None:
        altura_logo = LOGO_LARGURA * logo.shape[0] / logo.shape[1]
        logo_base = LOGO_TOPO + altura_logo
        if incluir_logo:
            eixo = fig.add_axes([logo_esq / L, 1 - logo_base / peca.A,
                                 LOGO_LARGURA / L, altura_logo / peca.A], zorder=5)
            eixo.imshow(logo, aspect="auto")
            eixo.axis("off")

    # Centrado na peça: a largura útil é o dobro da distância do centro à logo.
    largura_util = 2 * (logo_esq - RESPIRO - L / 2)
    y = TITULO_TOPO
    titulo = str(titulo or "").strip()
    if titulo:
        linhas, corpo = None, TITULO_CORPOS[-1]
        for corpo in TITULO_CORPOS:
            linhas = gp._linhas_titulo(fig, titulo, peca.familia, corpo,
                                       largura_util / L, max_linhas=3)
            if linhas:
                break
        if not linhas:
            linhas = gp._quebrar_corrido(fig, gp._tokens_titulo(titulo),
                                         peca.familia, corpo, largura_util / L)
        bloco = "\n".join(linhas)
        peca.texto(L / 2, y, bloco, ha="center", fontsize=corpo,
                   fontweight="bold", color=MARINHO,
                   linespacing=gp.TITULO_ENTRELINHA)
        y += peca.medir(bloco, corpo, "bold", gp.TITULO_ENTRELINHA)[1]

    subtitulo = str(subtitulo or "").strip()
    if subtitulo:
        y += 9 if titulo else 0
        bloco = peca.quebrar(subtitulo, 9.5, largura_util)
        peca.texto(L / 2, y, bloco, ha="center", fontsize=9.5, color=SUBTEXTO,
                   linespacing=1.4)
        y += peca.medir(bloco, 9.5, entrelinha=1.4)[1]

    topo = max(y, logo_base) + RESPIRO + 4

    base = peca.A - 26
    rodape = str(rodape or "").strip()
    if rodape:
        bloco = peca.quebrar(rodape, 8, L - 2 * MARGEM)
        altura = peca.medir(bloco, 8, entrelinha=1.5)[1]
        peca.texto(MARGEM, peca.A - 24 - altura, bloco, fontsize=8,
                   color=SUBTEXTO, linespacing=1.5)
        base = peca.A - 24 - altura - RESPIRO
    return topo, base


def _legenda(peca: _Peca, itens: list[tuple[str, str]], topo: float) -> float:
    """Legenda em linha, centrada, quebrando quando não cabe. Devolve o novo
    topo. Com uma série só não há legenda: o título já diz o que ela é."""
    if len(itens) < 2:
        return topo
    amostra, folga, entre, alt_linha = 10, 6, 20, 19
    larguras = [amostra + folga + peca.medir(nome, 9.5)[0] for nome, _ in itens]
    limite = peca.L - 2 * MARGEM
    linhas, atual, soma = [], [], 0.0
    for item, largura in zip(itens, larguras):
        extra = largura + (entre if atual else 0)
        if atual and soma + extra > limite:
            linhas.append((atual, soma))
            atual, soma, extra = [], 0.0, largura
        atual.append((item, largura))
        soma += extra
    linhas.append((atual, soma))

    y = topo
    for linha, soma in linhas:
        x = (peca.L - soma) / 2
        for (nome, cor), largura in linha:
            peca.retangulo(x, y + (alt_linha - amostra) / 2 - 2, amostra, amostra, cor)
            peca.texto(x + amostra + folga, y + alt_linha / 2 - 2, nome,
                       va="center", fontsize=9.5, color=TINTA)
            x += largura + entre
        y += alt_linha
    return y + 10


def _eixos(peca: _Peca, eixo_valor: str):
    ax = peca.fig.add_axes([0.1, 0.2, 0.8, 0.6])
    ax.set_facecolor(peca.fundo)
    for lado in ("top", "right", "left", "bottom"):
        ax.spines[lado].set_visible(False)
    base = "bottom" if eixo_valor == "y" else "left"
    ax.spines[base].set_visible(True)
    ax.spines[base].set_color(SUBTEXTO)
    ax.spines[base].set_linewidth(0.8)
    # Por cima das marcas: o fio branco das empilhadas não pode picotar a base.
    ax.spines[base].set_zorder(6)
    ax.grid(axis=eixo_valor, color=SUBTEXTO, alpha=0.28, linewidth=0.8,
            linestyle=(0, (2, 4)), zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", length=0, colors=SUBTEXTO, labelsize=9.5)
    ax.tick_params(axis="x" if eixo_valor == "y" else "y", labelcolor=TINTA,
                   labelsize=10)
    return ax


def _encaixar(peca: _Peca, ax, esquerda, topo, direita, base) -> None:
    """Posiciona os eixos de modo que TUDO o que é deles (marcas, nomes do
    eixo, rótulos) caiba na caixa em px. Margem fixa corta nome longo; aqui a
    sobra é medida e devolvida, em poucas passadas."""
    alvo = (esquerda / peca.L, 1 - base / peca.A, direita / peca.L, 1 - topo / peca.A)
    pos = list(alvo)
    for _ in range(3):
        ax.set_position([pos[0], pos[1], max(0.05, pos[2] - pos[0]),
                         max(0.05, pos[3] - pos[1])])
        peca.fig.canvas.draw()
        caixa = ax.get_tightbbox(peca.fig.canvas.get_renderer())
        real = (caixa.x0 / peca.L, caixa.y0 / peca.A, caixa.x1 / peca.L, caixa.y1 / peca.A)
        pos = [p + (a - r) for p, a, r in zip(pos, alvo, real)]
    ax.set_position([pos[0], pos[1], max(0.05, pos[2] - pos[0]),
                     max(0.05, pos[3] - pos[1])])
    peca.fig.canvas.draw()


def _escala_valor(ax, eixo: str, valores: list[float], unidade: str,
                  do_zero: bool, folga: float = 0.12) -> None:
    """Limites e marcas do eixo de valor, com folga para o rótulo."""
    vmin, vmax = min(valores), max(valores)
    lo, hi = (min(0.0, vmin), max(0.0, vmax)) if do_zero else (vmin, vmax)
    vao = (hi - lo) or abs(hi) or 1.0
    if hi > 0 or not do_zero:
        hi += vao * folga
    if lo < 0:
        lo -= vao * folga
    elif not do_zero:
        lo = max(0.0, lo - vao * folga)
    marcas = [m for m in MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]).tick_values(lo, hi)
              if lo - 1e-9 <= m <= hi + 1e-9]
    casas = _casas_das_marcas(marcas)
    prefixo, sufixo = UNIDADES.get(unidade, ("", ""))
    rotulos = [f"{prefixo}{fmt_num(m, casas)}{sufixo}" for m in marcas]
    if eixo == "y":
        ax.set_ylim(lo, hi)
        ax.set_yticks(marcas)
        ax.set_yticklabels(rotulos)
    else:
        ax.set_xlim(lo, hi)
        ax.set_xticks(marcas)
        ax.set_xticklabels(rotulos)
    if lo < 0:
        (ax.axhline if eixo == "y" else ax.axvline)(0, color=SUBTEXTO, linewidth=0.8, zorder=2)


def _categorias_no_x(peca: _Peca, ax, categorias: list[str]) -> None:
    ax.set_xticks(range(len(categorias)))
    ax.set_xticklabels([gp._quebrar(c, 14) for c in categorias])
    if gp._rotulos_x_colidem(peca.fig, ax):
        ax.set_xticklabels(categorias, rotation=32, ha="right",
                           rotation_mode="anchor")


# Tons de uma cor só se sustentam até três séries: claro, cor da marca e
# escuro ficam longe um do outro. Com quatro ou cinco os vizinhos se confundem
# e ninguém sabe qual faixa é qual. Daí para cima, uma cor por série.
MAX_TONS = 3


def _tons(n: int, rampa: tuple) -> list[str]:
    """n tons (até MAX_TONS) do claro ao escuro: os extremos da rampa e, com
    três séries, a cor da marca no meio."""
    marca = VINHO if rampa is RAMPA_VINHO else rampa[2]
    escuro = rampa[5] if rampa is RAMPA_VINHO else rampa[4]
    return {1: [escuro if rampa is RAMPA_MARINHO else marca],
            2: [rampa[0], escuro if rampa is RAMPA_MARINHO else marca],
            3: [rampa[0], marca, escuro]}[n]


def _cores(series: list[dict], ident: dict, esquema: str, destaque: str) -> list[str]:
    """Cor de cada série conforme o papel que a cor cumpre na peça.

    tons: as séries são etapas ordenadas da mesma coisa (PLOA, dotação,
        empenhado, pago). Um matiz só, do claro ao escuro, na ordem das
        colunas. Matizes diferentes diriam que são coisas diferentes.
    destaque: uma série na cor da marca e as outras em cinza. É o que a peça
        quer que se leia; o resto é contexto.
    categorias: entidades distintas e sem ordem (órgãos, UFs, programas).
    """
    if len(series) == 1:
        return [ident["destaque"]]
    if esquema == "tons" and len(series) <= MAX_TONS:
        return _tons(len(series), ident["rampa"])
    if esquema == "destaque":
        nomes = [s["nome"] for s in series]
        alvo = destaque if destaque in nomes else nomes[-1]
        return [ident["destaque"] if n == alvo else CINZA_CONTEXTO for n in nomes]
    if all(0 <= s.get("indice", -1) < MAX_SERIES for s in series) and \
            len({s["indice"] for s in series}) == len(series):
        return [PALETA[s["indice"]] for s in series]
    return [PALETA[i] for i in range(len(series))]


def _tinta_sobre(cor: str) -> str:
    """Branco sobre preenchimento escuro, tinta sobre claro."""
    r, g, b = (int(cor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return BRANCO if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.42 else TINTA


def _corpo_rotulo(n_marcas: int) -> float:
    return 10.5 if n_marcas <= 8 else 9 if n_marcas <= 14 else 8 if n_marcas <= 22 else 7


def _eixo_valor_visivel(ax, eixo: str, visivel: bool) -> None:
    """Liga ou desliga os números e a grade do eixo de valor.

    Quando toda marca já tem o número escrito, o eixo repete a informação e a
    grade só suja. Sem rótulo, é o eixo que dá a escala e ele fica.
    """
    ax.grid(visivel, axis=eixo)
    if eixo == "y":
        ax.tick_params(axis="y", labelleft=visivel)
    else:
        ax.tick_params(axis="x", labelbottom=visivel)


def _nota_da_escala(peca, caixa, texto: str):
    """Sem eixo de valor, a unidade precisa estar escrita em algum lugar da
    peça. Vai uma linha discreta no canto da área do gráfico. Devolve a caixa
    já descontada dessa linha."""
    esquerda, topo, direita, base = caixa
    if not texto:
        return caixa
    peca.texto(esquerda, topo, texto, fontsize=8.5, color=SUBTEXTO)
    return esquerda, topo + 20, direita, base


# ── os desenhos ──────────────────────────────────────────────────────────────

def _desenhar_linha(peca, caixa, categorias, series, cores, unidade, casas,
                    rotulos, eixo_zero):
    esquerda, topo, direita, base = caixa
    ax = _eixos(peca, "y")
    n = len(categorias)
    ax.set_xlim(-0.35, n - 0.65)
    _escala_valor(ax, "y", [v for s in series for v in s["valores"] if v is not None],
                  unidade, eixo_zero)
    _categorias_no_x(peca, ax, categorias)

    finais, todos = [], []
    for serie, cor in zip(series, cores):
        contexto = cor == CINZA_CONTEXTO
        ys = [math.nan if v is None else v for v in serie["valores"]]
        # Anel branco no marcador: separa os pontos onde duas linhas se cruzam.
        # Série de contexto vai mais fina e por baixo da destacada.
        ax.plot(range(n), ys, color=cor, linewidth=1.6 if contexto else 2.4,
                marker="o", markersize=5 if contexto else 6.5,
                markeredgecolor=BRANCO, markeredgewidth=1.5,
                zorder=3 if contexto else 4, solid_capstyle="round")
        pontos = [(x, v) for x, v in enumerate(serie["valores"]) if v is not None]
        if not pontos:
            continue
        todos.extend((x, v) for x, v in pontos)
        finais.append((pontos[-1][0], pontos[-1][1], serie["nome"], cor))

    # No modo "último ponto" o nome da série vai escrito na ponta da linha, e
    # não numa legenda separada: o olho não precisa ir e voltar.
    def texto_final(v, nome):
        return f"{nome}  {_fmt_rotulo(v, unidade, casas)}" if len(series) > 1 \
            else _fmt_rotulo(v, unidade, casas)

    reserva = 0.0
    if rotulos == "ultimo" and finais:
        reserva = 30 + max(peca.medir(texto_final(v, nome), 9, "bold")[0]
                           for _, v, nome, _ in finais)
    _encaixar(peca, ax, esquerda, topo, direita - reserva, base)

    if rotulos == "todos":
        # Rótulo acima de cada ponto. No mesmo x, valores próximos empilham de
        # baixo para cima em vez de se sobrepor; número repetido sai uma vez.
        por_x: dict[int, list] = {}
        for x, v in todos:
            por_x.setdefault(x, []).append(v)
        for x, grupo in por_x.items():
            anterior, escritos = None, set()
            for v in sorted(grupo):
                texto = _fmt_rotulo(v, unidade, casas)
                if texto in escritos:
                    continue
                escritos.add(texto)
                y_px = ax.transData.transform((x, v))[1]
                alvo = y_px + 9 if anterior is None else max(y_px + 9, anterior + 13)
                anterior = alvo
                ax.annotate(texto, (x, v), xytext=(0, (alvo - y_px) * 0.72),
                            textcoords="offset points", ha="center", va="bottom",
                            fontsize=8.5, color=TINTA, zorder=5,
                            annotation_clip=False, path_effects=_halo(peca))

    if rotulos == "ultimo":
        # Os rótulos formam uma coluna à direita do gráfico, cada um na altura
        # do último ponto da sua série e com a amostra de cor ao lado. Rótulos
        # próximos se afastam (o ponto fica onde está, quem cede é o texto), e
        # a série que termina antes do fim ganha um fio até o seu rótulo.
        borda = ax.get_window_extent(peca.fig.canvas.get_renderer()).x1
        coluna = borda + 12
        anterior = None
        for x, v, nome, cor in sorted(finais, key=lambda f: f[1]):
            x_px, y_px = ax.transData.transform((x, v))
            alvo = y_px if anterior is None else max(y_px, anterior + 16)
            anterior = alvo
            contexto = cor == CINZA_CONTEXTO
            if x_px < borda - 12 or abs(alvo - y_px) > 3:
                peca.fig.add_artist(Line2D(
                    [(x_px + 6) / peca.L, (coluna - 3) / peca.L],
                    [y_px / peca.A, alvo / peca.A], transform=peca.fig.transFigure,
                    color=SUBTEXTO, linewidth=0.6, alpha=0.55))
            peca.retangulo(coluna, peca.A - alvo - 4, 8, 8, cor)
            peca.texto(coluna + 13, peca.A - alvo, texto_final(v, nome), va="center",
                       fontsize=9, fontweight="normal" if contexto else "bold",
                       color=SUBTEXTO if contexto else TINTA)


def _desenhar_barras(peca, caixa, categorias, series, cores, unidade, casas,
                     rotulos, vertical):
    eixo = "y" if vertical else "x"
    ax = _eixos(peca, eixo)
    n, k = len(categorias), len(series)
    valores = [v for s in series for v in s["valores"] if v is not None]
    _escala_valor(ax, eixo, valores, unidade, True,
                  folga=0.12 if vertical else 0.16)
    if vertical:
        ax.set_xlim(-0.6, n - 0.4)
        _categorias_no_x(peca, ax, categorias)
    else:
        ax.set_ylim(n - 0.4, -0.6)   # primeira categoria no topo
        ax.set_yticks(range(n))
        ax.set_yticklabels(categorias)

    if rotulos == "todos":
        _eixo_valor_visivel(ax, eixo, False)
        caixa = _nota_da_escala(peca, caixa, NOTA_UNIDADE.get(unidade, ""))

    grupo = 0.62 if k == 1 else 0.78
    passo = grupo / k
    largura = passo * (1.0 if k == 1 else 0.9)   # vão entre barras vizinhas
    corpo, girado = _corpo_rotulo(len(valores)), False
    if vertical and rotulos == "todos":
        # O rótulo não pode ser mais largo que o passo entre barras, senão
        # encosta no vizinho. Mede a barra numa passada sem rótulo e desce o
        # corpo até caber. Abaixo de 8 o número não se lê: aí o rótulo sobe
        # deitado sobre a barra, e se nem assim couber não é desenhado.
        _encaixar(peca, ax, *caixa)
        passo_px = abs(ax.transData.transform((passo, 0))[0]
                       - ax.transData.transform((0, 0))[0])
        textos = [_fmt_rotulo(v, unidade, casas) for v in valores]
        for corpo in (10.5, 10, 9.5, 9, 8.5, 8):
            if max(peca.medir(t, corpo, "bold")[0] for t in textos) <= passo_px - 3:
                break
        else:
            corpo, girado = 8, True
            if peca.medir("0", corpo, "bold")[1] > passo_px - 1:
                # Sem rótulo nenhum, quem dá a escala volta a ser o eixo.
                rotulos = "nenhum"
                _eixo_valor_visivel(ax, eixo, True)
            else:
                # Deitado, o rótulo precisa de altura: abre folga no topo.
                _escala_valor(ax, "y", valores, unidade, True, folga=0.22)
                _eixo_valor_visivel(ax, eixo, False)
    marcas = []
    for j, serie in enumerate(series):
        for i, v in enumerate(serie["valores"]):
            if v is None:
                continue
            centro = i - grupo / 2 + passo * (j + 0.5)
            marcas.append((centro, v, cores[j]))
            if rotulos != "todos":
                continue
            texto = _fmt_rotulo(v, unidade, casas)
            if vertical:
                ax.annotate(texto, (centro, v), xytext=(0, 4 if v >= 0 else -4),
                            textcoords="offset points", ha="center",
                            va="bottom" if v >= 0 else "top", fontsize=corpo,
                            rotation=90 if girado else 0,
                            fontweight="normal" if girado else "bold",
                            color=TINTA, zorder=4)
            else:
                ax.annotate(texto, (v, centro), xytext=(5 if v >= 0 else -5, 0),
                            textcoords="offset points",
                            ha="left" if v >= 0 else "right", va="center",
                            fontsize=corpo, fontweight="bold", color=TINTA, zorder=4)

    _encaixar(peca, ax, *caixa)

    # O raio só existe depois que os eixos têm posição e escala definitivas.
    raio_x, raio_y = gp._px_em_dados(ax, gp.RAIO_PONTA_PX)
    for centro, v, cor in marcas:
        sinal = 1 if v >= 0 else -1
        if vertical:
            caminho = gp._path_barra(centro - largura / 2, centro + largura / 2,
                                     0, v, raio_x, sinal * min(raio_y, abs(v)), True)
        else:
            caminho = gp._path_barra(0, v, centro - largura / 2, centro + largura / 2,
                                     sinal * min(raio_x, abs(v)), raio_y, False)
        ax.add_patch(PathPatch(caminho, facecolor=cor, edgecolor="none", zorder=3))


def _desenhar_empilhadas(peca, caixa, categorias, series, cores, unidade, casas,
                         rotulos, vertical):
    if any(v is not None and v < 0 for s in series for v in s["valores"]):
        raise ValueError("Barras empilhadas não aceitam valor negativo. "
                         "Use Barras, que desenha cada série lado a lado.")
    eixo = "y" if vertical else "x"
    ax = _eixos(peca, eixo)
    n = len(categorias)
    totais = [sum(s["valores"][i] or 0 for s in series) for i in range(n)]
    _escala_valor(ax, eixo, totais, unidade, True,
                  folga=0.12 if vertical else 0.16)
    if vertical:
        ax.set_xlim(-0.6, n - 0.4)
        _categorias_no_x(peca, ax, categorias)
    else:
        ax.set_ylim(n - 0.4, -0.6)
        ax.set_yticks(range(n))
        ax.set_yticklabels(categorias)

    if rotulos in ("todos", "total"):
        _eixo_valor_visivel(ax, eixo, False)
        caixa = _nota_da_escala(peca, caixa, NOTA_UNIDADE.get(unidade, ""))

    largura = 0.6
    if rotulos in ("todos", "total"):
        for i, total in enumerate(totais):
            if not total:
                continue
            texto = _fmt_rotulo(total, unidade, casas)
            if vertical:
                ax.annotate(texto, (i, total), xytext=(0, 4), textcoords="offset points",
                            ha="center", va="bottom", fontsize=_corpo_rotulo(n),
                            fontweight="bold", color=TINTA, zorder=4)
            else:
                ax.annotate(texto, (total, i), xytext=(5, 0), textcoords="offset points",
                            ha="left", va="center", fontsize=_corpo_rotulo(n),
                            fontweight="bold", color=TINTA, zorder=4)

    _encaixar(peca, ax, *caixa)

    # Fio na cor do fundo entre as partes: separa segmento de segmento sem
    # depender só da cor.
    fio = BRANCO if peca.fundo == "none" else peca.fundo
    acumulado = [0.0] * n
    for serie, cor in zip(series, cores):
        for i, v in enumerate(serie["valores"]):
            if not v:
                continue
            inicio = acumulado[i]
            acumulado[i] += v
            if vertical:
                forma = Rectangle((i - largura / 2, inicio), largura, v)
            else:
                forma = Rectangle((inicio, i - largura / 2), v, largura)
            forma.set(facecolor=cor, edgecolor=fio, linewidth=1.6, zorder=3)
            ax.add_patch(forma)
            if rotulos != "todos" or len(series) < 2:
                continue
            # Rótulo da parte só entra se couber dentro dela.
            texto = _fmt_rotulo(v, unidade, casas)
            larg_txt, alt_txt = peca.medir(texto, 8.5)
            p0 = ax.transData.transform((i - largura / 2, inicio) if vertical
                                        else (inicio, i - largura / 2))
            p1 = ax.transData.transform((i + largura / 2, inicio + v) if vertical
                                        else (inicio + v, i + largura / 2))
            if abs(p1[0] - p0[0]) < larg_txt + 6 or abs(p1[1] - p0[1]) < alt_txt + 4:
                continue
            centro = (i, inicio + v / 2) if vertical else (inicio + v / 2, i)
            ax.text(*centro, texto, ha="center", va="center", fontsize=8.5,
                    color=_tinta_sobre(cor), zorder=4)


def _desenhar_execucao(peca, caixa, categorias, previsto, realizado, ident,
                       unidade, casas):
    """Previsto x realizado: a barra larga e clara é o que estava autorizado, a
    estreita e escura por dentro é o que foi realizado. Em cima, o percentual.

    É a forma usual de mostrar execução orçamentária: as duas medidas são o
    mesmo dinheiro em momentos diferentes, então uma fica DENTRO da outra, e
    não ao lado (seriam duas coisas) nem empilhada (seria uma soma).
    """
    ax = _eixos(peca, "y")
    n = len(categorias)
    valores = [v for s in (previsto, realizado) for v in s["valores"] if v is not None]
    _escala_valor(ax, "y", valores, unidade, True, folga=0.2)
    ax.set_xlim(-0.6, n - 0.4)
    _categorias_no_x(peca, ax, categorias)
    _eixo_valor_visivel(ax, "y", False)

    nota = NOTA_UNIDADE.get(unidade, "")
    razao = f"Percentual: {realizado['nome']} / {previsto['nome']}"
    caixa = _nota_da_escala(peca, caixa, f"{nota}. {razao}" if nota else razao)

    cor_prev, cor_real = ident["rampa"][0], ident["destaque"]
    larg_prev, larg_real = 0.64, 0.34
    for i in range(n):
        p, r = previsto["valores"][i], realizado["valores"][i]
        topo = max(v for v in (p, r, 0) if v is not None)
        if p is not None and r is not None and p:
            ax.annotate(f"{fmt_num(r / p * 100, 1)}%", (i, topo), xytext=(0, 17),
                        textcoords="offset points", ha="center", va="bottom",
                        fontsize=11, fontweight="bold", color=TINTA, zorder=5)
        if p is not None:
            ax.annotate(f"de {_fmt_rotulo(p, unidade, casas)}" if r is not None
                        else _fmt_rotulo(p, unidade, casas), (i, topo),
                        xytext=(0, 4), textcoords="offset points", ha="center",
                        va="bottom", fontsize=8.5, color=SUBTEXTO, zorder=5)

    _encaixar(peca, ax, *caixa)

    raio_x, raio_y = gp._px_em_dados(ax, gp.RAIO_PONTA_PX)
    for i in range(n):
        p, r = previsto["valores"][i], realizado["valores"][i]
        for v, larg, cor, z in ((p, larg_prev, cor_prev, 3), (r, larg_real, cor_real, 4)):
            if v is None or v <= 0:
                continue
            caminho = gp._path_barra(i - larg / 2, i + larg / 2, 0, v,
                                     raio_x, min(raio_y, v), True)
            ax.add_patch(PathPatch(caminho, facecolor=cor, edgecolor="none", zorder=z))
        if r is not None and r > 0:
            # Valor realizado dentro da barra escura, se couber.
            texto = _fmt_rotulo(r, unidade, casas)
            larg_txt, alt_txt = peca.medir(texto, 8.5, "bold")
            p0 = ax.transData.transform((i - larg_real / 2, 0))
            p1 = ax.transData.transform((i + larg_real / 2, r))
            if p1[0] - p0[0] >= larg_txt + 4 and p1[1] - p0[1] >= alt_txt + 12:
                ax.annotate(texto, (i, r), xytext=(0, -7), textcoords="offset points",
                            ha="center", va="top", fontsize=8.5, fontweight="bold",
                            color=_tinta_sobre(cor_real), zorder=5)


# ── formas novas ─────────────────────────────────────────────────────────────

def _desenhar_ranking(peca, caixa, itens, ident, unidade, casas, destaque):
    """Barras deitadas, da maior para a menor. Todas medem a mesma coisa, então
    têm a mesma cor; com um item em destaque, ele fica na cor da marca e os
    outros recuam para o cinza."""
    ax = _eixos(peca, "x")
    n = len(itens)
    valores = [v for _, v in itens]
    _escala_valor(ax, "x", valores, unidade, True, folga=0.16)
    ax.set_ylim(n - 0.4, -0.6)
    ax.set_yticks(range(n))
    ax.set_yticklabels([c for c, _ in itens])
    _eixo_valor_visivel(ax, "x", False)
    caixa = _nota_da_escala(peca, caixa, NOTA_UNIDADE.get(unidade, ""))
    corpo = 10.5 if n <= 10 else 9.5 if n <= 16 else 8.5
    for i, (cat, v) in enumerate(itens):
        forte = not destaque or cat == destaque
        ax.annotate(_fmt_rotulo(v, unidade, casas), (v, i),
                    xytext=(5 if v >= 0 else -5, 0), textcoords="offset points",
                    ha="left" if v >= 0 else "right", va="center", fontsize=corpo,
                    fontweight="bold" if forte else "normal",
                    color=TINTA if forte else SUBTEXTO, zorder=4)
    if destaque:
        for rotulo, (cat, _) in zip(ax.get_yticklabels(), itens):
            if cat == destaque:
                rotulo.set_fontweight("bold")
    _encaixar(peca, ax, *caixa)
    raio_x, raio_y = gp._px_em_dados(ax, gp.RAIO_PONTA_PX)
    for i, (cat, v) in enumerate(itens):
        cor = ident["destaque"] if not destaque or cat == destaque else CINZA_CONTEXTO
        sinal = 1 if v >= 0 else -1
        caminho = gp._path_barra(0, v, i - 0.32, i + 0.32,
                                 sinal * min(raio_x, abs(v)), raio_y, False)
        ax.add_patch(PathPatch(caminho, facecolor=cor, edgecolor="none", zorder=3))


def _desenhar_variacao(peca, caixa, categorias, serie, unidade, casas, vertical):
    """Barras a partir do zero, para cima ou para baixo. Duas cores porque são
    dois sentidos; nenhuma delas é verde ou vermelha, para a peça não dizer
    por conta própria que subir é bom e cair é ruim."""
    itens = [(c, v) for c, v in zip(categorias, serie["valores"]) if v is not None]
    eixo = "y" if vertical else "x"
    ax = _eixos(peca, eixo)
    n = len(itens)
    _escala_valor(ax, eixo, [v for _, v in itens] + [0], unidade, True,
                  folga=0.14 if vertical else 0.2)
    if vertical:
        ax.set_xlim(-0.6, n - 0.4)
        _categorias_no_x(peca, ax, [c for c, _ in itens])
    else:
        ax.set_ylim(n - 0.4, -0.6)
        ax.set_yticks(range(n))
        ax.set_yticklabels([c for c, _ in itens])
    _eixo_valor_visivel(ax, eixo, False)
    caixa = _nota_da_escala(peca, caixa, NOTA_UNIDADE.get(unidade, ""))
    corpo = _corpo_rotulo(n)
    for i, (_, v) in enumerate(itens):
        texto = ("+" if v > 0 else "") + _fmt_rotulo(v, unidade, casas)
        if vertical:
            ax.annotate(texto, (i, v), xytext=(0, 4 if v >= 0 else -4),
                        textcoords="offset points", ha="center",
                        va="bottom" if v >= 0 else "top", fontsize=corpo,
                        fontweight="bold", color=TINTA, zorder=4)
        else:
            ax.annotate(texto, (v, i), xytext=(5 if v >= 0 else -5, 0),
                        textcoords="offset points", ha="left" if v >= 0 else "right",
                        va="center", fontsize=corpo, fontweight="bold",
                        color=TINTA, zorder=4)
    _encaixar(peca, ax, *caixa)
    raio_x, raio_y = gp._px_em_dados(ax, gp.RAIO_PONTA_PX)
    for i, (_, v) in enumerate(itens):
        if not v:
            continue
        cor = COR_SOBE if v > 0 else COR_CAI
        sinal = 1 if v > 0 else -1
        if vertical:
            caminho = gp._path_barra(i - 0.31, i + 0.31, 0, v, raio_x,
                                     sinal * min(raio_y, abs(v)), True)
        else:
            caminho = gp._path_barra(0, v, i - 0.31, i + 0.31,
                                     sinal * min(raio_x, abs(v)), raio_y, False)
        ax.add_patch(PathPatch(caminho, facecolor=cor, edgecolor="none", zorder=3))


def _desenhar_cem(peca, caixa, categorias, series, cores, casas):
    """Cada linha é um todo de 100% dividido nas séries. Deitada, porque o que
    se compara é a fatia de cada linha, e nome de categoria se lê deitado."""
    if any(v is not None and v < 0 for s in series for v in s["valores"]):
        raise ValueError("Participação não aceita valor negativo.")
    linhas = []
    for i, cat in enumerate(categorias):
        partes = [s["valores"][i] or 0 for s in series]
        if sum(partes) > 0:
            linhas.append((cat, [p / sum(partes) * 100 for p in partes]))
    if not linhas:
        raise ValueError("Nenhuma linha com valor para dividir em 100%.")
    ax = _eixos(peca, "x")
    n = len(linhas)
    ax.set_xlim(0, 100)
    ax.set_xticks([])
    ax.set_ylim(n - 0.4, -0.6)
    ax.set_yticks(range(n))
    ax.set_yticklabels([c for c, _ in linhas])
    ax.spines["left"].set_visible(False)
    _eixo_valor_visivel(ax, "x", False)
    _encaixar(peca, ax, *caixa)
    fio = BRANCO if peca.fundo == "none" else peca.fundo
    for i, (_, partes) in enumerate(linhas):
        inicio = 0.0
        for parte, cor in zip(partes, cores):
            if parte <= 0:
                continue
            forma = Rectangle((inicio, i - 0.31), parte, 0.62)
            forma.set(facecolor=cor, edgecolor=fio, linewidth=1.6, zorder=3)
            ax.add_patch(forma)
            texto = fmt_num(parte, min(casas, 1)) + "%"
            larg_txt = peca.medir(texto, 9.5, "bold")[0]
            p0 = ax.transData.transform((inicio, 0))[0]
            p1 = ax.transData.transform((inicio + parte, 0))[0]
            if p1 - p0 >= larg_txt + 8:
                ax.text(inicio + parte / 2, i, texto, ha="center", va="center",
                        fontsize=9.5, fontweight="bold", color=_tinta_sobre(cor),
                        zorder=4)
            inicio += parte


def _desenhar_dois(peca, caixa, itens, antes, depois, ident, unidade, casas):
    """Dois momentos da mesma medida, ligados por um fio em cada linha. O olho
    lê o tamanho e o sentido da mudança de cada item."""
    ax = _eixos(peca, "x")
    n = len(itens)
    valores = [v for _, a, d in itens for v in (a, d) if v is not None]
    _escala_valor(ax, "x", valores, unidade, False, folga=0.22)
    ax.set_ylim(n - 0.4, -0.6)
    ax.set_yticks(range(n))
    ax.set_yticklabels([c for c, _, _ in itens])
    ax.spines["left"].set_visible(False)
    _eixo_valor_visivel(ax, "x", False)
    caixa = _nota_da_escala(peca, caixa, NOTA_UNIDADE.get(unidade, ""))
    cor_antes, cor_depois = ident["rampa"][1], ident["destaque"]
    for i, (_, a, d) in enumerate(itens):
        ax.axhline(i, color=FILETE, linewidth=0.8, zorder=1)
        if a is not None and d is not None:
            ax.plot([a, d], [i, i], color=CINZA_CONTEXTO, linewidth=3, zorder=2,
                    solid_capstyle="round")
        for v, cor, forte in ((a, cor_antes, False), (d, cor_depois, True)):
            if v is None:
                continue
            outro = d if not forte else a
            # O rótulo vai para o lado de fora do par, para não cair no fio.
            direita = outro is None or v >= outro
            if outro is not None and v == outro and not forte:
                continue
            ax.plot([v], [i], marker="o", markersize=10, color=cor,
                    markeredgecolor=BRANCO, markeredgewidth=1.5, zorder=4 if forte else 3)
            ax.annotate(_fmt_rotulo(v, unidade, casas), (v, i),
                        xytext=(10 if direita else -10, 0), textcoords="offset points",
                        ha="left" if direita else "right", va="center", fontsize=9.5,
                        fontweight="bold" if forte else "normal",
                        color=TINTA if forte else SUBTEXTO, zorder=5)
    _encaixar(peca, ax, *caixa)


# Mapa de UFs em grade: cada UF é um quadrado do mesmo tamanho, na posição
# aproximada do mapa. (linha, coluna)
GRADE_UF = {
    "RR": (0, 1), "AP": (0, 3),
    "AC": (1, 0), "AM": (1, 1), "PA": (1, 2), "MA": (1, 3), "CE": (1, 4), "RN": (1, 5),
    "RO": (2, 1), "TO": (2, 2), "PI": (2, 3), "PB": (2, 4), "PE": (2, 5),
    "MT": (3, 1), "GO": (3, 2), "BA": (3, 3), "AL": (3, 4), "SE": (3, 5),
    "MS": (4, 1), "DF": (4, 2), "MG": (4, 3), "ES": (4, 4),
    "SP": (5, 2), "RJ": (5, 3),
    "PR": (6, 2), "SC": (6, 3),
    "RS": (7, 2),
}

_NOMES_UF = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
    "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}

SEM_DADO = "#ECEBE6"


def sigla_uf(texto: str) -> str:
    """'pe', 'Pernambuco' ou 'PE' -> 'PE'. Vazio se não for UF."""
    bruto = str(texto or "").strip()
    if bruto.upper() in GRADE_UF:
        return bruto.upper()
    chave = unicodedata.normalize("NFKD", bruto.lower())
    chave = "".join(c for c in chave if not unicodedata.combining(c))
    return _NOMES_UF.get(chave, "")


def _classes_do_mapa(categorias, serie, ident, unidade, casas):
    """(cor e texto de cada UF, legenda). Coluna numérica vira até cinco faixas
    de um tom só; coluna de texto vira uma cor por categoria."""
    dados = {}
    for cat, valor, texto in zip(categorias, serie["valores"], serie["textos"]):
        uf = sigla_uf(cat)
        if uf and str(texto).strip() and str(texto).strip().lower() not in _VAZIOS:
            dados[uf] = (valor, str(texto).strip())
    if not dados:
        raise ValueError("Nenhuma UF reconhecida na primeira coluna. Use a sigla "
                         "(PE) ou o nome do estado.")
    numerico = all(v is not None for v, _ in dados.values())
    por_uf, legenda = {}, []
    if numerico:
        valores = [v for v, _ in dados.values()]
        lo, hi = min(valores), max(valores)
        k = min(5, len(set(valores)))
        passos = [round(j * 4 / max(1, k - 1)) for j in range(k)] if k > 1 else [3]
        cores = [ident["rampa"][p] for p in passos]
        for uf, (v, _) in dados.items():
            classe = 0 if hi == lo else min(int((v - lo) / (hi - lo) * k), k - 1)
            por_uf[uf] = (cores[classe], _fmt_rotulo(v, unidade, casas))
        for j, cor in enumerate(cores):
            if k == 1 or hi == lo:
                legenda.append((cor, _fmt_rotulo(lo, unidade, casas)))
            else:
                a, b = lo + (hi - lo) * j / k, lo + (hi - lo) * (j + 1) / k
                legenda.append((cor, f"{_fmt_rotulo(a, unidade, casas)} a "
                                     f"{_fmt_rotulo(b, unidade, casas)}"))
    else:
        nomes = list(dict.fromkeys(t for _, t in dados.values()))
        if len(nomes) > MAX_SERIES:
            raise ValueError(f"O mapa aceita até {MAX_SERIES} categorias; "
                             f"esta coluna tem {len(nomes)}.")
        # Duas categorias: a cor da marca contra um neutro. Três: tons. Mais:
        # uma cor por categoria.
        if len(nomes) <= 2:
            cores = [ident["destaque"], ident["rampa"][0]][:len(nomes)]
        elif len(nomes) == 3:
            cores = list(reversed(_tons(3, ident["rampa"])))
        else:
            cores = list(PALETA[:len(nomes)])
        cor_de = dict(zip(nomes, cores))
        for uf, (_, t) in dados.items():
            por_uf[uf] = (cor_de[t], "")
        legenda = [(cor_de[nome], nome) for nome in nomes]
    if len(por_uf) < len(GRADE_UF):
        legenda.append((SEM_DADO, "Sem dado"))
    return por_uf, legenda


def _desenhar_mapa(peca, caixa, categorias, serie, ident, unidade, casas):
    esquerda, topo, direita, base = caixa
    por_uf, legenda = _classes_do_mapa(categorias, serie, ident, unidade, casas)
    larg_leg = 26 + max(peca.medir(t, 9.5)[0] for _, t in legenda)
    vao = 4
    lado = min((base - topo) / 8, (direita - esquerda - larg_leg - 44) / 6) - vao
    larg_mapa = 6 * (lado + vao) - vao
    x0 = esquerda + (direita - esquerda - larg_mapa - 44 - larg_leg) / 2
    y0 = topo + (base - topo - (8 * (lado + vao) - vao)) / 2
    for uf, (lin, col) in GRADE_UF.items():
        cor, valor = por_uf.get(uf, (SEM_DADO, ""))
        x, y = x0 + col * (lado + vao), y0 + lin * (lado + vao)
        peca.retangulo(x, y, lado, lado, cor)
        tinta = _tinta_sobre(cor) if uf in por_uf else SUBTEXTO
        cabe = bool(valor) and peca.medir(valor, 7.5)[0] <= lado - 6
        peca.texto(x + lado / 2, y + lado / 2 - (6 if cabe else 0), uf, ha="center",
                   va="center", fontsize=10, fontweight="bold", color=tinta)
        if cabe:
            peca.texto(x + lado / 2, y + lado / 2 + 8, valor, ha="center",
                       va="center", fontsize=7.5, color=tinta)
    xl = x0 + larg_mapa + 44
    yl = y0 + (8 * (lado + vao) - len(legenda) * 24) / 2
    if serie["nome"]:
        peca.texto(xl, yl - 24, serie["nome"], fontsize=9.5, fontweight="bold",
                   color=TINTA, va="center")
    for j, (cor, texto) in enumerate(legenda):
        peca.retangulo(xl, yl + j * 24, 14, 14, cor)
        peca.texto(xl + 22, yl + j * 24 + 7, texto, fontsize=9.5, color=TINTA,
                   va="center")


def _desenhar_hemiciclo(peca, caixa, grupos, cores, rotulo_total):
    """Um ponto por cadeira, em arcos. Os grupos ocupam fatias da esquerda para
    a direita, na ordem em que vieram na tabela."""
    esquerda, topo, direita, base = caixa
    total = sum(n for _, n in grupos)
    if total < 1:
        raise ValueError("O hemiciclo precisa de pelo menos uma cadeira.")
    if total > 700:
        raise ValueError("O hemiciclo desenha até 700 cadeiras.")
    cx, cy = (esquerda + direita) / 2, base - 6
    # Folga do tamanho de um ponto: a cadeira da borda não pode sair da área.
    raio = min((direita - esquerda) / 2, base - topo - 10) - 14
    cy -= 14
    interno = raio * 0.40
    # Menor número de arcos em que todas as cadeiras cabem com o mesmo
    # espaçamento entre arcos e ao longo de cada arco.
    for arcos in range(1, 20):
        passo = (raio - interno) / max(1, arcos - 1) if arcos > 1 else raio - interno
        raios = [interno + i * passo for i in range(arcos)] if arcos > 1 else [raio * 0.8]
        capacidade = [int(math.pi * r / passo) + 1 for r in raios]
        if sum(capacidade) >= total:
            break
    soma = sum(raios)
    cotas = [total * r / soma for r in raios]
    por_arco = [int(c) for c in cotas]
    for i in sorted(range(arcos), key=lambda i: cotas[i] - por_arco[i], reverse=True):
        if sum(por_arco) >= total:
            break
        por_arco[i] += 1
    cadeiras = []
    for r, n in zip(raios, por_arco):
        for j in range(n):
            angulo = math.pi - j * math.pi / (n - 1) if n > 1 else math.pi / 2
            cadeiras.append((angulo, r))
    cadeiras.sort(key=lambda c: (-c[0], c[1]))
    arco_menor = math.pi * raios[0] / max(1, por_arco[0] - 1) if por_arco[0] > 1 else passo
    ponto = min(min(passo, arco_menor) * 0.40, 12)
    donos = [cor for (_, n), cor in zip(grupos, cores) for _ in range(n)]
    for (angulo, r), cor in zip(cadeiras, donos):
        peca.circulo(cx + r * math.cos(angulo), cy - r * math.sin(angulo), ponto, cor)
    peca.texto(cx, cy - 30, fmt_num(total, 0), ha="center", va="center",
               fontsize=26, fontweight="bold", color=MARINHO)
    if rotulo_total:
        peca.texto(cx, cy - 6, rotulo_total.lower(), ha="center", va="center",
                   fontsize=9.5, color=SUBTEXTO)


def _desenhar_numero(peca, topo, itens, ident) -> float:
    """De um a quatro números grandes lado a lado, cada um com a sua legenda.
    Devolve a altura ocupada."""
    esquerda, direita = MARGEM, peca.L - MARGEM
    coluna = (direita - esquerda) / len(itens)
    for corpo in (64, 56, 48, 42, 36, 30, 26):
        if max(peca.medir(numero, corpo, "bold")[0] for _, numero in itens) <= coluna - 36:
            break
    alt_num = peca.medir("0", corpo, "bold")[1]
    blocos = []
    for legenda, numero in itens:
        texto = peca.quebrar(legenda, 11, coluna - 40)
        blocos.append((numero, texto, peca.medir(texto, 11, entrelinha=1.4)[1]))
    alt_total = alt_num + 16 + max(b[2] for b in blocos)
    y = topo + 22
    for i, (numero, texto, _) in enumerate(blocos):
        cx = esquerda + coluna * (i + 0.5)
        if i:
            peca.retangulo(esquerda + coluna * i, y, 1, alt_total, FILETE)
        peca.texto(cx, y, numero, ha="center", fontsize=corpo, fontweight="bold",
                   color=ident["destaque"])
        peca.texto(cx, y + alt_num + 16, texto, ha="center", fontsize=11,
                   color=TINTA, linespacing=1.4)
    return alt_total + 44


def _desenhar_tempo(peca, topo, marcos, ident) -> float:
    """Marcos de cima para baixo: data à esquerda, ponto no fio, texto à
    direita. Devolve a altura ocupada; a peça cresce com o número de marcos."""
    larg_data = min(190, max(peca.medir(d, 10, "bold")[0] for d, _ in marcos))
    x_fio = MARGEM + larg_data + 20
    x_txt = x_fio + 20
    y = topo + 6
    pontos = []
    for data, texto in marcos:
        bloco = peca.quebrar(texto, 10, peca.L - MARGEM - x_txt) if texto else ""
        alt = max(16, peca.medir(bloco, 10, entrelinha=1.45)[1] if bloco else 0)
        peca.texto(x_fio - 20, y, data, ha="right", fontsize=10, fontweight="bold",
                   color=MARINHO)
        if bloco:
            peca.texto(x_txt, y, bloco, fontsize=10, color=TINTA, linespacing=1.45)
        pontos.append(y + 7)
        y += alt + 22
    if len(pontos) > 1:
        peca.retangulo(x_fio - 1, pontos[0], 2, pontos[-1] - pontos[0], FILETE)
    for py in pontos:
        peca.circulo(x_fio, py, 5.5, ident["destaque"], borda=BRANCO)
    return y - 22 - topo + 6


def _desenhar_matriz(peca, topo, categorias, series, ident, unidade, casas) -> float:
    """Linhas x colunas com a célula mais escura onde o valor é maior. Devolve
    a altura ocupada."""
    valores = [v for s in series for v in s["valores"] if v is not None]
    if not valores:
        raise ValueError("Nenhum valor numérico para a matriz.")
    lo, hi = min(valores), max(valores)
    util = peca.L - 2 * MARGEM
    larg_rot = min(util * 0.34, 14 + max(peca.medir(c, 10, "bold")[0] for c in categorias))
    col = (util - larg_rot) / len(series)
    if col < 44:
        raise ValueError("A matriz não cabe na largura da peça: tire colunas ou "
                         "escolha um tamanho mais largo.")
    cab = [peca.quebrar(s["nome"], 8.5, col - 8, "bold") for s in series]
    alt_cab = max(peca.medir(c, 8.5, "bold", 1.3)[1] for c in cab) + 14
    alt_lin, vao = 34, 3
    for j, texto in enumerate(cab):
        peca.texto(MARGEM + larg_rot + col * (j + 0.5), topo + alt_cab - 8, texto,
                   ha="center", va="bottom", multialignment="center", fontsize=8.5,
                   fontweight="bold", color=SUBTEXTO, linespacing=1.3)
    y = topo + alt_cab
    for i, cat in enumerate(categorias):
        rot = peca.quebrar(cat, 10, larg_rot - 10, "bold").split("\n")[0]
        peca.texto(MARGEM, y + alt_lin / 2, rot, va="center", fontsize=10,
                   fontweight="bold", color=MARINHO)
        for j, serie in enumerate(series):
            v = serie["valores"][i]
            x = MARGEM + larg_rot + col * j
            if v is None:
                peca.retangulo(x, y, col - vao, alt_lin - vao, SEM_DADO)
                continue
            passo = 2 if hi == lo else min(int((v - lo) / (hi - lo) * 5), 4)
            cor = ident["rampa"][passo]
            peca.retangulo(x, y, col - vao, alt_lin - vao, cor)
            peca.texto(x + (col - vao) / 2, y + (alt_lin - vao) / 2,
                       _fmt_rotulo(v, unidade, casas), ha="center", va="center",
                       fontsize=9.5, color=_tinta_sobre(cor))
        y += alt_lin
    return y - topo


def _tabela_medidas(peca, cabecalho, celulas, largura_util):
    """Maior corpo em que a tabela cabe na largura. Devolve (corpo, corpo do
    cabeçalho, cabeçalhos já quebrados, larguras de coluna)."""
    recuo = 12
    cab = [gp._quebrar(str(c).upper(), 12) for c in cabecalho]
    # Mede uma vez no corpo 10 e escala: a largura do texto é linear no corpo.
    larg_cab = [peca.medir(c, 10, "bold", 1.3)[0] for c in cab]
    larg_cel = [max((peca.medir(linha[j], 10, "bold" if j == 0 else "normal")[0]
                     for linha in celulas), default=0) for j in range(len(cab))]
    for corpo in (11, 10.5, 10, 9.5, 9, 8.5, 8, 7.5, 7):
        corpo_cab = max(6.5, corpo - 2.5)
        colunas = [max(c * corpo_cab / 10, v * corpo / 10) + 2 * recuo
                   for c, v in zip(larg_cab, larg_cel)]
        if sum(colunas) <= largura_util:
            sobra = (largura_util - sum(colunas)) / len(colunas)
            return corpo, corpo_cab, cab, [c + sobra for c in colunas]
    raise ValueError("A tabela não cabe na largura da peça: tire colunas, "
                     "encurte os nomes ou escolha um tamanho mais largo.")


def _desenhar_tabela(peca, topo, medidas, celulas, destaque):
    corpo, corpo_cab, cab, colunas = medidas
    recuo = 12
    alt_cab = max(peca.medir(c, corpo_cab, "bold", 1.3)[1] for c in cab) + 22
    alt_linha = corpo * 100 / 72 * 2.5
    x0 = MARGEM
    largura = sum(colunas)

    peca.retangulo(x0, topo, largura, alt_cab, destaque)
    x = x0
    for j, (texto, larg) in enumerate(zip(cab, colunas)):
        peca.texto(x + recuo if j == 0 else x + larg - recuo, topo + alt_cab / 2,
                   texto, ha="left" if j == 0 else "right", va="center",
                   multialignment="left" if j == 0 else "right",
                   fontsize=corpo_cab, fontweight="bold", color=BRANCO,
                   linespacing=1.3)
        x += larg

    y = topo + alt_cab
    for r, linha in enumerate(celulas):
        if r % 2:
            peca.retangulo(x0, y, largura, alt_linha, GELO)
        peca.retangulo(x0, y + alt_linha - 0.8, largura, 0.8, FILETE)
        x = x0
        for j, (texto, larg) in enumerate(zip(linha, colunas)):
            peca.texto(x + recuo if j == 0 else x + larg - recuo, y + alt_linha / 2,
                       texto, ha="left" if j == 0 else "right", va="center",
                       fontsize=corpo, fontweight="bold" if j == 0 else "normal",
                       color=MARINHO if j == 0 else TINTA)
            x += larg
        y += alt_linha
    return alt_cab + alt_linha * len(celulas)


# ── entrada única ────────────────────────────────────────────────────────────

# Uma peça por vez. A figura já não é compartilhada, mas o rc_context (fonte,
# svg.fonttype) é estado global do matplotlib: dois desenhos ao mesmo tempo
# trocariam a configuração um do outro.
_TRAVA = threading.Lock()


def gerar_peca(*args, **kwargs) -> bytes:
    """Devolve o arquivo em bytes, pronto pro st.image e pro st.download_button.

    series: [{nome, valores, marcas, pct, indice}], como sai de
    series_da_tabela(). Série com pct=True só é aceita na tabela.

    Na tabela a altura da peça acompanha o número de linhas; o tamanho escolhido
    manda só na largura.
    """
    with _TRAVA:
        return _gerar_peca(*args, **kwargs)


def _gerar_peca(
    tipo: str,
    categorias: list[str],
    series: list[dict],
    *,
    titulo: str = "",
    subtitulo: str = "",
    rodape: str = "",
    rotulo_categoria: str = "",
    unidade: str = "Número",
    casas: int = 1,
    orientacao: str = "vertical",
    rotulos: str = "",
    eixo_zero: bool = True,
    esquema: str = "categorias",
    destaque: str = "",
    limite: int = 0,
    identidade: str = "EixoGov",
    incluir_logo: bool = True,
    tamanho: str = "",
    escala: int = 2,
    formato: str = "png",
    fundo_transparente: bool = False,
) -> bytes:
    if tipo not in TIPOS:
        raise ValueError(f"Tipo desconhecido: {tipo}")
    if not categorias or not series:
        raise ValueError("Sem dados para desenhar.")
    if tipo != "tabela" and any(s.get("pct") for s in series):
        raise ValueError("Série de percentual calculado só entra na tabela.")
    if tipo in UMA_SERIE and len(series) != 1:
        raise ValueError(f"{TIPOS[tipo]} usa uma coluna de valor só.")
    if tipo in DUAS_SERIES and len(series) != 2:
        raise ValueError(f"{TIPOS[tipo]} usa exatamente duas séries.")
    if tipo in ("linha", "barras", "empilhadas", "cem") and len(series) > MAX_SERIES:
        raise ValueError(f"Gráfico com mais de {MAX_SERIES} séries não se lê: "
                         "escolha até 6 ou use a tabela.")
    if tipo not in ("tabela", "tempo", "mapa") and \
            not any(v is not None for s in series for v in s["valores"]):
        raise ValueError("Nenhum valor numérico nas séries escolhidas.")

    ident = IDENTIDADES.get(identidade) or IDENTIDADES["EixoGov"]
    largura, altura = TAMANHOS.get(tamanho) or next(iter(TAMANHOS.values()))
    escala = escala if escala in ESCALAS_EXPORT else 2
    formato = formato if formato in FORMATOS else "png"
    opcoes_rotulo = ROTULOS.get(tipo, {})
    rotulos = rotulos if rotulos in opcoes_rotulo else next(iter(opcoes_rotulo), "")
    familia = gp._registrar_fonte()
    fundo = "none" if fundo_transparente else BRANCO
    moldura = (titulo, subtitulo, rodape, ident["logo"], incluir_logo)
    um = series[0]
    com_valor = [(c, v, i) for i, (c, v) in enumerate(zip(categorias, um["valores"]))
                 if v is not None]

    # Texto do SVG vira contorno: o arquivo abre igual em máquina sem Montserrat.
    with matplotlib.rc_context({"font.family": familia, "svg.fonttype": "path"}):
        if tipo in ALTURA_LIVRE:
            # Primeira passada só mede: cabeçalho e rodapé têm altura em px que
            # não depende da altura da figura.
            rascunho = _Peca(largura, 600, fundo, familia)
            topo, base = _moldura(rascunho, *moldura)
            if tipo == "tabela":
                celulas = [[cat] + [_fmt_celula(s["valores"][i], s["marcas"][i],
                                                s.get("pct"), unidade, casas)
                                    for s in series]
                           for i, cat in enumerate(categorias)]
                cabecalho = [rotulo_categoria] + [s["nome"] for s in series]
                medidas = _tabela_medidas(rascunho, cabecalho, celulas,
                                          largura - 2 * MARGEM)
                desenhar = lambda p, t: _desenhar_tabela(p, t, medidas, celulas,
                                                         ident["destaque"])
            elif tipo == "tempo":
                marcos = [(c, t) for c, t in zip(categorias, um["textos"]) if c or t]
                if not marcos:
                    raise ValueError("Nenhum marco para a linha do tempo.")
                desenhar = lambda p, t: _desenhar_tempo(p, t, marcos, ident)
            elif tipo == "numero":
                itens = [(c, _fmt_celula(v, um["marcas"][i], False, unidade, casas))
                         for c, v, i in com_valor]
                if len(itens) > 4:
                    raise ValueError("Número em destaque mostra até quatro números. "
                                     "Deixe na tabela só as linhas que entram.")
                desenhar = lambda p, t: _desenhar_numero(p, t, itens, ident)
            else:
                desenhar = lambda p, t: _desenhar_matriz(p, t, categorias, series,
                                                         ident, unidade, casas)
            ocupado = desenhar(rascunho, topo)
            altura = math.ceil(topo + ocupado + RESPIRO + (600 - base))
            peca = _Peca(largura, altura, fundo, familia)
            topo, _ = _moldura(peca, *moldura)
            desenhar(peca, topo)
        else:
            # Barra deitada precisa de altura por linha: a peça cresce quando a
            # lista é comprida, em vez de espremer as barras.
            deitada = tipo in ("ranking", "cem", "dois") or \
                (tipo == "variacao" and orientacao == "horizontal")
            if deitada:
                n_linhas = len(com_valor) if tipo in ("ranking", "variacao") else len(categorias)
                if tipo == "ranking" and limite:
                    n_linhas = min(n_linhas, limite)
                altura = max(altura, 240 + 36 * n_linhas)
            peca = _Peca(largura, altura, fundo, familia)
            topo, base = _moldura(peca, *moldura)
            caixa = (MARGEM, topo, largura - MARGEM, base)

            def com_legenda(itens):
                return (MARGEM, _legenda(peca, itens, topo), largura - MARGEM, base)

            if tipo == "execucao":
                _desenhar_execucao(
                    peca, com_legenda([(series[0]["nome"], ident["rampa"][0]),
                                       (series[1]["nome"], ident["destaque"])]),
                    categorias, series[0], series[1], ident, unidade, casas)
            elif tipo == "ranking":
                itens = sorted(((c, v) for c, v, _ in com_valor),
                               key=lambda t: t[1], reverse=True)
                _desenhar_ranking(peca, caixa, itens[:limite] if limite else itens,
                                  ident, unidade, casas, destaque)
            elif tipo == "variacao":
                _desenhar_variacao(peca, caixa, categorias, um, unidade, casas,
                                   orientacao != "horizontal")
            elif tipo == "dois":
                antes, depois = series
                itens = [(c, a, d) for c, a, d in zip(categorias, antes["valores"],
                                                     depois["valores"])
                         if a is not None or d is not None]
                itens.sort(key=lambda t: (t[2] is None, -(t[2] or 0)))
                _desenhar_dois(
                    peca, com_legenda([(antes["nome"], ident["rampa"][1]),
                                       (depois["nome"], ident["destaque"])]),
                    itens, antes, depois, ident, unidade, casas)
            elif tipo == "mapa":
                _desenhar_mapa(peca, caixa, categorias, um, ident, unidade, casas)
            elif tipo == "hemiciclo":
                grupos = [(c, int(round(v))) for c, v, _ in com_valor if v > 0]
                if len(grupos) > MAX_SERIES:
                    raise ValueError(f"O hemiciclo aceita até {MAX_SERIES} grupos: "
                                     "junte os menores numa linha Outros.")
                cores = list(PALETA[:len(grupos)]) if len(grupos) > 1 else [ident["destaque"]]
                _desenhar_hemiciclo(
                    peca, com_legenda([(f"{nome}  {fmt_num(n, 0)}", cor)
                                       for (nome, n), cor in zip(grupos, cores)]),
                    grupos, cores, um["nome"])
            else:
                cores = _cores(series, ident, esquema, destaque)
                legenda = [(s["nome"], c) for s, c in zip(series, cores)]
                if tipo == "linha":
                    # Linha com o nome escrito na ponta dispensa legenda.
                    esq, topo_l, dir_, base_l = caixa if rotulos == "ultimo" \
                        else com_legenda(legenda)
                    _desenhar_linha(peca, (esq, topo_l + 6, dir_, base_l), categorias,
                                    series, cores, unidade, casas, rotulos, eixo_zero)
                elif tipo == "barras":
                    _desenhar_barras(peca, com_legenda(legenda), categorias, series,
                                     cores, unidade, casas, rotulos,
                                     orientacao != "horizontal")
                elif tipo == "cem":
                    _desenhar_cem(peca, com_legenda(legenda), categorias, series,
                                  cores, casas)
                else:
                    _desenhar_empilhadas(peca, com_legenda(legenda), categorias,
                                         series, cores, unidade, casas, rotulos,
                                         orientacao != "horizontal")

        buffer = io.BytesIO()
        peca.fig.savefig(buffer, format=formato, dpi=100 * escala,
                         facecolor=fundo, transparent=fundo_transparente)
    return buffer.getvalue()


def slug_arquivo(titulo: str, tipo: str, extensao: str = "png", sufixo: str = "") -> str:
    """Nome do arquivo baixado: linha_acao-217m-evolucao-orcamentaria_com-logo.png"""
    bruto = unicodedata.normalize("NFKD", str(titulo or ""))
    bruto = "".join(c for c in bruto if not unicodedata.combining(c))
    bruto = re.sub(r"[^A-Za-z0-9]+", "-", bruto).strip("-").lower()[:60].strip("-")
    pedacos = [p for p in (tipo, bruto or "grafico", sufixo) if p]
    return "_".join(pedacos) + f".{extensao}"
