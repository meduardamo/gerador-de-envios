"""Síntese da Semana (saúde): da Divisão semanal ao Word por cliente.

Entrada: o doc "Divisão semanal - Saúde" baixado em .docx ou .pdf (links agrupados por
tema, tabela NOVAS PROPOSIÇÕES com a coluna Cliente). Cada notícia é baixada e lida;
o Gemini faz uma chamada por cliente, só com a fatia da matriz temática daquele cliente,
e devolve os bullets. Movimentações da semana: proposições acompanhadas (aba
"Acompanhadas") consultadas nas APIs da Câmara e do Senado, com o XLS da Matriz do
Inteligov como complemento. DOU: aba do cliente na planilha da raspagem.

Saída: um .docx por cliente no modelo das sínteses enviadas (UNFPA para todos, IDEC por
área) e o corpo do email em HTML para colar no Wix.
"""
from __future__ import annotations

import copy
import datetime as dt
import html as _html
import io
import json
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import requests

# ─── Clientes e matriz temática ──────────────────────────────────────────────
# Matriz do último prompt do NotebookLM (Mayara, 22/10/2026), uma linha por tema.
MATRIZ_TXT = """
Saúde mental: Cactus, IEPS, Umane, Vital.
Saúde mental de crianças e adolescentes: Cactus, Infinis.
Saúde mental de meninas e mulheres: Cactus.
Saúde mental nas escolas, Programa Saúde na Escola e Política Nacional de Atenção Psicossocial nas Comunidades Escolares: Cactus.
Saúde mental nas eleições e programas de governo: Cactus.
Participação e protagonismo juvenil: Cactus, Infinis.
Bullying: Cactus.
Bets e saúde mental: Cactus, IEPS, Umane, Vital.
Publicidade de bets: IEPS, Vital.
Comunidades terapêuticas: Cactus.
Casamento infantil, união precoce e idade núbil: UNFPA.
Reforma do Código Civil: UNFPA, Coletivo.
Direitos de crianças e adolescentes e proteção integral: UNFPA, Infinis, IEPS, Cactus.
Direitos das mulheres: UNFPA, Coletivo, Vital.
Direitos sexuais e reprodutivos: UNFPA, Coletivo.
Saúde sexual e reprodutiva: UNFPA, Coletivo.
Gravidez na adolescência: UNFPA.
Planejamento reprodutivo e educação sexual: UNFPA.
Violência sexual contra meninas e adolescentes: UNFPA, Coletivo, Infinis.
Aborto, interrupção legal da gestação e autodeterminação reprodutiva: Coletivo.
Campanha Criança Não é Mãe, gravidez infantil e maternidade forçada: Coletivo.
Violência contra mulheres e Lei Maria da Penha: Coletivo, Vital.
Alienação parental: Coletivo.
Laicidade do Estado: Coletivo.
Representatividade feminina: Coletivo.
Redução da maioridade penal: UNFPA, Infinis.
ECA Digital e proteção de crianças e adolescentes no ambiente digital: Cactus, IDEC, IEPS, Infinis, Vital.
Regulamentação e responsabilização de plataformas, proteção de dados e direitos digitais: IDEC.
Telemarketing abusivo: IDEC.
Medicamentos e precificação de medicamentos: IDEC.
Infraestruturas públicas digitais, Pix e gov.br: IDEC.
Democratização do acesso à internet: IDEC.
SUS, fortalecimento, regionalização, gestão, planejamento e financiamento: IEPS, Umane.
Atenção Primária à Saúde: IEPS, Umane.
Emendas parlamentares na saúde: IEPS.
Qualidade dos serviços e segurança do paciente: IEPS, Umane.
Força de trabalho, formação médica, residência, Profimed e Enamed: IEPS, ASBAI.
Acesso à atenção especializada e Agora Tem Especialistas: ASBAI.
Saúde digital, dados, informação e inteligência em saúde: IDEC, IEPS, Umane, Vital.
Equidade, desigualdades e acesso à saúde: IEPS, Umane.
Avaliação de políticas públicas e saúde baseada em evidências: IEPS, Umane.
Saúde em áreas remotas: Umane.
Alergia e imunologia, imunodeficiências e anafilaxia: ASBAI.
Medicamentos, tratamentos e tecnologias para doenças alérgicas e imunológicas no SUS: ASBAI.
Caneta de adrenalina autoinjetável no SUS: ASBAI.
Notificação e vigilância de anafilaxia: ASBAI.
Formação e provimento de especialistas em alergia e imunologia: ASBAI.
Asma, rinite, dermatite atópica e alergias alimentares: ASBAI.
Alimentação adequada e saudável: IDEC, Umane, Vital, Desiderata.
Alimentação escolar: IDEC, Desiderata.
Obesidade infantil e adolescente: Umane, Desiderata.
Prevenção da obesidade e promoção da atividade física: Umane, Desiderata.
Ambientes alimentares saudáveis: Desiderata.
Ultraprocessados: IDEC, Vital, Desiderata.
Rotulagem nutricional: IDEC, Desiderata.
Publicidade de alimentos para crianças e adolescentes: Desiderata, Vital, IDEC.
Cesta básica, Programa Alimenta Cidades e transgênicos: IDEC.
Tabagismo, álcool e produtos nocivos à saúde: Vital, Umane.
DCNT e prevenção e controle: Vital, Umane.
Determinantes comerciais da saúde: Vital.
Imposto Seletivo, reforma tributária e tributação de produtos nocivos: Vital.
Energia e sustentabilidade, tarifa de energia, CCC, geração distribuída e tarifa social: IDEC.
Usinas a carvão e transição energética: IDEC.
Greenwashing, economia circular e plásticos: IDEC.
Agrotóxicos: IDEC.
Datacenters e Redata: IDEC.
Minerais críticos: IDEC.
Mudanças climáticas, ondas de calor, PNAR Brasil, Plano Clima 2024–2035 e saúde ambiental: Vital.
Chumbo e contaminação ambiental: Vital.
Inteligência artificial e saúde: Vital, IDEC, Umane.
Insegurança alimentar: Infinis, IDEC.
Primeira infância: Infinis, Cactus, UNFPA.
Violência psicológica, física e sexual contra crianças e adolescentes: Infinis, UNFPA.
Exploração sexual de crianças e adolescentes: Infinis, UNFPA.
Saúde mental e física de crianças e adolescentes indígenas e políticas para essa população: Infinis.
Plano Nacional de Enfrentamento da Violência contra Crianças e Adolescentes: Infinis.
Mudanças no ECA: Infinis.
Orçamento e financiamento de políticas para primeira infância, crianças e adolescentes: Infinis.
""".strip()

# chave curta da matriz -> nome no título do Word, código do cliente no Inteligov, aba do DOU
CLIENTES = {
    "Cactus":     {"titulo": "Cactus", "inteligov": 3428, "dou": "Cactus"},
    "UNFPA":      {"titulo": "UNFPA", "inteligov": 3583, "dou": "UNFPA"},
    "IDEC":       {"titulo": "IDEC", "inteligov": 3426, "dou": "IDEC"},
    "IEPS":       {"titulo": "IEPS", "inteligov": 3424, "dou": "IEPS"},
    "Vital":      {"titulo": "Vital Strategies", "inteligov": 3423, "dou": "Vital Strategies"},
    "Umane":      {"titulo": "Umane", "inteligov": 3425, "dou": "Umane"},
    "Infinis":    {"titulo": "Infinis", "inteligov": 3534, "dou": "Infinis"},
    "Coletivo":   {"titulo": "Coletivo Feminista", "inteligov": 3528, "dou": "Coletivo Feminista"},
    "ASBAI":      {"titulo": "ASBAI", "inteligov": 3540, "dou": "ASBAI", "quinzenal": True},
    "Desiderata": {"titulo": "Instituto Desiderata", "inteligov": None, "dou": "Desiderata", "quinzenal": True},
}

