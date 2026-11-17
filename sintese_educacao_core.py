"""Síntese da Semana (educação): do doc "Links educação" ao Word de ISG, IU e FMCSV.

Entrada: o doc semanal da pasta "z_links educação" (um por semana, "Links educação - dd.mm a
dd.mm"), lido pelo link compartilhado (export em HTML, sem login). A equipe cola os links
embaixo de LEGISLATIVO, EXECUTIVO, JUDICIÁRIO, NOTÍCIAS e DIÁRIO OFICIAL DA UNIÃO, e as
proposições na tabela NOVAS PROPOSIÇÕES. Item com texto já escrito pela equipe (título e
parágrafos) fica como está; item só com link vai para o Gemini.

Quem recebe cada item (regra da Bruna, 17/11/2026, conferida na semana 9 a 13/11):
- IU recebe tudo o que está no doc.
- ISG recebe o mesmo que o IU, menos clima e meio ambiente.
- FMCSV recebe primeira infância, crianças e adolescentes e pautas gerais de educação básica.
Marcação no começo do item ("FMCSV:", "ISG:", "IU:", "[FMCSV]") manda só para aquele cliente.

Saída: um .docx por cliente no modelo das sínteses enviadas (ISG e IU usam o mesmo, a FMCSV
tem o dela) e o corpo do email para o Wix (1 notícia por eixo + aviso do PDF).
"""
from __future__ import annotations

import copy
import datetime as dt
import html as _html
import io
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

import requests

import sintese_semana_core as ss

# ─── Clientes e seções ───────────────────────────────────────────────────────
CLIENTES = {
    "IU": {"titulo": "IU", "modelo": "sintese_edu_modelo.docx"},
    "ISG": {"titulo": "ISG", "modelo": "sintese_edu_modelo.docx"},
    "FMCSV": {"titulo": "FMCSV", "modelo": "sintese_edu_modelo_fmcsv.docx"},
}
SECOES = ["CENÁRIO ELEITORAL", "LEGISLATIVO", "EXECUTIVO", "JUDICIÁRIO", "NOTÍCIAS", "DIÁRIO OFICIAL DA UNIÃO"]
EIXOS_EMAIL = ["LEGISLATIVO", "EXECUTIVO", "NOTÍCIAS"]  # o Wix recebe 1 notícia de cada
_RE_SECAO = {
    "CENÁRIO ELEITORAL": r"cen[áa]rio (eleitoral|pol[íi]tico)|conjuntura",
    "LEGISLATIVO": r"legislativo",
    "EXECUTIVO": r"executivo",
    "JUDICIÁRIO": r"judici[áa]rio",
    "NOTÍCIAS": r"not[íi]cias",
    "DIÁRIO OFICIAL DA UNIÃO": r"di[áa]rio oficial|^dou$",
}
_RE_PROPOSICOES = re.compile(r"^\s*novas proposi", re.I)
_RE_MARCA = re.compile(r"^\s*[\[(]?\s*((?:FMCSV|ISG|IU)(?:\s*[,/e+]\s*(?:FMCSV|ISG|IU))*)\s*[\])]?\s*[:\-–]\s*", re.I)
_RE_PROP = re.compile(r"^\s*((?:PL|PLP|PEC|PDL|PLN|MPV|REQ|RIC|INC|PRC|PLS)\s*n?[°º.]?\s*[\d.]+\s*/\s*\d{4}(?:\s*[-–]?\s*(?-i:[A-Z]{2,10})\b)?)", re.I)
_RE_PROP_EXTENSO = re.compile(r"^\s*Projeto de Lei(?: Complementar)?\s*n?[°º.]?\s*([\d.]+)\s*,?\s*de\s*(\d{4})", re.I)


def _proposicao(txt: str) -> str | None:
    """'PL5797/2026', 'Projeto de Lei n° 5638, de 2026' -> 'PL 5797/2026', 'PL 5638/2026'."""
    m = _RE_PROP.match(txt or "")
    if m:
        p = re.sub(r"\s+", " ", m.group(1)).strip()
        return re.sub(r"^([A-Za-z]+)\s*n?[°º.]?\s*", lambda x: x.group(1).upper() + " ", p)
    m = _RE_PROP_EXTENSO.match(txt or "")
    if m:
        sigla = "PLP" if "complementar" in m.group(0).lower() else "PL"
        return f"{sigla} {m.group(1)}/{m.group(2)}"
    return None


def _autor(txt: str) -> str:
    """'Aline Gurgel - UNIÃO/AP' -> 'Aline Gurgel (UNIÃO/AP)'; o que já vem com parênteses fica."""
    t = re.sub(r"\s+", " ", txt or "").strip(" .")
    m = re.match(r"^(.+?)\s*[-–]\s*([A-ZÀ-Ú]+)\s*/\s*([A-Z]{2})$", t)
    return f"{m.group(1)} ({m.group(2)}/{m.group(3)})" if m else t


def _link_publico(url: str) -> str:
    """Link de proposição só se for de Câmara ou Senado (o do Inteligov pede login)."""
    return url if re.search(r"camara\.leg\.br|senado\.leg\.br|congressonacional\.leg\.br", url or "") else ""


def periodo_curto(ini: dt.date, fim: dt.date) -> str:
    """'09.11 a 13.11.2026', como no cabeçalho das sínteses de educação."""
    return f"{ini:%d.%m} a {fim:%d.%m.%Y}"


