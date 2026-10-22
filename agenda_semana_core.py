"""Agenda da Semana: coleta a pauta da Câmara e do Senado e gera um .docx por cliente.

A coleta usa só as APIs de dados abertos das duas Casas. Cada item da pauta vira
um dict no formato que a página de seleção e o gerador de Word entendem:

    id, dia (iso), hora ("14h", "10h30"), ordem ("HH:MM"), casa ("CD"|"SF"),
    colegiado, reuniaoLink, tipo ("materia"|"audiencia"|"evento"), rotulo,
    titulo, tituloLink, ementa, autor, relator, parecer, parecerLink, convidados,
    situacao ("Cancelada"|"Adiada", só quando a reunião não vai acontecer)

Regra de conteúdo (da Lívia): tudo o que está na pauta entra, haja ou não matéria
para votar. Quem decide o que é relevante é quem marca os clientes na página.
Reunião cancelada também entra, marcada, para a equipe saber se o cliente perguntar;
ela não vai para o Word. Em requerimento de audiência, os convidados saem do texto
do requerimento (PDF).
"""
from __future__ import annotations

import datetime as dt
import io
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from xml.sax.saxutils import escape

import requests

CLIENTES = ["IEPS", "Vital", "Umane", "IDEC", "Infinis", "UNFPA", "Coletivo"]
DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
PARALELO = 6

_sessao = requests.Session()
_sessao.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0 (agenda-eixo)"})


# ─── utilitários ─────────────────────────────────────────────────────────────

