"""
Gerador de Slides (beta): conteúdo estruturado entra e sai .pptx no modelo de
apresentação da Eixo, para abrir no PowerPoint ou importar no Canva e no
Google Slides.

O molde (modelos/slides_eixo.pptx) é a exportação do "Modelo PPT Institucional"
do Canva da Comunicação (DAGiL4fmmj4), reduzida a dez layouts, sem a página de
equipe nem a de pessoas com foto:

    capa            duas linhas de título sobre o padrão da Eixo
    texto           título e bloco de texto
    topicos         título em dois pesos, 2 a 5 tópicos e imagem à direita
    lista           chamada em três linhas e 2 a 6 itens numerados
    destaque        título em destaque, frase curta e imagem à direita
    secao_vinho     divisória de seção em vinho
    secao_marinho   divisória de seção em marinho
    cartoes_3       título e três cartões numerados
    cartoes_2       título e dois cartões numerados
    encerramento    "Obrigado!" e o contato de quem apresenta

Cada slide do resultado é cópia de um slide do molde com o texto trocado. A
formatação vem do próprio molde (fonte, cor, espaçamento); quando o texto não
cabe, a fonte diminui até caber, medida com a Montserrat de fontes/. Nos
layouts com imagem, a imagem enviada entra recortada na área da foto; sem
imagem, fica o espaço do modelo para trocar no Canva.

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
from PIL import Image, ImageFont
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
_ORIGINAL = {}  # caixa -> txBody do molde, refeito a cada gerar_pptx

# índice do slide no molde
LAYOUTS = {"capa": 0, "texto": 1, "topicos": 2, "lista": 3, "destaque": 4, "secao_vinho": 5,
           "secao_marinho": 6, "cartoes_3": 7, "cartoes_2": 8, "encerramento": 9}

NOMES = {
    "capa": "Capa",
    "texto": "Título e texto",
    "topicos": "Tópicos com imagem",
    "lista": "Lista numerada",
    "destaque": "Destaque com imagem",
    "secao_vinho": "Divisória vinho",
    "secao_marinho": "Divisória marinho",
    "cartoes_3": "Três cartões",
    "cartoes_2": "Dois cartões",
    "encerramento": "Encerramento",
}

# campos de cada layout: (chave, rótulo, limite de caracteres sugerido)
CAMPOS = {
    "capa": [("linha_1", "Linha de cima", 24), ("linha_2", "Linha de baixo (destaque)", 30)],
    "texto": [("titulo", "Título", 50), ("corpo", "Texto", 650)],
    "topicos": [("titulo_1", "Título, parte fina", 30), ("titulo_2", "Título, parte forte", 24),
                ("itens", "Tópicos (2 a 5)", 70)],
    "lista": [("linha_1", "Chamada (linha de cima)", 30), ("destaque", "Palavra em destaque", 16),
              ("linha_3", "Complemento (linha de baixo)", 50), ("itens", "Itens (2 a 6)", 90)],
    "destaque": [("linha_1", "Linha de cima", 18), ("destaque", "Palavra em destaque", 14),
                 ("texto", "Frase", 90)],
    "secao_vinho": [("titulo", "Título", 40)],
    "secao_marinho": [("titulo", "Título", 40)],
    "cartoes_3": [("titulo", "Título", 45)] + [
        (f"cartao_{i}_{k}", f"Cartão {i}: {r}", lim) for i in (1, 2, 3)
        for k, r, lim in (("titulo", "título", 30), ("texto", "texto", 200))],
    "cartoes_2": [("titulo", "Título", 45)] + [
        (f"cartao_{i}_{k}", f"Cartão {i}: {r}", lim) for i in (1, 2)
        for k, r, lim in (("titulo", "título", 40), ("texto", "texto", 280))],
    "encerramento": [("titulo", "Título", 30), ("contato", "Contato de quem apresenta", 80)],
}

ITENS = {"topicos": (2, 5), "lista": (2, 6)}
COM_IMAGEM = {"topicos", "destaque"}
PADRAO_ENCERRAMENTO = "Obrigado!"


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


def _estilos(body):
    """rPr normal e rPr de destaque do primeiro parágrafo da caixa."""
    runs = body.findall(".//a:r", NS)
    base = runs[0].find("a:rPr", NS)
    def cor(rp):
        el = rp.find(".//a:srgbClr", NS)
        return el.get("val") if el is not None else ""

    # destaque do molde: primeiro o run em vinho num texto que não é vinho
    # (o "Aqui" de "Título Aqui"), senão o primeiro run com outro peso
    rprs = [r.find("a:rPr", NS) for r in runs if (r.findtext("a:t", namespaces=NS) or "").strip()]
    dest = next((rp for rp in rprs if cor(rp) == VINHO and cor(base) != VINHO), None)
    if dest is None:
        dest = next((rp for rp in rprs if _peso(rp) != _peso(base)), None)
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


def _metricas(body):
    """(estilos para medir, entrelinha em pt) da caixa."""
    base, dest = _estilos(body)
    def m(rp):
        return (_peso(rp), int(rp.get("sz", "1800")) / 100, int(rp.get("spc", "0")) / 100)
    sp = body.find(".//a:pPr/a:lnSpc/a:spcPts", NS)
    ln = int(sp.get("val")) / 100 if sp is not None else m(base)[1] * 1.2
    return {False: m(base), True: m(dest)}, ln


def escrever(sh, texto: str, *, largura_pol: float | None = None, altura_max_pol: float | None = None,
             uma_linha: bool = False, escala_min: float = 0.35, escala: float | None = None,
             escala_max: float = 1.0) -> float:
    """Troca o texto da caixa mantendo a formatação do molde e reduz a fonte até
    caber. Devolve a escala usada (1 = tamanho do molde). Com `escala`, usa essa
    sem medir (para igualar caixas irmãs)."""
    if largura_pol:
        sh.width = Emu(int(largura_pol * POL))
    # formatação sempre a do molde: a segunda escrita na mesma caixa (para
    # igualar irmãs) não pode partir do texto já reduzido ou aumentado
    original = _ORIGINAL.setdefault(sh._element, copy.deepcopy(sh._element.txBody))
    estilos, ln = _metricas(original)
    pars = _paragrafos(texto)
    # folga: PowerPoint, LibreOffice, Canva e Slides desenham a Montserrat um
    # pouco mais larga que a medida da PIL, e o espaçamento negativo nem sempre entra
    largura_pt = sh.width / POL * 72 * FOLGA

    if escala is None:
        escala = escala_max
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
    ppr = original.find("a:p", NS).find("a:pPr", NS)
    base, dest = _estilos(original)

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




def _linhas_usadas(sh) -> int:
    estilos, ln = _metricas(sh._element.txBody)
    return max(1, round(sh.height / POL * 72 / ln))


def _ancora_meio(sh):
    bp = sh._element.txBody.find("a:bodyPr", NS)
    bp.set("anchor", "ctr")
    for el in list(bp):
        if el.tag == _q("a:spAutoFit"):
            bp.remove(el)


def _txt(c, k):
    return str(c.get(k) or "").strip()


def _capa(s, c):
    f = _formas(s)
    l1, l2 = _txt(c, "linha_1"), _txt(c, "linha_2")
    baixo, cima = f["TextBox 2"], f["TextBox 3"]
    base = baixo.top + baixo.height  # rodapé do título no molde
    escrever(baixo, l2 or " ", largura_pol=15.0, uma_linha=True, escala_min=0.45)
    if _linhas_usadas(baixo) > 1:
        escrever(baixo, l2, largura_pol=15.0, altura_max_pol=4.2)
    baixo.top = base - baixo.height
    if l1:
        escrever(cima, l1, largura_pol=15.0, uma_linha=True, escala_min=0.45)
        cima.top = baixo.top - int(cima.height * 0.76)
    else:
        _tirar(cima)


def _texto(s, c):
    f = _formas(s)
    tit, corpo = f["TextBox 5"], f["TextBox 2"]
    escrever(tit, _txt(c, "titulo"), largura_pol=16.5, altura_max_pol=2.6)
    corpo.top = tit.top + tit.height + _pol(0.7)
    escrever(corpo, _txt(c, "corpo"), largura_pol=17.0, altura_max_pol=10.2 - corpo.top / POL, escala_min=0.5)


def _itens(c, layout):
    lo, hi = ITENS[layout]
    v = c.get("itens") or []
    if isinstance(v, str):
        v = v.split("\n")
    return [str(i).strip() for i in v if str(i).strip()][:hi]


def _alinhar_no_circulo(texto, circulo, numero=None):
    """Caixa do texto centralizada no círculo e com âncora no meio: se o
    programa quebrar a linha diferente da medida, o texto continua alinhado."""
    meio = circulo.top + circulo.height // 2
    texto.height = max(texto.height, circulo.height)
    texto.top = meio - texto.height // 2
    _ancora_meio(texto)
    if numero is not None:
        numero.top = meio - numero.height // 2


def _imagem(s, grupo, dados: bytes | None, dica=None):
    """Troca a foto do modelo pela imagem enviada, recortada para preencher a
    área sem deformar. Sem imagem, fica a do modelo e a dica para trocar no Canva."""
    if not dados:
        return
    im = Image.open(io.BytesIO(dados))
    im = im.convert("RGB")
    im.thumbnail((2000, 2000))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    buf.seek(0)
    _, rid = s.part.get_or_add_image_part(buf)
    blip = grupo._element.find(".//a:blip", NS)
    blip.set("{%s}embed" % R, rid)
    forma = blip.getparent().getparent()  # spPr da forma com a foto
    ext = forma.find("a:xfrm/a:ext", NS)
    a_area = int(ext.get("cx")) / int(ext.get("cy"))
    a_img = im.width / im.height
    ret = blip.getparent().find("a:stretch/a:fillRect", NS)
    for k in ("l", "t", "r", "b"):
        ret.attrib.pop(k, None)
    if a_img > a_area:  # mais larga: sobra dos lados
        sobra = int((a_img / a_area - 1) / 2 * 100000)
        ret.set("l", str(-sobra)); ret.set("r", str(-sobra))
    else:
        sobra = int((a_area / a_img - 1) / 2 * 100000)
        ret.set("t", str(-sobra)); ret.set("b", str(-sobra))
    if dica is not None:
        _tirar(dica)


TOPICOS = [("Freeform 2", "TextBox 12"), ("Freeform 3", "TextBox 13"), ("Freeform 4", "TextBox 14"),
           ("Freeform 5", "TextBox 15"), ("Freeform 9", "TextBox 16")]


def _topicos(s, c):
    f = _formas(s)
    t1, t2 = f["TextBox 10"], f["TextBox 11"]
    escrever(t1, _txt(c, "titulo_1") or " ", largura_pol=10.2, uma_linha=True, escala_min=0.5)
    escrever(t2, _txt(c, "titulo_2") or " ", largura_pol=10.2, uma_linha=True, escala_min=0.5)
    t2.top = t1.top + int(t1.height * 0.78)
    itens = _itens(c, "topicos")
    for circ, t in TOPICOS[len(itens):]:
        _tirar(f[circ], f[t])
    usados = TOPICOS[:len(itens)]
    escalas = [escrever(f[t], txt, largura_pol=8.9, altura_max_pol=1.3) for (_, t), txt in zip(usados, itens)]
    e = min(escalas) if escalas else 1.0
    for (circ, t), txt in zip(usados, itens):
        escrever(f[t], txt, largura_pol=8.9, escala=e)
        _alinhar_no_circulo(f[t], f[circ])
    _imagem(s, f["Group 6"], c.get("imagem"), f["TextBox 17"])


ESQ = [("Freeform 4", "TextBox 5", "TextBox 6"), ("Freeform 8", "TextBox 9", "TextBox 20"),
       ("Freeform 10", "TextBox 11", "TextBox 21")]
DIR = [("Freeform 12", "TextBox 13", "TextBox 22"), ("Freeform 14", "TextBox 15", "TextBox 23"),
       ("Freeform 17", "TextBox 18", "TextBox 24")]


def _lista(s, c):
    f = _formas(s)
    l1, dest, l3 = _txt(c, "linha_1"), _txt(c, "destaque"), _txt(c, "linha_3")
    itens = _itens(c, "lista")
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
        escrever(f["TextBox 19"], l3, largura_pol=16.0, uma_linha=True)
        f["TextBox 19"].top = f["TextBox 3"].top + int(f["TextBox 3"].height * 0.70)
    else:
        _tirar(f["TextBox 19"])

    n = len(itens)
    if n <= 3:
        posicoes, sobra, larguras = ESQ[:n], ESQ[n:] + DIR, [15.0] * n
    else:
        k = math.ceil(n / 2)
        posicoes, sobra = ESQ[:k] + DIR[:n - k], ESQ[k:] + DIR[n - k:]
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
        _alinhar_no_circulo(f[t], f[circ], f[num])


def _destaque(s, c):
    f = _formas(s)
    l1, dest, txt = _txt(c, "linha_1"), _txt(c, "destaque"), _txt(c, "texto")
    t3, t4, t5 = f["TextBox 3"], f["TextBox 4"], f["TextBox 5"]
    topo = t3.top
    if l1:
        escrever(t3, l1, largura_pol=10.0, uma_linha=True)
        t4.top = t3.top + int(t3.height * 0.70)
    else:
        _tirar(t3)
        t4.top = topo
    escrever(t4, dest or " ", largura_pol=10.0, uma_linha=True)
    if txt:
        t5.top = t4.top + int(t4.height * 1.24)
        escrever(t5, txt, largura_pol=10.0, altura_max_pol=10.4 - t5.top / POL)
    else:
        _tirar(t5)
    _imagem(s, f["Group 6"], c.get("imagem"), f["TextBox 8"])


def _secao(s, c):
    f = _formas(s)
    escrever(f["TextBox 4"], _txt(c, "titulo") or " ", largura_pol=17.0, altura_max_pol=2.6)


def _numero_no_circulo(grupo, texto):
    caixa = grupo._element.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}txBody")
    p = caixa.find("a:p", NS)
    for r in p.findall("a:r", NS):
        p.remove(r)
    r = etree.SubElement(p, _q("a:r"))
    rp = etree.SubElement(r, _q("a:rPr"), lang="pt-BR", sz="6000", b="1")
    etree.SubElement(etree.SubElement(rp, _q("a:solidFill")), _q("a:srgbClr"), val=VINHO)
    for tag in ("a:latin", "a:ea", "a:cs", "a:sym"):
        etree.SubElement(rp, _q(tag), typeface="Montserrat Bold")
    etree.SubElement(r, _q("a:t")).text = texto
    sp = p.find(".//a:spcPts", NS)
    if sp is not None:
        sp.set("val", "7200")


def _cartoes(s, c, titulo, largura_titulo, altura_titulo, pares):
    """pares: (título do cartão, texto do cartão, grupo do círculo, caixa da
    instrução do Canva sobre o círculo), da esquerda para a direita."""
    f = _formas(s)
    escrever(f[titulo], _txt(c, "titulo"), largura_pol=largura_titulo, altura_max_pol=altura_titulo)
    esc_t, esc_x = [], []
    for i, (tt, tx, _, _) in enumerate(pares, 1):
        esc_t.append(escrever(f[tt], _txt(c, f"cartao_{i}_titulo"), altura_max_pol=1.2, escala_max=1.3))
    for i, (tt, tx, _, _) in enumerate(pares, 1):
        topo = f[tt].top + f[tt].height + _pol(0.25)
        # texto curto cresce até 1,25x (18 -> 22,5 pt) para não sobrar cartão
        # vazio; o título do cartão vai até 1,3x e fica sempre maior
        esc_x.append(escrever(f[tx], _txt(c, f"cartao_{i}_texto"),
                              altura_max_pol=min(3.0, 10.2 - topo / POL), escala_max=1.25))
    for i, (tt, tx, grupo, dica) in enumerate(pares, 1):
        escrever(f[tt], _txt(c, f"cartao_{i}_titulo"), escala=min(esc_t))
        escrever(f[tx], _txt(c, f"cartao_{i}_texto"), escala=min(esc_x))
        _numero_no_circulo(f[grupo], f"0{i}")
        _tirar(f[dica])
    # títulos na mesma altura e textos começando juntos, abaixo do título mais alto
    topo = min(f[tt].top for tt, _, _, _ in pares)
    fundo = max(topo + f[tt].height for tt, _, _, _ in pares)
    for tt, tx, _, _ in pares:
        f[tt].top = topo
        f[tx].top = fundo + _pol(0.25)


def _cartoes_3(s, c):
    _cartoes(s, c, "TextBox 22", 17.0, 1.3, [
        ("TextBox 27", "TextBox 28", "Group 19", "TextBox 29"),
        ("TextBox 23", "TextBox 24", "Group 7", "TextBox 30"),
        ("TextBox 25", "TextBox 26", "Group 13", "TextBox 31")])


def _cartoes_2(s, c):
    _cartoes(s, c, "TextBox 16", 6.6, 8.0, [
        ("TextBox 19", "TextBox 20", "Group 6", "TextBox 22"),
        ("TextBox 17", "TextBox 18", "Group 12", "TextBox 21")])


def _encerramento(s, c):
    f = _formas(s)
    escrever(f["TextBox 5"], _txt(c, "titulo") or PADRAO_ENCERRAMENTO, largura_pol=12.0, altura_max_pol=2.8)
    contato = _txt(c, "contato")
    if contato:
        escrever(f["TextBox 7"], contato, largura_pol=10.5, altura_max_pol=2.0)
    else:
        _tirar(f["TextBox 6"], f["TextBox 7"], f["Freeform 2"])


PREENCHER = {"capa": _capa, "texto": _texto, "topicos": _topicos, "lista": _lista, "destaque": _destaque,
             "secao_vinho": _secao, "secao_marinho": _secao, "cartoes_3": _cartoes_3, "cartoes_2": _cartoes_2,
             "encerramento": _encerramento}


def gerar_pptx(slides: list[dict]) -> bytes:
    """slides: [{"layout": "capa", "campos": {...}}] -> bytes do .pptx. Nos
    layouts com imagem, campos["imagem"] traz os bytes da imagem (opcional)."""
    _ORIGINAL.clear()
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
        partes = []
        for ck, _, lim in campos:
            if ck == "itens":
                lo, hi = ITENS[k]
                partes.append(f'"itens" (lista de {lo} a {hi} frases, cada uma até {lim} caracteres)')
            else:
                partes.append(f'"{ck}" (até {lim} caracteres)')
        linhas.append(f"- {k} ({NOMES[k]}): " + ", ".join(partes))
    return "\n".join(linhas)


PROMPT = """Você organiza um conteúdo em slides no modelo de apresentação da Eixo, uma consultoria política.