# IDEC não usa Executivo/Legislativo: o corpo vai por área (síntese de 26 a 30/10/2026)
AREAS_IDEC = ["Defesa do Consumidor", "Alimentação Adequada e Saudável", "Energia e Sustentabilidade",
              "Saúde", "Telecomunicações e Direitos Digitais", "Consumo Sustentável"]
SECOES_PADRAO = ["Executivo", "Legislativo"]

# como a coluna Cliente da tabela de proposições escreve cada um
_APELIDOS = {"cactus": "Cactus", "unfpa": "UNFPA", "idec": "IDEC", "ieps": "IEPS", "vital": "Vital",
             "vital strategies": "Vital", "umane": "Umane", "infinis": "Infinis", "coletivo": "Coletivo",
             "coletivo feminista": "Coletivo", "asbai": "ASBAI", "desiderata": "Desiderata",
             "instituto desiderata": "Desiderata"}


def temas_do_cliente(cliente: str) -> list[str]:
    out = []
    for linha in MATRIZ_TXT.splitlines():
        tema, _, quem = linha.rpartition(":")
        nomes = [n.strip(" .") for n in quem.split(",")]
        if cliente in nomes:
            out.append(tema.strip())
    return out


def secoes_do_cliente(cliente: str) -> list[str]:
    return AREAS_IDEC if cliente == "IDEC" else SECOES_PADRAO


def cliente_da_celula(txt: str) -> list[tuple[str, bool]]:
    """'IDEC, IEPS, Vital?' -> [('IDEC', False), ('IEPS', False), ('Vital', True)] (True = com dúvida)."""
    out = []
    for parte in re.split(r"[,;/\n]| e ", txt or ""):
        p = parte.strip()
        if not p:
            continue
        duvida = "?" in p
        chave = _APELIDOS.get(re.sub(r"[?.()*]", "", p).strip().lower())
        if chave and chave not in [c for c, _ in out]:
            out.append((chave, duvida))
    return out


# ─── Período ─────────────────────────────────────────────────────────────────
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


def periodo_extenso(ini: dt.date, fim: dt.date) -> str:
    if ini.month == fim.month:
        return f"{ini.day} a {fim.day} de {MESES[fim.month - 1]} de {fim.year}"
    return f"{ini.day} de {MESES[ini.month - 1]} a {fim.day} de {MESES[fim.month - 1]} de {fim.year}"


def nome_arquivo(cliente: str, ini: dt.date, fim: dt.date, sufixo: str = "") -> str:
    return f"Síntese da Semana - {CLIENTES[cliente]['titulo']} ({ini:%d.%m} a {fim:%d.%m.%Y}){sufixo}.docx"


# ─── Leitura da Divisão semanal ──────────────────────────────────────────────
# Seções que não são notícia: lista de sites, portais, modelo, audiências
_IGNORAR_SECAO = re.compile(r"lista de sites|portais de not|^modelo|audi[êe]ncias p", re.I)
_FIM_NOTICIAS = re.compile(r"^\s*NOVAS PROPOSI", re.I)
_URL_HOME = re.compile(r"^https?://[^/]+/?([a-z\-]+/?){0,3}$", re.I)


def _e_noticia(url: str) -> bool:
    if not url.startswith("http") or "drive.google.com" in url or "docs.google.com" in url:
        return False
    if "fichadetramitacao" in url or "in.gov.br" in url:
        return False
    caminho = re.sub(r"^https?://[^/]+", "", url).strip("/")
    return len(caminho) > 25  # home de portal ("gov.br/saude/pt-br") fica de fora


def _secao_limpa(txt: str) -> str:
    t = re.sub(r"\s+", " ", txt.replace("\u200b", "")).strip(" .:")
    return t


def ler_divisao(dados: bytes, nome: str) -> dict:
    """Notícias com a seção (tema) de onde vieram e a tabela de novas proposições."""
    if nome.lower().endswith(".docx"):
        return _ler_divisao_docx(dados)
    return _ler_divisao_pdf(dados)


def _ler_divisao_docx(dados: bytes) -> dict:
    import docx
    d = docx.Document(io.BytesIO(dados))
    noticias, secao, ativo = [], "", False
    body = d.element.body
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    rels = d.part.rels
    for el in body.iterchildren():
        if el.tag != W + "p":
            continue
        texto = "".join(t.text or "" for t in el.iter(W + "t")).strip()
        urls = []
        for h in el.iter(W + "hyperlink"):
            rid = h.get(R + "id")
            if rid and rid in rels and rels[rid].is_external:
                urls.append(rels[rid].target_ref)
        urls += re.findall(r"https?://\S+", texto)
        if _FIM_NOTICIAS.match(texto):
            break
        if texto.lower().startswith("modelo"):
            ativo = True
            continue
        if not urls and texto and len(texto) < 120:
            secao = _secao_limpa(texto)
            continue
        if ativo and not _IGNORAR_SECAO.search(secao):
            for u in urls:
                if _e_noticia(u):
                    noticias.append({"secao": secao, "url": u.strip()})
    props = []
    for t in d.tables:
        cab = [c.text.strip().upper() for c in t.rows[0].cells]
        if not any("PROPOSI" in c for c in cab) or not any("CLIENTE" in c for c in cab):
            continue
        idx = {k: next((i for i, c in enumerate(cab) if k in c), None)
               for k in ("PROPOSI", "EMENTA", "AUTOR", "CLIENTE")}
        for row in t.rows[1:]:
            cel = [c.text.strip() for c in row.cells]
            pega = lambda k: cel[idx[k]] if idx[k] is not None and idx[k] < len(cel) else ""  # noqa: E731
            link = ""
            for h in row.cells[idx["PROPOSI"]]._tc.iter(W + "hyperlink"):
                rid = h.get(R + "id")
                if rid in rels:
                    link = rels[rid].target_ref
            if not cel[idx["PROPOSI"]]:
                continue
            m_p = _PROP.match(cel[idx["PROPOSI"]])
            props.append({"proposicao": f"{m_p.group(1)} {m_p.group(2)}/{m_p.group(3)}" if m_p else cel[idx["PROPOSI"]],
                          "ementa": pega("EMENTA"), "autor": pega("AUTOR"), "link": link,
                          "clientes": cliente_da_celula(pega("CLIENTE"))})
    return {"noticias": _dedup(noticias), "proposicoes": props}


def _ler_divisao_pdf(dados: bytes) -> dict:
    """PDF baixado do Docs: o texto dá as seções e os links vêm das anotações da página."""
    import fitz
    doc = fitz.open(stream=dados, filetype="pdf")
    eventos = []  # (página, y, tipo, valor)
    for pno, pg in enumerate(doc):
        for b in pg.get_text("blocks"):
            for linha in b[4].splitlines():
                if linha.strip():
                    eventos.append((pno, b[1], "t", linha.strip()))
        for ln in pg.get_links():
            if ln.get("uri"):
                eventos.append((pno, ln["from"].y0, "u", ln["uri"]))
    eventos.sort(key=lambda e: (e[0], e[1], e[2] == "u"))
    noticias, secao, ativo, vistos = [], "", False, set()
    for _, _, tipo, val in eventos:
        if tipo == "t":
            if _FIM_NOTICIAS.match(val):
                break
            if val.lower().startswith("modelo"):
                ativo = True
                continue
            limpo = _secao_limpa(val)
            if (limpo and not re.search(r"https?://|www\.|\.br/|\.gov|-$", val) and len(limpo) < 120
                    and not limpo.startswith("•") and not _pedaco_de_url(limpo)):
                secao = limpo
        elif ativo and not _IGNORAR_SECAO.search(secao) and _e_noticia(val) and val not in vistos:
            vistos.add(val)
            noticias.append({"secao": secao, "url": val})
    props = [{**r, "clientes": cliente_da_celula(r.pop("cliente_txt"))} for r in tabela_proposicoes_pdf(doc)]
    return {"noticias": _dedup(noticias), "proposicoes": props}


_PROP = re.compile(r"^([A-Z]{2,6})\s*(\d+)\s*/\s*(\d{4})")