def _get(url: str, params: dict | None = None, tentativas: int = 3):
    for i in range(tentativas):
        try:
            r = _sessao.get(url, params=params, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(1.5 * (i + 1))


def _lista(x) -> list:
    """A API do Senado devolve objeto solto quando a lista tem um item só."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _hora(hhmm: str) -> str:
    h, m = hhmm[:5].split(":")
    return f"{int(h)}h" + ("" if m == "00" else m)


def _limpa(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


_MINUSCULAS = {"da", "de", "do", "das", "dos", "e", "di", "du", "van", "von"}


def _nome_proprio(s: str) -> str:
    partes = s.lower().split()
    return " ".join(p if (i and p in _MINUSCULAS) else p[:1].upper() + p[1:] for i, p in enumerate(partes))


def _sem_cargo(nome: str) -> str:
    return re.sub(r"^(Senador|Senadora|Deputado|Deputada)\s+", "", _limpa(nome))


def _maiuscula(s: str) -> str:
    return s[:1].upper() + s[1:]


_SIGLAS = {"PEC", "MPV", "PL", "PLP", "PDL", "CPI", "CPMI", "SUS", "LOA", "LDO", "CN", "SF", "CD"}
_PARTICULAS = _MINUSCULAS | {"a", "o", "as", "os", "à", "às", "ao", "aos", "em", "no", "na", "nos", "nas",
                             "para", "sobre", "com", "por", "pela", "pelo"}


def nome_colegiado(s: str) -> str:
    """'COMISSÃO DE SAÚDE (CSAUDE)' -> 'Comissão de Saúde (CSAUDE)'; a sigla entre parênteses fica."""
    m = re.match(r"^(.*?)\s*\(([^()]*)\)$", s or "")
    base, sigla = (m.group(1), m.group(2)) if m else (s or "", "")
    if sigla and " " in sigla and not any(ch.isdigit() for ch in sigla):
        base, sigla = f"{base} ({sigla})", ""
    palavras = []
    for i, p in enumerate(base.split()):
        nu = p.strip("().,-").upper()
        if nu in _SIGLAS or any(ch.isdigit() for ch in p):
            palavras.append(p.upper() if nu in _SIGLAS else p)
        elif i and p.lower() in _PARTICULAS:
            palavras.append(p.lower())
        elif p.startswith("("):
            palavras.append("(" + _maiuscula(p[1:].lower()))
        else:
            palavras.append(_maiuscula(p.lower()))
    return " ".join(palavras) + (f" ({sigla})" if sigla else "")


def _situacao(txt) -> str:
    """'Cancelada' ou 'Adiada' quando a reunião não vai acontecer; vazio no resto."""
    t = _limpa(txt).lower()
    return "Cancelada" if "cancelad" in t else ("Adiada" if "adiad" in t else "")


def periodo_extenso(ini: dt.date, fim: dt.date) -> str:
    if ini.month == fim.month:
        return f"{ini.day} a {fim.day} de {MESES[fim.month - 1]} de {fim.year}"
    return f"{ini.day} de {MESES[ini.month - 1]} a {fim.day} de {MESES[fim.month - 1]} de {fim.year}"


def semana_seguinte(hoje: dt.date | None = None) -> tuple[dt.date, dt.date]:
    hoje = hoje or dt.date.today()
    seg = hoje + dt.timedelta(days=7 - hoje.weekday())
    return seg, seg + dt.timedelta(days=4)


# ─── Câmara ──────────────────────────────────────────────────────────────────

def _colegiado_camara(orgao: dict) -> str:
    sigla = orgao.get("sigla", "")
    if sigla == "PLEN":
        return "PLENÁRIO"
    if sigla == "CN":
        return "PLENÁRIO (CONGRESSO NACIONAL)"
    if sigla == "EVENTOS":
        return "EVENTOS DA CÂMARA"
    return f"{_limpa(orgao.get('nome')).rstrip('.').upper()} ({sigla})"


_RE_CONVIDADO = re.compile(r"^([A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý'’ .\-]{3,}),\s*(.+)$")


def _convidados_camara(descricao: str) -> list[str]:
    """Na Câmara, o convidado vem numa linha 'NOME EM CAIXA ALTA, cargo'."""
    out = []
    for linha in str(descricao or "").splitlines():
        linha = _limpa(linha)
        m = _RE_CONVIDADO.match(linha)
        if not m:
            continue
        cargo = re.sub(r"(;| e|\.)$", "", m.group(2).strip()).strip(" ;")
        out.append(f"{_nome_proprio(m.group(1).strip())}, {cargo}")
    return out


def _eventos_camara(ini: dt.date, fim: dt.date) -> list[dict]:
    url = f"{CAMARA}/eventos"
    params = {"dataInicio": ini.isoformat(), "dataFim": fim.isoformat(), "itens": 100,
              "ordem": "ASC", "ordenarPor": "dataHoraInicio"}
    eventos = []
    while url:
        d = _get(url, params)
        eventos += d.get("dados", [])
        url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
        params = None
    # sessão do Congresso aparece também na agenda do Senado, que traz os requerentes
    return [e for e in eventos if (e.get("orgaos") or [{}])[0].get("sigla") != "CN"]


def coletar_camara(ini: dt.date, fim: dt.date) -> list[dict]:
    eventos = _eventos_camara(ini, fim)
    with ThreadPoolExecutor(PARALELO) as ex:
        pautas = list(ex.map(lambda e: _lista((_get(f"{CAMARA}/eventos/{e['id']}/pauta") or {}).get("dados")), eventos))

    # autores, partidos e links de parecer: busca uma vez cada
    ids_prop, ids_prl, ids_dep = set(), set(), set()
    for pauta in pautas:
        for p in pauta:
            prop = p.get("proposicao_") or {}
            rel = p.get("proposicaoRelacionada_") or {}
            if prop.get("siglaTipo") == "REQ" or not rel:
                ids_prop.add(prop.get("id"))
            else:
                ids_prop.add(rel.get("id"))
                if prop.get("siglaTipo") == "PRL":
                    ids_prl.add(prop.get("id"))
            r = p.get("relator") or {}
            if r.get("id") and not r.get("siglaPartido"):
                ids_dep.add(r["id"])
    ids_prop.discard(None)

    with ThreadPoolExecutor(PARALELO) as ex:
        autores = dict(zip(ids_prop, ex.map(lambda i: _lista((_get(f"{CAMARA}/proposicoes/{i}/autores") or {}).get("dados")), ids_prop)))
        prls = dict(zip(ids_prl, ex.map(lambda i: (_get(f"{CAMARA}/proposicoes/{i}") or {}).get("dados") or {}, ids_prl)))
    for lst in autores.values():
        if lst and "/deputados/" in (lst[0].get("uri") or ""):
            ids_dep.add(int(lst[0]["uri"].rsplit("/", 1)[1]))
    with ThreadPoolExecutor(PARALELO) as ex:
        deps = dict(zip(ids_dep, ex.map(lambda i: (_get(f"{CAMARA}/deputados/{i}") or {}).get("dados") or {}, ids_dep)))

    def partido_uf(dep_id, partido=None, uf=None):
        st = (deps.get(dep_id) or {}).get("ultimoStatus") or {}
        return partido or st.get("siglaPartido") or "", uf or st.get("siglaUf") or ""

    def autoria(prop_id) -> str:
        lst = sorted(autores.get(prop_id) or [], key=lambda a: a.get("ordemAssinatura") or 99)
        if not lst:
            return ""
        a = lst[0]
        nome = _limpa(a.get("nome"))
        if "/deputados/" in (a.get("uri") or ""):
            p, u = partido_uf(int(a["uri"].rsplit("/", 1)[1]))
            if p and u:
                nome += f" ({p}/{u})"
        return nome

    itens, reqs = [], []
    for ev, pauta in zip(eventos, pautas):
        inicio = ev["dataHoraInicio"]
        orgao = (ev.get("orgaos") or [{}])[0]
        base = {
            "casa": "CD", "dia": inicio[:10], "hora": _hora(inicio[11:16]), "ordem": inicio[11:16],
            "colegiado": _colegiado_camara(orgao),
            "reuniaoLink": f"https://www.camara.leg.br/evento-legislativo/{ev['id']}",
            "reuniao": _limpa(ev.get("descricaoTipo")),
            "situacao": _situacao(ev.get("situacao")),
        }
        tipo_ev = base["reuniao"]
        linhas = [_limpa(l) for l in str(ev.get("descricao") or "").splitlines() if _limpa(l)]

        if not pauta:
            titulo = linhas[0] if linhas else tipo_ev
            if "solene" in tipo_ev.lower():
                tipo, titulo, ementa = "evento", "Sessão solene", (linhas[0] if linhas else "")
            elif tipo_ev in ("Audiência Pública", "Seminário", "Mesa Redonda", "Audiência Pública e Deliberação"):
                tipo, ementa = "audiencia", titulo
            else:
                tipo, ementa = "evento", ""
            itens.append({**base, "id": f"CD-{ev['id']}", "tipo": tipo, "rotulo": tipo_ev,
                          "titulo": titulo, "tituloLink": base["reuniaoLink"], "ementa": ementa,
                          "convidados": _convidados_camara(ev.get("descricao"))})
            continue

        for n, p in enumerate(pauta, 1):
            prop = p.get("proposicao_") or {}
            rel = p.get("proposicaoRelacionada_") or {}
            if prop.get("siglaTipo") == "REQ" or not rel:
                alvo, rotulo = prop, ("Requerimento" if prop.get("siglaTipo") == "REQ" else tipo_ev)
                titulo = f"{prop.get('siglaTipo')} {prop.get('numero')}/{prop.get('ano')}"
            else:
                alvo, rotulo = rel, tipo_ev
                titulo = f"{rel.get('siglaTipo')} {int(rel.get('numero'))}/{rel.get('ano')}"
            relator, parecer, parecer_link = "", "", ""
            r = p.get("relator") or {}
            if r.get("nome") and prop.get("siglaTipo") != "REQ":
                part, uf = partido_uf(r.get("id"), r.get("siglaPartido"), r.get("siglaUf"))
                relator = f"{r['nome']} ({part}/{uf})" if part else r["nome"]
            if p.get("textoParecer"):
                # "Parecer do Relator, Dep. X (P-UF), pela ..." e "Parecer às Emendas ... Dep. X (P-UF) pela: ..."
                parecer = _maiuscula(re.sub(r"^Parecer\b.*?Dep\.\s*[^()]+\([^)]*\)[,:]?\s*", "", _limpa(p["textoParecer"])))
                parecer_link = (prls.get(prop.get("id")) or {}).get("urlInteiroTeor") or ""
            itens.append({**base, "id": f"CD-{ev['id']}-{n}", "tipo": "materia", "rotulo": rotulo,
                          "titulo": titulo, "ementa": _limpa(alvo.get("ementa")),
                          "tituloLink": f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={alvo.get('id')}",
                          "autor": autoria(alvo.get("id")), "relator": relator,
                          "parecer": parecer, "parecerLink": parecer_link})
            if prop.get("siglaTipo") == "REQ" and _pede_audiencia(itens[-1]["ementa"]):
                reqs.append((itens[-1], lambda i=prop.get("id"): ((_get(f"{CAMARA}/proposicoes/{i}") or {})
                                                                  .get("dados") or {}).get("urlInteiroTeor")))
    _anexar_convidados(reqs)
    return itens


# ─── Convidados de requerimento de audiência ─────────────────────────────────
# A pauta só traz a ementa; os nomes estão no texto do requerimento, numa lista
# depois de "seguintes convidados:". Se a lista não sai limpa, o item fica sem
# convidados (melhor vazio do que nome errado).

_RE_PEDE_AUDIENCIA = re.compile(r"audiência|seminário|mesa redonda|convidad|palestr|debate", re.I)
_RE_INICIO_LISTA = re.compile(r"convidad|participantes|palestrantes|expositores|debatedores"
                              r"|seguintes\s+(?:e\s+)?(?:entidades|instituições|autoridades|nomes|especialistas"
                              r"|representantes|pessoas|órgãos|organizações|associações)", re.I)
_RE_FIM_LISTA = re.compile(r"^\s*(?:JUSTIFI|Sala d[ae]s? |Sala das|Plenário d|Brasília,|Novos participantes"
                           r"|Outros (?:convidados|participantes) poderão)", re.I | re.M)
# cabeçalho, rodapé e carimbo de assinatura que o PDF intercala no meio da lista
_RE_LIXO_PDF = re.compile(r"^(?:\*CD\d+\*|Apresentação:|Assinado eletronicamente"
                          r"|SF/\d|Gabinete d|Página \d|REQ n\.|Câmara dos Deputados|Praça dos Três Poderes|\d{1,3}$)"
                          r"|Para verificar a|DEPUTAD[OA] FEDERAL|Anexo IV|Gabinete:? ?\d|@camara\.leg\.br|CEP:? ?\d|Tel(?:efone)?:? ?\(", re.I)
_RE_MARCADOR = re.compile(r"^(?:(?:[•\uf0b7\uf0a7\uf076▪●◦○■–-]|\d{1,2}\s*[.)ºª–-]|[a-z]\)|[IVX]{1,5}\s*[.)–-])\s*)+")
_RE_SO_SIGLA = re.compile(r"^[–-]\s*[A-ZÀ-Ý0-9/]{2,15}[;.]?$")   # "- CONASEMS" quebrado da linha de cima


def _pede_audiencia(ementa: str) -> bool:
    return bool(_RE_PEDE_AUDIENCIA.search(ementa or ""))


def _url_requerimento_senado(cod_materia) -> str:
    docs = _get(f"{SENADO}/processo/documento", {"codigoMateria": cod_materia}) or []
    return next((d.get("urlDocumento") for d in _lista(docs) if d.get("siglaTipo") == "REQUERIMENTO"), "")


def _texto_pdf(url: str) -> str:
    import pymupdf
    r = requests.get(url, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return ""
    with pymupdf.open(stream=r.content, filetype="pdf") as pdf:
        return "\n".join(p.get_text() for p in pdf)


def convidados_do_requerimento(texto: str) -> list[str]:
    # "convidados" aparece também no título ("para inclusão de convidados"); vale a
    # primeira ocorrência que abre uma lista
    for m in _RE_INICIO_LISTA.finditer(texto or ""):
        out = _lista_apos(texto[m.end():])
        if out:
            return out
    return []


def _lista_apos(resto: str) -> list[str]:
    abre = re.match(r"\w*\s*\.\s*\n", resto)        # "o seguinte convidado." e a lista embaixo
    if abre:
        corpo = resto[abre.end():]
    else:
        dois_pontos = resto.find(":")
        if dois_pontos < 0 or dois_pontos > 200:
            return []
        corpo = resto[dois_pontos + 1:]
    fim = _RE_FIM_LISTA.search(corpo)
    if fim:
        corpo = corpo[:fim.start()]
    # blocos separados por linha em branco (alguns PDFs listam assim, sem marcador)
    blocos, atual = [], []
    for l in corpo.splitlines():
        l = _limpa(l)
        if not l:
            if atual:
                blocos.append(atual)
                atual = []
        elif not _RE_LIXO_PDF.search(l):
            atual.append(l)
    if atual:
        blocos.append(atual)
    linhas = [l for b in blocos for l in b]
    entradas: list[str] = []
    if any(_RE_MARCADOR.match(l) for l in linhas):
        for l in linhas:
            if _RE_SO_SIGLA.match(l) and entradas:
                entradas[-1] = _limpa(entradas[-1] + " " + l)
            elif _RE_MARCADOR.match(l):
                entradas.append(_RE_MARCADOR.sub("", l, count=1))
            elif entradas and not entradas[-1].endswith((".", ";")):
                entradas[-1] = _limpa(entradas[-1] + " " + l)
            elif entradas:
                break   # linha sem marcador depois de item fechado: a lista acabou
    else:
        # sem marcador: itens separados por ";" ou por linha em branco, até o ponto final
        bloco = []
        for b in blocos:
            bloco.append(" ".join(b))
            if bloco[-1].endswith("."):
                break
        entradas = [e for b in bloco for e in re.split(r";\s*(?:e\s+)?", b)]
        if len(entradas) == 1 and len(linhas) > 1 and len(bloco) == 1:
            return []   # várias linhas sem separador: não dá para saber onde cada nome termina
        if any(re.match(r"(?:da|do|das|dos|de)\s", _limpa(e)) for e in entradas[1:]):
            return []   # frase corrida ("os Ministros X; da Fazenda, Y"), não é lista
    out = []
    for e in entradas:
        e = re.sub(r"(?:;\s*e|;|,\s*e|\.)$", "", _limpa(e)).strip(" ;,")
        if len(e) > 2:
            out.append(e)
    if not out or len(out) > 40 or any(len(e) > 300 for e in out):
        return []
    return out


def _anexar_convidados(pares: list[tuple[dict, callable]]) -> None:
    """Para cada (item, função que acha a URL do texto), lê o PDF e grava item['convidados']."""
    def um(par):
        item, achar_url = par
        try:
            url = achar_url()
            conv = convidados_do_requerimento(_texto_pdf(url)) if url else []
        except Exception:
            return
        if conv:
            item["convidados"] = conv
            # a ementa da Câmara às vezes repete a lista; fica só a frase de abertura
            corte = re.search(r"\s*[•\uf0b7]", item.get("ementa") or "")
            if corte:
                item["ementa"] = re.sub(r":$", ".", item["ementa"][:corte.start()].rstrip())
    with ThreadPoolExecutor(PARALELO) as ex:
        list(ex.map(um, pares))


# ─── Senado ──────────────────────────────────────────────────────────────────

def _parecer_senado(txt: str) -> str:
    t = _limpa(txt).rstrip(".")
    return _maiuscula(t) + "." if t else ""


def _convidado_senado(c: dict) -> str:
    nome = _limpa(c.get("nome"))
    if c.get("tratamento"):
        nome = f"{_limpa(c['tratamento'])} {nome}"
    if c.get("cargo"):
        nome += f", {_limpa(c['cargo'])}"
    return nome


def coletar_senado_comissoes(ini: dt.date, fim: dt.date) -> list[dict]:
    d = _get(f"{SENADO}/comissao/agenda/{ini:%Y%m%d}/{fim:%Y%m%d}.json") or {}
    reunioes = _lista(((d.get("AgendaReuniao") or {}).get("reunioes") or {}).get("reuniao"))
    itens, reqs = [], []
    for reu in reunioes:
        col = reu.get("colegiadoCriador") or {}
        sigla = col.get("sigla", "")
        inicio = reu.get("dataInicio") or ""
        obs = _limpa(reu.get("observacaoHorario"))
        base = {
            "casa": "SF", "dia": inicio[:10], "ordem": inicio[11:16],
            "hora": (obs[:1].lower() + obs[1:]) if obs else _hora(inicio[11:16]),
            "colegiado": f"{_limpa(col.get('nome')).rstrip('.').upper()} ({sigla})",
            "reuniaoLink": f"https://legis.senado.leg.br/atividade/comissoes/comissao/{col.get('codigo')}/reuniao/{reu.get('codigo')}",
            "situacao": _situacao(reu.get("situacao")),
        }
        base["reuniao"] = f"Reunião {_limpa((reu.get('tipo') or {}).get('descricao'))}".strip()
        partes = _lista(reu.get("partes"))
        if not partes:
            itens.append({**base, "id": f"SF-{reu.get('codigo')}", "tipo": "evento",
                          "rotulo": _limpa((reu.get("tipo") or {}).get("descricao")),
                          "titulo": _limpa(reu.get("titulo")), "tituloLink": base["reuniaoLink"], "ementa": ""})
            continue
        for parte in partes:
            rotulo = _limpa(parte.get("nome") or parte.get("descricaoTipo"))
            ev = parte.get("evento")
            if ev:
                tipo = "audiencia" if "audiência" in rotulo.lower() or "seminário" in rotulo.lower() else "evento"
                itens.append({**base, "id": f"SF-{reu.get('codigo')}-{parte.get('codigo')}", "tipo": tipo,
                              "reuniao": rotulo, "rotulo": rotulo, "titulo": rotulo, "tituloLink": base["reuniaoLink"],
                              "ementa": _limpa(ev.get("finalidade")),
                              "convidados": [_convidado_senado(c) for c in _lista(ev.get("convidados"))]})
            for it in _lista(parte.get("itens")):
                doma = it.get("doma") or {}
                autor = it.get("autorItemPauta") or {}
                parl = autor.get("parlamentar") or {}
                if parl.get("nome") and parl.get("partidoSigla"):
                    autoria = f"{parl['nome']} ({parl['partidoSigla']}/{parl.get('uf', '')})"
                else:
                    autoria = _sem_cargo(autor.get("nomeAutoria") or doma.get("autoria"))
                # relatoria aberta no colegiado; depois da votação ela fecha, então vale a mais recente
                rels = sorted((r.get("relator") or {} for r in _lista(doma.get("relatorias"))
                               if r.get("siglaColegiado") == sigla),
                              key=lambda r: (r.get("aberta") == "true", r.get("dataDesignacao") or ""))
                relator = ""
                if rels:
                    pa = rels[-1].get("parlamentar") or {}
                    relator = f"{_sem_cargo(pa.get('nomeComCargo'))} ({pa.get('siglaPartido')}/{pa.get('ufPartido')})"
                parecer_link = next((t.get("urlDownload") for t in _lista(it.get("textosPauta"))
                                     if t.get("siglaTipoDoma") == "RELATORIO"), "")
                cod = doma.get("codigoMateria")
                itens.append({**base, "id": f"SF-{reu.get('codigo')}-{it.get('codigo')}", "tipo": "materia",
                              "rotulo": rotulo, "titulo": _limpa(it.get("nome")),
                              "tituloLink": f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{cod}" if cod else "",
                              "ementa": _limpa(doma.get("ementa")), "autor": autoria, "relator": relator,
                              "parecer": _parecer_senado(it.get("relatorio")),
                              "parecerLink": parecer_link if it.get("relatorio") else ""})
                if cod and _limpa(it.get("nome")).startswith("REQ") and _pede_audiencia(itens[-1]["ementa"]):
                    reqs.append((itens[-1], lambda c=cod: _url_requerimento_senado(c)))
    _anexar_convidados(reqs)
    return itens


def coletar_senado_plenario(ini: dt.date, fim: dt.date) -> list[dict]:
    dias = [ini + dt.timedelta(days=i) for i in range((fim - ini).days + 1)]
    with ThreadPoolExecutor(PARALELO) as ex:
        agendas = list(ex.map(lambda d: _get(f"{SENADO}/plenario/agenda/dia/{d:%Y%m%d}.json") or {}, dias))
    itens = []
    for ag in agendas:
        for s in _lista(((ag.get("AgendaPlenario") or {}).get("Sessoes") or {}).get("Sessao")):
            cod = s.get("CodigoSessao")
            base = {
                "casa": "SF", "dia": s.get("Data"), "ordem": s.get("Hora") or "", "hora": _hora(s.get("Hora") or "00:00"),
                "colegiado": "PLENÁRIO (CONGRESSO NACIONAL)" if s.get("Casa") == "CN" else "PLENÁRIO",
                "reuniaoLink": f"https://www25.senado.leg.br/web/atividade/sessao-plenaria/-/pauta/{cod}",
                "situacao": _situacao(s.get("SituacaoSessao")),
            }
            tipo_sessao = _limpa(s.get("TipoSessao")).capitalize()
            base["reuniao"] = tipo_sessao
            ev = s.get("Evento") or {}
            if ev.get("DescricaoEvento"):
                titulo = _limpa(ev.get("DescricaoTipoEvento")).capitalize() or tipo_sessao
                itens.append({**base, "id": f"SF-PLEN-{cod}", "tipo": "evento", "rotulo": titulo,
                              "titulo": titulo, "tituloLink": base["reuniaoLink"],
                              "ementa": _limpa(ev.get("DescricaoEvento"))})
            for n, m in enumerate(_lista((s.get("Materias") or {}).get("Materia")), 1):
                cm = m.get("CodigoMateria")
                itens.append({**base, "id": f"SF-PLEN-{cod}-{n}", "tipo": "materia", "rotulo": tipo_sessao,
                              "titulo": _limpa(m.get("DescricaoIdentificacaoMateria")),
                              "tituloLink": f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{cm}" if cm else "",
                              "ementa": _limpa(m.get("Ementa")), "autor": _limpa(m.get("NomeAutor")),
                              "parecer": _limpa(m.get("Parecer"))})
    return itens


def coletar_semana(ini: dt.date, fim: dt.date) -> dict:
    """Pauta das duas Casas entre ini e fim (inclusive). Uma Casa fora do ar não derruba a outra."""
    itens, erros = [], []
    for nome, fn in (("Câmara", coletar_camara), ("Senado (comissões)", coletar_senado_comissoes),
                     ("Senado (plenário)", coletar_senado_plenario)):
        try:
            itens += fn(ini, fim)
        except Exception as e:
            erros.append(f"{nome}: {e}")
    itens = [i for i in itens if ini.isoformat() <= (i.get("dia") or "") <= fim.isoformat()]
    itens.sort(key=lambda i: (i["dia"], i["casa"], i.get("ordem", ""), i["reuniaoLink"]))
    dias = sorted({(ini + dt.timedelta(days=k)).isoformat() for k in range((fim - ini).days + 1)
                   if (ini + dt.timedelta(days=k)).weekday() < 5} | {i["dia"] for i in itens})
    return {"periodo": periodo_extenso(ini, fim), "dias": dias, "itens": itens, "erros": erros}


# ─── Word ────────────────────────────────────────────────────────────────────
# Segue o modelo "Modelo - AGENDA SEMANAL - Saúde.docx" (out/2026): tabela com uma
# faixa vinho por dia; dentro, Casa, colegiado, tipo da reunião com a hora e as
# matérias em lista com Autoria, Relatoria e Parecer recuados embaixo.

F = '<w:rFonts w:ascii="Montserrat" w:cs="Montserrat" w:eastAsia="Montserrat" w:hAnsi="Montserrat"/>'
S9 = '<w:sz w:val="18"/><w:szCs w:val="18"/>'
B = '<w:b w:val="1"/><w:bCs w:val="1"/>'
LINK = '<w:color w:val="1155cc"/>'
U = '<w:u w:val="single"/>'
CASAS = [("CD", "Câmara dos Deputados"), ("SF", "Senado Federal"), ("EX", "Poder Executivo")]
PPR = '<w:widowControl w:val="0"/><w:spacing w:line="240" w:lineRule="auto"/>'
NUM_MATERIA, NUM_CONVIDADO = 5, 6   # listas com marcador do modelo


class _Doc:
    def __init__(self):
        self.rels: list[tuple[str, str]] = []

    def rid(self, url: str) -> str:
        rid = f"rIdAg{len(self.rels) + 1}"
        self.rels.append((rid, url))
        return rid

    @staticmethod
    def run(text: str, rpr: str = F + S9) -> str:
        return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'

    def link(self, text: str, url: str, bold: bool = False) -> str:
        if not url:
            return self.run(text, F + (B if bold else "") + S9)
        return (f'<w:hyperlink r:id="{self.rid(url)}">'
                + self.run(text, F + (B if bold else "") + LINK + S9 + U) + "</w:hyperlink>")

    @staticmethod
    def p(runs: str = "", extra: str = "") -> str:
        return f'<w:p><w:pPr>{PPR}{extra}<w:jc w:val="both"/><w:rPr>{F}{S9}</w:rPr></w:pPr>{runs}</w:p>'

    @staticmethod
    def bullet(runs: str, num: int) -> str:
        return _Doc.p(runs, f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>'
                            '<w:ind w:left="720" w:hanging="360"/>')

    @staticmethod
    def recuo(runs: str = "") -> str:
        return _Doc.p(runs, '<w:ind w:left="720" w:firstLine="0"/>')

    def negrito(self, text: str) -> str:
        return self.p(self.run(text, F + B + S9))


def _cell(content: str, header: bool = False) -> str:
    shd = "97304e" if header else "auto"
    bd = "".join(f'<w:{s} w:color="b84349" w:space="0" w:sz="8" w:val="single"/>' for s in ("top", "left", "bottom", "right"))
    mar = "".join(f'<w:{s} w:w="100.0" w:type="dxa"/>' for s in ("top", "left", "bottom", "right"))
    return (f'<w:tr><w:trPr><w:cantSplit w:val="0"/><w:tblHeader w:val="0"/></w:trPr><w:tc><w:tcPr>'
            f'<w:tcBorders>{bd}</w:tcBorders><w:shd w:fill="{shd}" w:val="clear"/><w:tcMar>{mar}</w:tcMar>'
            f'<w:vAlign w:val="top"/></w:tcPr>{content}</w:tc></w:tr>')


def _rotulado(d: _Doc, rotulo: str, valor: str, url: str = "") -> str:
    return d.recuo(d.run(f"{rotulo}: ", F + B + S9) + (d.link(valor, url) if url else d.run(valor)))


def _item_xml(d: _Doc, it: dict) -> list[str]:
    t = it.get("tipo")
    if t == "materia":
        out = [d.bullet(d.link(f'{it["titulo"]}:', it.get("tituloLink"), bold=True)
                        + d.run(" " + (it.get("ementa") or "")), NUM_MATERIA)]
        if it.get("autor"):
            out.append(_rotulado(d, "Autoria", it["autor"]))
        if it.get("relator"):
            out.append(_rotulado(d, "Relatoria", it["relator"]))
        if it.get("parecer"):
            out.append(_rotulado(d, "Parecer", it["parecer"], it.get("parecerLink")))
        if it.get("convidados"):
            out.append(d.recuo(d.run("Convidados:", F + B + S9)))
            out += _lista_convidados(d, it["convidados"])
        return out
    if t == "audiencia":
        out = [d.p(d.run(it.get("ementa") or it.get("titulo") or ""))]
    else:
        txt = d.link(it["titulo"], it.get("tituloLink"), bold=True)
        if it.get("ementa") and it["ementa"] != it["titulo"]:
            txt += d.run(" - " + it["ementa"])
        out = [d.p(txt)]
    if it.get("convidados"):
        out += [d.p(), d.negrito("Participantes confirmados:")]
        out += _lista_convidados(d, it["convidados"])
    return out


def _lista_convidados(d: _Doc, conv: list[str]) -> list[str]:
    fins = ["." if i == len(conv) - 1 else ("; e" if i == len(conv) - 2 else ";") for i in range(len(conv))]
    return [d.bullet(d.run(c + f), NUM_CONVIDADO) for c, f in zip(conv, fins)]


def _heading(text: str) -> str:
    rpr = F + B + '<w:color w:val="962e4d"/><w:sz w:val="20"/><w:szCs w:val="20"/>'
    return (f'<w:p><w:pPr>{PPR}<w:jc w:val="both"/><w:rPr>{F}{S9}</w:rPr></w:pPr>'
            f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


def _tabela(d: _Doc, modelo_doc: str, dias: list[str], itens: list[dict]) -> str:
    rows = []
    for iso in dias:
        data = dt.date.fromisoformat(iso)
        nome = DIAS_SEMANA[data.weekday()]
        hrpr = F + B + '<w:color w:val="ffffff"/><w:sz w:val="24"/><w:szCs w:val="24"/>'
        rows.append(_cell(f'<w:p><w:pPr>{PPR}<w:jc w:val="both"/></w:pPr><w:r><w:rPr>{hrpr}</w:rPr>'
                          f'<w:t xml:space="preserve">{nome} ({data:%d.%m})</w:t></w:r></w:p>', header=True))
        body = []
        for casa, casa_nome in CASAS:
            if body:
                body.append(_Doc.p())
            body += [_heading(casa_nome), _Doc.p()]
            do_dia = [i for i in itens if i["dia"] == iso and i["casa"] == casa]
            if not do_dia:
                body.append(_Doc.p(d.run(f"Sem destaques para a {nome.lower()}.")))
                continue
            grupos: dict[tuple, list] = {}
            for i in do_dia:
                grupos.setdefault((i.get("ordem", ""), i["reuniaoLink"]), []).append(i)
            colegiado_ant = None
            for k, (_, gi) in enumerate(sorted(grupos.items(), key=lambda kv: kv[0])):
                g = gi[0]
                if k:
                    body.append(_Doc.p())
                if g["colegiado"] != colegiado_ant:
                    body += [d.negrito(nome_colegiado(g["colegiado"])), _Doc.p()]
                    colegiado_ant = g["colegiado"]
                reuniao = g.get("reuniao") or g.get("rotulo") or ""
                hora = g.get("hora") or ""
                linha = f"{reuniao} - {hora}" if reuniao and hora else (reuniao or hora)
                if linha:
                    body += [d.negrito(linha), _Doc.p()]
                for j, it in enumerate(gi):
                    if j:
                        body.append(_Doc.recuo() if it.get("tipo") == "materia" else _Doc.p())
                    body += _item_xml(d, it)
        rows.append(_cell("".join(body)))
    tblpr = re.search(r"<w:tblPr>.*?(?=<w:tr[ >])", modelo_doc, re.S).group(0)
    return f"<w:tbl>{tblpr}{''.join(rows)}</w:tbl>"


def nome_arquivo(cliente: str, dias: list[str]) -> str:
    ini, fim = dt.date.fromisoformat(dias[0]), dt.date.fromisoformat(dias[-1])
    return f"Agenda da Semana - {cliente} {ini:%d.%m} a {fim:%d.%m}.docx"


def gerar_docx(modelo: bytes, cliente: str, periodo: str, dias: list[str], itens: list[dict]) -> bytes:
    zin = zipfile.ZipFile(io.BytesIO(modelo))
    doc = zin.read("word/document.xml").decode("utf8")
    rels = zin.read("word/_rels/document.xml.rels").decode("utf8")
    rels = re.sub(r'<Relationship [^>]*TargetMode="External"[^>]*/>', "", rels)
    rels = re.sub(r'<Relationship [^>]*relationships/hyperlink"[^>]*/>', "", rels)
    d = _Doc()
    corte = doc.index("<w:tbl>")
    titulo = escape(f"{cliente} | {periodo}")
    novo = re.sub(r"(<w:t(?: [^>]*)?>)[^<]*\|[^<]*(</w:t>)", lambda m: m.group(1) + titulo + m.group(2),
                  doc[:corte], count=1) + doc[corte:]
    tbl = _tabela(d, doc, dias, itens)
    novo = re.sub(r"<w:tbl>.*</w:tbl>", lambda m: tbl, novo, count=1, flags=re.S)
    extra = "".join(f'<Relationship Id="{r}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                    f'relationships/hyperlink" Target="{escape(u, {chr(34): "&quot;"})}" TargetMode="External"/>'
                    for r, u in d.rels)
    rels = rels.replace("</Relationships>", extra + "</Relationships>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "word/document.xml":
                data = novo.encode("utf8")
            elif info.filename == "word/_rels/document.xml.rels":
                data = rels.encode("utf8")
            zout.writestr(zipfile.ZipInfo(info.filename, info.date_time), data, zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def gerar_pacote(modelo: bytes, semana: dict, selecao: dict[str, list[str]]) -> tuple[bytes, dict[str, int]]:
    """Zip com um .docx por cliente que tenha ao menos um item marcado."""
    contagem = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for cli in CLIENTES:
            itens = [i for i in semana["itens"] if cli in selecao.get(i["id"], []) and not i.get("situacao")]
            if not itens:
                continue
            contagem[cli] = len(itens)
            z.writestr(nome_arquivo(cli, semana["dias"]),
                       gerar_docx(modelo, cli, semana["periodo"], semana["dias"], itens))
    return buf.getvalue(), contagem