def nome_arquivo(cliente: str, ini: dt.date, fim: dt.date) -> str:
    return f"Síntese da Semana - {CLIENTES[cliente]['titulo']} ({ini:%d.%m} a {fim:%d.%m.%Y}).docx"


# ─── Achar o doc da semana na pasta ──────────────────────────────────────────
def listar_pasta(pasta_id: str) -> list[dict]:
    """Arquivos de uma pasta compartilhada por link (embeddedfolderview não pede login)."""
    req = urllib.request.Request(f"https://drive.google.com/embeddedfolderview?id={pasta_id}",
                                 headers={"User-Agent": ss.UA["User-Agent"]})
    s = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'<a href="([^"]+)"[^>]*>.*?flip-entry-title">([^<]+)<', s, re.S):
        link, nome = m.group(1), _html.unescape(m.group(2)).strip()
        mid = re.search(r"/d/([\w-]{20,})", link)
        out.append({"nome": nome, "link": link, "id": mid.group(1) if mid else ""})
    return out


def _datas_do_nome(nome: str, ano: int) -> tuple[dt.date, dt.date] | None:
    m = re.search(r"(\d{1,2})[./](\d{1,2})\s*(?:a|até|-|–)\s*(\d{1,2})[./](\d{1,2})", nome)
    if not m:
        return None
    try:
        return dt.date(ano, int(m.group(2)), int(m.group(1))), dt.date(ano, int(m.group(4)), int(m.group(3)))
    except ValueError:
        return None


def doc_da_semana(arquivos: list[dict], ini: dt.date) -> dict | None:
    """O 'Links educação - dd.mm a dd.mm' cuja segunda-feira é `ini` (nome com 'Cópia de' também vale)."""
    for a in arquivos:
        if "docs.google.com/document" not in a["link"] or "links educa" not in a["nome"].lower():
            continue
        datas = _datas_do_nome(a["nome"], ini.year)
        if datas and datas[0] - dt.timedelta(days=datas[0].weekday()) == ini:
            return a
    return None


def id_do_doc(link_ou_id: str) -> str:
    """ID de um Google Doc a partir do link (ou do próprio ID). Erro claro para pasta, arquivo do Drive etc."""
    t = (link_ou_id or "").strip()
    m = re.search(r"docs\.google\.com/document/(?:u/\d+/)?d/([\w-]{20,})", t)
    if m:
        return m.group(1)
    if re.fullmatch(r"[\w-]{25,}", t):
        return t
    if "/folders/" in t:
        raise ValueError("Esse é o link de uma pasta. Abra o doc da semana e cole o link dele.")
    if "drive.google.com/file" in t or "/spreadsheets/" in t:
        raise ValueError("Esse link não é de um Google Doc. Se o doc está em Word, abra como Google Docs "
                         "(Arquivo > Salvar como Google Docs) e cole o link novo.")
    raise ValueError("Não reconheci o link. Cole o endereço do doc, que começa com https://docs.google.com/document/d/")


def baixar_doc(doc_id: str) -> str:
    """HTML do doc pelo export público. Erro claro se o doc não estiver aberto para quem tem o link."""
    r = requests.get(f"https://docs.google.com/document/d/{doc_id}/export?format=html",
                     headers={"User-Agent": ss.UA["User-Agent"]}, timeout=40)
    if r.status_code != 200 or "<html" not in r.text[:500].lower() or "accounts.google.com" in r.url:
        raise RuntimeError("Não consegui abrir o doc. Confira se ele está compartilhado como "
                           "'Qualquer pessoa com o link pode ver'.")
    r.encoding = "utf-8"
    return r.text