Layouts disponíveis e seus campos:
{layouts}

Como usar cada layout:
- capa: sempre o primeiro slide. linha_1 é curta, em minúsculas e em tom de chamada (ex.: "relatório de"); linha_2 é o tema (ex.: "pedidos de LAI").
- secao_vinho e secao_marinho: abrem um bloco do conteúdo. Título curto em MAIÚSCULAS. Alterne as duas cores quando houver mais de um bloco.
- texto: título e um ou dois parágrafos. No título, a palavra-chave pode vir entre ** (ex.: "Prazos **legais**"). No texto, até três trechos-chave com **.
- topicos: título em duas partes (titulo_1 fina, titulo_2 forte, ex.: "Somos guiados por" / "fortes valores") e de 2 a 5 tópicos curtos. Tem área de imagem à direita.
- lista: etapas ou pontos paralelos numerados. linha_1 em maiúsculas (ex.: "DISTRIBUIÇÃO DOS"), destaque é UMA palavra (ex.: "prazos"), linha_3 completa a frase (ex.: "dos 28 pedidos sem resposta").
- destaque: uma ideia central. linha_1 curta em minúsculas, destaque é UMA palavra em maiúsculas, texto é uma frase. Tem área de imagem à direita.
- cartoes_3 e cartoes_2: três ou duas coisas lado a lado (frentes, produtos, grupos). Cada cartão tem título curto e texto.
- encerramento: último slide, só se o pedido ou o conteúdo indicar fechamento. Devolva "campos": {{}}; quem monta preenche o contato.

Regras:
- Use só o que está no conteúdo. Não invente número, nome, data, cliente nem resultado.
- Pode resumir e reescrever para caber no limite, sem mudar o sentido.
- Respeite os limites de caracteres. Texto acima do limite fica com fonte pequena.
- Varie os layouts; não repita o mesmo layout em mais de dois slides seguidos.
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
                v = v if isinstance(v, list) else str(v or "").split("\n")
                v = [str(i).replace("—", ",").strip() for i in v if str(i).strip()][:ITENS[s["layout"]][1]]
            else:
                v = str(v or "").replace("—", ",").strip()
            campos[chave] = v
        if s["layout"] == "encerramento":
            campos = {"titulo": "", "contato": ""}  # quem monta preenche, na página
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
