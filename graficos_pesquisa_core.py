"""
Gráfico de barras de pesquisa eleitoral, gerado por código a partir do MESMO
payload que o Polling Manual extrai (ver polling_extracao_core).

Layout fixo de propósito: o gráfico é peça de divulgação e precisa sair igual
toda vez. Quem chama escolhe só orientação e logo; o resto (cor, tipografia,
escala, rodapé) é regra, não opção.

Decisões que valem explicação:

- Escala sempre de 0 a 100%. Barra com base cortada mente sobre proporção, e
  percentual de um todo lê naturalmente contra os 100%.
- Uma cor só de matiz. O candidato é identificado pelo rótulo do eixo, não pela
  cor, então não existe paleta categórica aqui. Brancos/nulos/indecisos usam um
  passo mais claro do mesmo vinho para recuar sem virar outra entidade.
  Separação medida: ΔE 16,7 (visão normal) e 15,2 (deuteranopia).
- Ponta arredondada só no lado do valor. A base fica reta, colada no zero.

Sem Streamlit: dá pra gerar PNG por script e conferir sem subir o app.
"""

import io
import os
import re
import unicodedata

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import PathPatch
from matplotlib.path import Path

RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_FONTES = os.path.join(RAIZ, "fontes")
LOGO_PADRAO = os.path.join(RAIZ, "Marca_eixo_vetor_Logo horizontal magenta.png")

# Paleta Eixo (mesma do app, ver Gerador_de_Envios.py).
VINHO = "#962E4D"       # candidato
VINHO_CLARO = "#AE7286"  # branco/nulo/indeciso: mesmo matiz, passo mais claro
GELO = "#F4F3EF"        # fundo
MARINHO = "#192D4E"     # título
TINTA = "#111111"       # rótulo de valor e nome no eixo
SUBTEXTO = "#767672"    # eixo, grade e rodapé

LARGURA_PX = 850
ALTURA_PX = 600
RAIO_PONTA_PX = 4
ORIENTACOES = ("vertical", "horizontal")
FORMATOS = ("png", "svg")

# Multiplicador sobre 850x600. O 2x é o padrão: 1700x1200 é nítido no WhatsApp
# sem virar arquivo pesado.
ESCALAS_EXPORT = {
    1: "Original",
    2: "Alta qualidade",
    3: "Impressão",
    4: "Ultra HD",
}


def resolucao(escala: int = 2) -> tuple[int, int]:
    """Dimensão final do PNG naquela escala, pra página mostrar antes de baixar."""
    escala = escala if escala in ESCALAS_EXPORT else 2
    return LARGURA_PX * escala, ALTURA_PX * escala

_FONTE_PRONTA = False


def _registrar_fonte() -> str:
    """Registra a Montserrat que vive em fontes/. Se faltar, cai na fonte padrão
    do matplotlib em vez de estourar: melhor gráfico fora da tipografia da casa
    do que nenhum gráfico."""
    global _FONTE_PRONTA
    if not _FONTE_PRONTA:
        for peso in ("Regular", "SemiBold", "Bold"):
            caminho = os.path.join(DIR_FONTES, f"Montserrat-{peso}.ttf")
            if os.path.exists(caminho):
                font_manager.fontManager.addfont(caminho)
        _FONTE_PRONTA = True
    disponiveis = {f.name for f in font_manager.fontManager.ttflist}
    return "Montserrat" if "Montserrat" in disponiveis else "DejaVu Sans"


def montserrat_disponivel() -> bool:
    """Pra página avisar quando o gráfico vai sair fora da tipografia da casa."""
    return _registrar_fonte() == "Montserrat"


def _rotulo_candidato(item: dict) -> str:
    """'Maria Silva (PT)'. Brancos/nulos não levam partido."""
    nome = str(item.get("candidato") or "").strip()
    partido = str(item.get("partido") or "").strip()
    if item.get("tipo") == "nao_valido" or not partido:
        return nome
    return f"{nome} ({partido})"


def _quebrar(texto: str, limite: int = 12) -> str:
    """Quebra o rótulo em no máximo 2 linhas, pra nome longo não colidir com o
    vizinho no eixo X."""
    palavras = texto.split()
    linhas, atual = [], ""
    for palavra in palavras:
        teste = f"{atual} {palavra}".strip()
        if len(teste) <= limite or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    if len(linhas) > 2:
        linhas = [linhas[0], " ".join(linhas[1:])]
    return "\n".join(linhas)