# ─── Leitura do doc ──────────────────────────────────────────────────────────
class _Blocos(HTMLParser):
    """Parágrafos (p, li, h*) e células de tabela do export do Docs, com os links de cada um."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocos: list[dict] = []
        self._atual = None
        self._link = None
        self._linha = None   # células da linha de tabela em curso
        self._celula = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._linha = []
        elif tag == "td":
            self._celula = {"texto": "", "links": []}
        elif tag in ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6") and self._celula is None:
            self._atual = {"tag": tag, "partes": []}
        elif tag == "a" and a.get("href"):
            href = a["href"]
            m = re.search(r"[?&]q=([^&]+)", href) if "google.com/url" in href else None
            link = requests.utils.unquote(m.group(1)) if m else href
            self._link = link if link.startswith("http") else None
            if self._celula is not None and self._link:
                self._celula["links"].append(self._link)
        elif tag == "br" and self._atual is not None:
            self._atual["partes"].append(("\n", None))

    def handle_endtag(self, tag):
        if tag == "a":
            self._link = None
        elif tag == "td" and self._celula is not None:
            self._linha.append(self._celula)
            self._celula = None
        elif tag == "tr" and self._linha is not None:
            self.blocos.append({"tag": "tr", "celulas": self._linha})
            self._linha = None
        elif self._atual is not None and tag == self._atual["tag"]:
            # quebra simples (Shift+Enter) no Docs vira <br>: cada linha é um bloco
            linhas, atual = [], []
            for txt, link in self._atual["partes"]:
                if txt == "\n":
                    linhas.append(atual)
                    atual = []
                else:
                    atual.append((txt, link))
            linhas.append(atual)
            for partes in linhas:
                texto = re.sub(r"[ \t ​]+", " ", "".join(t for t, _ in partes)).strip()
                links = list(dict.fromkeys(lk for _, lk in partes if lk))
                if texto or links:
                    self.blocos.append({"tag": self._atual["tag"], "texto": texto, "links": links,
                                        "trechos": [(re.sub(r"\s+", " ", t).strip(), lk) for t, lk in partes
                                                    if lk and t.strip()]})
            self._atual = None

    def handle_data(self, data):
        if self._celula is not None:
            self._celula["texto"] += data
        elif self._atual is not None:
            self._atual["partes"].append((data, self._link))


def _qual_secao(texto: str) -> str | None:
    t = texto.strip(" :.").lower()
    if len(t) > 40:
        return None
    for nome, rx in _RE_SECAO.items():
        if re.search(rx, t, re.I):
            return nome
    return None


def _marcas(texto: str) -> tuple[list[str], str]:
    """'FMCSV: título' -> (['FMCSV'], 'título')."""
    m = _RE_MARCA.match(texto or "")
    if not m:
        return [], texto
    quem = [c.upper() for c in re.findall(r"FMCSV|ISG|IU", m.group(1), re.I)]
    return list(dict.fromkeys(quem)), texto[m.end():].strip()


def _e_url(texto: str) -> bool:
    return bool(re.fullmatch(r"https?://\S+", texto.strip()))


def _cabeca_de_item(b: dict, anterior_cabeca: bool = False) -> bool:
    """Bloco que abre um item: link solto, título curto (com ou sem link, sem ponto final) ou item de lista."""
    t = b["texto"]
    if t.startswith("- "):
        return False
    if b["tag"] == "li":
        return True
    if b["links"] and (_e_url(t) or len(t) < 230):
        return True
    return len(t) < 200 and not t.rstrip().endswith((".", ":", ";")) and not anterior_cabeca


def ler_doc(html: str) -> dict:
    """{'semana': '09.11 a 13.11', 'itens': [...], 'proposicoes': [...]}."""
    p = _Blocos()
    p.feed(html)
    itens, props = [], []
    secao, semana = None, ""
    em_props = False
    for b in p.blocos:
        if b["tag"] == "tr":
            cel = b["celulas"]
            txts = [re.sub(r"\s+", " ", c["texto"]).strip() for c in cel]
            if not any(txts) or "PROPOSI" in txts[0].upper():
                continue
            prop = _proposicao(txts[0])
            if not prop:
                continue
            quem = [c.upper() for c in re.findall(r"\b(FMCSV|ISG|IU)\b", " ".join(txts[3:]), re.I)]
            props.append({"proposicao": prop, "link": _link_publico((cel[0]["links"] or [""])[0]),
                          "ementa": txts[1].lstrip(". ") if len(txts) > 1 else "",
                          "autor": _autor(txts[2]) if len(txts) > 2 else "", "clientes": quem})
            continue
        t = b["texto"]
        if not semana and re.match(r"^\d{1,2}[./]\d{1,2}\s*a\s*\d{1,2}[./]\d{1,2}", t):
            semana = t
            continue
        if not b["links"]:
            if _RE_PROPOSICOES.match(t):
                em_props, secao = True, None
                continue
            nova = _qual_secao(t)
            if nova and t.upper() == t:
                secao, em_props = nova, False
                continue
        if em_props:
            mp = _RE_PROP.match(t)
            if mp:  # "PL 5797/2026 – Institui ..." solto, fora da tabela
                resto = t[mp.end():].strip(" –-:")
                props.append({"proposicao": _proposicao(t), "link": _link_publico((b["links"] or [""])[0]),
                              "ementa": resto, "autor": "", "clientes": []})
            elif props and re.match(r"^autor(a|ia)?\s*:", t, re.I):
                props[-1]["autor"] = _autor(re.sub(r"^autor(a|ia)?\s*:\s*", "", t, flags=re.I))
            elif b["links"] and _cabeca_de_item(b):  # notícia colada embaixo das proposições
                itens.append(_novo_item(b, "NOTÍCIAS"))
            elif itens and not b["links"] and not _RE_PROP.match(t) and not re.match(r"^ementa\s*:", t, re.I):
                itens[-1]["paragrafos_equipe"].append(t)
            continue
        if secao is None:
            continue
        ant = bool(itens) and itens[-1]["secao"] == secao and not itens[-1]["paragrafos_equipe"]
        if _cabeca_de_item(b, ant):
            itens.append(_novo_item(b, secao))
        elif itens and itens[-1]["secao"] == secao:
            itens[-1]["paragrafos_equipe"].append(t)
            itens[-1]["documentos_equipe"] += [{"nome": n, "url": u} for n, u in b["trechos"] if len(n) > 3]
    for i, it in enumerate(itens):
        it["paragrafos_equipe"] = [x for x in it["paragrafos_equipe"] if x.strip()]
        it["_pos"] = i
    return {"semana": semana, "itens": itens, "proposicoes": props}


def _novo_item(b: dict, secao: str) -> dict:
    marcas, texto = _marcas(b["texto"])
    url = b["links"][0] if b["links"] else ""
    titulo = "" if _e_url(texto) else texto.strip()
    return {"secao": secao, "url": url, "titulo_equipe": titulo, "paragrafos_equipe": [], "marcas": marcas,
            "documentos_equipe": []}


ENCURTADORES = ("tinyurl.com", "share.google", "bit.ly", "goo.gl", "encurtador.com.br", "abre.ai", "t.co/")


def _curto(url: str) -> bool:
    return any(e in (url or "") for e in ENCURTADORES)


def _destino_tinyurl(pagina: str) -> str | None:
    """O TinyURL manda link de API antiga para uma página "preview/deprecated" em vez da matéria;
    o destino vem nessa página, em window.externalPageData.jsonUrl ("original" = base64 do endereço)."""
    import base64
    import json
    from urllib.parse import unquote
    try:
        m = re.search(r"window\.externalPageData\s*=\s*(\{.*?\});\s*</script>", pagina, re.S)
        j = json.loads(json.loads(m.group(1))["jsonUrl"])
        if j.get("original"):
            return unquote(base64.b64decode(j["original"]).decode())
        return f"{j['scheme']}://{j['host']}{j['path']}" + (f"?{j['query']}" if j.get("query") else "")
    except Exception:  # noqa: BLE001
        return None


def _abrir(url: str):
    """GET seguindo encurtadores (TinyURL com página de aviso, share.google). Devolve (resposta, endereço final)."""
    r = requests.get(url, headers=ss.UA, timeout=25, allow_redirects=True)
    if "tinyurl.com/preview" in r.url:
        destino = _destino_tinyurl(r.text)
        if not destino:
            raise ValueError("o TinyURL não mostrou o destino do link")
        r = requests.get(destino, headers=ss.UA, timeout=25, allow_redirects=True)
    r.raise_for_status()
    r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
    final = r.url
    if "share.google" in final:
        m = re.search(r'<link rel="canonical" href="([^"]+)"', r.text) or re.search(r'property="og:url" content="([^"]+)"', r.text)
        if m:
            final = _html.unescape(m.group(1))
    return r, final


def resolver(url: str) -> str:
    """Endereço final de um link curto (para o título no Word não levar à página do encurtador)."""
    if not _curto(url):
        return url
    try:
        return _abrir(url)[1]
    except Exception:  # noqa: BLE001
        return url


# ─── Download dos links ──────────────────────────────────────────────────────
def baixar(url: str) -> dict:
    """Como ss.baixar_noticia, mas guarda o endereço final (encurtadores levam para a matéria)."""
    import trafilatura
    out = {"url_final": url, "titulo_pagina": "", "texto": "", "erro": ""}
    try:
        r, final = _abrir(url)
        out["url_final"] = final
        meta = trafilatura.bare_extraction(r.text, url=final, with_metadata=True)
        meta = meta.as_dict() if hasattr(meta, "as_dict") else (meta or {})
        out["titulo_pagina"] = (meta.get("title") or "").strip()
        out["texto"] = (trafilatura.extract(r.text, url=final, output_format="markdown", include_links=True) or "")[:9000]
        if len(out["texto"]) < 200:
            out["erro"] = "página com pouco texto (pode exigir login ou ser só índice)"
    except requests.HTTPError as e:
        cod = e.response.status_code if e.response is not None else ""
        if e.response is not None and "tinyurl.com" not in e.response.url:
            out["url_final"] = e.response.url  # o encurtador resolveu; o site é que falhou
        out["erro"] = f"o site recusou a leitura automática (HTTP {cod})" if cod in (401, 403, 429) \
            else f"o site deu erro (HTTP {cod}); tente de novo mais tarde"
    except requests.Timeout:
        out["erro"] = "o site demorou demais para responder"
    except Exception as e:  # noqa: BLE001
        out["erro"] = f"{type(e).__name__}: {e}"[:200]
    return out


def baixar_todos(itens: list[dict], workers: int = 8) -> list[dict]:
    """Baixa o que a equipe ainda não resumiu; do que ela já escreveu, só resolve link curto."""
    falta = [i for i, it in enumerate(itens) if not it["paragrafos_equipe"] and it["url"]]
    curtos = [i for i, it in enumerate(itens) if it["paragrafos_equipe"] and _curto(it["url"])]
    with ThreadPoolExecutor(workers) as ex:
        res = dict(zip(falta, ex.map(lambda i: baixar(itens[i]["url"]), falta)))
        res.update({i: {"url_final": u, "texto": "", "erro": "", "titulo_pagina": ""}
                    for i, u in zip(curtos, ex.map(lambda i: resolver(itens[i]["url"]), curtos))})
    return [{**it, **res.get(i, {"url_final": it["url"], "texto": "", "erro": "", "titulo_pagina": ""})}
            for i, it in enumerate(itens)]


# ─── Gemini ──────────────────────────────────────────────────────────────────
REGRAS = """
Você redige itens da síntese semanal de educação de uma consultoria de relações governamentais. Os clientes são o IU, o ISG e a FMCSV (Fundação Maria Cecilia Souto Vidigal, primeira infância).

