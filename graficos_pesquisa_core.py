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
LOGO_PADRAO = os.path.join(RAIZ, "Logo eleições_Negativa.png")

# Paleta Eixo (mesma do app, ver Gerador_de_Envios.py).
MARINHO = "#192D4E"      # candidato e título
MARINHO_CLARO = "#485B7B"  # branco/nulo/indeciso: mesmo matiz, passo mais claro
GELO = "#F4F3EF"        # fundo do app
BRANCO = "#FFFFFF"      # fundo do gráfico exportado
TINTA = "#111111"       # rótulo de valor e nome no eixo
SUBTEXTO = "#767672"    # eixo, grade e rodapé

LARGURA_PX = 850
ALTURA_PX = 600
RAIO_PONTA_PX = 4
ORIENTACOES = ("vertical", "horizontal")
FORMATOS = ("png", "svg")

# Geometria da logo, no canto superior direito. Sai daqui, e não de dentro de
# _colocar_logo, porque o título mede a largura livre contra esta borda.
LOGO_LARGURA_FIG = 0.10
LOGO_DIREITA = 0.955
LOGO_TOPO = 0.945
LOGO_ESQUERDA = LOGO_DIREITA - LOGO_LARGURA_FIG

TITULO_Y = 0.93         # uma linha: a altura que sempre valeu
TITULO_TOPO = 0.962     # duas linhas ou mais: o bloco desce a partir daqui
TITULO_PISO = 0.838     # onde o bloco tem que parar, antes da área do gráfico
TITULO_CORPOS = (17, 16, 15, 14, 13, 12, 11, 10, 9, 8)
TITULO_MAX_LINHAS = 4
TITULO_ENTRELINHA = 1.25
TITULO_RESPIRO = 0.015  # folga entre o fim do título e a logo

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


def _margem_esquerda_para_rotulos(fig, ax, minimo: float, teto: float = 0.46,
                                  respiro_px: float = 12.0) -> float:
    """Fração da figura que os nomes do eixo Y precisam à esquerda.

    A margem era fixa em 0.26, que não cobre nome longo com partido junto:
    "Cel. André David (Republicanos)" saía cortado na borda da imagem, virando
    "el. André David (Republicanos)". Aqui a largura é MEDIDA, como já era feito
    para decidir a rotação no modo vertical.
    """
    fig.canvas.draw()
    larguras = [t.get_window_extent().width
                for t in ax.get_yticklabels() if t.get_text()]
    if not larguras:
        return minimo
    largura_fig_px = fig.get_size_inches()[0] * fig.dpi
    necessario = (max(larguras) + respiro_px) / largura_fig_px
    return min(teto, max(minimo, necessario))


def _px_em_dados(ax, px: float) -> tuple[float, float]:
    """Converte px de tela em unidades de dado nos dois eixos, pra ponta
    arredondada sair redonda de verdade e não oval."""
    origem = ax.transData.inverted().transform((0, 0))
    deslocado = ax.transData.inverted().transform((px, px))
    return abs(deslocado[0] - origem[0]), abs(deslocado[1] - origem[1])


def _colocar_logo(fig, caminho: str) -> None:
    """Canto superior direito, na altura do título. Embaixo ela disputava espaço
    com a ficha técnica, que é a linha mais larga do gráfico.

    Recorta a margem transparente/branca antes de dimensionar. A marca Eleições
    2026 vive no canto de um canvas grande e, sem esse recorte, seus 10% viravam
    cerca de 3% visíveis na figura.
    """
    if not caminho or not os.path.exists(caminho):
        return
    try:
        imagem = plt.imread(caminho)
    except Exception:
        return

    # PNG negativo: os elementos brancos somem no fundo branco do gráfico; o
    # selo escuro é a parte visível. Para logos coloridas, a mesma máscara apenas
    # elimina as margens. Se a arte for toda branca, mantém o alpha como fallback.
    if imagem.ndim == 3:
        alpha = imagem[:, :, 3] > 0.02 if imagem.shape[2] >= 4 else True
        rgb = imagem[:, :, :3]
        limite_branco = 0.92 if rgb.max() <= 1.0 else 235
        visivel = alpha & (rgb.min(axis=2) < limite_branco)
        if visivel.any():
            ys, xs = visivel.nonzero()
            margem = max(4, round(max(xs.max() - xs.min(), ys.max() - ys.min()) * 0.04))
            x0, x1 = max(0, xs.min() - margem), min(imagem.shape[1], xs.max() + margem + 1)
            y0, y1 = max(0, ys.min() - margem), min(imagem.shape[0], ys.max() + margem + 1)
            imagem = imagem[y0:y1, x0:x1]

    altura, largura = imagem.shape[0], imagem.shape[1]
    larg_fig = LOGO_LARGURA_FIG            # largura VISÍVEL na figura
    alt_fig = larg_fig * (altura / largura) * (LARGURA_PX / ALTURA_PX)
    eixo = fig.add_axes([LOGO_ESQUERDA, LOGO_TOPO - alt_fig, larg_fig, alt_fig],
                        zorder=5)
    eixo.imshow(imagem)
    eixo.axis("off")


