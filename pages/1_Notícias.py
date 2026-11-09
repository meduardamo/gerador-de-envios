"""Notícias: o feed raspado pelo eixo-eleicoes, com alerta pronto para o WhatsApp.

Mesma aba do painel-eleitoral-interno (pages/5_Notícias.py), no visual do
EixoGov. Lê a aba `noticias` da planilha de coleta (secret COLETA_SHEET_ID) com a
conta de serviço do app (GOOGLE_SHEETS_CREDS), e grava nela só duas coisas: a
marca de visto e o texto do alerta salvo. As regras de cabeçalho e escopo
espelham o scraper (outros/noticias_eleicoes_scraper.py): mudou lá, mudar aqui e
no painel interno.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

from base_pagina import exigir_login, iniciar
from estilo_paginas import BORDA, MARINHO, MUDO, VINHO, cabecalho, esc, resumo, secao, vazio

iniciar("Notícias")

APP_TZ = timezone(timedelta(hours=-3))
CACHE_TTL_MIN = 10

st.markdown(f"""<style>
.block-container, [data-testid="stMainBlockContainer"] {{ max-width: 1320px !important; padding: 1.8rem 2.5rem 4rem !important; }}
.nt-card {{ background: #fff; border: 1px solid {BORDA}; border-radius: 8px; padding: 11px 15px; }}
.nt-card.visto {{ background: #F7F6F2; }}
.nt-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }}
.nt-tit {{ font-size: 14px; font-weight: 700; color: {MARINHO}; line-height: 1.4; }}
.nt-tit a, .nt-tit a:visited {{ color: {MARINHO} !important; text-decoration: none !important; }}
.nt-tit a:hover {{ color: {VINHO} !important; text-decoration: underline !important; text-underline-offset: 3px; }}
.nt-selos {{ display: flex; gap: 4px; flex-shrink: 0; }}
.nt-selo {{ display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; white-space: nowrap; line-height: 1.6; }}
.nt-selo.alerta {{ background: {VINHO}; color: #fff; }}
.nt-selo.repetido {{ background: #fff; color: {MUDO}; border: 1px solid {BORDA}; }}
.nt-meta {{ font-size: 12px; color: #6A6A66; margin-top: 4px; line-height: 1.5; }}
.nt-meta a {{ color: inherit; }}
.nt-tipo {{ display: inline-flex; align-items: center; gap: 5px; font-weight: 700; color: #222; }}
.nt-tipo i {{ display: inline-block; width: 9px; height: 9px; border-radius: 3px; }}
[data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{ display: none; }}
</style>""", unsafe_allow_html=True)

authenticator = exigir_login()

cabecalho("Notícias",
          "Notícias de eleição e transição de governo raspadas e classificadas a cada rodada, "
          "da mais recente para a mais antiga. O envelope gera o alerta para o WhatsApp.")

with st.sidebar:
    st.markdown(
        '<div style="border-left:3px solid #962E4D;padding:10px 12px;'
        'margin:10px 0 0 0;background:transparent;">'
        '<p style="font-family:Montserrat,sans-serif;font-size:12.5px;'
        'color:#111;line-height:1.65;margin:0;">'
        'Monitoramento de <strong>notícias</strong> sobre eleições e transição de governo, '
        'raspadas e classificadas automaticamente.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("Atualizar dados", icon=":material/refresh:", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** "
               f"({st.session_state.get('username', '')})")
    authenticator.logout("Sair", "sidebar")


def secret_value(*names: str) -> str:
    for name in names:
        try:
            value = st.secrets.get(name, "")
        except Exception:
            value = ""
        value = value or os.getenv(name, "")
        if str(value).strip():
            return str(value).strip()
    return ""


# ─── Normalização de partido/candidato ─────────────────────────────────────────
# O Gemini (no scraper) extrai esses campos em texto livre, o que gera variações
# pra mesma coisa ("PSol", "PSOL-Rede", "PSOL/Rede" viram "PSOL/REDE"). Aplicado
# aqui em vez de reescrever a planilha, então cobre os dados antigos.
_PARTIDO_ALIAS = {
    "UNIAO": "UNIÃO",
    "UNIÃO BRASIL": "UNIÃO", "UNIAO BRASIL": "UNIÃO",
    "UNIÃO PROGRESSISTA": "UNIÃO/PP", "UNIAO PROGRESSISTA": "UNIÃO/PP",
    "UNIÃO/PROGRESSISTA": "UNIÃO/PP", "UNIAO/PROGRESSISTA": "UNIÃO/PP",
    "FEDERAÇÃO": "", "FEDERACAO": "",
}
_PARTIDO_VAZIO = {"", "NAN", "NONE", "NULL"}


def normalize_partido(raw) -> str:
    v = str(raw or "").strip()
    if not v:
        return ""
    key = re.sub(r"\s*[-/]\s*", "/", v.upper())
    if key in _PARTIDO_VAZIO:
        return ""
    return _PARTIDO_ALIAS.get(key, key)


_CANDIDATO_MINUSCULAS = {"de", "da", "do", "das", "dos", "e"}


def normalize_candidato(raw) -> str:
    v = re.sub(r"\s+", " ", str(raw or "")).strip()
    if not v or v.lower() in ("nan", "none", "null"):
        return ""
    palavras = []
    for p in v.split(" "):
        pl = p.lower()
        if pl in _CANDIDATO_MINUSCULAS:
            palavras.append(pl)
        elif p.isupper() and len(p) > 3:
            # só CAIXA ALTA de 4+ letras: preserva siglas curtas como "ACM", "JHC"
            palavras.append(pl.capitalize())
        else:
            palavras.append(p)
    return " ".join(palavras)


# ─── Cabeçalho e escopo do alerta (espelham o scraper) ─────────────────────────
TEMAS_EDUCACAO = ("educação",)


def _sem_acento_min(texto) -> str:
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()


def _cargo_do_fato(cargo: str = "", candidato: str = "") -> str:
    """Cargo da linha, mas Lula e Flávio Bolsonaro contam sempre como presidente."""
    # Pelo nome inteiro: "Cadu de Lula", governador eleito do RN, não é o presidente.
    cand = " ".join(re.findall(r"[a-z]+", _sem_acento_min(candidato)))
    if (cand in ("lula", "presidente lula", "luiz inacio lula da silva", "lula da silva")
            or cand.startswith("luiz inacio") or "flavio bolsonaro" in cand):
        return "presidente"
    return str(cargo or "").strip().lower()


_RE_TITULO_FEDERAL = re.compile(
    r"(?<!ex-)\bministr[oa]s?\b|\bministerios?\b(?!\s+publico)|\besplanada\b"
    r"|reforma ministerial|\blula 4\b"
    r"|(?<!secretaria da )(?<!secretario da )(?<!secretaria de )(?<!secretario de )(?<!de estado da )"
    r"\bfazenda\b(?!\s+(?:estadual\b|(?:do|de|da)\s+(?:estado|estadual|rio|sao paulo|minas|bahia|parana|goias|pernambuco|ceara|para|piaui|maranhao|alagoas|sergipe|paraiba|amazonas|acre|amapa|roraima|rondonia|tocantins|mato grosso|espirito santo|santa catarina|distrito federal|df|rs|sp|rj|mg|ba|pe|ce|go|pr|sc|es|ma|pa|pi|al|se|pb|am|ac|ap|rr|ro|to|mt|ms|rn)\b))")
# Sinal fraco: só faz a notícia federal quando ela não tem UF.
_RE_TITULO_FEDERAL_FRACO = re.compile(r"\bquarto mandato\b|governo lula")
_UF_POR_NOME = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
    "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}


def _uf_ajustada(uf, tema, titulo="", busca="") -> str:
    """Transição com título de ministério é federal (fica sem UF); transição sem
    UF que veio da busca de um estado fica com a UF desse estado."""
    uf = str(uf or "").strip().upper()
    uf = "" if uf in ("NAN", "NONE", "NULL") else uf
    if str(tema or "").strip().lower() != "transição":
        return uf
    if _RE_TITULO_FEDERAL.search(_sem_acento_min(titulo)) or (
            not uf and _RE_TITULO_FEDERAL_FRACO.search(_sem_acento_min(titulo))):
        return ""
    if not uf and '("equipe de transição"' in str(busca or ""):
        return _UF_POR_NOME.get(_sem_acento_min(str(busca).split(' ("equipe de transição"')[0]).strip(), "")
    return uf


def _uf_relevante(uf: str, cargo: str = "", alerta_tema: str = "", candidato: str = "") -> str:
    """UF que descreve o fato, não o veículo que publicou. Em notícia de
    presidente a UF só vale quando é pesquisa estadual ou visita."""
    uf = str(uf or "").strip().upper()
    if uf in ("", "NAN", "NONE", "NULL"):
        return ""
    if (_cargo_do_fato(cargo, candidato) == "presidente"
            and alerta_tema not in ("pesquisa-executivo", "visita-presidencial")):
        return ""
    return uf


def _escopo_alerta(uf: str, cargo: str = "", alerta_tema: str = "", candidato: str = "") -> str:
    """'Subnacional', 'Gov. Federal' ou vazio, pela mesma regra do cabeçalho."""
    if _uf_relevante(uf, cargo, alerta_tema, candidato):
        return "Subnacional"
    if (_cargo_do_fato(cargo, candidato) == "presidente"
            or str(alerta_tema or "").strip() == "transição"):
        return "Gov. Federal"
    return ""


def _montar_header_alerta(uf: str, cargo: str = "", alerta_tema: str = "",
                          candidato: str = "") -> str:
    """Alerta | EixoGov | Eleições/Educação/Transição | Subnacional | UF, ou Gov. Federal."""
    tema = str(alerta_tema or "").strip()
    assunto = ("Educação" if tema in TEMAS_EDUCACAO
               else "Transição" if tema == "transição" else "Eleições")
    escopo = _escopo_alerta(uf, cargo, alerta_tema, candidato)
    if escopo == "Subnacional":
        return (f"Alerta | EixoGov | {assunto} | Subnacional | "
                f"{_uf_relevante(uf, cargo, alerta_tema, candidato)}")
    if escopo:
        return f"Alerta | EixoGov | {assunto} | {escopo}"
    return f"Alerta | EixoGov | {assunto}"


# ─── Planilha ─────────────────────────────────────────────────────────────────
SHEET = secret_value("COLETA_SHEET_ID")
NOTICIAS_ABA = "noticias"
# texto_completo fica fora da carga (em 24/09 eram 149 MB só desse campo); é lido
# quando alguém abre o envelope.
_COLUNAS_FORA_DA_CARGA = {"texto_completo"}


def _creds_dict():
    try:
        if "GOOGLE_SHEETS_CREDS" in st.secrets:
            return dict(st.secrets["GOOGLE_SHEETS_CREDS"])
        if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
            raw = st.secrets["GOOGLE_CREDENTIALS_JSON"]
            return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        pass
    raw = os.getenv("GOOGLE_SHEETS_CREDS", "") or os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    return json.loads(raw) if raw else None


@st.cache_resource(show_spinner=False)
def _cliente_sheets():
    """Cliente com escrita: a página grava visto e resumo na aba de notícias."""
    info = _creds_dict()
    if not info:
        return None
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds)


_DEFINITIVOS = ("worksheetnotfound", "spreadsheetnotfound", "404", "403", "400", "permission")


def _com_retry(fn, descricao: str):
    """Repete em falha transitória do Sheets (quota, 5xx, rede); levanta se não der."""
    ultimo = None
    for tentativa in range(1, 4):
        try:
            return fn()
        except Exception as e:
            ultimo = e
            if any(t in f"{type(e).__name__} {e}".lower() for t in _DEFINITIVOS) or tentativa == 3:
                break
            time.sleep(0.6 * tentativa)
    raise RuntimeError(f"{descricao}: {ultimo}")


def _letra_coluna(n: int) -> str:
    letra = ""
    while n:
        n, r = divmod(n - 1, 26)
        letra = chr(65 + r) + letra
    return letra


def _aba_noticias():
    client = _cliente_sheets()
    if client is None:
        raise RuntimeError("sem credencial do Sheets")
    return client.open_by_key(SHEET).worksheet(NOTICIAS_ABA)


@st.cache_data(ttl=CACHE_TTL_MIN * 60, show_spinner=False)
def _carregar_noticias_cache(sheet_id: str) -> pd.DataFrame:
    """Lê a aba por coluna, sem texto_completo, e guarda a linha da planilha em _linha.

    Levanta em falha, para o cache não guardar o erro.
    """
    client = _cliente_sheets()
    if client is None:
        raise RuntimeError("sem credencial do Sheets")
    sh = _com_retry(lambda: client.open_by_key(sheet_id), "abrir a planilha")
    ws = _com_retry(lambda: sh.worksheet(NOTICIAS_ABA), "abrir a aba de notícias")
    headers = _com_retry(lambda: ws.row_values(1), "ler o cabeçalho")
    quero = [(i, h) for i, h in enumerate(headers, start=1)
             if h.strip() and h.strip() not in _COLUNAS_FORA_DA_CARGA]
    faixas = [f"'{NOTICIAS_ABA}'!{_letra_coluna(i)}:{_letra_coluna(i)}" for i, _ in quero]
    resp = _com_retry(lambda: sh.values_batch_get(faixas, params={"majorDimension": "COLUMNS"}),
                      "ler as colunas de notícias")
    colunas = [(vr.get("values") or [[]])[0] for vr in resp.get("valueRanges", [])]
    total = max((len(c) for c in colunas), default=0)
    # Leitura que volta sem linhas é falha, não aba vazia (senão fica no cache).
    if total < 2:
        raise RuntimeError("a leitura voltou sem linhas")
    cab = [h.strip() for _, h in quero] + ["_linha"]
    linhas = [[c[j] if j < len(c) else "" for c in colunas] + [str(j + 1)] for j in range(1, total)]
    return pd.DataFrame(linhas, columns=cab)


def carregar_noticias(sheet_id: str) -> pd.DataFrame:
    if not sheet_id:
        st.session_state["_noticias_erro"] = "planilha de notícias não configurada"
        return pd.DataFrame()
    # Na segunda tentativa o cliente do Sheets é refeito: um cliente quebrado
    # guardado no processo fazia a página falhar até o reboot do app.
    for tentativa in (1, 2):
        try:
            st.session_state.pop("_noticias_erro", None)
            return _carregar_noticias_cache(sheet_id)
        except Exception as e:
            print(f"[noticias] falha ao carregar (tentativa {tentativa}): {e!r}", flush=True)
            st.session_state["_noticias_erro"] = f"{type(e).__name__}: {e}"
            _cliente_sheets.clear()
    return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def _texto_completo_da_linha(sheet_id: str, linha: str, link: str) -> str:
    """texto_completo de uma notícia, lido na hora.

    Vai na linha guardada na carga e confere o link (o scraper insere no topo e a
    linha pode ter descido). Se não bater, procura o link na coluna inteira.
    Vazio quando não achar: aí o alerta lê a página da notícia.
    """
    try:
        ws = _aba_noticias()
        headers = ws.row_values(1)
        if "texto_completo" not in headers or "link" not in headers:
            return ""
        c_texto = headers.index("texto_completo") + 1
        c_link = headers.index("link") + 1
        n = int(linha) if str(linha).isdigit() else 0
        if n:
            vals = ws.batch_get([f"{_letra_coluna(c_link)}{n}", f"{_letra_coluna(c_texto)}{n}"])
            _link_na_linha = (vals[0][0][0] if vals[0] and vals[0][0] else "").strip()
            _texto = (vals[1][0][0] if vals[1] and vals[1][0] else "").strip()
            if _link_na_linha == link and _texto:
                return _texto
        _linhas = [j for j, v in enumerate(ws.col_values(c_link), start=1) if v.strip() == link]
        if not _linhas:
            return ""
        for v in ws.batch_get([f"{_letra_coluna(c_texto)}{j}" for j in _linhas]):
            if v and v[0] and v[0][0].strip():
                return v[0][0].strip()
        return ""
    except Exception as e:
        print(f"[noticias] texto_completo não lido: {e}", flush=True)
        return ""


def _salvar_resumo_planilha(link: str, texto: str) -> str | None:
    """Grava o alerta na coluna 'resumo' da linha do link. Devolve o link da linha ou None."""
    if not link:
        return None
    try:
        ws = _aba_noticias()
        headers = ws.row_values(1)
        if "link" not in headers or "resumo" not in headers:
            return None
        cell = ws.find(link, in_column=headers.index("link") + 1)
        if not cell:
            return None
        ws.update_cell(cell.row, headers.index("resumo") + 1, texto)
        _carregar_noticias_cache.clear()
        return f"https://docs.google.com/spreadsheets/d/{SHEET}/edit#gid={ws.id}&range=A{cell.row}"
    except Exception:
        return None


def _marcar_visto_planilha(link: str, valor: str) -> bool:
    """Grava 'visto'/'não visto' na coluna 'visto' da linha do link."""
    if not link:
        return False
    try:
        ws = _aba_noticias()
        headers = ws.row_values(1)
        if "link" not in headers:
            return False
        if "visto" not in headers:
            if len(headers) + 1 > ws.col_count:
                ws.add_cols(len(headers) + 1 - ws.col_count)
            ws.update_cell(1, len(headers) + 1, "visto")
            headers = headers + ["visto"]
        cell = ws.find(link, in_column=headers.index("link") + 1)
        if not cell:
            return False
        ws.update_cell(cell.row, headers.index("visto") + 1, valor)
        return True
    except Exception:
        return False


# ─── Carga ────────────────────────────────────────────────────────────────────
with st.spinner("Carregando notícias…"):
    df = carregar_noticias(SHEET)

if df.empty:
    vazio("Não consegui carregar as notícias agora. Clique em Atualizar dados na barra lateral; "
          "se continuar assim, avise a equipe de dados.")
    if st.session_state.get("_noticias_erro"):
        st.caption(f"Erro: {st.session_state['_noticias_erro'][:300]}")
    st.stop()

df.columns = [str(c).strip().lower() for c in df.columns]

# Visto marcado nesta sessão: aplica por cima sem esperar o cache expirar.
_visto_overrides = st.session_state.setdefault("_visto_overrides", {})
if _visto_overrides:
    if "visto" not in df.columns:
        df["visto"] = ""
    if "link" in df.columns:
        _link_norm = df["link"].astype(str).str.strip()
        for _link_ov, _valor_ov in _visto_overrides.items():
            df.loc[_link_norm == _link_ov, "visto"] = _valor_ov

if "data" in df.columns:
    _dt = pd.to_datetime(df["data"], errors="coerce", dayfirst=True)
    if _dt.isna().all():
        _dt = pd.to_datetime(df["data"], errors="coerce")
    df["_data"] = _dt
else:
    df["_data"] = pd.NaT

# Notícia que o classificador marcou como sem relação com política brasileira some sempre.
if "status" in df.columns:
    df = df[df["status"].astype(str).str.strip().str.lower() != "não relacionado"].copy()

# Assunto da notícia (coluna tipo): cor fixa por tipo, para o selo dizer sempre a mesma coisa.
_TIPO_COR = {
    "transição": "#2a9d8f", "agenda": "#6091d8", "pesquisa": MARINHO,
    "debate": "#9bd0b7", "aliança": "#d5b6d5", "apoio": "#d8be6a",
    "crítica-educação": VINHO, "proposta-educação": "#c98a00",
    "fato-eleitoral": "#b84349", "impugnação": "#7d5a8c",
    "visita-presidencial": "#3e4a5e",
}
_TIPO_ROTULO = {
    "transição": "Transição", "agenda": "Agenda", "pesquisa": "Pesquisa",
    "debate": "Debate", "aliança": "Aliança", "apoio": "Apoio",
    "crítica-educação": "Crítica à educação", "proposta-educação": "Proposta para educação",
    "fato-eleitoral": "Fato eleitoral", "impugnação": "Impugnação",
    "visita-presidencial": "Visita presidencial",
}


def _vals(col: str, base: pd.DataFrame | None = None) -> list:
    base = df if base is None else base
    if col not in base.columns:
        return []
    return sorted({str(v).strip() for v in base[col] if str(v).strip() and str(v).strip().lower() != "nan"})


# ─── Filtros ──────────────────────────────────────────────────────────────────
PERIODOS_DIA = [
    ("Madrugada (antes das 7h)", 0, 7),
    ("Manhã (7h–12h)", 7, 12),
    ("Tarde (12h–16h)", 12, 16),
    ("Fim de tarde/noite (após 16h)", 16, 24),
]
_UF_TODAS, _UF_NAC = "Todas as UFs", "Nacional / sem UF"

with st.expander("Filtros", expanded=False):
    _uf_series = (df["uf"].astype(str).str.strip().str.upper() if "uf" in df.columns
                  else pd.Series("", index=df.index))
    _sem_uf = (_uf_series == "") | (_uf_series == "NAN")
    _uf_opts = ([_UF_TODAS] + sorted({u for u in _uf_series if u and u != "NAN"})
                + ([_UF_NAC] if _sem_uf.any() else []))

    c1, c2, c3, c4 = st.columns(4)
    f_uf = c1.selectbox("UF", _uf_opts, key="nt_uf")
    f_escopo = c2.selectbox("Escopo", ["Todos", "Gov. Federal", "Subnacional"], key="nt_escopo")
    f_alerta = c3.selectbox("Alerta", ["Todas", "Só alertas", "Alertas e já alertados", "Sem alerta"],
                            key="nt_alerta",
                            help="Já alertado: mesmo fato de um alerta das últimas 48h, saído em outro veículo.")
    f_visto = c4.selectbox("Já vista?", ["Todas", "Só vistas", "Só não vistas"], key="nt_visto")

    # As pessoas citadas dependem da UF escolhida.
    _df_uf = df if f_uf == _UF_TODAS else df[_sem_uf] if f_uf == _UF_NAC else df[_uf_series == f_uf]
    _op_cand = sorted({v for v in (normalize_candidato(x) for x in _df_uf.get("candidato", [])) if v})
    _op_partido = sorted({v for v in (normalize_partido(x) for x in df.get("partido", [])) if v})
    # Debate saiu em 27/10/2026: sem eleição pela frente, a raspagem não marca mais.
    _op_tipo = [t for t in _vals("tipo") if t != "debate"]

    c1, c2, c3, c4 = st.columns(4)
    f_tipo = c1.multiselect("Tipo", _op_tipo, format_func=lambda t: _TIPO_ROTULO.get(t, t),
                            placeholder="Todos", key="nt_tipo")
    f_cargo = c2.multiselect("Cargo", _vals("cargo"), placeholder="Todos", key="nt_cargo")
    f_partido = c3.multiselect("Partido", _op_partido, placeholder="Todos", key="nt_partido")
    f_cand = c4.multiselect("Nome", _op_cand, placeholder="Todos", key="nt_cand")

    c1, c2 = st.columns([1, 3])
    f_horario = c1.multiselect("Horário", [p[0] for p in PERIODOS_DIA], placeholder="Todos",
                               key="nt_horario")
    f_busca = c2.text_input("Buscar no título", placeholder="palavra-chave…", key="nt_busca")

    view = df.copy()
    if f_uf != _UF_TODAS and "uf" in view.columns:
        _ufn = view["uf"].astype(str).str.strip().str.upper()
        view = view[((_ufn == "") | (_ufn == "NAN")) if f_uf == _UF_NAC else (_ufn == f_uf)]
    if f_cargo and "cargo" in view.columns:
        view = view[view["cargo"].astype(str).str.strip().isin(f_cargo)]
    if f_partido and "partido" in view.columns:
        view = view[view["partido"].map(normalize_partido).isin(f_partido)]
    if f_tipo and "tipo" in view.columns:
        view = view[view["tipo"].astype(str).str.strip().isin(f_tipo)]
    if f_cand and "candidato" in view.columns:
        view = view[view["candidato"].map(normalize_candidato).isin(f_cand)]
    if f_busca.strip() and "titulo" in view.columns:
        view = view[view["titulo"].astype(str).str.contains(f_busca.strip(), case=False, na=False, regex=False)]
    if f_alerta != "Todas":
        _alertan = (view["alerta"].astype(str).str.strip().str.lower()
                    if "alerta" in view.columns else pd.Series("", index=view.index))
        if f_alerta == "Só alertas":
            view = view[_alertan == "sim"]
        elif f_alerta == "Alertas e já alertados":
            view = view[_alertan.isin(["sim", "repetido"])]
        else:
            view = view[~_alertan.isin(["sim", "repetido"])]
    if f_escopo != "Todos":
        _col = lambda c: view[c] if c in view.columns else pd.Series("", index=view.index)
        _esc = []
        for u, c, t, tp, k, ti, b in zip(_col("uf"), _col("cargo"), _col("alerta_tema"),
                                         _col("tipo"), _col("candidato"), _col("titulo"),
                                         _col("busca")):
            _t = (str(t).strip() if str(t).strip().lower() != "nan" else "") or str(tp).strip().lower()
            _esc.append(_escopo_alerta(_uf_ajustada(u, _t, ti, b), c, _t, k))
        view = view[[e == f_escopo for e in _esc]]
    if f_visto != "Todas":
        _vistn = (view["visto"].astype(str).str.strip().str.lower() if "visto" in view.columns
                  else pd.Series("", index=view.index))
        view = view[(_vistn == "visto") if f_visto == "Só vistas" else (_vistn != "visto")]
    if f_horario and view["_data"].notna().any():
        _hora = view["_data"].dt.hour
        _mask = pd.Series(False, index=view.index)
        for _label, _h0, _h1 in PERIODOS_DIA:
            if _label in f_horario:
                _mask = _mask | ((_hora >= _h0) & (_hora < _h1))
        view = view[_mask]

    if view["_data"].notna().any():
        _dmin = view["_data"].min().date()
        _dmax = view["_data"].max().date()
        _modo_periodo = st.radio("Período", ["Intervalo", "Um único dia"], horizontal=True, key="nt_modo")
        if _modo_periodo == "Um único dia":
            _dia_sel = st.date_input("Dia", min_value=_dmin, max_value=_dmax, value=_dmax,
                                     format="DD/MM/YYYY", key="nt_dia")
            view = view[view["_data"].dt.date == _dia_sel]
        elif _dmin < _dmax:
            periodo = st.slider("Intervalo", min_value=_dmin, max_value=_dmax, value=(_dmin, _dmax),
                                format="DD/MM/YYYY", label_visibility="collapsed", key="nt_periodo")
            view = view[(view["_data"].dt.date >= periodo[0]) & (view["_data"].dt.date <= periodo[1])]

# ─── Resumo ───────────────────────────────────────────────────────────────────
n_cands = (len({v for v in (normalize_candidato(x) for x in view["candidato"]) if v})
           if "candidato" in view.columns else 0)
n_fontes = (view["fonte"].astype(str).str.strip().replace("", pd.NA).nunique()
            if "fonte" in view.columns else 0)
n_alertas = (int((view["alerta"].astype(str).str.strip().str.lower() == "sim").sum())
             if "alerta" in view.columns else 0)
_per = (f'{view["_data"].min().strftime("%d/%m")} a {view["_data"].max().strftime("%d/%m/%Y")}'
        if view["_data"].notna().any() else "")
resumo([(len(view), " notícias"), (n_alertas, " alertas"), (n_cands, " pessoas citadas"),
        (n_fontes, " fontes")] + ([(_per, "")] if _per else []))
st.caption(f"Atualiza a cada {CACHE_TTL_MIN} min · carregado às {datetime.now(APP_TZ).strftime('%H:%M')}")

if view.empty:
    vazio("Nenhuma notícia para os filtros escolhidos.")
    st.stop()

# ─── Alerta (Gemini) e envio no WhatsApp ───────────────────────────────────────
GEMINI_MODEL = "gemini-3.6-flash"   # 2.5-flash dá 404 para a chave do projeto novo

REGRAS_POLITICOS_ALERTA = (
    "Formatação de políticos (obrigatório):\n"
    "- Formato: 'Nome (PARTIDO/UF)'. Use barra, nunca hífen entre PARTIDO e UF.\n"
    "- Se partido/UF não estiverem na notícia, não invente.\n"
    "- PRIMEIRA menção de um político: use 'Nome (PARTIDO/UF)'. Menções seguintes: só o nome.\n"
)

_CLIENT = None


def _gemini_client():
    # Guardado num global: o Client do google-genai fecha a conexão no __del__,
    # então um cliente temporário morre antes da chamada sair.
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    from google import genai
    key = secret_value("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Faltou a GEMINI_API_KEY.")
    _CLIENT = genai.Client(api_key=key)
    return _CLIENT


def _extrair_texto_noticia(url: str, limite: int = 4000) -> str:
    """Texto visível da página da notícia, para quando a planilha não tem o texto."""
    import requests
    if not url or not url.startswith("http"):
        return ""
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        resp.raise_for_status()
        html = re.sub(r"(?is)<(script|style|nav|header|footer|aside|form)[^>]*>.*?</\1>", " ", resp.text)
        texto = re.sub(r"(?s)<[^>]+>", " ", html)
        texto = re.sub(r"&nbsp;|&amp;|&#\d+;|&\w+;", " ", texto)
        return re.sub(r"\s+", " ", texto).strip()[:limite]
    except Exception:
        return ""


def _encurtar_link(url: str) -> str:
    if not url or not url.startswith("http"):
        return url
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://tinyurl.com/api-create.php?url={quote(url)}", timeout=5) as resp:
            curto = resp.read().decode().strip()
            return curto if curto.startswith("http") else url
    except Exception:
        return url


def _gerar_alerta_texto(titulo, fonte, data_fmt, cand, part, uf, cargo, status, trecho="") -> str:
    contexto = "\n".join(filter(None, [
        f"Título: {titulo}",
        f"Fonte: {fonte}" if fonte else "",
        f"Data: {data_fmt}" if data_fmt else "",
        f"Pessoa citada: {cand} ({part})" if cand else "",
        f"UF: {uf}" if uf and uf.lower() != "nan" else "",
        f"Cargo: {cargo}" if cargo and cargo.lower() != "nan" else "",
        f"Classificação: {status}" if status and status.lower() != "nan" else "",
        f"Trecho do artigo:\n{trecho}" if trecho else "",
    ]))
    prompt = (
        "Você é um analista que produz alertas padronizados para WhatsApp.\n"
        "Escreva um texto curto (PT-BR), factual e direto, a partir da notícia abaixo.\n"
        "Sem opinião, sem especulação, sem bullets e sem emojis.\n"
        "Comece pelo fato principal (quem fez o quê e a consequência imediata, se houver).\n"
        "1 parágrafo, no máximo 90 palavras.\n"
        "Não comece com 'ALERTA' nem título.\n"
        "Preserve nomes, cargos, datas e números exatamente como na notícia. "
        "Se houver trecho do artigo, baseie os fatos e números nele — é mais completo que o "
        "título. Sem trecho, use só o título e não invente detalhes que não estão nele.\n\n"
        f"{REGRAS_POLITICOS_ALERTA}\n"
        f"NOTÍCIA:\n{contexto}"
    )
    resp = _gemini_client().models.generate_content(model=GEMINI_MODEL, contents=prompt)
    texto = (getattr(resp, "text", "") or "").strip()
    if not texto:
        raise RuntimeError("Não consegui gerar o texto do alerta. Tente novamente.")
    return texto


def _compilar_alerta(uf, titulo, corpo, link, cargo="", alerta_tema="", candidato="") -> str:
    partes = [
        f"*{_montar_header_alerta(uf, cargo, alerta_tema, candidato)}*",
        datetime.now(APP_TZ).strftime("%d/%m/%Y"),
        "",
        f"*{titulo.strip()}*",
        "",
        corpo.strip(),
    ]
    if link and link.startswith("http"):
        partes += ["", f"Link: {link}"]
    return "\n".join(partes)


@st.dialog("Criar alerta")
def _dialog_alerta(ridx, titulo, fonte, data_fmt, cand, part, uf, cargo, status, link,
                   linha="", resumo_salvo="", alerta_tema=""):
    _key = f"nt_alerta_texto_{ridx}"
    if _key not in st.session_state:
        if resumo_salvo:
            # Já escrito (pela raspagem ou salvo antes): reusa, sem chamar o Gemini.
            st.session_state[_key] = resumo_salvo
        else:
            with st.spinner("Lendo a notícia e gerando o alerta…"):
                try:
                    trecho = _texto_completo_da_linha(SHEET, linha, link) or _extrair_texto_noticia(link)
                    corpo = _gerar_alerta_texto(titulo, fonte, data_fmt, cand, part, uf, cargo, status, trecho)
                    st.session_state[_key] = _compilar_alerta(
                        uf, titulo, corpo, _encurtar_link(link), cargo, alerta_tema, cand)
                except Exception as e:
                    st.error(f"Erro ao gerar alerta: {e}")
                    st.session_state[_key] = ""

    if st.button("Gerar novamente", icon=":material/refresh:", key=f"{_key}_regen"):
        del st.session_state[_key]
        st.rerun()

    texto_final = st.text_area("Alerta completo", value=st.session_state[_key], height=220, key=f"{_key}_edit")
    st.caption("Vai abrir o WhatsApp com o texto já preenchido. O envio final acontece por lá.")
    st.link_button("Abrir WhatsApp", f"https://wa.me/?text={quote(texto_final)}" if texto_final.strip()
                   else "https://wa.me/", type="primary", width="stretch", disabled=not texto_final.strip())
    if st.button("Salvar texto na planilha", key=f"{_key}_save", disabled=not texto_final.strip()):
        url_planilha = _salvar_resumo_planilha(link, texto_final)
        if url_planilha:
            st.success(f"Texto salvo. [Ver na planilha]({url_planilha})")
        else:
            st.error("Não consegui salvar o texto. Tente de novo ou avise a equipe de dados.")


# ─── De qual alerta cada "repetido" é repetição ────────────────────────────────
# Montado a partir de df, não de view: o alerta de origem pode estar fora do
# recorte. O scraper só compara com alertas das últimas 48h, então a origem é o
# alerta de mesma chave dentro de 48h com a manchete mais parecida.
_origem_alerta: dict = {}
if {"alerta", "alerta_chave"} <= set(df.columns):
    _orig = df[(df["alerta"].astype(str).str.strip().str.lower() == "sim")
               & (df["alerta_chave"].astype(str).str.strip() != "")
               & df["_data"].notna()]
    for _c, _g in _orig.groupby(_orig["alerta_chave"].astype(str).str.strip()):
        _origem_alerta[_c] = [(_p["_data"], str(_p.get("titulo", "")).strip(), str(_p.get("link", "")).strip())
                              for _, _p in _g.iterrows()]

_PALAVRAS_VAZIAS = set(
    "a o as os e de da do das dos em no na nos nas um uma para por com que se ao aos "
    "sua seu mais apos sobre diz contra entre como ja nao".split())


def _palavras_titulo(titulo) -> set:
    """Espelha _palavras_titulo() do scraper, que decide o que é o mesmo fato."""
    t = re.sub(r"\s+-\s+[^-]+$", "", str(titulo or ""))
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 2 and w not in _PALAVRAS_VAZIAS}


def _alerta_de_origem(chave: str, quando, titulo: str = ""):
    if pd.isna(quando):
        return None
    _cands = [o for o in _origem_alerta.get(chave, []) if abs(o[0] - quando) <= pd.Timedelta(hours=48)]
    if not _cands:
        return None
    _w = _palavras_titulo(titulo)
    _sim = lambda o: len(_w & _palavras_titulo(o[1])) / max(1, len(_w | _palavras_titulo(o[1])))
    return max(_cands, key=lambda o: (_sim(o), -abs(o[0] - quando).total_seconds()))


# ─── Feed ─────────────────────────────────────────────────────────────────────
_FEED_LIM = 200
_feed = view.sort_values("_data", ascending=False, na_position="last")
secao("Notícias", f"{len(_feed)}",
      explicacao="Título abre a fonte original. O envelope cria o alerta e abre o WhatsApp; "
                 "envelope aberto quer dizer que o texto do alerta já está escrito. "
                 "A caixa ao lado marca a notícia como vista para toda a equipe.")
if len(_feed) > _FEED_LIM:
    st.caption(f"Mostrando as {_FEED_LIM} mais recentes de {len(_feed)}. Refine os filtros para ver as demais.")

for _ridx, r in _feed.head(_FEED_LIM).iterrows():
    _cand = normalize_candidato(r.get("candidato", ""))
    _part = normalize_partido(r.get("partido", ""))
    _cargo_r = str(r.get("cargo", "")).strip()
    _ident = _cand + (f" ({_part})" if _part else "")
    _titulo = str(r.get("titulo", "")).strip() or "(sem título)"
    _fonte = str(r.get("fonte", "")).strip()
    _link = str(r.get("link", "")).strip()
    _data_fmt = r["_data"].strftime("%d/%m/%Y %H:%M") if pd.notna(r["_data"]) else ""
    _status = str(r.get("status", "")).strip()
    _linha_r = str(r.get("_linha", "")).strip()
    _resumo_salvo_r = str(r.get("resumo", "")).strip()
    _resumo_salvo_r = "" if _resumo_salvo_r.lower() == "nan" else _resumo_salvo_r
    _visto_r = str(r.get("visto", "")).strip().lower() == "visto"
    _tipo_r = str(r.get("tipo", "")).strip().lower()
    _alerta_r = str(r.get("alerta", "")).strip().lower()
    _tema_r = str(r.get("alerta_tema", "")).strip()
    _tema_r = "" if _tema_r.lower() == "nan" else _tema_r
    _uf_r = _uf_ajustada(r.get("uf", ""), _tema_r or _tipo_r, _titulo, r.get("busca", ""))
    _escopo_r = _escopo_alerta(_uf_r, _cargo_r, _tema_r or _tipo_r, _cand)
    if _escopo_r == "Subnacional":
        _escopo_r += f" · {_uf_relevante(_uf_r, _cargo_r, _tema_r or _tipo_r, _cand)}"

    _tipo_html = (f'<span class="nt-tipo"><i style="background:{_TIPO_COR.get(_tipo_r, MUDO)}"></i>'
                  f'{_TIPO_ROTULO[_tipo_r]}</span>' if _tipo_r in _TIPO_ROTULO else "")
    _selo, _repete = "", ""
    if _alerta_r == "sim":
        _tema_dif = _TIPO_ROTULO.get(_tema_r, _tema_r) if _tema_r and _tema_r != _tipo_r else ""
        _selo = f'<span class="nt-selo alerta">{esc(" · ".join(filter(None, ["Alerta", _tema_dif])))}</span>'
    elif _alerta_r == "repetido":
        _selo = ('<span class="nt-selo repetido" title="Mesmo fato de um alerta das últimas 48h, '
                 'saído em outro veículo. Não gera email de novo.">Já alertado em outra notícia</span>')
        _o = _alerta_de_origem(str(r.get("alerta_chave", "")).strip(), r["_data"], _titulo)
        if _o:
            _o_tit = (f'<a href="{esc(_o[2])}" target="_blank">{esc(_o[1])}</a>'
                      if _o[2].startswith("http") else esc(_o[1]))
            _repete = f'repete o alerta de {_o[0].strftime("%d/%m %H:%M")}: {_o_tit}'
    _titulo_html = (f'<a href="{esc(_link)}" target="_blank">{esc(_titulo)}</a>'
                    if _link.startswith("http") else esc(_titulo))
    _meta = " · ".join(filter(None, [_tipo_html, esc(_escopo_r), esc(_ident), esc(_fonte), _data_fmt]))
    if _repete:
        _meta += f"<br>{_repete}"

    _col_card, _col_visto, _col_btn = st.columns([0.80, 0.14, 0.06], vertical_alignment="center")
    with _col_card:
        st.markdown(
            f'<div class="nt-card{" visto" if _visto_r else ""}"><div class="nt-head">'
            f'<span class="nt-tit">{_titulo_html}</span><span class="nt-selos">{_selo}</span></div>'
            f'<div class="nt-meta">{_meta}</div></div>',
            unsafe_allow_html=True,
        )
    with _col_visto:
        _novo_visto = st.selectbox("Vista", ["não visto", "visto"], index=1 if _visto_r else 0,
                                   key=f"nt_visto_{_ridx}", label_visibility="collapsed",
                                   help="Já vista por alguém da equipe")
        if (_novo_visto == "visto") != _visto_r:
            if _marcar_visto_planilha(_link, _novo_visto):
                _visto_overrides[_link] = _novo_visto
                st.rerun()
            else:
                st.toast("Não consegui gravar o visto na planilha.")
    with _col_btn:
        _icone, _ajuda = ((":material/mark_email_read:", "Texto do alerta pronto: abrir e enviar no WhatsApp")
                          if _resumo_salvo_r else (":material/mail:", "Criar alerta e enviar no WhatsApp"))
        if st.button("", icon=_icone, key=f"nt_alerta_btn_{_ridx}", help=_ajuda):
            _dialog_alerta(_ridx, _titulo, _fonte, _data_fmt, _cand, _part, _uf_r, _cargo_r, _status, _link,
                           _linha_r, _resumo_salvo_r, _tema_r)