Use exclusivamente o texto fornecido de cada item. Não invente, não complemente com fontes externas, não faça inferências não sustentadas pelo texto.

FORMATO DE CADA ITEM
- "titulo": uma frase no presente que resume o fato, começando por quem agiu (ex.: "Senado instala Subcomissão Permanente do Plano Nacional de Educação"; "MEC homologa diretrizes nacionais para utilização da inteligência artificial na educação"). Sem ponto final. Nunca "a notícia destaca" e equivalentes.
- "paragrafos": 1 a 3 parágrafos, cada um com 2 ou 3 frases. O primeiro diz o que aconteceu, quem fez, quando e o número da proposição ou do ato. Os seguintes trazem o conteúdo da medida, posições atribuídas a quem as defende e o próximo passo de tramitação quando o texto informar. O que já aconteceu vai no pretérito perfeito (aprovou, homologou, afirmou); presente só para o que segue valendo (a norma estabelece, o texto prevê).
- Cite parlamentar como Nome (PARTIDO/UF). Use as siglas dos órgãos depois da primeira menção por extenso.
- Ato do Diário Oficial: diga o número do ato, a data e o que ele estabelece.
- "primeira_infancia": se o texto trouxer algo específico sobre educação infantil, creche, pré-escola, primeira infância (0 a 6 anos), gestação ou parto, uma frase com essa informação; senão "".
- "documentos": documentos citados com link no próprio texto (lei, decreto, portaria, parecer, resolução, pesquisa, relatório). Só links que aparecem no texto, com o nome como aparece nos parágrafos.