def _desenhar_rodape(fig, texto: str, familia: str) -> None:
    """Ficha técnica em UMA linha, encolhendo a fonte até caber.

    Quebrar em duas linhas afasta o rodapé do eixo e desequilibra a peça, então
    a largura manda: mede o texto de verdade e reduz o corpo até entrar. Só se
    não couber nem no menor corpo é que quebra.
    """
    esquerda, direita = 0.045, 0.955
    alvo = fig.text(esquerda, 0.045, texto, ha="left", va="center",
                    fontfamily=familia, fontsize=8.5, color=SUBTEXTO)
    for corpo in (8.5, 8.0, 7.5, 7.0, 6.5, 6.0):
        alvo.set_fontsize(corpo)
        fig.canvas.draw()
        largura = alvo.get_window_extent().width / fig.bbox.width
        if largura <= (direita - esquerda):
            return
    # Ficha muito longa (instituto de nome comprido + tudo preenchido): aí sim
    # quebra, já no menor corpo.
    alvo.set_text(_quebrar_rodape(texto, orcamento=118))
    alvo.set_linespacing(1.6)


def _quebrar_rodape(texto: str, orcamento: int = 96) -> str:
    """Quebra a ficha técnica nos separadores ' | ', respeitando um orçamento de
    caracteres por linha. Sem isso o rodapé atravessa a figura e passa por baixo
    da logo (o wrap do matplotlib usa a largura cheia e ignora a logo)."""
    if not texto:
        return ""
    blocos = texto.split(" | ")
    linhas, atual = [], ""
    for bloco in blocos:
        teste = f"{atual} | {bloco}" if atual else bloco
        if len(teste) <= orcamento or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = bloco
    if atual:
        linhas.append(atual)
    return "\n".join(linhas)