def _largura_texto(fig, texto: str, familia: str, corpo: float) -> float:
    """Largura do texto em fração da figura, medida no corpo em que vai sair.

    Mede pelo renderer em vez de redesenhar a figura: o título testa várias
    quebras e vários corpos, e um draw() inteiro por teste travaria a prévia.
    """
    alvo = fig.text(0, 0, texto, fontfamily=familia, fontsize=corpo,
                    fontweight="bold")
    try:
        largura = alvo.get_window_extent(fig.canvas.get_renderer()).width
    except Exception:
        largura = len(texto) * corpo * 0.62   # sem renderer: estimativa
    finally:
        alvo.remove()
    return largura / fig.bbox.width


def _tokens_titulo(texto: str) -> list[str]:
    """Palavras do título, com o hífen da UF colado no que vem depois: quebrar
    entre "-" e "PE" deixaria a primeira linha terminando em traço solto."""
    tokens: list[str] = []
    for palavra in str(texto or "").split():
        if tokens and tokens[-1] in ("-", "–", "—"):
            tokens[-1] = f"{tokens[-1]} {palavra}"
        else:
            tokens.append(palavra)
    return tokens


def _partir_palavra(fig, palavra: str, familia: str, corpo: float,
                    largura_max: float) -> list[str]:
    """Corta com hífen a palavra que sozinha é mais larga que a linha.

    Não acontece com título de pesquisa escrito à mão, mas acontece com texto
    colado sem espaço. Sem isto ela sairia inteira por cima da logo, que é
    exatamente o que este arquivo passou a evitar.
    """
    pedacos, atual = [], ""
    for letra in palavra:
        if atual and _largura_texto(fig, f"{atual}{letra}-", familia,
                                    corpo) > largura_max:
            pedacos.append(f"{atual}-")
            atual = letra
        else:
            atual += letra
    if atual:
        pedacos.append(atual)
    return pedacos or [palavra]


def _quebrar_corrido(fig, tokens: list[str], familia: str, corpo: float,
                     largura_max: float) -> list[str]:
    """Quebra palavra a palavra, enchendo cada linha até a largura permitida.
    Toda linha que sai daqui cabe na faixa livre, custe quantas linhas custar."""
    linhas, atual = [], ""
    for token in tokens:
        if _largura_texto(fig, token, familia, corpo) > largura_max:
            if atual:
                linhas.append(atual)
                atual = ""
            pedacos = _partir_palavra(fig, token, familia, corpo, largura_max)
            linhas.extend(pedacos[:-1])
            atual = pedacos[-1]
            continue
        teste = f"{atual} {token}".strip()
        if not atual or _largura_texto(fig, teste, familia, corpo) <= largura_max:
            atual = teste
        else:
            linhas.append(atual)
            atual = token
    if atual:
        linhas.append(atual)
    return linhas


def _linhas_titulo(fig, texto: str, familia: str, corpo: float,
                   largura_max: float,
                   max_linhas: int = TITULO_MAX_LINHAS) -> list[str] | None:
    """Quebra o título naquele corpo, ou None se não couber no limite de linhas.

    Uma linha quando cabe. Em duas, a quebra é a mais EQUILIBRADA das possíveis
    (a que deixa a linha mais larga o mais estreita possível), não a primeira
    que encher: corrido, sairia "Intenção de voto para Governador (votos" em
    cima e "válidos) - PE" pendurado embaixo.
    """
    tokens = _tokens_titulo(texto)
    if not tokens:
        return [""]
    inteiro = " ".join(tokens)
    if _largura_texto(fig, inteiro, familia, corpo) <= largura_max:
        return [inteiro]

    if max_linhas >= 2 and len(tokens) >= 2:
        melhor = None
        for corte in range(1, len(tokens)):
            duas = [" ".join(tokens[:corte]), " ".join(tokens[corte:])]
            pior = max(_largura_texto(fig, linha, familia, corpo) for linha in duas)
            if melhor is None or pior < melhor[0]:
                melhor = (pior, duas)
        if melhor[0] <= largura_max:
            return melhor[1]

    linhas = _quebrar_corrido(fig, tokens, familia, corpo, largura_max)
    return linhas if len(linhas) <= max_linhas else None


