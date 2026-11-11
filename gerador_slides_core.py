"""
Gerador de Slides (beta): conteúdo estruturado entra e sai .pptx no modelo
institucional da Eixo, para abrir no PowerPoint ou importar no Canva e no
Google Slides.

O molde (modelos/slides_eixo.pptx) é a exportação do Institucional do Canva
reduzida a seis layouts, sem fotos da equipe nem logos de clientes:

    capa          duas linhas de título sobre o padrão da Eixo
    texto         título e um bloco de texto
    lista         chamada em três linhas e de 2 a 6 itens numerados
    secao         divisória com foto
    cartoes       título e dois cartões numerados
    encerramento  "Dúvidas? Entre em contato." com os contatos da Eixo

Cada slide do resultado é cópia de um slide do molde com o texto trocado. A
formatação vem do próprio molde (fonte, cor, espaçamento); quando o texto não
cabe, a fonte diminui até caber, medida com a Montserrat de fontes/.

No texto, **assim** vira destaque (negrito na cor da Eixo). Linha em branco
separa parágrafos.

Sem Streamlit, como os outros cores. A estruturação pelo Gemini mora em
estruturar() no fim do arquivo.
"""

import copy
import io
import math
import re
from functools import lru_cache
from pathlib import Path

from lxml import etree
from PIL import ImageFont
from pptx import Presentation
from pptx.util import Emu

RAIZ = Path(__file__).resolve().parent
MOLDE = RAIZ / "modelos" / "slides_eixo.pptx"
FONTES = RAIZ / "fontes"

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"a": A}
POL = 914400  # EMU por polegada
VINHO = "95304D"  # o vinho do molde do Canva
FOLGA = 0.9

# índice do slide no molde
LAYOUTS = {"capa": 0, "texto": 1, "lista": 2, "secao": 3, "cartoes": 4, "encerramento": 5}

NOMES = {
    "capa": "Capa",
    "texto": "Título e texto",
    "lista": "Lista numerada",
    "secao": "Divisória de seção",
    "cartoes": "Dois cartões",
    "encerramento": "Encerramento",
}

# campos de cada layout: (chave, rótulo, limite de caracteres sugerido)
CAMPOS = {
    "capa": [("linha_1", "Linha de cima", 24), ("linha_2", "Linha de baixo (destaque)", 30)],
    "texto": [("titulo", "Título", 50), ("corpo", "Texto", 650)],
    "lista": [("linha_1", "Chamada (linha de cima)", 30), ("destaque", "Palavra em destaque", 16),
              ("linha_3", "Complemento (linha de baixo)", 50), ("itens", "Itens (2 a 6)", 90)],
    "secao": [("linha_1", "Linha de cima", 18), ("destaque", "Palavra em destaque", 14),
              ("subtitulo", "Subtítulo", 90)],
    "cartoes": [("titulo", "Título", 45), ("cartao_1_titulo", "Cartão 1: título", 40),
                ("cartao_1_texto", "Cartão 1: texto", 280), ("cartao_2_titulo", "Cartão 2: título", 40),
                ("cartao_2_texto", "Cartão 2: texto", 280)],
    "encerramento": [("titulo", "Título", 40)],
}

PADRAO_ENCERRAMENTO = "Dúvidas?\nEntre em contato."


# ── medida do texto ──────────────────────────────────────────────────────────

@lru_cache(maxsize=None)
def _fonte(peso: str):
    arquivo = {"heavy": "Montserrat-ExtraBold.ttf", "bold": "Montserrat-Bold.ttf"}.get(peso, "Montserrat-Regular.ttf")
    return ImageFont.truetype(str(FONTES / arquivo), 100)


def _peso(rpr) -> str:
    face = (rpr.find("a:latin", NS).get("typeface") if rpr.find("a:latin", NS) is not None else "") or ""
    if "Heavy" in face or "Black" in face or "ExtraBold" in face:
        return "heavy"
    if "Bold" in face or rpr.get("b") in ("1", "true"):
        return "bold"
    return "regular"


def _largura(texto: str, peso: str, pt: float, spc_pt: float) -> float:
    """Largura em pontos."""
    return _fonte(peso).getlength(texto) * pt / 100 + spc_pt * len(texto)