def _reguas(pg, larg_min):
    import fitz as _fitz
    ys = set()
    for d in pg.get_drawings():
        for it in d["items"]:
            r = _fitz.Rect(it[1], it[2]) if it[0] == "l" else (it[1] if it[0] == "re" else None)
            if r is not None and r.height < 2 and r.width >= larg_min:
                ys.add(round(r.y0, 1))
    return sorted(ys)


def _texto(words, x0, x1, y0, y1):
    ws = [w for w in words if x0 <= w[0] < x1 and y0 < (w[1] + w[3]) / 2 < y1]
    ws.sort(key=lambda w: (round(w[1]), w[0]))
    return re.sub(r"\s+", " ", " ".join(w[4] for w in ws)).strip()


def tabela_proposicoes_pdf(doc):
    """Tabela NOVAS PROPOSIÇÕES do PDF: colunas da 1ª página da tabela, linhas pelas réguas horizontais."""
    import fitz as _fitz
    # cabeçalho: a tabela (detectada na 1ª página dela) cuja 1ª linha tem PROPOSIÇÃO e CLIENTE
    xs = None
    for p_cab, pg in enumerate(doc):
        if "PROPOSI" not in pg.get_text().upper():
            continue
        for t in pg.find_tables().tables:
            cab = [(x or "").upper() for x in t.extract()[0]]
            if any("PROPOSI" in c for c in cab) and any("CLIENTE" in c for c in cab) and len(cab) == 4:
                xs = [c[0] for c in t.rows[0].cells] + [t.bbox[2]]
                y_cab = t.rows[0].bbox[3]
                break
        if xs:
            break
    if not xs:
        return []
    larg = (xs[-1] - xs[0]) * 0.9
    out, comecou = [], False
    for pno in range(p_cab, doc.page_count):
        pg = doc[pno]
        words = pg.get_text("words")
        links = [l for l in pg.get_links() if l.get("uri")]
        ys = [y for y in _reguas(pg, larg) if pno != p_cab or y > y_cab]
        for y0, y1 in zip(ys, ys[1:]):
            cel = [_texto(words, xs[i], xs[i + 1], y0, y1) for i in range(4)]
            m = _PROP.match(cel[0])
            if not m:
                if comecou:
                    return out
                continue
            comecou = True
            area = _fitz.Rect(xs[0], y0, xs[1], y1)
            link = next((l["uri"] for l in links if area.intersects(l["from"])), "")
            out.append({"proposicao": f"{m.group(1)} {m.group(2)}/{m.group(3)}", "ementa": cel[1],
                        "autor": cel[2], "cliente_txt": cel[3], "link": link})
    return out


def _pedaco_de_url(t: str) -> bool:
    """Linha quebrada de um link longo ('pauta-e-vai-aguardar-camara /')."""
    t = t.strip(" /")
    return " " not in t and bool(re.search(r"[-/_.=?]", t))


def _dedup(noticias: list[dict]) -> list[dict]:
    vistos, out = set(), []
    for n in noticias:
        chave = n["url"].split("#")[0].rstrip("/")
        if chave in vistos:
            continue
        vistos.add(chave)
        out.append(n)
    return out


# ─── Download das notícias ───────────────────────────────────────────────────
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def baixar_noticia(url: str) -> dict:
    import trafilatura
    out = {"url": url, "titulo": "", "data": "", "texto": "", "lide": "", "erro": ""}
    try:
        r = requests.get(url, headers=UA, timeout=25)
        r.raise_for_status()
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        meta = trafilatura.bare_extraction(r.text, url=url, with_metadata=True)
        meta = meta.as_dict() if hasattr(meta, "as_dict") else (meta or {})
        md = trafilatura.extract(r.text, url=url, output_format="markdown", include_links=True) or ""
        out["titulo"] = (meta.get("title") or "").strip()
        out["data"] = meta.get("date") or ""
        out["texto"] = md[:9000]
        corpo = (meta.get("text") or "").strip()
        if corpo.startswith(out["titulo"]):
            corpo = corpo[len(out["titulo"]):].strip()
        out["lide"] = _lide(corpo)
        if len(corpo) < 200:
            out["erro"] = "texto curto (página pode exigir login ou ser só índice)"
    except Exception as e:  # noqa: BLE001
        out["erro"] = f"{type(e).__name__}: {e}"[:200]
    return out


def _lide(corpo: str) -> str:
    """Primeiro parágrafo de verdade (pula linha de data/autor/foto)."""
    for par in corpo.split("\n"):
        p = par.strip()
        if len(p) > 120 and not re.match(r"^(\d{2}/\d{2}/\d{4}|por |foto)", p, re.I):
            return p
    return corpo[:400]


def baixar_todas(noticias: list[dict], workers: int = 8) -> list[dict]:
    with ThreadPoolExecutor(workers) as ex:
        baixadas = list(ex.map(lambda n: baixar_noticia(n["url"]), noticias))
    return [{**n, **b} for n, b in zip(noticias, baixadas)]


# ─── Clipping (título + lide da própria matéria, sem reescrever) ─────────────
def secao_de_clipping(secao: str) -> str | None:
    """'clipping unfpa' -> 'UNFPA'."""
    m = re.match(r"^\s*clipping\b[:\s–-]*(.*)$", secao or "", re.I)
    if not m:
        return None
    resto = m.group(1).strip()
    resto = re.sub(r"^(?:da|do|de)\s+", "", resto, flags=re.I)
    resto = re.sub(r"[?.()*]", "", resto).strip().lower()
    return _APELIDOS.get(resto)