FIDELIDADE
- Nada de conclusões, impactos, recomendações ou avaliações que não estejam explícitos no texto. Nada de "a medida busca", "o que pode", "reforça a importância".
- Preserve nomes, cargos, números e datas.

REDAÇÃO
- Linguagem objetiva e profissional. Proibido: gerúndio, "restou", "junto a", travessão (— ou –).
- Evite "para que + verbo"; prefira o infinitivo. Sem adjetivos desnecessários.

CLASSIFICAÇÃO (para separar por cliente; a equipe revisa depois)
- "clima": true se o assunto principal for clima, mudanças climáticas, COP, meio ambiente, transição energética ou desastres ambientais (mesmo quando cita escolas). Senão false.
- "fmcsv": true se o item tratar de primeira infância, educação infantil, creche, pré-escola, alfabetização, gestação, parto, saúde materno-infantil, crianças e adolescentes (proteção, violência, abuso, exploração sexual, casamento infantil, maioridade penal, ECA, Conanda) ou de pauta geral da educação básica que alcança a educação infantil e o ensino fundamental (Fundeb, orçamento e financiamento da educação, ajuste fiscal com efeito na educação, PNE, CNE, diretrizes do MEC para toda a educação básica, carreira e formação de professores, livro didático, conjuntura do MEC). false para ensino superior, ensino médio, educação profissional, Sisu, cotas em instituições federais, conectividade, currículo de temas específicos do ensino médio, clima.
""".strip()


def _prompt(itens: list[dict]) -> str:
    blocos = []
    for i, it in enumerate(itens, 1):
        if it["paragrafos_equipe"]:
            fonte = "TEXTO JÁ ESCRITO PELA EQUIPE (só classifique; repita título e parágrafos como estão):\n" \
                    + (it["titulo_equipe"] + "\n" if it["titulo_equipe"] else "") + "\n".join(it["paragrafos_equipe"])
        else:
            fonte = f"Título da página: {it.get('titulo_pagina', '')}\n" + \
                    (f"Título dado pela equipe: {it['titulo_equipe']}\n" if it["titulo_equipe"] else "") + \
                    "\n" + it.get("texto", "")
        blocos.append(f"### ITEM {i}\nSeção no doc: {it['secao']}\nURL: {it.get('url_final') or it['url']}\n{fonte}")
    return f"""{REGRAS}

Responda SOMENTE com JSON, sem comentários, no formato:
{{"itens": [{{"item": <número>, "titulo": "...", "paragrafos": ["...", "..."], "primeira_infancia": "", "clima": false, "fmcsv": false, "documentos": [{{"nome": "...", "url": "..."}}]}}]}}
Devolva um objeto para cada item, na mesma numeração.

ITENS DA SEMANA:

""" + "\n\n".join(blocos)


def _json(texto: str | None) -> list:
    bruto = re.sub(r"^```(?:json)?|```$", "", (texto or "").strip()).strip()
    import json
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", bruto, re.S)
        if not m:
            raise ValueError("o Gemini não devolveu JSON; rode de novo") from None
        dados = json.loads(m.group(0))
    if isinstance(dados, dict):
        dados = dados.get("itens")
    return dados if isinstance(dados, list) else []


def _chamar(client, modelo: str, prompt: str):
    import gemini_config
    for tentativa in range(2):  # 429/503 do Gemini costumam passar na segunda
        try:
            return client.models.generate_content(
                model=modelo, contents=prompt,
                config=gemini_config.config(json=True))
        except Exception as e:  # noqa: BLE001
            if tentativa == 1 or not re.search(r"429|500|503|UNAVAILABLE|RESOURCE_EXHAUSTED|DEADLINE", str(e)):
                raise
            time.sleep(15)


def gerar(client, modelo: str, itens: list[dict], lote: int = 8) -> tuple[list[dict], list[str]]:
    """Resume e classifica os itens em lotes paralelos. Devolve (itens, erros dos lotes).

    Nenhum item some: o que não deu para ler ou resumir volta com "falha" e sem parágrafos,
    para quem revisa escrever o texto ou tentar de novo."""
    validos = [it for it in itens if it["paragrafos_equipe"] or it.get("texto")]
    lotes = [validos[i:i + lote] for i in range(0, len(validos), lote)]
    erros: list[str] = []

    def _um(grupo):
        try:
            return grupo, _json(_chamar(client, modelo, _prompt(grupo)).text), None
        except Exception as e:  # noqa: BLE001
            return grupo, [], f"{type(e).__name__}: {e}"[:300]

    prontos = [{**montar_item(it, {}), "falha": "não consegui ler o link" + (f" ({it['erro']})" if it.get("erro") else "")}
               for it in itens if not (it["paragrafos_equipe"] or it.get("texto"))]
    with ThreadPoolExecutor(4) as ex:
        for grupo, resp, err in ex.map(_um, lotes):
            if err:
                erros.append(err)
            por_n = {}
            for r in resp:
                try:
                    por_n[int(r["item"])] = r
                except (KeyError, ValueError, TypeError):
                    continue
            for i, it in enumerate(grupo, 1):
                r = por_n.get(i)
                if r is None:
                    if not it["paragrafos_equipe"]:
                        prontos.append({**montar_item(it, {}), "falha": "o Gemini não resumiu este item"})
                        continue
                    r = {}  # texto da equipe vai mesmo sem a classificação
                prontos.append({**montar_item(it, r), "aviso": it.get("erro", "")})
    ordem = {s: i for i, s in enumerate(SECOES)}
    prontos.sort(key=lambda x: (ordem.get(x["secao"], 99), x["_pos"]))
    return prontos, erros


def montar_item(it: dict, r: dict) -> dict:
    fonte = it.get("texto", "")
    if it["paragrafos_equipe"]:  # a equipe já escreveu: o texto fica como está
        titulo = it["titulo_equipe"] or ss._limpar(r.get("titulo") or "")
        pars = list(it["paragrafos_equipe"])
    else:
        titulo = ss._limpar(r.get("titulo") or it["titulo_equipe"] or it.get("titulo_pagina", "") or "")
        pars = [ss._limpar(p) for p in (r.get("paragrafos") or []) if isinstance(p, str) and p.strip()]
    docs = [d for d in (r.get("documentos") if isinstance(r.get("documentos"), list) else [])
            if isinstance(d, dict) and d.get("url") and d.get("nome") and d["url"] in fonte]
    if it["paragrafos_equipe"]:  # links que a equipe pôs no meio do texto
        docs = it.get("documentos_equipe", [])
    clima, fmcsv = bool(r.get("clima")), bool(r.get("fmcsv"))
    marcas = it["marcas"]
    if marcas:
        clientes = [c for c in CLIENTES if c in marcas]
    else:
        clientes = ["IU"] + ([] if clima else ["ISG"]) + (["FMCSV"] if fmcsv else [])
    return {"secao": it["secao"], "url": it.get("url_final") or it["url"], "titulo": titulo.rstrip(". "),
            "paragrafos": pars, "primeira_infancia": ss._limpar(r.get("primeira_infancia") or ""),
            "clima": clima, "fmcsv": fmcsv, "marcas": marcas, "clientes": clientes, "documentos": docs,
            "da_equipe": bool(it["paragrafos_equipe"]), "_pos": it.get("_pos", 0), "_id": it.get("_id", ""),
            "falha": "", "aviso": ""}


# ─── Word ────────────────────────────────────────────────────────────────────
W = ss.W
R_HYPER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"


def _txt(el) -> str:
    return "".join(t.text or "" for t in el.iter(f"{W}t")).strip()


def _prototipos(doc) -> dict:
    corpo = doc.element.body
    filhos = list(corpo)
    tit = next(e for e in filhos if _txt(e).startswith("Síntese da Semana"))
    resto = filhos[filhos.index(tit) + 1:]
    ps = [e for e in resto if e.tag == f"{W}p" and _txt(e)]
    return {"titulo": tit, "data": ps[0], "secao": ps[1], "item": ps[2], "par": ps[3], "sub": ps[4],
            "tabela": next(e for e in resto if e.tag == f"{W}tbl")}


def _runs(p_el, partes: list[tuple[str, str | None]], doc, link_proprio: bool = False):
    """Troca o texto do parágrafo, mantendo o rPr do 1º run. Link sublinhado; azul só no corpo
    (o título do item já é vinho com sublinhado, como no modelo da equipe)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    r0 = next(iter(p_el.iter(f"{W}r")), None)
    rpr0 = copy.deepcopy(r0.find(f"{W}rPr")) if r0 is not None and r0.find(f"{W}rPr") is not None else OxmlElement("w:rPr")
    for x in rpr0.findall(qn("w:u")):
        rpr0.remove(x)
    for child in list(p_el):
        if child.tag != f"{W}pPr":
            p_el.remove(child)
    for texto, link in partes:
        if not texto:
            continue
        r = OxmlElement("w:r")
        rpr = copy.deepcopy(rpr0)
        if link:
            if not link_proprio:
                for x in rpr.findall(qn("w:color")):
                    rpr.remove(x)
                c = OxmlElement("w:color"); c.set(qn("w:val"), "1155CC"); rpr.append(c)  # noqa: E702
            u = OxmlElement("w:u"); u.set(qn("w:val"), "single"); rpr.append(u)  # noqa: E702
        r.append(rpr)
        t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve"); t.text = re.sub(r"\s*[\r\n]+\s*", " ", texto)  # noqa: E702
        r.append(t)
        if link:
            h = OxmlElement("w:hyperlink")
            h.set(qn("r:id"), doc.part.relate_to(link, R_HYPER, is_external=True))
            h.append(r)
            p_el.append(h)
        else:
            p_el.append(r)
    return p_el


def _partes_paragrafo(texto: str, docs: list[dict]) -> list[tuple[str, str | None]]:
    marcos = sorted((texto.find(d["nome"]), d) for d in docs if d["nome"] in texto)
    out, pos = [], 0
    for ini, d in marcos:
        if ini < pos:
            continue
        out += [(texto[pos:ini], None), (d["nome"], d["url"])]
        pos = ini + len(d["nome"])
    out.append((texto[pos:], None))
    return out