def _bloco_cabe(fig, linhas: list[str], familia: str, corpo: float) -> bool:
    """O bloco de título tem que parar antes da área do gráfico: mais de uma
    linha em corpo grande passa por cima da primeira barra e do 100% do eixo.

    A altura é medida, não calculada a partir do corpo: acento, parêntese e
    entrelinha somam mais que o tamanho nominal da fonte, e a conta estimada
    deixava três linhas descerem para dentro do gráfico.
    """
    alvo = fig.text(0, 0, "\n".join(linhas), fontfamily=familia, fontsize=corpo,
                    fontweight="bold", linespacing=TITULO_ENTRELINHA)
    try:
        altura = alvo.get_window_extent(fig.canvas.get_renderer()).height
        altura /= fig.bbox.height
    except Exception:
        altura = len(linhas) * TITULO_ENTRELINHA * (corpo / 72) / (ALTURA_PX / 100)
    finally:
        alvo.remove()
    return TITULO_TOPO - altura >= TITULO_PISO


def _desenhar_titulo(fig, texto: str, familia: str) -> None:
    """Título centrado, quebrado antes de encostar na logo.

    O limite é MEDIDO contra a borda da logo, não contado em caracteres: o que
    esconde o título por baixo do selo é a largura do texto, e a mesma contagem
    de caracteres ocupa larguras diferentes. "Intenção de voto para Governador
    (votos válidos) - PE" passava por baixo da logo; agora sai em duas linhas.

    A busca desce por corpo e sobe por linha: primeiro tenta caber grande em
    poucas linhas, depois aceita menor e mais linhas, e a última tentativa
    quebra até dentro da palavra. Título nunca sai cortado nem escondido; o que
    cede é o tamanho da letra.

    A conta vale também na versão sem logo, para as duas peças (com e sem, que
    saem no mesmo .zip) terem a mesma quebra e a mesma altura de título.
    """
    texto = str(texto or "").strip()
    if not texto:
        return
    # Texto centrado em 0.5: a largura útil é o dobro da distância até a logo.
    largura_max = 2 * (LOGO_ESQUERDA - TITULO_RESPIRO - 0.5)

    linhas, corpo = None, TITULO_CORPOS[-1]
    for corpo in TITULO_CORPOS:
        tentativa = _linhas_titulo(fig, texto, familia, corpo, largura_max)
        if tentativa and (len(tentativa) == 1
                          or _bloco_cabe(fig, tentativa, familia, corpo)):
            linhas = tentativa
            break
    if not linhas:
        # Título descomunal: sai no menor corpo, quebrado até onde precisar.
        # Passar do piso é melhor que sumir por baixo da logo ou cortar texto.
        linhas = _quebrar_corrido(fig, _tokens_titulo(texto), familia, corpo,
                                  largura_max)

    if len(linhas) == 1:
        fig.text(0.5, TITULO_Y, linhas[0], ha="center", va="center",
                 fontfamily=familia, fontsize=corpo, fontweight="bold",
                 color=MARINHO)
    else:
        fig.text(0.5, TITULO_TOPO, "\n".join(linhas), ha="center", va="top",
                 fontfamily=familia, fontsize=corpo, fontweight="bold",
                 color=MARINHO, linespacing=TITULO_ENTRELINHA)