def clipping_por_cliente(noticias: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for n in noticias:
        cli = secao_de_clipping(n.get("secao", ""))
        if cli and n.get("titulo"):
            out.setdefault(cli, []).append({"titulo": n["titulo"], "lide": n.get("lide", ""), "url": n["url"]})
    return out


# ─── Bullets pelo Gemini ─────────────────────────────────────────────────────
REGRAS = """
Você elabora a síntese semanal de notícias de um cliente de uma consultoria de relações governamentais e advocacy.

Use exclusivamente as notícias fornecidas abaixo. Não invente, não complemente com fontes externas, não faça inferências não sustentadas pelo texto.

SELEÇÃO
- Os temas do cliente abaixo são critério de seleção e de exclusão, não justificativa para forçar enquadramento.
- Só inclua uma notícia quando a relação com um dos temas for direta, substantiva e evidente no conteúdo da própria notícia. Não inclua por associação genérica ou indireta, consequência potencial, público afetado ou conexão ampla com saúde, políticas públicas, medicamentos ou tecnologia.
- Não use um tema amplo para puxar notícia de outro assunto.
- Na dúvida, exclua. É preferível deixar de fora uma notícia marginal a incluir uma cujo enquadramento dependa de interpretação.
- Não crie bullet apenas pela presença de uma palavra-chave.
- A seção do documento interno de onde a notícia veio é só uma pista; quem decide é o conteúdo (salvo exceção expressa de Conjuntura Política descrita abaixo).

FORMATO DE CADA BULLET
- "titulo": uma frase no presente que contextualiza o fato (ex.: "Senacon determina suspensão de novas revendas de ingressos por cinco plataformas."). Começa pelo fato, nunca por "a notícia destaca", "a matéria aborda" e equivalentes.
- "texto": 1 a 3 frases seguintes com fatos, desdobramentos, posicionamentos ou medidas. O que já aconteceu vai no pretérito perfeito (aprovou, reuniu, afirmou); presente só para o que segue valendo (a norma estabelece, o prazo vai até).
- Mencione, quando relevante, órgãos, instituições, parlamentares, autoridades, projetos de lei, decretos, portarias, programas e medidas. Use as siglas dos órgãos. Cite parlamentar como Nome (PARTIDO/UF).
- "documentos": documentos citados na notícia e com link no próprio texto (lei, decreto, portaria, resolução, pesquisa, estudo, nota técnica, cartilha, relatório, consulta pública). Use só links que aparecem no texto da notícia, com o nome do documento como aparece no bullet. Não invente link nem crie link para pessoa ou instituição.

FIDELIDADE
- Não acrescente conclusões, relações causais, impactos, implicações, recomendações ou avaliações que não estejam explícitos na notícia. Nada de "a medida busca", "o que pode", "reforça a importância", "é relevante para".
- Limite-se ao que aconteceu, quem participou e o que foi decidido, proposto, anunciado ou discutido, com os dados da notícia.
- Posições divergentes vão atribuídas a quem as defende.
- Preserve nomes, cargos, números e datas.

REDAÇÃO
- Linguagem objetiva, clara e profissional.
- Proibido: gerúndio, o verbo "restou", "junto a", travessão (— ou –).
- Evite "para que + verbo"; prefira o infinitivo.
- Datas sem zero à esquerda: 7/3/2026.
- Sem adjetivos desnecessários, opiniões ou repetição mecânica entre bullets.

PRIORIDADE (quando houver muitas): 1. mudanças legislativas e regulatórias; 2. decisões e medidas do Executivo, Legislativo e Judiciário; 3. políticas, programas e regulamentações; 4. movimentações no Congresso; 5. dados, pesquisas e evidências; 6. declarações de autoridades com efeito sobre a agenda; 7. demais. A prioridade não autoriza incluir notícia sem relação direta.
""".strip()


def montar_prompt(cliente: str, noticias: list[dict]) -> str:
    temas = "\n".join(f"- {t}" for t in temas_do_cliente(cliente))
    secoes = secoes_do_cliente(cliente)
    if cliente == "IDEC":
        regra_secao = ("Classifique cada bullet em UMA destas áreas do IDEC: " + "; ".join(secoes) + ".")
        regra_conjuntura = (
            "CONJUNTURA POLÍTICA (IDEC):\n"
            "- Notícias gerais de conjuntura política (ex.: CÂMARA/SENADO/EXECUTIVO/JUDICIÁRIO) "
            "NÃO devem ser incluídas para o IDEC, a menos que tratem diretamente de uma das áreas temáticas do IDEC listadas acima."
        )
    else:
        regra_secao = ('Classifique cada bullet em "Executivo" (governo, ministérios, agências, órgãos de controle, '
                       'Judiciário, conselhos, organismos internacionais, eventos) ou "Legislativo" '
                       '(Câmara, Senado, comissões, projetos de lei, parlamentares).')
        regra_conjuntura = (
            "CONJUNTURA POLÍTICA (TODOS EXCETO IDEC):\n"
            "- Notícias cuja 'Seção no documento interno' for de conjuntura política geral "
            "(CÂMARA/SENADO/EXECUTIVO/JUDICIÁRIO ou similar) são de interesse geral e DEVEM ser incluídas para este cliente, "
            "mesmo sem relação direta com os temas específicos de saúde acima.\n"
            "- Classifique essas notícias em 'Executivo' ou 'Legislativo' conforme o poder envolvido, "
            "e no campo 'tema' use 'Conjuntura Política'."
        )
    blocos = []
    for i, n in enumerate(noticias, 1):
        blocos.append(f"### NOTÍCIA {i}\nURL: {n['url']}\nSeção no documento interno: {n.get('secao', '')}\n"
                      f"Data: {n.get('data', '')}\nTítulo: {n.get('titulo', '')}\n\n{n.get('texto', '')}")
    return f"""{REGRAS}

CLIENTE: {CLIENTES[cliente]['titulo']}
TEMAS DO CLIENTE (só estes contam):
{temas}

SEÇÃO: {regra_secao}

{regra_conjuntura}

Responda SOMENTE com JSON, sem comentários, no formato:
{{"bullets": [{{"noticia": <número da notícia>, "secao": "<seção>", "tema": "<tema da lista acima ou 'Conjuntura Política'>", "titulo": "...", "texto": "...", "documentos": [{{"nome": "...", "url": "..."}}]}}]}}
Se nenhuma notícia tiver relação direta, responda {{"bullets": []}}.

NOTÍCIAS DA SEMANA:

""" + "\n\n".join(blocos)


_PROIBIDOS = [(re.compile(r"(\d)\s*[—–]\s*(\d)"), r"\1 a \2"),  # 2020–2024 -> 2020 a 2024
              (re.compile(r"\s*[—–]\s*"), ", "), (re.compile(r"\bjunto a(o|os|as)?\b", re.I), "com")]


def _limpar(txt: str) -> str:
    t = (txt or "").strip()
    for rx, rep in _PROIBIDOS:
        t = rx.sub(rep, t)
    # data com zero à esquerda: 07/03/2026 -> 7/3/2026
    # parlamentar como (PARTIDO/UF), nunca com hífen
    t = re.sub(r"\(\s*([A-Za-zÀ-ú]+(?: [A-Za-zÀ-ú]+)*)\s*[-–]\s*([A-Z]{2})\s*\)", r"(\1/\2)", t)
    t = re.sub(r"\b0(\d)/(\d{1,2})/(\d{4})\b", r"\1/\2/\3", t)
    t = re.sub(r"\b(\d{1,2})/0(\d)/(\d{4})\b", r"\1/\2/\3", t)
    return re.sub(r"\s{2,}", " ", t)


def _json_da_resposta(texto: str | None) -> list:
    """Lista de bullets da resposta, aceitando cerca de código, texto em volta e lista solta."""
    bruto = re.sub(r"^```(?:json)?|```$", "", (texto or "").strip()).strip()
    if not bruto:
        return []
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", bruto, re.S)
        if not m:
            if bruto.startswith(("{", "[")):
                raise ValueError("o Gemini devolveu JSON incompleto; rode de novo") from None
            raise ValueError("o Gemini não devolveu JSON") from None
        try:
            dados = json.loads(m.group(0))
        except json.JSONDecodeError:
            raise ValueError("o Gemini devolveu JSON incompleto; rode de novo") from None
    if isinstance(dados, dict):
        dados = dados.get("bullets")
    return dados if isinstance(dados, list) else []


def gerar_bullets(client, modelo: str, cliente: str, noticias: list[dict]) -> list[dict]:
    from google.genai import types
    validas = [n for n in noticias if n.get("texto") and not secao_de_clipping(n.get("secao", ""))]
    if not validas:
        return []
    prompt = montar_prompt(cliente, validas)
    for tentativa in range(2):  # 429/503 do Gemini costumam passar na segunda
        try:
            resp = client.models.generate_content(
                model=modelo, contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"))
            break
        except Exception as e:  # noqa: BLE001
            if tentativa == 1 or not re.search(r"429|500|503|UNAVAILABLE|RESOURCE_EXHAUSTED|DEADLINE", str(e)):
                raise
            time.sleep(15)
    dados = _json_da_resposta(resp.text)
    secoes = secoes_do_cliente(cliente)
    out = []
    for b in dados:
        if not isinstance(b, dict):
            continue
        try:
            i = int(b["noticia"])
        except (KeyError, ValueError, TypeError):
            continue
        if not 1 <= i <= len(validas):  # 0 ou negativo pegaria a notícia errada pelo fim da lista
            continue
        n = validas[i - 1]
        sec = b.get("secao") if b.get("secao") in secoes else secoes[0]
        texto_fonte = n.get("texto", "")
        docs = [d for d in (b.get("documentos") if isinstance(b.get("documentos"), list) else [])
                if isinstance(d, dict) and d.get("url") and d.get("nome")
                and d["url"] in texto_fonte]  # link tem de estar na notícia
        out.append({"url": n["url"], "secao": sec, "tema": b.get("tema") or "",
                    "titulo": _limpar(b.get("titulo") or ""), "texto": _limpar(b.get("texto") or ""),
                    "documentos": docs, "fonte_titulo": n.get("titulo", "")})
    ordem = {s: i for i, s in enumerate(secoes)}
    out.sort(key=lambda b: ordem.get(b["secao"], 99))
    return out


# ─── Movimentações (proposições acompanhadas + APIs da Câmara e do Senado) ────
# A lista de acompanhadas fica na aba "Acompanhadas" da planilha da Agenda (veio da
# Matriz do Inteligov em 5/11/2026; as novas proposições da Divisão entram sozinhas).
# Toda semana a tramitação de cada uma é consultada nas APIs abertas.
ABA_ACOMP = "Acompanhadas"
CAB_ACOMP = ["Cliente", "Proposição", "Casa", "ID na Casa", "Origem", "Incluída em"]
_JSON = {"Accept": "application/json"}
CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"


def ler_acompanhadas(ws) -> list[dict]:
    vals = ws.get_all_values()
    cab = vals[0] if vals else CAB_ACOMP
    return [dict(zip(cab, r + [""] * (len(cab) - len(r)))) for r in vals[1:] if any(r)]


def _get(url, **params):
    for tentativa in range(3):
        try:
            r = requests.get(url, params=params or None, headers=_JSON, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            if tentativa == 2:
                raise
            time.sleep(2 * (tentativa + 1))
    return None


def _palavras(t: str) -> set:
    return {w for w in re.findall(r"\w{4,}", (t or "").lower())}


def _candidatos(proposicao: str) -> list[tuple[str, str, str]]:
    """(casa, id, ementa) de cada casa onde existe essa sigla/número/ano."""
    m = re.match(r"(\w+)\s+(\d+)/(\d{4})", proposicao.strip())
    if not m:
        return []
    sig, num, ano = m.groups()
    out = []
    for d in (_get(f"{CAMARA}/proposicoes", siglaTipo=sig, numero=num, ano=ano) or {}).get("dados") or []:
        ementa = d.get("ementa", "")
        out.append(("Câmara dos Deputados", str(d["id"]), ementa))
    for d in _get(f"{SENADO}/processo", sigla=sig, numero=num, ano=ano) or []:
        if d.get("casaIdentificadora") == "SF":
            out.append(("Senado Federal", str(d["id"]), d.get("ementa", "")))
    return out


def casa_e_id(proposicao: str, ementa: str = "") -> tuple[str, str]:
    """Escolhe a casa pela ementa da Divisão quando o número existe nas duas."""
    cands = _candidatos(proposicao)
    if not cands:
        return "Câmara dos Deputados", ""
    if len(cands) > 1 and ementa:
        alvo = _palavras(ementa)
        cands.sort(key=lambda c: -len(alvo & _palavras(c[2])))
    return cands[0][0], cands[0][1]


def acrescentar_novas(ws, novas: list[dict], atuais: list[dict], hoje: str) -> int:
    """Põe na aba as novas proposições da Divisão (por cliente) que ainda não estão lá."""
    tem = {(a["Cliente"], a["Proposição"].strip().upper()) for a in atuais}
    linhas = []
    for p in novas:
        clis = [cli for cli, _d in p["clientes"] if (cli, p["proposicao"].strip().upper()) not in tem]
        if not clis:
            continue
        m_id = re.search(r"idProposicao=(\d+)", p.get("link") or "")
        casa, id_ = ("Câmara dos Deputados", m_id.group(1)) if m_id else casa_e_id(p["proposicao"], p.get("ementa", ""))
        for cli in clis:
            tem.add((cli, p["proposicao"].strip().upper()))
            linhas.append([cli, p["proposicao"].strip(), casa, id_, "Divisão semanal", hoje])
    if linhas:
        ws.append_rows(linhas, value_input_option="RAW")
    return len(linhas)


def _autor_camara(id_: str) -> str:
    d = (_get(f"{CAMARA}/proposicoes/{id_}/autores") or {}).get("dados") or []
    nomes = []
    for a in d[:3]:
        uri = a.get("uri", "")
        if "/deputados/" in uri:
            st = ((_get(uri) or {}).get("dados") or {}).get("ultimoStatus") or {}
            nomes.append(f"{st.get('nome', a['nome'])} ({st.get('siglaPartido', '')}/{st.get('siglaUf', '')})")
        else:
            nomes.append(re.sub(r"^Senado Federal - ", "", a.get("nome", "")))
    return ", ".join(nomes) + (" e outros" if len(d) > 3 else "")


def _relator_camara(uri: str) -> str:
    if not uri:
        return ""
    d = (_get(uri) or {}).get("dados") or {}
    st = d.get("ultimoStatus") or {}
    if st.get("idLegislatura") != 57:  # relator de legislatura passada não vale mais
        return ""
    return f"{st.get('nome', '')} ({st.get('siglaPartido', '')}/{st.get('siglaUf', '')})"


def _mov_camara(id_: str, ini: dt.date, fim: dt.date) -> dict | None:
    det = (_get(f"{CAMARA}/proposicoes/{id_}") or {}).get("dados")
    if not det:
        return None
    stt = det.get("statusProposicao") or {}
    if (stt.get("dataHora") or "")[:10] < ini.isoformat():  # último andamento antes da semana
        return None
    tram = [t for t in (_get(f"{CAMARA}/proposicoes/{id_}/tramitacoes", dataInicio=ini.isoformat(),
                             dataFim=fim.isoformat()) or {}).get("dados") or []
            if ini.isoformat() <= (t.get("dataHora") or "")[:10] <= fim.isoformat()]
    if not tram:
        return None
    ult = sorted(tram, key=lambda t: (t.get("dataHora", ""), t.get("sequencia", 0)))[-1]
    d = dt.date.fromisoformat(ult["dataHora"][:10])
    return {"proposicao": f"{det['siglaTipo']} {det['numero']}/{det['ano']}", "ementa": det.get("ementa", ""),
            "autor": _autor_camara(id_), "relator": _relator_camara(ult.get("uriUltimoRelator", "")),
            "data": f"{d.day}/{d.month}/{d.year}", "orgao": ult.get("siglaOrgao", ""),
            "andamento": (ult.get("despacho") or ult.get("descricaoTramitacao") or "").strip(),
            "link": det.get("urlInteiroTeor") or f"https://www.camara.leg.br/propostas-legislativas/{id_}",
            "teor": ult.get("url") or ""}


def _mov_senado(id_: str, ini: dt.date, fim: dt.date) -> dict | None:
    det = _get(f"{SENADO}/processo/{id_}")
    if not det:
        return None
    infs = [i for a in det.get("autuacoes") or [] for i in a.get("informesLegislativos") or []
            if ini.isoformat() <= (i.get("data") or "")[:10] <= fim.isoformat()]
    if not infs:
        return None
    ult = sorted(infs, key=lambda i: i["data"])[-1]
    d = dt.date.fromisoformat(ult["data"][:10])
    relator = ""
    rel = _get(f"{SENADO}/processo/relatoria", codigoMateria=det.get("codigoMateria")) or []
    atuais = [r for r in rel if not r.get("dataDestituicao") and not r.get("dataFimColegiado")]
    if atuais:
        r = atuais[-1]
        relator = f"{r.get('nomeParlamentar', '')} ({r.get('siglaPartidoParlamentar', '')}/{r.get('ufParlamentar', '')})"
    autores = []
    for a in det.get("autoriaIniciativa") or []:
        nome = a.get("autor") or ""
        if a.get("siglaPartido") and a.get("uf"):
            nome += f" ({a['siglaPartido']}/{a['uf']})"
        if nome:
            autores.append(nome)
    autor = ", ".join(autores[:3]) + (" e outros" if len(autores) > 3 else "")
    doc = (ult.get("documentosAssociados") or [{}])[0]
    return {"proposicao": det.get("identificacao", ""), "ementa": (det.get("conteudo") or {}).get("ementa", ""),
            "autor": autor, "relator": relator,
            "data": f"{d.day}/{d.month}/{d.year}", "orgao": (ult.get("colegiado") or {}).get("sigla", ""),
            "andamento": re.sub(r"\s+", " ", ult.get("descricao", "")).strip(),
            "link": f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{det.get('codigoMateria')}",
            "teor": doc.get("url") or ""}


def _ids_camara_no_periodo(ini: dt.date, fim: dt.date) -> tuple[set[str] | None, str]:
    """IDs de toda proposição com tramitação na Câmara no período. Retorna (ids, erro)."""
    try:
        primeira = _get(f"{CAMARA}/proposicoes", dataInicio=ini.isoformat(), dataFim=fim.isoformat(),
                        itens=100, pagina=1) or {}
        ultimo = next((l["href"] for l in primeira.get("links") or [] if l.get("rel") == "last"), "")
        n_pag = int(re.search(r"pagina=(\d+)", ultimo).group(1)) if "pagina=" in ultimo else 1

        def pagina(p):
            d = primeira if p == 1 else _get(f"{CAMARA}/proposicoes", dataInicio=ini.isoformat(),
                                               dataFim=fim.isoformat(), itens=100, pagina=p)
            return [str(x["id"]) for x in (d or {}).get("dados") or []]
        with ThreadPoolExecutor(8) as ex:
            return {i for lista in ex.map(pagina, range(1, n_pag + 1)) for i in lista}, ""
    except Exception as e:  # noqa: BLE001
        msg = f"HTTP {e.response.status_code} ({e.response.reason})" if getattr(e, "response", None) is not None else str(e)[:100]
        return None, msg


SEM_RESPOSTA = "_sem_resposta"  # chave do resultado com as proposições que as APIs não responderam
ERRO_CAMARA = "_erro_camara"    # motivo específico caso a API da Câmara tenha falhado por completo


def movimentacoes_semana(acomp: list[dict], ini: dt.date, fim: dt.date, workers: int = 16,
                         progresso=None) -> dict[str, list[dict]]:
    """Cliente -> movimentações da semana (uma linha por proposição, o último andamento)."""
    unicos = {(a["Casa"], a["ID na Casa"]) for a in acomp if a.get("ID na Casa")}
    na_camara, erro_camara = _ids_camara_no_periodo(ini, fim)
    camara_fora = set()
    if na_camara is not None:
        unicos = {(c, i) for c, i in unicos if not c.startswith("Câmara") or i in na_camara}
    else:
        # Se a listagem da Câmara falhou (ex.: API da Câmara fora do ar com 503), evita fazer 1,4 mil
        # chamadas individuais que travam a página por dezenas de minutos. Trata a Câmara como indisponível.
        camara_fora = {(c, i) for c, i in unicos if c.startswith("Câmara")}
        unicos = {(c, i) for c, i in unicos if not c.startswith("Câmara")}
    feitos = [0]

    falhou = object()

    def um(chave):
        casa, id_ = chave
        try:
            m = _mov_camara(id_, ini, fim) if casa.startswith("Câmara") else _mov_senado(id_, ini, fim)
        except Exception:  # noqa: BLE001
            m = falhou
        feitos[0] += 1
        if progresso:
            progresso(feitos[0], len(unicos))
        return chave, m

    with ThreadPoolExecutor(workers) as ex:
        res = dict(ex.map(um, unicos))
    if camara_fora:
        for k in camara_fora:
            res[k] = falhou
    # quem falhou é consultado de novo, devagar (exceto se a Câmara já estiver fora do ar)
    repetir = [k for k, v in res.items() if v is falhou and k not in camara_fora]
    if repetir:
        time.sleep(5)
        with ThreadPoolExecutor(4) as ex:
            res.update(dict(ex.map(um, repetir)))
    sem_resposta = sorted(k for k, v in res.items() if v is falhou)
    res = {k: (None if v is falhou else v) for k, v in res.items()}
    out: dict[str, list[dict]] = {}
    for a in acomp:
        m = res.get((a["Casa"], a.get("ID na Casa")))
        if m and m["proposicao"] not in [x["proposicao"] for x in out.get(a["Cliente"], [])]:
            out.setdefault(a["Cliente"], []).append(m)
    for v in out.values():
        v.sort(key=lambda m: tuple(reversed([int(x) for x in m["data"].split("/")])))
    if erro_camara:
        out[ERRO_CAMARA] = erro_camara
    if sem_resposta:  # a página avisa; as chaves de cliente seguem intactas
        out[SEM_RESPOSTA] = [{"casa": c, "id": i} for c, i in sem_resposta]
    return out


# ─── Inteligov (conferência e complemento) ───────────────────────────────────
def url_matriz_inteligov(cliente: str, ini: dt.date, fim: dt.date) -> str | None:
    cod = CLIENTES[cliente].get("inteligov")
    if not cod:
        return None
    return (f"https://app.inteligov.com.br/beta/proposicoes?cf=t&fcl%5B%5D={cod}"
            f"&bsd={ini:%d/%m/%Y}&bed={fim:%d/%m/%Y}")


def ler_movimentacoes(dados: bytes, nome: str) -> list[dict]:
    """Lê o XLS/XLSX exportado da Matriz de monitoramento do Inteligov.

    O cabeçalho é localizado pelo nome das colunas (o export tem linhas de título antes).
    """
    import pandas as pd
    try:
        bruto = pd.read_excel(io.BytesIO(dados), header=None, dtype=str)
    except Exception:  # noqa: BLE001
        # alguns ".xls" de sistema web são HTML com extensão de planilha
        bruto = pd.read_html(io.BytesIO(dados), header=None)[0].astype(str)
    linha_cab = 0
    for i in range(min(15, len(bruto))):
        vals = " | ".join(str(v).lower() for v in bruto.iloc[i].tolist())
        if "ementa" in vals and ("identifica" in vals or "proposi" in vals):
            linha_cab = i
            break
    df = bruto.iloc[linha_cab + 1:].copy()
    df.columns = [str(c).strip() for c in bruto.iloc[linha_cab].tolist()]
    df = df.fillna("")

    def col(*nomes):
        for c in df.columns:
            if any(n in c.lower() for n in nomes):
                return c
        return None

    c_id, c_em, c_aut = col("identifica", "proposi"), col("ementa"), col("autor")
    c_rel = col("relator")
    c_and = col("último andamento", "ultimo andamento", "andamento", "tramita")
    c_dt = col("data do último", "data do ultimo", "data último", "data andamento")
    c_org = col("órgão", "orgao", "local")
    c_link = col("inteiro teor", "link")
    out = []
    for _, r in df.iterrows():
        ident = str(r.get(c_id, "")).strip() if c_id else ""
        if not ident:
            continue
        out.append({"proposicao": ident, "ementa": r.get(c_em, "") if c_em else "",
                    "autor": r.get(c_aut, "") if c_aut else "", "relator": r.get(c_rel, "") if c_rel else "",
                    "data": r.get(c_dt, "") if c_dt else "", "orgao": r.get(c_org, "") if c_org else "",
                    "andamento": r.get(c_and, "") if c_and else "", "link": r.get(c_link, "") if c_link else ""})
    return out


# ─── DOU (aba do cliente na planilha da raspagem) ────────────────────────────
def _data_flex(txt: str) -> dt.date | None:
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(txt.strip(), fmt).date()
        except ValueError:
            pass
    return None


def ler_dou_cliente(gc, planilha_id: str, cliente: str, ini: dt.date, fim: dt.date,
                    aceitar=("Alinha",)) -> list[dict]:
    ws = gc.open_by_key(planilha_id).worksheet(CLIENTES[cliente]["dou"])
    vals = ws.get_all_values()
    if not vals:
        return []
    cab = vals[0]
    ix = {c: cab.index(c) for c in cab}
    out, vistos = [], set()
    for row in vals[1:]:
        g = lambda c: row[ix[c]].strip() if c in ix and ix[c] < len(row) else ""  # noqa: E731
        d = _data_flex(g("Data"))
        if d is None:
            continue
        if not (ini <= d <= fim) or g("Alinhamento") not in aceitar or g("Link") in vistos:
            continue
        vistos.add(g("Link"))
        out.append({"data": d, "ato": g("Portaria"), "link": g("Link"), "resumo": g("Resumo"),
                    "alinhamento": g("Alinhamento"), "justificativa": g("Justificativa")})
    return out


# Itens que entram desligados na página (quem revisa pode ligar de volta)
_DOU_REPASSE = re.compile(r"^Autoriza (?:o|a|os|as) .{0,80}?receber recursos", re.I)


def dou_rotina(ato: dict) -> bool:
    """Aviso de prefeitura ou portaria de repasse a ente/entidade: fora por padrão."""
    return (ato.get("orgao") or "").lower().startswith("prefeituras") or bool(_DOU_REPASSE.match(ato.get("resumo") or ""))


def mov_rotina(m: dict) -> bool:
    """Só recebimento do processo pelo órgão: fora por padrão."""
    return bool(re.match(r"Recebimento pel[oa]", (m.get("andamento") or "").strip(), re.I))


def so_apresentacao(m: dict) -> bool:
    return bool(re.match(r"Apresentaç[aã]o d", (m.get("andamento") or "").strip(), re.I))


def _campo_dou(pg: str, classe: str) -> str:
    m = re.search(rf'class="{classe}"[^>]*>(.*?)</(?:p|span|div)>', pg, re.S)
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1)))).strip() if m else ""