def _linhas(paragrafos, largura_pt, escala, estilos) -> int | None:
    """Quantas linhas o texto ocupa na largura. paragrafos: [[(texto, destaque)]].
    None quando uma palavra sozinha não cabe na linha."""
    total = 0
    for par in paragrafos:
        palavras = []
        for texto, dest in par:
            for w in re.findall(r"\S+", texto):
                palavras.append((w, dest))
        if not palavras:
            total += 1
            continue
        n, atual = 1, 0.0
        for w, dest in palavras:
            peso, pt, spc = estilos[dest]
            pt, spc = pt * escala, spc * escala
            lw = _largura(w, peso, pt, spc)
            if lw > largura_pt:
                return None
            sp = _largura(" ", peso, pt, spc)
            if atual == 0:
                atual = lw
            elif atual + sp + lw <= largura_pt:
                atual += sp + lw
            else:
                n += 1
                atual = lw
        total += n
    return total


# ── texto no XML ─────────────────────────────────────────────────────────────

def _q(tag):
    p, t = tag.split(":")
    return "{%s}%s" % ({"a": A}[p], t)


def _partes(texto: str):
    """'a **b** c' -> [('a ', False), ('b', True), (' c', False)]."""
    out = []
    for i, pedaco in enumerate(re.split(r"\*\*", texto)):
        if pedaco:
            out.append((pedaco, i % 2 == 1))
    return out


def _paragrafos(texto: str):
    """Linha em branco vira parágrafo vazio entre os dois (como no molde);
    linha que começa com '- ' vira item com marcador."""
    texto = re.sub(r"\n{3,}", "\n\n", str(texto or "").strip())
    pars = []
    for linha in texto.split("\n"):
        linha = linha.strip()
        if re.match(r"^[-•*]\s+", linha):
            linha = "• " + re.sub(r"^[-•*]\s+", "", linha)
        pars.append(_partes(linha))
    return pars


def _estilos(sh):
    """rPr normal e rPr de destaque do primeiro parágrafo da caixa."""
    runs = sh._element.txBody.findall(".//a:r", NS)
    base = runs[0].find("a:rPr", NS)
    dest = None
    for r in runs:
        rp = r.find("a:rPr", NS)
        cor = rp.find(".//a:srgbClr", NS)
        if _peso(rp) != _peso(base) or (cor is not None and cor.get("val") == VINHO and
                                        base.find(".//a:srgbClr", NS).get("val") != VINHO):
            dest = rp
            break
    if dest is None:
        dest = copy.deepcopy(base)
        dest.set("b", "true")
        for tag in ("a:latin", "a:ea", "a:cs", "a:sym"):
            el = dest.find(tag, NS)
            if el is not None and _peso(base) == "regular":
                el.set("typeface", "Montserrat Bold")
        cor = dest.find(".//a:srgbClr", NS)
        if cor is not None:
            cor.set("val", VINHO)
    return base, dest


def _metricas(sh):
    """(estilos para medir, entrelinha em pt) da caixa como está no molde."""
    base, dest = _estilos(sh)
    def m(rp):
        return (_peso(rp), int(rp.get("sz", "1800")) / 100, int(rp.get("spc", "0")) / 100)
    sp = sh._element.txBody.find(".//a:pPr/a:lnSpc/a:spcPts", NS)
    ln = int(sp.get("val")) / 100 if sp is not None else m(base)[1] * 1.2
    return {False: m(base), True: m(dest)}, ln