def gerar_grafico_pesquisa(
    titulo: str,
    itens: list[dict],
    rodape: str = "",
    *,
    orientacao: str = "horizontal",
    incluir_logo: bool = True,
    caminho_logo: str = "",
    escala_cheia: bool = True,
    escala: int = 2,
    formato: str = "png",
    fundo_transparente: bool = False,
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

    fundo_transparente=False (padrão) sai com fundo branco, que é como a peça
    costuma ser postada e o que evita a barra escura brigando com fundo de cor
    quando alguém joga o PNG em qualquer lugar. True sai sem fundo, para o
    gráfico assentar direto em slide ou story; o desenho não muda, e texto e
    barra continuam nas cores da casa, que pedem fundo claro.
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
    cores = [MARINHO_CLARO if i.get("tipo") == "nao_valido" else MARINHO for i in ordenados]

    if escala_cheia:
        topo, marcas = 100, [0, 25, 50, 75, 100]
    else:
        import math
        topo = min(100, max(40, int(math.ceil((max(valores) + 12) / 10.0) * 10)))
        passo = 10 if topo <= 60 else 25
        marcas = list(range(0, topo + 1, passo))

    fundo = "none" if fundo_transparente else BRANCO
    fig = plt.figure(figsize=(LARGURA_PX / 100, ALTURA_PX / 100), dpi=100)
    fig.patch.set_facecolor(fundo)
    vertical = orientacao == "vertical"

    # Geometria dos dois modos do eixo X. Girado, o rótulo desce e vai PRA
    # ESQUERDA do próprio tique, então a margem esquerda abre junto, senão o
    # primeiro nome sai da figura.
    # A altura sobe até 0.83 porque não há mais legenda ocupando a faixa abaixo
    # do título.
    RETO = (0.07, 0.17, 0.66)
    GIRADO = (0.115, 0.32, 0.51)
    # Piso da margem no modo horizontal. É o valor que sempre valeu; agora ele
    # só cresce, quando o nome mais longo não cabe nele.
    MARGEM_H = 0.26
    esquerda, base, altura = (MARGEM_H, 0.17, 0.66) if not vertical else RETO
    ax = fig.add_axes([esquerda, base, 0.955 - esquerda, altura])
    ax.set_facecolor(fundo)

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

    # Horizontal: abre a margem esquerda até o nome mais longo caber. Se nem no
    # teto couber, encolhe a fonte, porque cortar o nome de um candidato é pior
    # que uma linha um ponto menor.
    if not vertical:
        for tamanho in (10, 9.2, 8.4, 7.6):
            ax.tick_params(axis="y", labelsize=tamanho)
            esquerda = _margem_esquerda_para_rotulos(fig, ax, MARGEM_H)
            ax.set_position([esquerda, base, 0.955 - esquerda, altura])
            if esquerda < 0.46:
                break

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

    _desenhar_titulo(fig, titulo, familia)

    # Sem legenda de propósito. A cor mais clara distingue branco/nulo/indeciso,
    # mas quem diz o que a barra é já é o rótulo do eixo ("Brancos e nulos",
    # "Indecisos"): a legenda só repetia o que estava escrito ali embaixo.

    if rodape:
        _desenhar_rodape(fig, rodape, familia)

    if incluir_logo:
        _colocar_logo(fig, caminho_logo or LOGO_PADRAO)

    buffer = io.BytesIO()
    # transparent=True também zera o fundo dos eixos, não só o da figura.
    fig.savefig(buffer, format=formato, dpi=100 * escala,
                facecolor=fundo, transparent=fundo_transparente)
    plt.close(fig)
    return buffer.getvalue()


# ── título e rodapé a partir do payload ──────────────────────────────────────

CARGO_TITULO = {"governador": "Governador", "senador": "Senador",
                "presidente": "Presidente"}


MESES_PT = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
            "agosto", "setembro", "outubro", "novembro", "dezembro")