def completar_ato_dou(ato: dict) -> dict:
    """Órgão, data, identificação e ementa pelos campos da página do ato no in.gov.br.
    Sem ementa (aviso, despacho, consulta), fica o resumo da raspagem sem o título repetido."""
    try:
        pg = requests.get(ato["link"], headers=UA, timeout=20).text
        org = _campo_dou(pg, "orgao-dou-data")
        pub = _campo_dou(pg, "publicado-dou-data")
        ident = _campo_dou(pg, "identifica") or ato.get("ato", "")
        resumo = _campo_dou(pg, "ementa")
        if not resumo:
            resumo = (ato.get("resumo") or "").strip()
            if ident and resumo.lower().startswith(ident.lower()):
                resumo = resumo[len(ident):].strip()
        return {**ato, "ato": ident, "resumo": resumo, "orgao": org,
                "orgao_topo": org.split("/")[0].strip().upper() if org else "OUTROS",
                "publicado": pub if re.fullmatch(r"\d{2}/\d{2}/\d{4}", pub) else ato["data"].strftime("%d/%m/%Y")}
    except Exception:  # noqa: BLE001
        return {**ato, "orgao": "", "orgao_topo": "OUTROS", "publicado": ato["data"].strftime("%d/%m/%Y")}


# ─── Word ────────────────────────────────────────────────────────────────────
# Clona os parágrafos e tabelas das sínteses de 26 a 30/10/2026 (UNFPA para todos,
# IDEC para o IDEC): título, data, faixa de seção, bullet, subtítulo, tabelas e DOU.
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _prototipos(doc) -> dict:
    ps = [p for p in doc.paragraphs if p.text.strip()]
    get = lambda f: next(p for p in ps if f(p.text))  # noqa: E731
    proto = {
        "titulo": get(lambda t: t.startswith("SÍNTESE SEMANAL")),
        "data": ps[1],
        "bullet": get(lambda t: t.strip().startswith("•")),
        "sub": get(lambda t: t.strip().startswith("NOVAS PROPOSI")),
        "orgao": next(p for p in ps if p.style.name.startswith("Heading")),
    }
    i_org = ps.index(proto["orgao"])
    proto["ato"], proto["desc"] = ps[i_org + 1], ps[i_org + 2]
    secao = [p for p in ps if not p.text.strip().startswith("•") and ps.index(p) > 1
             and ps.index(p) < ps.index(proto["sub"])]
    proto["secao"] = secao[0]
    proto["tab_novas"], proto["tab_mov"] = doc.tables[0], doc.tables[1]
    return proto