def paragrafos_do_cliente(item: dict, cliente: str) -> list[str]:
    pars = list(item["paragrafos"])
    if cliente == "FMCSV" and item.get("primeira_infancia") and item["primeira_infancia"] not in " ".join(pars):
        pars.append(item["primeira_infancia"])
    return pars


def gerar_docx(modelo: bytes, cliente: str, periodo: str, itens: list[dict], proposicoes: list[dict],
               andamento: list[dict] | None = None) -> bytes:
    import docx
    doc = docx.Document(io.BytesIO(modelo))
    P = _prototipos(doc)
    corpo = doc.element.body
    sect = corpo.find(f"{W}sectPr")
    novo = lambda k: copy.deepcopy(P[k])  # noqa: E731
    els = []
    tit = P["titulo"]
    ts = list(tit.iter(f"{W}t"))
    ts[-1].text = CLIENTES[cliente]["titulo"]
    els.append(_runs(novo("data"), [(periodo, None)], doc))
    for sec in SECOES:
        doses = [i for i in itens if i["secao"] == sec]
        if not doses:
            continue
        els.append(_runs(novo("secao"), [(sec, None)], doc))
        for it in doses:
            els.append(_runs(novo("item"), [(it["titulo"], it["url"] or None)], doc, link_proprio=True))
            for par in paragrafos_do_cliente(it, cliente):
                els.append(_runs(novo("par"), _partes_paragrafo(par, it["documentos"]), doc))
    if proposicoes:
        els.append(_runs(novo("sub"), [("NOVAS PROPOSIÇÕES", None)], doc))
        els.append(_tabela(P, novo, [[(p["proposicao"], p.get("link") or None), (p["ementa"], None), (p["autor"], None)]
                                     for p in proposicoes], None, doc))
    if andamento:
        els.append(_runs(novo("sub"), [("ANDAMENTO DAS DEMAIS PROPOSIÇÕES DE INTERESSE", None)], doc))
        els.append(_tabela(P, novo, [[(m["proposicao"], m.get("link") or None), (m["ementa"], None), (m["autor"], None),
                                      (m["situacao"], None)] for m in andamento],
                           ["PROPOSIÇÃO", "EMENTA", "AUTOR", "SITUAÇÃO"], doc))
    filhos = list(corpo)
    for child in filhos[filhos.index(tit) + 1:]:
        if child is not sect:
            corpo.remove(child)
    for el in els:
        sect.addprevious(el)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ─── Andamento das demais proposições (lista na aba "Acompanhadas Educação") ─
# Mesma lógica da saúde (ss.movimentacoes_semana, APIs abertas da Câmara e do Senado), com a lista
# de ISG, IU e FMCSV numa aba própria da planilha da Agenda, para a consulta da saúde não crescer.
ABA_ACOMP = "Acompanhadas Educação"
INTELIGOV = {"ISG": 3421, "IU": 3648, "FMCSV": 3416}  # cliente na Matriz de monitoramento

# Regra da equipe de educação (Bruna, 17/11/2026): entra movimentação importante, como designação
# de relatoria, apresentação do parecer, aprovação em comissão ou no plenário.
_IMPORTANTE = re.compile(
    r"designad[oa]\s+relator|designa[çc][ãa]o\s+d[oa]\s+relator|parecer|\bPRL|relat[óo]rio\s+do\s+relator|aprovad|\baprova\b|"
    r"aprova[çc][ãa]o|rejeitad|sancionad|san[çc][ãa]o|promulga|transformad[oa]\s+n[ao]\s+(lei|norma)|"
    r"remessa\s+ao\s+senado|encaminhando\s+o\s+projeto|remetid[oa]\s+[àa]\s+(c[âa]mara|san[çc][ãa]o)|vetad|\bveto\b",
    re.I)
# novidade de rotina: prazo, recebimento, despacho às comissões, apensação, proposição recém-apresentada
_ROTINA = re.compile(r"^(recebid|recebimento|encaminhad[oa] [àa] publica|publica[çc][ãa]o|aguardando|prazo|abertura do prazo|"
                     r"às comissões|apense|retirad[oa] de pauta|n[ãa]o foram apresentadas emendas)", re.I)


def importante(m: dict) -> bool:
    and_ = (m.get("andamento") or "").strip()
    and_ = and_.split('"', 1)[0]  # o que vem entre aspas é a ementa citada, não o andamento
    if _ROTINA.search(and_):
        return False
    # vale para a principal, que aparece por conta própria; expediente e retirada de pauta são rotina
    if re.search(r"ao qual esta proposi[çc][ãa]o est[áa] apensad|em virtude da altera[çc][ãa]o do regime|parecer recebido para publica|retirada de pauta|"
                 r"relator[a]? da reda[çc][ãa]o final", and_, re.I):
        return False
    if re.match(r"apresenta[çc][ãa]o\s+d[oa]\s+[A-Z]{2,6}\s+n\.", and_, re.I) and not re.search(r"PRL|parecer", and_, re.I):
        return False  # proposição nova: vai em Novas proposições
    return bool(_IMPORTANTE.search(and_))


def andamentos(acomp: list[dict], ini: dt.date, fim: dt.date, progresso=None) -> dict:
    """Cliente -> movimentações da semana, cada uma com "importante" (regra da equipe).

    Se na semana houve uma movimentação importante e depois só rotina (ex.: aprovado na CFT e
    recebido na CCJC), vale a importante: é ela que vai para a síntese."""
    out = ss.movimentacoes_semana(acomp, ini, fim, progresso=progresso)
    for c, ms in out.items():
        if not isinstance(ms, list):
            continue
        for m in ms:
            imps = [h for h in m.get("historico") or [] if importante(h)]
            if imps and not importante(m):
                m.update(imps[-1])
            m["importante"] = bool(imps) or importante(m)
    return out