def escrever(sh, texto: str, *, largura_pol: float | None = None, altura_max_pol: float | None = None,
             uma_linha: bool = False, escala_min: float = 0.35, escala: float | None = None) -> float:
    """Troca o texto da caixa mantendo a formatação do molde e reduz a fonte até
    caber. Devolve a escala usada (1 = tamanho do molde). Com `escala`, usa essa
    sem medir (para igualar caixas irmãs)."""
    if largura_pol:
        sh.width = Emu(int(largura_pol * POL))
    estilos, ln = _metricas(sh)
    pars = _paragrafos(texto)
    # folga: PowerPoint, LibreOffice, Canva e Slides desenham a Montserrat um
    # pouco mais larga que a medida da PIL, e o espaçamento negativo nem sempre entra
    largura_pt = sh.width / POL * 72 * FOLGA

    if escala is None:
        escala = 1.0
        while escala > escala_min:
            n = _linhas(pars, largura_pt, escala, estilos)
            ok = n is not None
            if ok and uma_linha:
                ok = n <= len(pars)
            if ok and altura_max_pol:
                ok = n * ln * escala / 72 <= altura_max_pol
            if ok:
                break
            escala = round(escala - 0.03, 3)
    n = _linhas(pars, largura_pt, escala, estilos) or len(pars)

    body = sh._element.txBody
    p0 = body.find("a:p", NS)
    ppr = p0.find("a:pPr", NS)
    base, dest = _estilos(sh)
    for p in body.findall("a:p", NS):
        body.remove(p)
    for par in pars:
        p = etree.SubElement(body, _q("a:p"))
        if ppr is not None:
            p.append(copy.deepcopy(ppr))
        # parágrafo vazio leva um run vazio: a caixa continua com a formatação
        # do molde para a próxima escrita
        for txt, d in par or [("", False)]:
            r = etree.SubElement(p, _q("a:r"))
            r.append(copy.deepcopy(dest if d else base))
            t = etree.SubElement(r, _q("a:t"))
            t.text = txt
    if escala != 1.0:
        _escalar(sh, escala)
    sh.height = Emu(int(n * ln * escala / 72 * POL))
    return escala


def _escalar(sh, f: float):
    body = sh._element.txBody
    for rp in body.iter(_q("a:rPr"), _q("a:endParaRPr")):
        if rp.get("sz"):
            rp.set("sz", str(max(100, int(int(rp.get("sz")) * f))))
        if rp.get("spc"):
            rp.set("spc", str(int(int(rp.get("spc")) * f)))
    for sp in body.iter(_q("a:spcPts")):
        sp.set("val", str(int(int(sp.get("val")) * f)))


# ── slides ───────────────────────────────────────────────────────────────────

def _duplicar(prs, origem):
    """Copia um slide do molde para o fim da apresentação, com as imagens."""
    novo = prs.slides.add_slide(origem.slide_layout)
    mapa = {}
    for rid, rel in origem.part.rels.items():
        if rel.reltype.endswith("/slideLayout") or rel.reltype.endswith("/notesSlide"):
            continue
        if rel.is_external:
            mapa[rid] = novo.part.relate_to(rel.target_ref, rel.reltype, is_external=True)
        else:
            mapa[rid] = novo.part.relate_to(rel.target_part, rel.reltype)
    csld = copy.deepcopy(origem._element.cSld)
    for el in csld.iter():
        for at, val in list(el.attrib.items()):
            if at.startswith("{%s}" % R) and val in mapa:
                el.set(at, mapa[val])
    # troca o conteúdo dentro do spTree do slide novo (o python-pptx guarda
    # referência a ele em slide.shapes) e copia o fundo
    arvore = novo._element.cSld.spTree
    for el in list(arvore)[2:]:
        arvore.remove(el)
    for el in list(csld.spTree)[2:]:
        arvore.append(el)
    if csld.bg is not None:
        if novo._element.cSld.bg is not None:
            novo._element.cSld.remove(novo._element.cSld.bg)
        novo._element.cSld.insert(0, csld.bg)
    return novo


def _formas(slide):
    return {sh.name: sh for sh in slide.shapes}


def _tirar(*formas):
    for sh in formas:
        sh._element.getparent().remove(sh._element)


def _pol(v):
    return Emu(int(v * POL))