def _set_texto(p_el, partes: list[tuple[str, bool, str | None]], doc):
    """Troca o conteúdo do parágrafo por runs (texto, negrito, link) com o rPr do 1º run."""
    runs = p_el.findall(f".//{W}r")
    rpr0 = copy.deepcopy(runs[0].find(f"{W}rPr")) if runs and runs[0].find(f"{W}rPr") is not None else None
    for child in list(p_el):
        if child.tag != f"{W}pPr":
            p_el.remove(child)
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    for texto, negrito, link in partes:
        texto = re.sub(r"[ \t]*[\r\n]+[ \t]*", " ", texto)  # \r da API do Senado desmonta a tabela no LibreOffice
        r = OxmlElement("w:r")
        rpr = copy.deepcopy(rpr0) if rpr0 is not None else OxmlElement("w:rPr")
        for tag in ("w:b", "w:bCs", "w:u", "w:color"):
            for x in rpr.findall(qn(tag)):
                rpr.remove(x)
        if negrito:
            b = OxmlElement("w:b"); b.set(qn("w:val"), "1"); rpr.insert(0, b)  # noqa: E702
        if link:
            c = OxmlElement("w:color"); c.set(qn("w:val"), "1155CC"); rpr.append(c)  # noqa: E702
            u = OxmlElement("w:u"); u.set(qn("w:val"), "single"); rpr.append(u)  # noqa: E702
        r.append(rpr)
        t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve"); t.text = texto  # noqa: E702
        r.append(t)
        if link:
            rid = doc.part.relate_to(link, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                                     is_external=True)
            h = OxmlElement("w:hyperlink"); h.set(qn("r:id"), rid); h.append(r)  # noqa: E702
            p_el.append(h)
        else:
            p_el.append(r)
    return p_el