def _fmt_pct(valor) -> str:
    """34.0 -> '34%'; 4.5 -> '4,5%' (vírgula decimal, como se publica no Brasil)."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return ""
    if abs(n - round(n)) < 0.05:
        return f"{int(round(n))}%"
    return f"{n:.1f}".replace(".", ",") + "%"


def _path_barra(x0, x1, y0, y1, raio_x, raio_y, vertical: bool) -> Path:
    """Retângulo com as DUAS pontas do lado do valor arredondadas e a base reta.
    Ponta arredondada dos dois lados soltaria a barra do eixo."""
    if vertical:
        r_lado, r_ponta = raio_x, raio_y
        r_lado = min(r_lado, abs(x1 - x0) / 2)
        r_ponta = min(r_ponta, abs(y1 - y0))
        pts = [
            (Path.MOVETO, (x0, y0)),
            (Path.LINETO, (x0, y1 - r_ponta)),
            (Path.CURVE3, (x0, y1)), (Path.CURVE3, (x0 + r_lado, y1)),
            (Path.LINETO, (x1 - r_lado, y1)),
            (Path.CURVE3, (x1, y1)), (Path.CURVE3, (x1, y1 - r_ponta)),
            (Path.LINETO, (x1, y0)),
            (Path.CLOSEPOLY, (x0, y0)),
        ]
    else:
        r_lado, r_ponta = raio_y, raio_x
        r_lado = min(r_lado, abs(y1 - y0) / 2)
        r_ponta = min(r_ponta, abs(x1 - x0))
        pts = [
            (Path.MOVETO, (x0, y0)),
            (Path.LINETO, (x1 - r_ponta, y0)),
            (Path.CURVE3, (x1, y0)), (Path.CURVE3, (x1, y0 + r_lado)),
            (Path.LINETO, (x1, y1 - r_lado)),
            (Path.CURVE3, (x1, y1)), (Path.CURVE3, (x1 - r_ponta, y1)),
            (Path.LINETO, (x0, y1)),
            (Path.CLOSEPOLY, (x0, y0)),
        ]
    codigos, vertices = zip(*pts)
    return Path(vertices, codigos)


def _rotulos_x_colidem(fig, ax, respiro_px: float = 6.0) -> bool:
    """Algum nome no eixo X encosta no vizinho?

    Contar candidato não resolve: o que colide é o comprimento do nome. Mede a
    caixa de cada rótulo já renderizado e compara com a do vizinho.
    """
    fig.canvas.draw()
    caixas = [t.get_window_extent() for t in ax.get_xticklabels() if t.get_text()]
    return any(a.x1 + respiro_px > b.x0 for a, b in zip(caixas, caixas[1:]))


def _px_em_dados(ax, px: float) -> tuple[float, float]:
    """Converte px de tela em unidades de dado nos dois eixos, pra ponta
    arredondada sair redonda de verdade e não oval."""
    origem = ax.transData.inverted().transform((0, 0))
    deslocado = ax.transData.inverted().transform((px, px))
    return abs(deslocado[0] - origem[0]), abs(deslocado[1] - origem[1])


def _colocar_logo(fig, caminho: str) -> None:
    """Canto superior direito, na altura do título. Embaixo ela disputava espaço
    com a ficha técnica, que é a linha mais larga do gráfico."""
    if not caminho or not os.path.exists(caminho):
        return
    try:
        imagem = plt.imread(caminho)
    except Exception:
        return
    altura, largura = imagem.shape[0], imagem.shape[1]
    larg_fig = 0.10                        # fração da largura da figura
    alt_fig = larg_fig * (altura / largura) * (LARGURA_PX / ALTURA_PX)
    eixo = fig.add_axes([0.955 - larg_fig, 0.945 - alt_fig, larg_fig, alt_fig],
                        zorder=5)
    eixo.imshow(imagem)
    eixo.axis("off")


def gerar_grafico_pesquisa(
    titulo: str,
    itens: list[dict],
    rodape: str = "",
    *,
    orientacao: str = "vertical",
    incluir_logo: bool = True,
    caminho_logo: str = "",
    escala_cheia: bool = True,
    escala: int = 2,
    formato: str = "png",
) -> bytes:
    """Devolve o arquivo em bytes, pronto pro st.image e pro st.download_button.

    escala multiplica 850x600 (2 = 1700x1200). Não muda o desenho, só a
    resolução: o layout é definido em polegadas e o dpi é que varia.

    formato "svg" sai em vetor, para quem for editar depois no Illustrator.
    O texto vira contorno, então o arquivo abre igual em máquina sem Montserrat.

    itens: [{candidato, partido, percentual, tipo}] — o formato que
    normalizar_payload_polling() já entrega em cada cenário.

    escala_cheia=True mantém o eixo em 0–100% em toda pesquisa, que é o que
    deixa dois gráficos comparáveis entre si. False aperta o topo até um pouco
    acima do maior valor, para pesquisa muito fragmentada não sair com metade da
    área vazia. Nos dois casos a base fica no zero: barra com base cortada mente.
    """
    familia = _registrar_fonte()
    orientacao = orientacao if orientacao in ORIENTACOES else "vertical"
    formato = formato if formato in FORMATOS else "png"
    escala = escala if escala in ESCALAS_EXPORT else 2
    # Texto do SVG vira contorno: o arquivo abre igual em máquina sem Montserrat.
    matplotlib.rcParams["svg.fonttype"] = "path"

    validos = [i for i in itens or [] if i.get("percentual") is not None]
    if not validos:
        raise ValueError("Nenhum item com percentual para desenhar.")

    # Candidatos primeiro, do maior pro menor; brancos/nulos no fim, também
    # ordenados. É a mesma ordem de leitura do texto do alerta.
    candidatos = [i for i in validos if i.get("tipo") != "nao_valido"]
    invalidos = [i for i in validos if i.get("tipo") == "nao_valido"]
    candidatos.sort(key=lambda i: float(i["percentual"]), reverse=True)
    invalidos.sort(key=lambda i: float(i["percentual"]), reverse=True)
    ordenados = candidatos + invalidos

    rotulos = [_rotulo_candidato(i) for i in ordenados]
    valores = [float(i["percentual"]) for i in ordenados]
    cores = [VINHO_CLARO if i.get("tipo") == "nao_valido" else VINHO for i in ordenados]

    if escala_cheia:
        topo, marcas = 100, [0, 25, 50, 75, 100]
    else:
        import math
        topo = min(100, max(40, int(math.ceil((max(valores) + 12) / 10.0) * 10)))
        passo = 10 if topo <= 60 else 25
        marcas = list(range(0, topo + 1, passo))

    fig = plt.figure(figsize=(LARGURA_PX / 100, ALTURA_PX / 100), dpi=100)
    fig.patch.set_facecolor(GELO)
    vertical = orientacao == "vertical"

    # Geometria dos dois modos do eixo X. Girado, o rótulo desce e vai PRA
    # ESQUERDA do próprio tique, então a margem esquerda abre junto, senão o
    # primeiro nome sai da figura.
    # A altura sobe até 0.83 porque não há mais legenda ocupando a faixa abaixo
    # do título.
    RETO = (0.07, 0.17, 0.66)
    GIRADO = (0.115, 0.32, 0.51)
    esquerda, base, altura = (0.26, 0.17, 0.66) if not vertical else RETO
    ax = fig.add_axes([esquerda, base, 0.955 - esquerda, altura])
    ax.set_facecolor(GELO)

    for lado in ("top", "right", "left" if vertical else "bottom"):
        ax.spines[lado].set_visible(False)
    eixo_base = "bottom" if vertical else "left"
    ax.spines[eixo_base].set_color(SUBTEXTO)
    ax.spines[eixo_base].set_linewidth(0.8)

    posicoes = list(range(len(ordenados)))
    largura_barra = 0.62 if vertical else 0.6

    rotulos_marcas = [f"{m}%" for m in marcas]
    if vertical:
        ax.set_xlim(-0.6, len(ordenados) - 0.4)
        ax.set_ylim(0, topo)
        ax.set_yticks(marcas)
        ax.set_yticklabels(rotulos_marcas)
        ax.set_xticks(posicoes)
        ax.set_xticklabels([_quebrar(r) for r in rotulos])
        ax.grid(axis="y", color=SUBTEXTO, alpha=0.28, linewidth=0.8,
                linestyle=(0, (2, 4)), zorder=0)
    else:
        ax.set_ylim(len(ordenados) - 0.4, -0.6)   # maior no topo
        ax.set_xlim(0, topo)
        ax.set_xticks(marcas)
        ax.set_xticklabels(rotulos_marcas)
        ax.set_yticks(posicoes)
        ax.set_yticklabels(rotulos)
        ax.grid(axis="x", color=SUBTEXTO, alpha=0.28, linewidth=0.8,
                linestyle=(0, (2, 4)), zorder=0)

    ax.set_axisbelow(True)
    # Nome longo em muitos candidatos: encolhe a fonte do eixo pra não colidir.
    corpo_rotulo = 9.0 if len(ordenados) > 6 else 9.8
    ax.tick_params(axis="both", length=0, colors=SUBTEXTO,
                   labelsize=corpo_rotulo if vertical else 10)
    for rotulo in ax.get_xticklabels() + ax.get_yticklabels():
        rotulo.set_fontfamily(familia)
    for rotulo in (ax.get_xticklabels() if vertical else ax.get_yticklabels()):
        rotulo.set_color(TINTA)

    # Girar ou não é decidido MEDINDO, não contando candidato. Quem causa
    # colisão é o comprimento do nome: "Coronel Busnello (MISSAO)" encosta no
    # vizinho já com 7 barras, enquanto sete nomes curtos cabem folgados.
    if vertical and _rotulos_x_colidem(fig, ax):
        esquerda, base, altura = GIRADO
        ax.set_position([esquerda, base, 0.955 - esquerda, altura])
        # Girado o nome fica em UMA linha: quebra mais rotação vira serrote.
        ax.set_xticklabels(rotulos, rotation=32, ha="right",
                           rotation_mode="anchor", fontfamily=familia,
                           color=TINTA, fontsize=corpo_rotulo)

    # O raio só existe depois que os eixos têm posição e escala definitivas.
    fig.canvas.draw()
    raio_x, raio_y = _px_em_dados(ax, RAIO_PONTA_PX)

    for pos, valor, cor in zip(posicoes, valores, cores):
        if vertical:
            caminho = _path_barra(pos - largura_barra / 2, pos + largura_barra / 2,
                                  0, valor, raio_x, raio_y, True)
        else:
            caminho = _path_barra(0, valor, pos - largura_barra / 2,
                                  pos + largura_barra / 2, raio_x, raio_y, False)
        ax.add_patch(PathPatch(caminho, facecolor=cor, edgecolor="none", zorder=3))

        texto = _fmt_pct(valor)
        folga = topo * 0.025
        if vertical:
            ax.text(pos, valor + folga, texto, ha="center", va="bottom",
                    fontfamily=familia, fontsize=13, fontweight="bold",
                    color=TINTA, zorder=4)
        else:
            ax.text(valor + folga * 0.6, pos, texto, ha="left", va="center",
                    fontfamily=familia, fontsize=12.5, fontweight="bold",
                    color=TINTA, zorder=4)

    fig.text(0.5, 0.93, titulo, ha="center", va="center", fontfamily=familia,
             fontsize=17, fontweight="bold", color=MARINHO)

    # Sem legenda de propósito. A cor mais clara distingue branco/nulo/indeciso,
    # mas quem diz o que a barra é já é o rótulo do eixo ("Brancos e nulos",
    # "Indecisos"): a legenda só repetia o que estava escrito ali embaixo.

    if rodape:
        _desenhar_rodape(fig, rodape, familia)

    if incluir_logo:
        _colocar_logo(fig, caminho_logo or LOGO_PADRAO)

    buffer = io.BytesIO()
    fig.savefig(buffer, format=formato, dpi=100 * escala, facecolor=GELO)
    plt.close(fig)
    return buffer.getvalue()


# ── título e rodapé a partir do payload ──────────────────────────────────────

CARGO_TITULO = {"governador": "Governador", "senador": "Senador",
                "presidente": "Presidente"}


def _data_br(iso: str) -> str:
    """'2026-03-20' -> '20/03/2026'. Devolve o original se não for ISO."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(iso or "").strip())
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(iso or "").strip()