def _capa(s, c):
    f = _formas(s)
    l1, l2 = (c.get("linha_1") or "").strip(), (c.get("linha_2") or "").strip()
    base = f["TextBox 5"].top + f["TextBox 5"].height  # rodapé do título no molde
    escrever(f["TextBox 5"], l2 or " ", largura_pol=15.0, uma_linha=True, escala_min=0.45)
    if f["TextBox 5"].height > _pol(2.6) or _linhas_usadas(f["TextBox 5"]) > 1:
        escrever(f["TextBox 5"], l2, largura_pol=15.0, altura_max_pol=4.2)
    f["TextBox 5"].top = base - f["TextBox 5"].height
    if l1:
        escrever(f["TextBox 6"], l1, largura_pol=15.0, uma_linha=True, escala_min=0.45)
        f["TextBox 6"].top = f["TextBox 5"].top - int(f["TextBox 6"].height * 0.76)
    else:
        _tirar(f["TextBox 6"])


def _linhas_usadas(sh) -> int:
    estilos, ln = _metricas(sh)
    return max(1, round(sh.height / POL * 72 / ln))


def _texto(s, c):
    f = _formas(s)
    tit, corpo = f["TextBox 6"], f["TextBox 5"]
    escrever(tit, c.get("titulo") or "", largura_pol=16.5, altura_max_pol=2.6)
    corpo.top = tit.top + tit.height + _pol(0.7)
    disponivel = 10.2 - corpo.top / POL
    escrever(corpo, c.get("corpo") or "", largura_pol=16.0, altura_max_pol=disponivel, escala_min=0.5)


ESQ = [("Freeform 4", "TextBox 5", "TextBox 6"), ("Freeform 8", "TextBox 9", "TextBox 23"),
       ("Freeform 11", "TextBox 12", "TextBox 10")]
DIR = [("Freeform 14", "TextBox 15", "TextBox 18"), ("Freeform 16", "TextBox 17", "TextBox 13"),
       ("Freeform 20", "TextBox 21", "TextBox 22")]


def _lista(s, c):
    f = _formas(s)
    l1, dest, l3 = ((c.get(k) or "").strip() for k in ("linha_1", "destaque", "linha_3"))
    itens = [str(i).strip() for i in (c.get("itens") or []) if str(i).strip()][:6]

    if l1:
        escrever(f["TextBox 7"], l1, largura_pol=17.0, uma_linha=True)
    else:
        _tirar(f["TextBox 7"])
    escrever(f["TextBox 3"], dest or " ", largura_pol=16.5, uma_linha=True)
    if l1:
        # no molde a chamada encosta no destaque; com maiúscula ou acento no
        # destaque ("PRAZOS", "DISTRIBUIÇÃO") as letras se batem
        f["TextBox 3"].top += _pol(0.35)
    if l3:
        escrever(f["TextBox 24"], l3, largura_pol=16.0, uma_linha=True)
        f["TextBox 24"].top = f["TextBox 3"].top + int(f["TextBox 3"].height * 0.70)
    else:
        _tirar(f["TextBox 24"])

    n = len(itens)
    if n <= 3:
        posicoes = ESQ[:n]
        sobra = ESQ[n:] + DIR
        larguras = [15.0] * n
    else:
        k = math.ceil(n / 2)
        posicoes = ESQ[:k] + DIR[:n - k]
        sobra = ESQ[k:] + DIR[n - k:]
        larguras = [6.3] * k + [7.6] * (n - k)
    for trio in sobra:
        _tirar(*(f[nome] for nome in trio))
    # mesma escala para todos os itens, pela do item que mais precisa reduzir
    escalas = [escrever(f[t], txt, largura_pol=w, altura_max_pol=1.6)
               for (_, _, t), txt, w in zip(posicoes, itens, larguras)]
    e = min(escalas) if escalas else 1.0
    for i, ((circ, num, t), txt, w) in enumerate(zip(posicoes, itens, larguras), 1):
        escrever(f[t], txt, largura_pol=w, escala=e)
        escrever(f[num], str(i))
        # caixa do texto centralizada no círculo e com âncora no meio: se o
        # programa quebrar a linha diferente da medida, o texto continua alinhado
        meio = f[circ].top + f[circ].height // 2
        f[t].height = max(f[t].height, f[circ].height)
        f[t].top = meio - f[t].height // 2
        _ancora_meio(f[t])
        f[num].top = meio - f[num].height // 2


def _ancora_meio(sh):
    bp = sh._element.txBody.find("a:bodyPr", NS)
    bp.set("anchor", "ctr")
    for el in list(bp):
        if el.tag == _q("a:spAutoFit"):
            bp.remove(el)