def _partes_bullet(b: dict) -> list[tuple[str, bool, str | None]]:
    """Título em negrito sem link, como no modelo da equipe; documentos com link no próprio nome."""
    partes = [("• ", True, None), (b["titulo"].rstrip(".") + ".", True, None), (" ", False, None)]
    texto = b.get("texto", "")
    marcos = []
    for d in b.get("documentos") or []:
        i = texto.find(d["nome"])
        if i >= 0:
            marcos.append((i, i + len(d["nome"]), d["url"]))
    pos = 0
    for ini, fim, url in sorted(marcos):
        if ini < pos:
            continue
        partes.append((texto[pos:ini], False, None))
        partes.append((texto[ini:fim], False, url))
        pos = fim
    partes.append((texto[pos:], False, None))
    sem_lugar = [d for d in b.get("documentos") or [] if d["nome"] not in texto]
    for d in sem_lugar:
        partes += [(" Acesse ", False, None), (d["nome"], False, d["url"]), (".", False, None)]
    return [p for p in partes if p[0]]


def _linha_tabela(tbl_proto, valores: list[tuple[str, str | None]], doc):
    tr = copy.deepcopy(tbl_proto._tbl.findall(f"{W}tr")[1])
    for tc, valor in zip(tr.findall(f"{W}tc"), valores):
        ps = tc.findall(f"{W}p")
        for extra in ps[1:]:
            tc.remove(extra)
        if isinstance(valor, list):  # já em partes (texto, negrito, link)
            _set_texto(ps[0], [x for x in valor if x[0]] or [("-", False, None)], doc)
        else:
            txt, link = valor
            _set_texto(ps[0], [(txt or "-", False, link)], doc)
    return tr