def _num(valor) -> str:
    """3.5 -> '3,5'; 800.0 -> '800'."""
    if valor is None:
        return ""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return str(valor).strip()
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return f"{n:.1f}".replace(".", ",")


def titulo_padrao(payload: dict, cenario: dict | None = None) -> str:
    """'Intenção de voto para Governador - PE'. Hífen, não travessão."""
    cenario = cenario or {}
    cargo = (cenario.get("cargo") or payload.get("cargo") or "").lower()
    uf = (cenario.get("uf") or payload.get("uf") or "").upper()
    turno = (cenario.get("turno") or payload.get("turno") or "t1").lower()

    partes = ["Intenção de voto"]
    if cargo in CARGO_TITULO:
        partes.append(f"para {CARGO_TITULO[cargo]}")
    if turno == "t2":
        partes.append("no 2º turno")
    titulo = " ".join(partes)
    return f"{titulo} - {uf}" if uf and uf != "BR" else titulo


def rodape_padrao(payload: dict) -> str:
    """Ficha técnica em linha, pulando o que a fonte não trouxe. Nada é
    inventado: campo vazio simplesmente não aparece."""
    p = payload or {}
    partes = []
    if str(p.get("instituto") or "").strip():
        partes.append(f"Pesquisa {str(p['instituto']).strip()}")
    if p.get("data_campo"):
        partes.append(f"Campo até {_data_br(p['data_campo'])}")
    if p.get("amostra"):
        partes.append(f"{_num(p['amostra'])} entrevistas")
    # Zero é campo vazio, não medida: nenhuma pesquisa tem margem de erro de 0
    # p.p. nem 0% de confiança. Publicar "±0 p.p." seria afirmar algo falso
    # sobre a metodologia, então o campo some do rodapé.
    if p.get("margem_erro"):
        partes.append(f"Margem de erro: ±{_num(p['margem_erro'])} p.p.")
    if p.get("confianca"):
        partes.append(f"Nível de confiança: {_num(p['confianca'])}%")
    if str(p.get("registro_tse") or "").strip():
        partes.append(f"Reg. TSE: {str(p['registro_tse']).strip()}")
    return " | ".join(partes)


def slug_arquivo(payload: dict, cenario: dict | None = None,
                 extensao: str = "png") -> str:
    """Nome do arquivo baixado: pesquisa_pe_governador_quaest_2026-03-20.png"""
    cenario = cenario or {}
    pedacos = [
        (cenario.get("uf") or payload.get("uf") or ""),
        (cenario.get("cargo") or payload.get("cargo") or ""),
        (payload.get("instituto") or ""),
        (payload.get("data_campo") or ""),
    ]
    bruto = "_".join(str(x).strip() for x in pedacos if str(x).strip())
    bruto = unicodedata.normalize("NFKD", bruto)
    bruto = "".join(c for c in bruto if not unicodedata.combining(c))
    bruto = re.sub(r"[^A-Za-z0-9_-]+", "-", bruto).strip("-_").lower()
    return f"pesquisa_{bruto or 'grafico'}.{extensao}"