def _secao(s, c):
    f = _formas(s)
    l1, dest, sub = (c.get("linha_1") or "").strip(), (c.get("destaque") or "").strip(), (c.get("subtitulo") or "").strip()
    t4, t5, t6 = f["TextBox 4"], f["TextBox 5"], f["TextBox 6"]
    topo = t4.top
    if l1:
        escrever(t4, l1, uma_linha=True)
        t5.top = t4.top + int(t4.height * 0.70)
    else:
        _tirar(t4)
        t5.top = topo
    escrever(t5, dest or " ", uma_linha=True)
    if sub:
        t6.top = t5.top + int(t5.height * 1.24)
        escrever(t6, sub, altura_max_pol=10.4 - t6.top / POL)
    else:
        _tirar(t6)


def _cartoes(s, c):
    f = _formas(s)
    escrever(f["TextBox 18"], c.get("titulo") or "", largura_pol=6.6, altura_max_pol=8.0)
    pares = [("TextBox 21", "TextBox 22", "Group 6"), ("TextBox 19", "TextBox 20", "Group 12")]
    esc_t, esc_x = [], []
    for i, (tt, tx, _) in enumerate(pares, 1):
        esc_t.append(escrever(f[tt], c.get(f"cartao_{i}_titulo") or "", altura_max_pol=1.2))
    for i, (tt, tx, _) in enumerate(pares, 1):
        topo = f[tt].top + f[tt].height + _pol(0.25)
        esc_x.append(escrever(f[tx], c.get(f"cartao_{i}_texto") or "", altura_max_pol=10.2 - topo / POL))
    for i, (tt, tx, grupo) in enumerate(pares, 1):
        escrever(f[tt], c.get(f"cartao_{i}_titulo") or "", escala=min(esc_t))
        f[tx].top = f[tt].top + f[tt].height + _pol(0.25)
        escrever(f[tx], c.get(f"cartao_{i}_texto") or "", escala=min(esc_x))
        _numero_no_circulo(f[grupo], f"0{i}")


def _numero_no_circulo(grupo, texto):
    caixa = grupo._element.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}txBody")
    p = caixa.find("a:p", NS)
    r = etree.SubElement(p, _q("a:r"))
    rp = etree.SubElement(r, _q("a:rPr"), lang="pt-BR", sz="6000", b="1")
    cor = etree.SubElement(etree.SubElement(rp, _q("a:solidFill")), _q("a:srgbClr"), val=VINHO)
    for tag in ("a:latin", "a:ea", "a:cs", "a:sym"):
        etree.SubElement(rp, _q(tag), typeface="Montserrat Bold")
    etree.SubElement(r, _q("a:t")).text = texto
    sp = p.find(".//a:spcPts", NS)
    if sp is not None:
        sp.set("val", "7200")


def _encerramento(s, c):
    f = _formas(s)
    escrever(f["TextBox 8"], (c.get("titulo") or "").strip() or PADRAO_ENCERRAMENTO,
             altura_max_pol=3.4)


PREENCHER = {"capa": _capa, "texto": _texto, "lista": _lista, "secao": _secao,
             "cartoes": _cartoes, "encerramento": _encerramento}


def gerar_pptx(slides: list[dict]) -> bytes:
    """slides: [{"layout": "capa", "campos": {...}}] -> bytes do .pptx."""
    prs = Presentation(str(MOLDE))
    moldes = list(prs.slides)
    feitos = 0
    for spec in slides:
        layout = spec.get("layout")
        if layout not in LAYOUTS:
            continue
        novo = _duplicar(prs, moldes[LAYOUTS[layout]])
        PREENCHER[layout](novo, spec.get("campos") or {})
        feitos += 1
    if not feitos:
        raise ValueError("Nenhum slide para gerar.")
    ids = prs.slides._sldIdLst
    for sid in list(ids)[:len(moldes)]:
        prs.part.drop_rel(sid.rId)
        ids.remove(sid)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ── Gemini ───────────────────────────────────────────────────────────────────