def gerar_docx(modelo: bytes, cliente: str, periodo: str, bullets: list[dict],
               clipping: list[dict] | None = None, novas: list[dict] | None = None,
               movs: list[dict] | None = None, dou: list[dict] | None = None,
               so_anexo: bool = False) -> bytes:
    import docx
    doc = docx.Document(io.BytesIO(modelo))
    P = _prototipos(doc)
    novo = lambda nome: copy.deepcopy(P[nome]._p)  # noqa: E731
    corpo = doc.element.body
    sect = corpo.find(f"{W}sectPr")
    els = []

    def add_par(nome, partes):
        els.append(_set_texto(novo(nome), partes, doc))

    add_par("titulo", [(f"SÍNTESE SEMANAL: {CLIENTES[cliente]['titulo'].upper()}", False, None)])
    add_par("data", [(periodo, False, None)])
    if not so_anexo:
        if clipping:
            add_par("secao", [("CLIPPING DA SEMANA", False, None)])
            for c in clipping:
                add_par("bullet", [("• ", True, None), (c["titulo"], True, c["url"]),
                                   (" - " + c["lide"], False, None)])
        for sec in secoes_do_cliente(cliente):
            doses = [b for b in bullets if b["secao"] == sec]
            if not doses:
                continue
            rotulo = sec if cliente == "IDEC" else f"DESTAQUES  {sec.upper()}"
            add_par("secao", [(rotulo, False, None)])
            for b in doses:
                add_par("bullet", _partes_bullet(b))
    if novas:
        add_par("sub", [("NOVAS PROPOSIÇÕES", False, None)])
        tbl = copy.deepcopy(P["tab_novas"]._tbl)
        for tr in tbl.findall(f"{W}tr")[1:]:
            tbl.remove(tr)
        for n in novas:
            tbl.append(_linha_tabela(P["tab_novas"], [(n["proposicao"], n.get("link") or None),
                                                      (n["ementa"], None), (n["autor"], None)], doc))
        _tirar_coluna_cliente(tbl)
        els.append(tbl)
    if movs:
        add_par("sub", [("MOVIMENTAÇÕES DA SEMANA", False, None)])
        tbl = copy.deepcopy(P["tab_mov"]._tbl)
        for tr in tbl.findall(f"{W}tr")[1:]:
            tbl.remove(tr)
        for m in movs:
            mov = " ".join(x for x in [m.get("data", ""), m.get("orgao", "")] if x)
            mov = (mov + " " if mov else "") + m.get("andamento", "")
            tbl.append(_linha_tabela(P["tab_mov"], [(m["proposicao"], m.get("link") or None), (m["ementa"], None),
                                                    (m["autor"], None), (m.get("relator") or "-", None),
                                                    [(mov, False, None)] + ([(" ", False, None), ("Inteiro teor", False, m["teor"])]
                                                                            if m.get("teor") else [])], doc))
        els.append(tbl)
    if dou:
        add_par("sub", [("NOVAS PUBLICAÇÕES", False, None)])
        por_org: dict[str, list[dict]] = {}
        for a in dou:
            por_org.setdefault(a.get("orgao_topo") or "OUTROS", []).append(a)
        for org, atos in por_org.items():
            add_par("orgao", [(org, True, None)])
            for a in atos:
                cab = f"{a['ato']} | Publicado em: {a.get('publicado', '')} | {a.get('orgao', '')}".rstrip(" |")
                add_par("ato", [(cab, True, a["link"])])
                if (a.get("resumo") or "").strip():
                    add_par("desc", [(a["resumo"], False, None)])
    # mantém os parágrafos vazios antes do título (espaço do logo do cabeçalho)
    filhos = list(corpo)
    i_tit = filhos.index(P["titulo"]._p)
    for child in filhos[i_tit:]:
        if child is not sect:
            corpo.remove(child)
    for el in els:
        sect.addprevious(el)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _tirar_coluna_cliente(tbl):
    """O modelo tem a coluna CLIENTE (uso interno); na síntese ela sai."""
    linhas = tbl.findall(f"{W}tr")
    if not linhas:
        return
    cab = ["".join(t.text or "" for t in tc.iter(f"{W}t")).strip().upper() for tc in linhas[0].findall(f"{W}tc")]
    if "CLIENTE" in cab:
        i = cab.index("CLIENTE")
    elif len(cab) == 4:  # no modelo a 4ª coluna (cliente) tem cabeçalho vazio
        i = 3
    else:
        return
    for tr in linhas:
        tcs = tr.findall(f"{W}tc")
        if i < len(tcs):
            tr.remove(tcs[i])
    grid = tbl.find(f"{W}tblGrid")
    cols = grid.findall(f"{W}gridCol") if grid is not None else []
    if i < len(cols):
        largura = int(float(cols[i].get(f"{W}w")))
        grid.remove(cols[i])
        cols = grid.findall(f"{W}gridCol")
        cols[1].set(f"{W}w", str(int(float(cols[1].get(f"{W}w"))) + largura))


# ─── Corpo do email (HTML para colar no Wix) ─────────────────────────────────
def html_email(cliente: str, periodo: str, bullets: list[dict], clipping: list[dict] | None = None) -> str:
    esc = _html.escape
    partes = [f"<p><b>Síntese da Semana - {esc(CLIENTES[cliente]['titulo'])}</b><br>{esc(periodo)}</p>"]
    if clipping:
        partes.append("<h3>Clipping da Semana</h3><ul>")
        for c in clipping:
            partes.append(f'<li><a href="{esc(c["url"])}"><b>{esc(c["titulo"])}</b></a> - {esc(c["lide"])}</li>')
        partes.append("</ul>")
    for sec in secoes_do_cliente(cliente):
        doses = [b for b in bullets if b["secao"] == sec]
        if not doses:
            continue
        partes.append(f"<h3>{esc(sec if cliente == 'IDEC' else 'Destaques ' + sec)}</h3><ul>")
        for b in doses:
            corpo = "".join(
                (f'<a href="{esc(link)}">{"<b>" if neg else ""}{esc(t)}{"</b>" if neg else ""}</a>' if link
                 else f'{"<b>" if neg else ""}{esc(t)}{"</b>" if neg else ""}')
                for t, neg, link in _partes_bullet(b)[1:])
            partes.append(f"<li>{corpo}</li>")
        partes.append("</ul>")
    return "<html><head><meta charset='utf-8'></head><body style='font-family:Montserrat,Arial,sans-serif;font-size:14px'>" \
           + "\n".join(partes) + "</body></html>"


# ─── PDF (LibreOffice convertendo o próprio Word, para sair com o mesmo layout) ──
def _instalar_fontes(pasta_fontes: str) -> None:
    """Montserrat não tem pacote no Debian 12: copia os .ttf do repo para ~/.fonts."""
    import glob
    import os
    import shutil
    import subprocess
    destino = os.path.expanduser("~/.fonts")
    os.makedirs(destino, exist_ok=True)
    novas = False
    for f in glob.glob(os.path.join(pasta_fontes, "*.ttf")):
        alvo = os.path.join(destino, os.path.basename(f))
        if not os.path.exists(alvo):
            shutil.copy(f, alvo)
            novas = True
    if novas and shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", destino], capture_output=True, timeout=60)


def pdf_disponivel() -> bool:
    import shutil
    return bool(shutil.which("soffice") or shutil.which("libreoffice"))


def docx_para_pdf(arquivos: dict[str, bytes], pasta_fontes: str = "fontes") -> dict[str, bytes]:
    """{nome.docx: bytes} -> {nome.pdf: bytes}, numa chamada só do LibreOffice."""
    import os
    import shutil
    import subprocess
    import tempfile
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice or not arquivos:
        return {}
    _instalar_fontes(pasta_fontes)
    with tempfile.TemporaryDirectory() as tmp:
        entrada, saida = os.path.join(tmp, "in"), os.path.join(tmp, "out")
        os.makedirs(entrada)
        os.makedirs(saida)
        apelido = {}
        for i, (nome, dados) in enumerate(arquivos.items()):
            caminho = os.path.join(entrada, f"{i}.docx")  # nome curto: acento e espaço não atrapalham
            with open(caminho, "wb") as f:
                f.write(dados)
            apelido[f"{i}.pdf"] = nome[:-5] + ".pdf"
        subprocess.run([soffice, "--headless", "--norestore", f"-env:UserInstallation=file://{tmp}/perfil",
                        "--convert-to", "pdf", "--outdir", saida]
                       + [os.path.join(entrada, f"{i}.docx") for i in range(len(arquivos))],
                       capture_output=True, timeout=300)
        out = {}
        for curto, nome in apelido.items():
            caminho = os.path.join(saida, curto)
            if os.path.exists(caminho):
                with open(caminho, "rb") as f:
                    out[nome] = f.read()
        return out


def pacote_zip(arquivos: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return buf.getvalue()