def _iso_partes(iso: str) -> tuple[int, int, int] | None:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(iso or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def periodo_campo_br(inicio: str, fim: str) -> str:
    """Período de coleta por extenso: '15 a 17 de julho'.

    Sem ano de propósito: a peça circula no mesmo ano do campo e o ano só ocupa
    espaço no rodapé, que é a linha mais apertada do gráfico. Mês diferente sai
    inteiro nos dois lados ('28 de junho a 2 de julho'); ano diferente (campo
    virando o réveillon) é o único caso em que o ano volta.

    Sem data inicial, devolve só a final ('17 de julho'). Data que não estiver
    em ISO volta como veio — é o que preserva o período digitado na mão.
    """
    p_fim = _iso_partes(fim)
    if not p_fim:
        return str(fim or "").strip()
    ano_f, mes_f, dia_f = p_fim

    p_ini = _iso_partes(inicio)
    # Início ausente, inválido ou depois do fim: só a data final.
    if not p_ini or p_ini > p_fim:
        return f"{dia_f} de {MESES_PT[mes_f - 1]}"
    ano_i, mes_i, dia_i = p_ini

    if (ano_i, mes_i, dia_i) == p_fim:
        return f"{dia_f} de {MESES_PT[mes_f - 1]}"
    if ano_i != ano_f:
        return (f"{dia_i} de {MESES_PT[mes_i - 1]} de {ano_i} a "
                f"{dia_f} de {MESES_PT[mes_f - 1]} de {ano_f}")
    if mes_i != mes_f:
        return f"{dia_i} de {MESES_PT[mes_i - 1]} a {dia_f} de {MESES_PT[mes_f - 1]}"
    return f"{dia_i} a {dia_f} de {MESES_PT[mes_f - 1]}"


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


def titulo_padrao(payload: dict, cenario: dict | None = None,
                  votos_validos: bool = False) -> str:
    """'Intenção de voto para Governador (votos válidos) - PE'. Hífen, não travessão.

    votos_validos diz a base no título. O alerta passou a sair na base de votos
    válidos, e sem essa marca o mesmo candidato aparece com dois números
    diferentes em duas peças sem nada explicando a diferença. Quem liga é a
    página: nada no JSON da extração diz em que base o instituto publicou.
    """
    cenario = cenario or {}
    cargo = (cenario.get("cargo") or payload.get("cargo") or "").lower()
    uf = (cenario.get("uf") or payload.get("uf") or "").upper()
    turno = (cenario.get("turno") or payload.get("turno") or "t1").lower()

    partes = ["Intenção de voto"]
    if cargo in CARGO_TITULO:
        partes.append(f"para {CARGO_TITULO[cargo]}")
    if turno == "t2":
        partes.append("no 2º turno")
    if votos_validos:
        partes.append("(votos válidos)")
    titulo = " ".join(partes)
    return f"{titulo} - {uf}" if uf and uf != "BR" else titulo


# Ficha técnica publicável: são estes seis campos que o rodapé mostra, e a peça
# circula fora da casa. Faltar um é publicar pesquisa sem metodologia, então a
# página trava em cima desta lista.
CAMPOS_FICHA = (
    ("instituto", "instituto"),
    ("registro_tse", "registro TSE"),
    ("data_campo", "data de campo"),
    ("amostra", "amostra"),
    ("margem_erro", "margem de erro"),
    ("confianca", "nível de confiança"),
)


def ficha_incompleta(payload: dict) -> list[str]:
    """Rótulos dos campos que o rodapé não teria como publicar. Lista vazia
    quando a ficha está completa."""
    p = payload or {}
    return [rotulo for chave, rotulo in CAMPOS_FICHA if not p.get(chave)]


def rodape_padrao(payload: dict) -> str:
    """Ficha técnica em linha, pulando o que a fonte não trouxe. Nada é
    inventado: campo vazio simplesmente não aparece."""
    p = payload or {}
    partes = []
    if str(p.get("instituto") or "").strip():
        partes.append(f"Pesquisa {str(p['instituto']).strip()}")
    # Só o período, sem rótulo: numa linha lida em sequência com o instituto e a
    # amostra, "21 a 25 de julho" já se lê como data de campo, e "Campo:" só
    # gasta espaço na linha mais apertada do gráfico.
    periodo = periodo_campo_br(p.get("data_campo_inicio"), p.get("data_campo"))
    if periodo:
        partes.append(periodo)
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
                 extensao: str = "png", sufixo: str = "") -> str:
    """Nome do arquivo baixado: pesquisa_pe_governador_quaest_2026-03-20.png

    sufixo distingue as versões do mesmo gráfico dentro do zip
    ('com-logo', 'sem-logo').
    """
    cenario = cenario or {}
    pedacos = [
        (cenario.get("uf") or payload.get("uf") or ""),
        (cenario.get("cargo") or payload.get("cargo") or ""),
        (payload.get("instituto") or ""),
        (payload.get("data_campo") or ""),
        sufixo,
    ]
    bruto = "_".join(str(x).strip() for x in pedacos if str(x).strip())
    bruto = unicodedata.normalize("NFKD", bruto)
    bruto = "".join(c for c in bruto if not unicodedata.combining(c))
    bruto = re.sub(r"[^A-Za-z0-9_-]+", "-", bruto).strip("-_").lower()
    return f"pesquisa_{bruto or 'grafico'}.{extensao}"