def acrescentar(ws, linhas: list[tuple[str, str, str, str]], atuais: list[dict], hoje: str, origem: str) -> int:
    """Põe na aba (cliente, proposição, casa, id) que ainda não estão lá. Casa/ID vazios: procura nas APIs."""
    tem = {(a["Cliente"], a["Proposição"].strip().upper()) for a in atuais}
    novas = []
    for cli, prop, casa, id_ in linhas:
        if (cli, prop.strip().upper()) in tem:
            continue
        if not id_:
            casa, id_ = ss.casa_e_id(prop)
        tem.add((cli, prop.strip().upper()))
        novas.append([cli, prop.strip(), casa, id_, origem, hoje])
    if novas:
        ws.append_rows(novas, value_input_option="RAW")
    return len(novas)


def _tabela(P, novo, linhas: list[list[tuple[str, str | None]]], cab: list[str] | None, doc):
    """Tabela do modelo (3 colunas) com as linhas dadas; com `cab` de 4 nomes, ganha a 4ª coluna."""
    tbl = novo("tabela")
    trs = tbl.findall(f"{W}tr")
    modelo_linha = trs[1]
    for tr in trs[1:]:
        tbl.remove(tr)
    for jc in modelo_linha.iter(f"{W}jc"):  # justificado em coluna estreita abre buracos entre as palavras
        if jc.get(f"{W}val") == "both":
            jc.set(f"{W}val", "left")
    if cab and len(cab) == 4:
        grid = tbl.find(f"{W}tblGrid")
        for mud in grid.findall(f"{W}tblGridChange"):  # grade antiga de 3 colunas guardada pelo Docs
            grid.remove(mud)
        for ind in [*tbl.iter(f"{W}ind"), *modelo_linha.iter(f"{W}ind")]:  # recuo negativo do modelo: texto passa da borda
            for lado in ("right", "end"):
                if ind.get(f"{W}{lado}"):
                    ind.set(f"{W}{lado}", "0")
        cols = grid.findall(f"{W}gridCol")
        total = sum(int(c.get(f"{W}w")) for c in cols)
        grid.append(copy.deepcopy(cols[-1]))
        larg = [int(total * f) for f in (0.19, 0.37, 0.18, 0.26)]
        for c, w in zip(grid.findall(f"{W}gridCol"), larg):
            c.set(f"{W}w", str(w))
        for tr in (trs[0], modelo_linha):
            tcs = tr.findall(f"{W}tc")
            tcs[-1].addnext(copy.deepcopy(tcs[-1]))
            for tc, w in zip(tr.findall(f"{W}tc"), larg):
                tw = tc.find(f"{W}tcPr/{W}tcW")
                if tw is not None:
                    tw.set(f"{W}w", str(w))
                    tw.set(f"{W}type", "dxa")
        for tc, nome in zip(trs[0].findall(f"{W}tc"), cab):
            pps = tc.findall(f"{W}p")
            for extra in pps[1:]:
                tc.remove(extra)
            _runs(pps[0], [(nome, None)], doc)
    for valores in linhas:
        tr = copy.deepcopy(modelo_linha)
        for tc, (txt, link) in zip(tr.findall(f"{W}tc"), valores):
            pps = tc.findall(f"{W}p")
            for extra in pps[1:]:
                tc.remove(extra)
            _runs(pps[0], [(txt or "-", link)], doc)
        tbl.append(tr)
    return tbl


# ─── Email (Wix: 1 notícia por eixo + o PDF da síntese completa) ─────────────
def html_email(cliente: str, periodo: str, destaques: dict[str, dict]) -> str:
    esc = _html.escape
    h3 = "font-size:15px;color:#192D4E;margin:16px 0 8px;font-family:Montserrat,Arial,sans-serif;"
    partes = [f"<p style='font-size:14px;line-height:1.5;margin:0 0 14px 0;'><b>Síntese da Semana - "
              f"{esc(CLIENTES[cliente]['titulo'])}</b><br>{esc(periodo)}</p>"]
    for eixo in EIXOS_EMAIL:
        it = destaques.get(eixo)
        if not it:
            continue
        partes.append(f"<h3 style='{h3}'>{esc(eixo.capitalize() if eixo != 'NOTÍCIAS' else 'Notícias gerais')}</h3>")
        partes.append(f'<p style="margin:0 0 6px;line-height:1.5;"><a href="{esc(it["url"])}" '
                      f'style="color:#97304E;text-decoration:underline;"><b>{esc(it["titulo"])}</b></a></p>')
        for par in paragrafos_do_cliente(it, cliente):
            corpo = "".join(f'<a href="{esc(u)}" style="color:#0056b3;text-decoration:underline;">{esc(t)}</a>' if u else esc(t)
                            for t, u in _partes_paragrafo(par, it["documentos"]))
            partes.append(f"<p style='margin:0 0 10px;line-height:1.5;'>{corpo}</p>")
    partes.append("<p style='margin:18px 0 0;line-height:1.5;'><b>A síntese completa da semana está no PDF anexo.</b></p>")
    return ("<html><head><meta charset='utf-8'></head><body style='font-family:Montserrat,Arial,sans-serif;"
            "font-size:14px;line-height:1.5;color:#222222;'>" + "\n".join(partes) + "</body></html>")