def _descricao_layouts() -> str:
    linhas = []
    for k, campos in CAMPOS.items():
        cs = ", ".join(f'"{ck}" (até {lim} caracteres)' if ck != "itens" else
                       f'"itens" (lista de 2 a 6 frases, cada uma até {lim} caracteres)'
                       for ck, _, lim in campos)
        linhas.append(f"- {k} ({NOMES[k]}): {cs}")
    return "\n".join(linhas)


PROMPT = """Você organiza um conteúdo em slides no modelo institucional da Eixo, uma consultoria política.

Layouts disponíveis e seus campos:
{layouts}

Como usar cada layout:
- capa: sempre o primeiro slide. linha_1 é curta e em tom de chamada (ex.: "material"), linha_2 é o tema em destaque (ex.: "institucional").
- secao: abre um bloco do conteúdo. linha_1 curta em minúsculas (ex.: "nossos"), destaque é UMA palavra em maiúsculas (ex.: "CLIENTES"), subtitulo explica o bloco.
- texto: um título e um parágrafo. Linha em branco separa parágrafos. Pode marcar até três trechos-chave com **negrito**.
- lista: etapas, frentes ou pontos paralelos. linha_1 em maiúsculas (ex.: "NOSSO FOCO É"), destaque é UMA palavra (ex.: "potencializar"), linha_3 completa a frase (ex.: "a atuação dos nossos clientes"). Os itens são frases curtas e completas.
- cartoes: duas coisas lado a lado (dois produtos, duas frentes, antes e depois). Cada cartão tem título e texto.
- encerramento: último slide, só se o pedido ou o conteúdo indicar fechamento. O texto é fixo ("Dúvidas? Entre em contato." e os contatos da Eixo): devolva "campos": {}.

Regras:
- Use só o que está no conteúdo. Não invente número, nome, data, cliente nem resultado.
- Pode resumir e reescrever para caber no limite, sem mudar o sentido.
- Respeite os limites de caracteres. Texto acima do limite fica com fonte pequena.
- Português do Brasil, sem travessão longo e sem emoji.
- Entre 3 e 15 slides, conforme o tamanho do conteúdo.

Responda só com o JSON:
{{"slides": [{{"layout": "capa", "campos": {{"linha_1": "", "linha_2": ""}}}}]}}
"""


def normalizar(payload) -> list[dict]:
    """Resposta do modelo -> lista de slides só com layouts e campos conhecidos."""
    slides = []
    for s in (payload or {}).get("slides") or []:
        if not isinstance(s, dict) or s.get("layout") not in LAYOUTS:
            continue
        brutos = s.get("campos") if isinstance(s.get("campos"), dict) else s
        campos = {}
        for chave, _, _ in CAMPOS[s["layout"]]:
            v = brutos.get(chave)
            if chave == "itens":
                v = [str(i).strip() for i in (v or []) if str(i).strip()][:6] if isinstance(v, list) else \
                    [x.strip() for x in str(v or "").split("\n") if x.strip()][:6]
            else:
                v = str(v or "").replace("—", ",").strip()
            campos[chave] = v
        if s["layout"] == "encerramento":
            campos = {"titulo": ""}  # texto fixo do molde; só a pessoa muda, na página
        slides.append({"layout": s["layout"], "campos": campos})
    return slides


def estruturar(conteudo: str, pedido: str = "") -> list[dict]:
    """Chama o Gemini e devolve os slides normalizados."""
    from polling_extracao_core import GEMINI_MODEL, extrair_json_de_texto_bruto, gerar_conteudo_gemini

    if not str(conteudo or "").strip():
        raise ValueError("Cole o conteúdo ou suba um arquivo.")
    partes = [PROMPT.format(layouts=_descricao_layouts())]
    if pedido.strip():
        partes.append(f"Pedido de quem está montando: {pedido.strip()}")
    partes.append(f"Conteúdo:\n{conteudo.strip()}")
    resp = gerar_conteudo_gemini(GEMINI_MODEL, partes)
    slides = normalizar(extrair_json_de_texto_bruto(getattr(resp, "text", "") or ""))
    if not slides:
        raise RuntimeError("O Gemini não devolveu slides. Tente de novo ou encurte o conteúdo.")
    return slides
