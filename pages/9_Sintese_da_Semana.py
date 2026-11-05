from __future__ import annotations

import datetime as dt
import html as _html
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

import sintese_semana_core as ss
import importlib

# o Streamlit Cloud às vezes mantém o módulo velho depois de um push; recarrega a cada rodada
ss = importlib.reload(ss)


st.set_page_config(page_title="Síntese da Semana", layout="wide")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');
html, body, [data-testid="stAppViewContainer"] { background: #F4F3EF !important; }
[data-testid="stAppViewContainer"] > section > div { background: #F4F3EF; }
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1320px !important; padding: 1.8rem 2.5rem 4rem !important; background: #F4F3EF; }
* { box-sizing: border-box; }
body, p, span, div, label, input, select, textarea { font-family: 'Montserrat', sans-serif !important; }
[data-testid="stHeader"], [data-testid="stDecoration"] { display: none; }
[data-testid="stSidebar"] { background: #F4F3EF !important; border-right: 1px solid #DADAD4 !important; }
[data-testid="stSidebar"] * { font-family: 'Montserrat', sans-serif !important; font-size: 13px !important; }
span.material-symbols-rounded, span.material-symbols-outlined, span.material-icons,
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    letter-spacing: normal !important; text-transform: none !important; }
footer, #MainMenu { display: none !important; }
[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) { display: none; }

/* botões: contorno neutro; a ação principal da etapa em vinho cheio */
[data-testid="stButton"] button, [data-testid="stDownloadButton"] > button, [data-testid="stPopover"] > div > button,
[data-testid="stPopover"] button[kind] {
    border-radius: 8px !important; border: 1px solid #DADAD4 !important; background: #fff !important;
    color: #192D4E !important; font-weight: 600 !important; letter-spacing: 0 !important; text-transform: none !important;
    padding: 6px 14px !important; min-height: 36px !important; box-shadow: none !important; transition: border-color .15s, background .15s; }
[data-testid="stButton"] button p, [data-testid="stDownloadButton"] button p, [data-testid="stPopover"] button p { font-size: 13px !important; font-weight: 600 !important; }
[data-testid="stButton"] button:hover, [data-testid="stDownloadButton"] > button:hover, [data-testid="stPopover"] button:hover { border-color: #192D4E !important; }
button[kind="primary"], [data-testid="stBaseButton-primary"] { background: #962E4D !important; border-color: #962E4D !important; color: #fff !important; }
button[kind="primary"] p, [data-testid="stBaseButton-primary"] p { color: #fff !important; }
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover { background: #7A2640 !important; border-color: #7A2640 !important; }

/* rótulo de campo como nos painéis de transição e apuração */
[data-testid="stWidgetLabel"] p { font-size: 0.72rem !important; font-weight: 600 !important; letter-spacing: .04em !important;
    text-transform: uppercase !important; color: #4E5A6E !important; }
[data-testid="stDateInput"] div[data-baseweb="input"] { background: #fff !important; border: 1px solid #DADAD4 !important; border-radius: 8px !important; }
label:has(input[role="switch"]:checked) > div:first-of-type { background-color: #962E4D !important; }
[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] p, [data-testid="stToggle"] [data-testid="stWidgetLabel"] p,
label:has(input[role="switch"]) p { text-transform: none !important; letter-spacing: 0 !important; font-size: 13px !important;
    font-weight: 500 !important; color: #192D4E !important; }
[data-testid="stFileUploaderDropzone"] { background: #fff !important; border: 1px dashed #B9B5AA !important; border-radius: 8px !important; }

/* cabeçalho */
.sx-cab { padding: 0 0 14px; border-bottom: 1px solid #DADAD4; margin: 0 0 14px; }
.sx-cab .k { font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: #962E4D; margin-bottom: 6px; }
.sx-cab .tit { color: #192D4E; font-weight: 800; font-size: clamp(28px, 3vw, 38px); line-height: 1.2; letter-spacing: -0.01em; }
.sx-cab .sub { color: #4A4A4A; font-size: 13.5px; font-weight: 500; margin-top: 6px; line-height: 1.55; }
.st-key-sx_barra { align-items: flex-end; gap: 28px !important; margin-bottom: 6px; }
.sx-periodo { font-size: 15px; font-weight: 700; color: #192D4E; padding-bottom: 7px; white-space: nowrap; }

/* régua das três etapas */
.sx-etapas { display: grid; grid-template-columns: repeat(3, 1fr); background: #fff; border: 1px solid #DADAD4; border-radius: 8px; margin: 10px 0 4px; }
.sx-etapa { display: flex; gap: 12px; padding: 14px 18px; align-items: flex-start; }
.sx-etapa + .sx-etapa { border-left: 1px solid #DADAD4; }
.sx-etapa .m { flex: 0 0 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800; }
.sx-etapa.feita .m { background: #1F5E43; color: #fff; }
.sx-etapa.atual .m { background: #962E4D; color: #fff; }
.sx-etapa.aberta .m { border: 2px dashed #A9A9A4; color: #8A8A8A; }
.sx-etapa .r { font-size: 13.5px; font-weight: 700; color: #111; line-height: 1.3; }
.sx-etapa.aberta .r { color: #4A4A4A; font-weight: 600; }
.sx-etapa .d { font-size: 12px; color: #4A4A4A; margin-top: 3px; line-height: 1.4; }
@media (max-width: 820px) { .sx-etapas { grid-template-columns: 1fr; } .sx-etapa + .sx-etapa { border-left: 0; border-top: 1px solid #DADAD4; } }

/* título de seção: quadrado de cor, nome, contagem e (i) */
.sx-secao { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 30px 0 8px; }
.sx-secao .q { width: 14px; height: 14px; border-radius: 4px; flex: none; }
.sx-secao .t { color: #192D4E; font-weight: 700; font-size: 19px; }
.sx-secao .n { color: #4A4A4A; font-size: 13px; }
.sx-secao.menor { margin: 26px 0 8px; }
.sx-secao.menor .t { font-size: 15.5px; }
.sx-info { display: inline-flex; align-items: center; justify-content: center; width: 17px; height: 17px; border-radius: 50%; background: #192D4E;
    color: #fff; font-size: 11px; font-weight: 700; cursor: help; position: relative; line-height: 1; flex-shrink: 0; }
.sx-info:hover, .sx-info:focus { background: #962E4D; outline: none; }
.sx-info .sx-bolha { display: none; position: absolute; bottom: calc(100% + 8px); left: 0; background: #fff; border: 1px solid #DADAD4; border-radius: 6px;
    padding: 11px 15px; width: 340px; font-size: 12px; font-weight: 400; line-height: 1.6; color: #111; z-index: 9999;
    box-shadow: 0 4px 16px rgba(0,0,0,0.10); white-space: normal; pointer-events: none; }
.sx-info:hover .sx-bolha, .sx-info:focus .sx-bolha { display: block; }
[data-testid="stTabs"], [data-baseweb="tab-panel"] { overflow: visible !important; }
.sx-explica, p.sx-explica { color: #4A4A4A !important; font-size: 13px !important; line-height: 1.5 !important; margin: 0 0 10px !important; }
.sx-explica a { color: #962E4D; }

/* faixa de resumo */
.sx-resumo { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 18px; background: #fff; border: 1px solid #DADAD4; border-radius: 8px;
    padding: 11px 16px; font-size: 13px; color: #4A4A4A; margin: 10px 0 8px; }
.sx-resumo b { color: #192D4E; font-size: 16px; font-weight: 800; margin-right: 3px; font-variant-numeric: tabular-nums; }
.sx-resumo .sep { color: #D5D2CA; }
.sx-resumo .alerta b { color: #B4532A; }

/* clientes em pílula; a escolhida em marinho */
[data-testid="stButtonGroup"] button { border: 1px solid #DADAD4 !important; border-radius: 999px !important; background: #fff !important; box-shadow: none !important;
    padding: 4px 14px !important; min-height: 34px; }
[data-testid="stButtonGroup"] button p { font-size: 12.5px !important; font-weight: 500 !important; color: #192D4E !important; }
[data-testid="stButtonGroup"] button[aria-pressed="true"], [data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[kind="pillsActive"] {
    background: #192D4E !important; border-color: #192D4E !important; }
[data-testid="stButtonGroup"] button[aria-pressed="true"] p, [data-testid="stButtonGroup"] button[aria-checked="true"] p, [data-testid="stButtonGroup"] button[kind="pillsActive"] p {
    color: #fff !important; font-weight: 600 !important; }

/* abas dos clientes: filete vinho na escolhida */
[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid #DADAD4 !important; gap: 0 !important; }
[data-testid="stTabs"] [role="tab"] { padding: 10px 18px 9px !important; border-bottom: 2px solid transparent !important; background: transparent !important; border-radius: 0 !important; }
[data-testid="stTabs"] [role="tab"] p { font-size: 13px !important; font-weight: 500 !important; color: #4A4A4A !important; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { border-bottom-color: #962E4D !important; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p { color: #192D4E !important; font-weight: 700 !important; }
[data-testid="stTabs"] div[data-baseweb="tab-highlight"], [data-testid="stTabs"] .react-aria-SelectionIndicator { background-color: #962E4D !important; }

/* números do cliente */
.sx-nums { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 16px 0 0; }
.sx-num { background: #fff; border: 1px solid #DADAD4; border-radius: 8px; padding: 12px 16px; }
.sx-num .v { display: flex; align-items: center; gap: 8px; font-size: 24px; font-weight: 800; color: #192D4E; line-height: 1.1; font-variant-numeric: tabular-nums; }
.sx-num .v i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.sx-num .d { font-size: 12px; color: #4A4A4A; margin-top: 3px; }
@media (max-width: 820px) { .sx-nums { grid-template-columns: repeat(2, minmax(0, 1fr)); } }

/* itens (bullet, proposição, movimentação, ato): bloco branco com a chave à direita */
div[class*="st-key-it_"] { background: #fff; border: 1px solid #DADAD4; border-radius: 8px; padding: 14px 18px; margin-bottom: 8px; gap: .35rem; transition: border-color .15s; }
div[class*="st-key-it_"]:hover { border-color: #B9B5AA; }
div[class*="st-key-it_"]:has(input[role="switch"]:not(:checked)) { background: #F7F6F2; }
div[class*="st-key-it_"] [data-testid="stMarkdownContainer"], div[class*="st-key-it_"] [data-testid="stMarkdown"] { margin-bottom: 0 !important; }
div[class*="st-key-ac_"] [data-testid="stPopover"] button { padding: 2px 10px !important; min-height: 30px !important; }
div[class*="st-key-ac_"] [data-testid="stPopover"] button p { font-size: 12px !important; }
[data-testid="stPopoverBody"] { width: min(640px, 90vw) !important; max-width: none !important; }
.sx-fora { opacity: .5; }
.sx-fora .sx-h a { text-decoration: line-through !important; }
.sx-top { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 7px; }
.sx-chip { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 600; white-space: nowrap; background: #ECEAE4; color: #3A3A3A; line-height: 1.6; }
.sx-chip.data { background: #F2E4E9; color: #7A2640; }
.sx-chip.org { background: #E4E9F1; color: #192D4E; }
.sx-chip.duvida { background: #F6E9BF; color: #5C4700; }
p.sx-h { font-size: 15px !important; line-height: 1.45 !important; margin: 0 0 4px !important; font-weight: 700; }
.sx-h a, .sx-h a:visited { color: #192D4E !important; text-decoration: none !important; }
.sx-h a:hover { color: #962E4D !important; text-decoration: underline !important; text-underline-offset: 3px; }
.sx-h .teor { font-size: 12px; font-weight: 600; margin-left: 8px; }
.sx-h .teor a { color: #962E4D !important; }
p.sx-txt { font-size: 14px !important; line-height: 1.6 !important; color: #222 !important; margin: 0 !important; }
p.sx-ementa { font-size: 13px !important; line-height: 1.55 !important; color: #3A3A3A !important; margin: 0 !important; }
p.sx-and { font-size: 13px !important; line-height: 1.55 !important; color: #111 !important; margin: 8px 0 0 !important; padding: 8px 12px; background: #F7F6F2; border-radius: 6px; }
.sx-and span { display: block; font-size: 10.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #4E5A6E; margin-bottom: 2px; }
p.sx-meta { font-size: 12px !important; color: #6A6A66 !important; margin: 7px 0 0 !important; line-height: 1.5 !important; }
p.sx-meta a { color: #962E4D !important; }
.sx-vazio { background: #fff; border: 1px dashed #CFCBC1; border-radius: 8px; padding: 12px 16px; font-size: 13px; color: #4A4A4A; }

/* expansores (notícias por seção, XLS do Inteligov) */
[data-testid="stExpander"] details { border: 1px solid #DADAD4 !important; border-radius: 8px !important; background: #fff !important; }
[data-testid="stExpander"] summary p { font-size: 13px !important; font-weight: 600 !important; color: #192D4E !important; }
.st-key-sb_falha [data-testid="stExpander"] details { border-color: #E8C9B5 !important; background: #FBF4EF !important; }
.st-key-sb_falha summary p { color: #B4532A !important; }

/* entregas: uma linha por cliente */
.st-key-sx_entregas { background: #fff; border: 1px solid #DADAD4; border-radius: 8px; padding: 4px 18px; gap: 0 !important; margin-top: 12px; }
div[class*="st-key-lin_"] { border-bottom: 1px solid #ECEBE6; padding: 10px 0; }
div[class*="st-key-lin_"]:last-child { border-bottom: 0; }
.st-key-lin_cab { padding: 10px 0 8px !important; border-bottom: 2px solid #192D4E !important; }
.sx-th { font-size: 0.69rem; font-weight: 600; letter-spacing: .03em; text-transform: uppercase; color: #4E5A6E; }
.sx-cli { font-size: 14px; font-weight: 700; color: #192D4E; margin: 0; line-height: 1.3; }
.sx-cli span { display: block; font-size: 12px; font-weight: 500; color: #6A6A66; margin-top: 2px; }
div[class*="st-key-lin_"] [data-testid="stDownloadButton"] button, div[class*="st-key-lin_"] [data-testid="stPopover"] button { min-height: 32px !important; padding: 3px 12px !important; }
.st-key-sx_entregas [data-testid="stPopoverBody"], div[class*="st-key-lin_"] [data-testid="stPopoverBody"] { width: min(760px, 92vw) !important; }
.sx-email { font-size: 14px; line-height: 1.6; }
.sx-email h3 { font-size: 15px; color: #192D4E; margin: 14px 0 6px; }
.sx-nota, p.sx-nota { font-size: 12.5px !important; color: #4A4A4A !important; margin: 8px 0 0 !important; }
.st-key-sx_entregas [data-testid="stMarkdownContainer"], .st-key-sx_entregas [data-testid="stMarkdown"] { margin-bottom: 0 !important; }
</style>""", unsafe_allow_html=True)


# ========= LOGIN =========
def _load_auth_config():
    if "AUTH_CONFIG" in st.secrets:
        return yaml.load(st.secrets["AUTH_CONFIG"], Loader=SafeLoader)

    if os.path.exists("config.yaml"):
        with open("config.yaml", "r", encoding="utf-8") as f:
            return yaml.load(f, Loader=SafeLoader)

    return None


_auth_cfg = _load_auth_config()
if not _auth_cfg:
    st.error("Auth não configurado. Defina AUTH_CONFIG nos Secrets ou crie config.yaml local.")
    st.stop()

authenticator = stauth.Authenticate(
    _auth_cfg["credentials"],
    _auth_cfg["cookie"]["name"],
    _auth_cfg["cookie"]["key"],
    _auth_cfg["cookie"]["expiry_days"],
)

# O campo branco do login vem daqui, e tem que ser desenhado antes do gate:
# sem ninguém logado o gate chama st.stop() e nada depois dele roda.
from ui_login import CSS_LOGIN
st.markdown(CSS_LOGIN, unsafe_allow_html=True)
from menu_paginas import CSS_MENU
st.markdown(CSS_MENU, unsafe_allow_html=True)

try:
    authenticator.login(location="main")
except TypeError:
    authenticator.login("Login", "main")

authentication_status = st.session_state.get("authentication_status", None)

if authentication_status is False:
    st.error("Usuário ou senha inválidos.")
    st.stop()

if authentication_status is None:
    st.stop()


# ========= DADOS =========
from concurrent.futures import ThreadPoolExecutor
from google import genai

LOGO_PATH = "logo_eixo_gov_magenta.png"
MODELO = Path("modelos/sintese_semana_modelo.docx")
MODELO_IDEC = Path("modelos/sintese_semana_modelo_idec.docx")
FONTES = Path("fontes")
GEMINI_API_KEY = (st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")).strip()
GEMINI_MODEL = "gemini-3.6-flash"
DOU_SHEET_ID = (st.secrets.get("DOU_CLIENTES_SHEET_ID") or os.getenv("DOU_CLIENTES_SHEET_ID", "")).strip()
AGENDA_SHEET_ID = (st.secrets.get("AGENDA_SHEET_ID") or os.getenv("AGENDA_SHEET_ID", "")).strip()
SS = st.session_state
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# cor de cada bloco, a mesma no número do topo e no título da seção
COR = {"dest": "#962E4D", "novas": "#192D4E", "movs": "#4FA882", "dou": "#A96FAB"}


def _carregar_google_creds_dict():
    if "GOOGLE_SHEETS_CREDS" in st.secrets:
        return dict(st.secrets["GOOGLE_SHEETS_CREDS"])
    if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
        raw = st.secrets["GOOGLE_CREDENTIALS_JSON"]
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    creds_json = os.getenv("GOOGLE_SHEETS_CREDS", "") or os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    return json.loads(creds_json) if creds_json else None


@st.cache_resource
def _gc():
    creds = _carregar_google_creds_dict()
    if not creds:
        raise RuntimeError("Credencial do Google não configurada.")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    return gspread.authorize(Credentials.from_service_account_info(creds, scopes=scopes))


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _movs_da_semana(ini: dt.date, fim: dt.date, chave_lista: int):
    ws = _gc().open_by_key(AGENDA_SHEET_ID).worksheet(ss.ABA_ACOMP)
    return ss.movimentacoes_semana(ss.ler_acompanhadas(ws), ini, fim)


def esc(x) -> str:
    return _html.escape(str(x or "").strip())


def _info(texto: str) -> str:
    return f'<span class="sx-info" tabindex="0" role="note">i<span class="sx-bolha">{esc(texto)}</span></span>'


def secao(titulo: str, contagem: str = "", cor: str = "", info: str = "", menor: bool = False):
    q = f'<span class="q" style="background:{cor}"></span>' if cor else ""
    n = f'<span class="n">{esc(contagem)}</span>' if contagem else ""
    st.markdown(f'<div class="sx-secao{" menor" if menor else ""}">{q}<span class="t">{esc(titulo)}</span>{n}'
                f'{_info(info) if info else ""}</div>', unsafe_allow_html=True)


def chip(texto, tipo: str = "") -> str:
    return f'<span class="sx-chip {tipo}">{esc(texto)}</span>' if texto else ""


def _a(url: str, txt: str) -> str:
    return f'<a href="{esc(url)}" target="_blank">{esc(txt)}</a>' if url else esc(txt)


def plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def vazio(texto: str):
    st.markdown(f'<div class="sx-vazio">{esc(texto)}</div>', unsafe_allow_html=True)


def _item(chave: str, html_corpo: str, valor: bool = True, editar=None):
    """Um bloco branco: conteúdo à esquerda; à direita, Editar (quando há) e a chave de incluir."""
    with st.container(key=f"it_{chave}"):
        col1, col2 = st.columns([0.85, 0.15], vertical_alignment="top")
        with col2, st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center",
                                gap="small", key=f"ac_{chave}"):
            if editar:
                with st.popover("Editar", icon=":material/edit:"):
                    editar()
            on = st.toggle("Incluir", value=valor, key=chave, label_visibility="collapsed",
                           help="Desligado, o item não vai para o Word nem para o email")
        with col1:
            st.markdown(f'<div class="{"" if on else "sx-fora"}">{html_corpo}</div>', unsafe_allow_html=True)


def _segunda(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


# ========= BARRA LATERAL (só logo e sair; a navegação entre páginas fica nela) =========
with st.sidebar:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width="stretch")
    authenticator.logout("Sair", "sidebar")

# ========= CABEÇALHO =========
st.markdown('<div class="sx-cab"><div class="k">Saúde · envio semanal</div><div class="tit">Síntese da Semana</div>'
            '<div class="sub">Da Divisão semanal ao Word, ao anexo em PDF e ao corpo do email de cada cliente.</div></div>',
            unsafe_allow_html=True)

hoje = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
padrao = _segunda(hoje) - dt.timedelta(days=7) if hoje.weekday() < 3 else _segunda(hoje)
with st.container(horizontal=True, key="sx_barra", vertical_alignment="bottom"):
    dia = st.date_input("Semana", value=padrao, format="DD/MM/YYYY", width=170,
                        help="Escolha qualquer dia: vale a semana de segunda a sexta.")
    INI = _segunda(dia)
    FIM = INI + dt.timedelta(days=4)
    PERIODO = ss.periodo_extenso(INI, FIM)
    st.markdown(f'<div class="sx-periodo">{esc(PERIODO)}</div>', unsafe_allow_html=True)
    quinzenal = st.toggle("Incluir ASBAI e Desiderata (quinzenais)", value=False)

if SS.get("sint_semana") != INI:  # trocou a semana: DOU, movimentações e arquivos são outros
    SS["sint_semana"] = INI
    for k in ("sint_dou", "sint_arquivos", "sint_emails", "sint_movs_xls"):
        SS.pop(k, None)
    for k in [k for k in SS.keys() if str(k).startswith(("sd_", "sm_"))]:
        del SS[k]

etapas_ph = st.empty()


def _etapas():
    div_ = SS.get("sint_div")
    bl = SS.get("sint_bullets") or {}
    arqs_ = SS.get("sint_arquivos")
    nb = sum(len(v) for v in bl.values())
    itens = [
        ("feita" if div_ else "atual", "Divisão semanal",
         f'{plural(len(div_["noticias"]), "notícia", "notícias")} e '
         f'{plural(len(div_["proposicoes"]), "proposição nova", "proposições novas")}' if div_
         else "Suba o PDF ou o Word baixado do Docs"),
        ("feita" if bl else ("atual" if div_ else "aberta"), "Bullets e revisão",
         f'{plural(nb, "bullet", "bullets")} em {plural(len(bl), "cliente", "clientes")}' if bl
         else "Gerados a partir das notícias e dos temas de cada cliente"),
        ("feita" if arqs_ else ("atual" if bl else "aberta"), "Word, PDF e email",
         f'{plural(len(SS.get("sint_emails") or {}), "cliente pronto", "clientes prontos")} para baixar' if arqs_
         else "Síntese, anexo e corpo do email por cliente"),
    ]
    etapas_ph.markdown('<div class="sx-etapas">' + "".join(
        f'<div class="sx-etapa {e}"><div class="m">{"✓" if e == "feita" else i}</div>'
        f'<div><div class="r">{esc(r)}</div><div class="d">{esc(d)}</div></div></div>'
        for i, (e, r, d) in enumerate(itens, 1)) + "</div>", unsafe_allow_html=True)


def _parar():
    _etapas()
    st.stop()


CLIS = [c for c, v in ss.CLIENTES.items() if quinzenal or not v.get("quinzenal")]

# ========= 1. DIVISÃO SEMANAL =========
secao("1. Divisão semanal", info="No Docs: Arquivo > Fazer download > PDF ou Microsoft Word (.docx). Os dois servem: "
      "a página lê os links de notícia por tema e a tabela de novas proposições.")
arq = st.file_uploader("Divisão semanal - Saúde", type=["docx", "pdf"], label_visibility="collapsed")
if arq is not None and SS.get("sint_arquivo") != (arq.name, arq.size):
    SS["sint_arquivo"] = (arq.name, arq.size)
    SS["sint_div"] = ss.ler_divisao(arq.getvalue(), arq.name)
    for k in ("sint_noticias", "sint_bullets", "sint_dou", "sint_arquivos", "sint_emails", "sint_acomp_ok",
              "sint_acomp_n", "sint_movs_xls"):
        SS.pop(k, None)
    for k in [k for k in SS.keys() if str(k).startswith(("sb_", "sc_", "sd_", "sp_", "sm_"))]:
        del SS[k]

div = SS.get("sint_div")
if not div:
    _parar()

nots = div["noticias"]
falhas = [n for n in (SS.get("sint_noticias") or []) if n.get("erro")]
partes = [f'<span><b>{len(nots)}</b>notícias</span>', '<span class="sep">|</span>',
          f'<span><b>{len({n["secao"] for n in nots})}</b>temas</span>', '<span class="sep">|</span>',
          f'<span><b>{len(div["proposicoes"])}</b>novas proposições</span>']
if falhas:
    partes += ['<span class="sep">|</span>', f'<span class="alerta"><b>{len(falhas)}</b>não lidas</span>']
st.markdown('<div class="sx-resumo">' + "".join(partes) + "</div>", unsafe_allow_html=True)
with st.expander("Ver as notícias por tema"):
    for sec in dict.fromkeys(n["secao"] for n in nots):
        st.markdown(f"**{_html.escape(sec)}**")
        for n in nots:
            if n["secao"] == sec:
                st.markdown(f"- {n['url']}")
if falhas:
    with st.container(key="sb_falha"), st.expander(f"{plural(len(falhas), 'notícia não foi lida e ficou', 'notícias não foram lidas e ficaram')} de fora"):
        for n in falhas:
            st.markdown(f"- {n['url']} ({n['erro']})")

# ========= 2. BULLETS =========
secao("2. Bullets por cliente", info="Uma chamada ao Gemini por cliente, só com os temas dele na matriz. "
      "O texto segue o padrão do prompt: fato no presente, sem análise. Revise, edite ou desligue o que não servir.")
st.markdown('<p class="sx-explica">Escolha os clientes desta rodada.</p>', unsafe_allow_html=True)
escolhidos = st.pills("Clientes", CLIS, default=CLIS, selection_mode="multi", label_visibility="collapsed",
                      format_func=lambda c: ss.CLIENTES[c]["titulo"])

if st.button("Ler notícias e gerar bullets", type="primary"):
    if not GEMINI_API_KEY:
        st.error("Faltou a GEMINI_API_KEY nos Secrets.")
        _parar()
    if not escolhidos:
        st.warning("Escolha ao menos um cliente.")
        _parar()
    with st.spinner("Baixando as notícias..."):
        SS["sint_noticias"] = ss.baixar_todas(nots)
    client = genai.Client(api_key=GEMINI_API_KEY)
    baixadas = SS["sint_noticias"]  # thread não enxerga st.session_state
    bullets, erros = {}, {}
    barra = st.progress(0.0, text=f"Gerando bullets: 0 de {len(escolhidos)} clientes")

    def _um(c):
        try:
            return c, ss.gerar_bullets(client, GEMINI_MODEL, c, baixadas), None
        except Exception as e:  # noqa: BLE001
            return c, [], f"{type(e).__name__}: {e}"[:300]

    with ThreadPoolExecutor(5) as ex:
        for n_feito, (c, bl, err) in enumerate(ex.map(_um, escolhidos), 1):
            barra.progress(n_feito / len(escolhidos), text=f"Gerando bullets: {n_feito} de {len(escolhidos)} clientes")
            bullets[c] = bl
            if err:
                erros[c] = err
    barra.empty()
    SS["sint_bullets"], SS["sint_erros"] = bullets, erros
    for k in list(SS.keys()):
        if str(k).startswith(("sb_", "sc_", "sd_", "sp_", "sm_")):
            del SS[k]
    SS.pop("sint_arquivos", None)
    SS.pop("sint_emails", None)
    st.rerun()  # redesenha o resumo (não lidas) e a régua com o resultado

noticias = SS.get("sint_noticias")
if noticias is None:
    _parar()
for c, e in SS.get("sint_erros", {}).items():
    st.error(f"{ss.CLIENTES[c]['titulo']}: {e}")

clipping = ss.clipping_por_cliente(noticias)
bullets = SS.get("sint_bullets", {})
abas = [c for c in bullets]
if not abas:
    _parar()

# DOU da raspagem (uma vez por semana e Divisão)
if DOU_SHEET_ID and "sint_dou" not in SS:
    with st.spinner("Lendo o DOU da raspagem..."):
        try:
            gc = _gc()
            brutos, falhou = {}, []
            for c in abas:
                try:
                    brutos[c] = ss.ler_dou_cliente(gc, DOU_SHEET_ID, c, INI, FIM)
                except Exception as e:  # noqa: BLE001
                    brutos[c] = []
                    falhou.append(f"{ss.CLIENTES[c]['titulo']} ({type(e).__name__})")
            if falhou:
                st.warning("DOU não lido para: " + ", ".join(falhou))
            todos = {a["link"]: a for v in brutos.values() for a in v}
            with ThreadPoolExecutor(8) as ex:
                completos = dict(zip(todos, ex.map(ss.completar_ato_dou, todos.values())))
            SS["sint_dou"] = {c: [completos[a["link"]] for a in v] for c, v in brutos.items()}
        except Exception as e:  # noqa: BLE001
            SS["sint_dou"] = {}
            st.warning(f"Não consegui ler o DOU da raspagem: {e}")
dou_por_cli = SS.get("sint_dou", {})

# proposições acompanhadas: as novas da Divisão entram na lista; depois, a tramitação da semana
movs_por_cli = None
if AGENDA_SHEET_ID:
    if div.get("proposicoes") and not SS.get("sint_acomp_ok"):
        try:
            ws = _gc().open_by_key(AGENDA_SHEET_ID).worksheet(ss.ABA_ACOMP)
            SS["sint_acomp_n"] = ss.acrescentar_novas(ws, div["proposicoes"], ss.ler_acompanhadas(ws),
                                                      hoje.strftime("%d/%m/%Y"))
        except Exception as e:  # noqa: BLE001
            st.warning(f"Não consegui pôr as novas proposições na lista de acompanhadas: {e}")
        SS["sint_acomp_ok"] = True
    with st.spinner("Consultando a tramitação na Câmara e no Senado (na primeira vez da semana leva até 2 minutos)..."):
        try:
            movs_por_cli = _movs_da_semana(INI, FIM, SS.get("sint_acomp_n", 0))
        except Exception as e:  # noqa: BLE001
            st.warning(f"Movimentações: {e}")
if SS.get("sint_acomp_n"):
    st.markdown(f'<p class="sx-explica">{plural(SS["sint_acomp_n"], "proposição nova da Divisão entrou", "proposições novas da Divisão entraram")} '
                'na lista de acompanhadas.</p>', unsafe_allow_html=True)


def _movs_de(c):
    return (movs_por_cli or {}).get(c, []) + SS.get("sint_movs_xls", {}).get(c, [])


def _novas_de(c):
    return [p for p in div["proposicoes"] if c in [x for x, _ in p["clientes"]]]


tabs = st.tabs([f"{ss.CLIENTES[c]['titulo']} · {len(bullets[c])}" for c in abas])
for c, tab in zip(abas, tabs):
    with tab:
        novas = _novas_de(c)
        movs_c = _movs_de(c)
        atos = dou_por_cli.get(c, [])
        nums = [("dest", len(bullets[c]) + len(clipping.get(c, [])), "destaques" if c != "IDEC" else "destaques por área"),
                ("novas", len(novas), "novas proposições"),
                ("movs", "-" if c == "Desiderata" else len(movs_c), "movimentações na semana"),
                ("dou", len(atos), "atos no DOU")]
        st.markdown('<div class="sx-nums">' + "".join(
            f'<div class="sx-num"><div class="v"><i style="background:{COR[k]}"></i>{v}</div><div class="d">{esc(d)}</div></div>'
            for k, v, d in nums) + "</div>", unsafe_allow_html=True)

        if clipping.get(c):
            secao("Clipping da semana", plural(len(clipping[c]), "matéria", "matérias"), COR["dest"],
                  "Seção de clipping da Divisão: título e lide da própria matéria, sem reescrever.", menor=True)
            for i, cl in enumerate(clipping[c]):
                _item(f"sc_{c}_{i}", f'<p class="sx-h">{_a(cl["url"], cl["titulo"])}</p>'
                                     f'<p class="sx-txt">{esc(cl["lide"])}</p>')

        for sec in ss.secoes_do_cliente(c):
            doses = [(i, b) for i, b in enumerate(bullets[c]) if b["secao"] == sec]
            if not doses:
                continue
            secao(sec if c == "IDEC" else f"Destaques {sec}", plural(len(doses), "bullet", "bullets"), COR["dest"],
                  "Gerados só com as notícias da Divisão e os temas do cliente. Editar muda título e texto; "
                  "a chave tira o bullet do Word e do email.", menor=True)
            for i, b in doses:
                tit = SS.get(f"sb_{c}_{i}_t", b["titulo"])
                txt = SS.get(f"sb_{c}_{i}_x", b["texto"])
                docs = " · ".join(_a(d["url"], d["nome"]) for d in b.get("documentos", []))

                def _editar(c=c, i=i, b=b):
                    st.text_input("Título", value=b["titulo"], key=f"sb_{c}_{i}_t")
                    st.text_area("Texto", value=b["texto"], key=f"sb_{c}_{i}_x", height=150)

                _item(f"sb_{c}_{i}_on",
                      (f'<div class="sx-top">{chip(b.get("tema"))}</div>' if b.get("tema") else "")
                      + f'<p class="sx-h">{_a(b["url"], tit.rstrip(".") + ".")}</p>'
                      f'<p class="sx-txt">{esc(txt)}</p>'
                      + (f'<p class="sx-meta">Documentos citados: {docs}</p>' if docs else ""), editar=_editar)
        if not bullets[c] and not clipping.get(c):
            secao("Destaques", "", COR["dest"], menor=True)
            vazio("Nenhuma notícia da semana tem relação direta com os temas do cliente.")

        secao("Novas proposições", plural(len(novas), "proposição", "proposições") if novas else "", COR["novas"],
              "Da tabela NOVAS PROPOSIÇÕES da Divisão. As marcadas com ? entram desligadas. "
              "Cada uma entra na lista de acompanhadas do cliente.", menor=True)
        if not novas:
            vazio("Nenhuma proposição nova marcada para o cliente na Divisão.")
        for j, p in enumerate(novas):
            duvida = any(x == c and d for x, d in p["clientes"])
            _item(f"sp_{c}_{j}",
                  (f'<div class="sx-top">{chip("marcada com ? na Divisão", "duvida")}</div>' if duvida else "")
                  + f'<p class="sx-h">{_a(p.get("link", ""), p["proposicao"])}</p>'
                  f'<p class="sx-ementa">{esc(p["ementa"])}</p>'
                  + (f'<p class="sx-meta">Autoria: {esc(p["autor"])}</p>' if p.get("autor") else ""), valor=not duvida)

        url_m = ss.url_matriz_inteligov(c, INI, FIM)
        secao("Movimentações da semana", plural(len(movs_c), "proposição", "proposições") if movs_c else "", COR["movs"],
              "Último andamento da semana de cada proposição que o cliente acompanha, consultado na Câmara e no Senado. "
              "A lista de acompanhadas veio da Matriz do Inteligov.", menor=True)
        if c == "Desiderata":
            vazio("Proposições do Desiderata são de Niterói e do RJ; entram à mão.")
        else:
            if url_m:
                st.markdown(f'<p class="sx-explica">Fonte: Câmara e Senado · <a href="{url_m}" target="_blank">'
                            'conferir na Matriz do Inteligov</a></p>', unsafe_allow_html=True)
            if movs_por_cli is None:
                vazio("Não consegui consultar a Câmara e o Senado agora.")
            elif not movs_c:
                vazio("Nenhuma proposição acompanhada andou na semana.")
            for j, m in enumerate(movs_c):
                casa = "Senado" if "senado" in (m.get("link") or "") else ("Câmara" if "camara" in (m.get("link") or "") else "")
                quem = " · ".join(x for x in [m.get("autor") and f"Autoria: {esc(m['autor'])}",
                                              m.get("relator") and f"Relatoria: {esc(m['relator'])}"] if x)
                teor = f'<span class="teor">{_a(m["teor"], "inteiro teor ↗")}</span>' if m.get("teor") else ""
                _item(f"sm_{c}_{j}",
                      f'<div class="sx-top">{chip(m.get("data"), "data")}{chip(m.get("orgao"), "org")}{chip(casa)}</div>'
                      f'<p class="sx-h">{_a(m.get("link", ""), m["proposicao"])}{teor}</p>'
                      f'<p class="sx-ementa">{esc(m.get("ementa", ""))}</p>'
                      f'<p class="sx-and"><span>Andamento</span>{esc(m.get("andamento", ""))}</p>'
                      + (f'<p class="sx-meta">{quem}</p>' if quem else ""))
            if url_m:
                with st.expander("Acrescentar do Inteligov (XLS)"):
                    st.markdown(f'<p class="sx-explica">Se faltar alguma, abra a <a href="{url_m}" target="_blank">'
                                'Matriz já filtrada</a>, clique em XLS e suba o arquivo. O que já está acima '
                                'não se repete.</p>', unsafe_allow_html=True)
                    xls = st.file_uploader("XLS do Inteligov", type=["xls", "xlsx"], key=f"xls_{c}",
                                           label_visibility="collapsed")
                    if xls is not None and SS.get(f"xls_lido_{c}") != (xls.name, xls.size):
                        try:
                            ja = {m["proposicao"].upper() for m in (movs_por_cli or {}).get(c, [])}
                            extra = [m for m in ss.ler_movimentacoes(xls.getvalue(), xls.name)
                                     if m["proposicao"].upper() not in ja]
                            SS.setdefault("sint_movs_xls", {})[c] = extra
                            SS[f"xls_lido_{c}"] = (xls.name, xls.size)
                            st.rerun()
                        except Exception as e:  # noqa: BLE001
                            st.error(f"Não consegui ler o arquivo: {e}")

        secao("Novas publicações (DOU)", plural(len(atos), "ato", "atos") if atos else "", COR["dou"],
              "Atos da raspagem do DOU marcados como alinhados ao cliente na semana.", menor=True)
        if not DOU_SHEET_ID:
            vazio("Planilha da raspagem do DOU não configurada.")
        elif not atos:
            vazio("Nenhum ato marcado como alinhado na semana.")
        for j, a in enumerate(atos):
            _item(f"sd_{c}_{j}",
                  f'<div class="sx-top">{chip(a.get("publicado"), "data")}{chip(a.get("orgao_topo") or a.get("orgao"), "org")}</div>'
                  f'<p class="sx-h">{_a(a["link"], a["ato"])}</p>'
                  f'<p class="sx-ementa">{esc(a.get("resumo", ""))}</p>')


# ========= 3. WORD, PDF E EMAIL =========
secao("3. Word, PDF e email", info="Síntese: o Word completo. Anexo: novas proposições, movimentações e DOU, "
      "o arquivo do botão do email (em Word e em PDF). Email: o corpo pronto para copiar e colar no Wix, com os links.")

with st.container(horizontal=True, vertical_alignment="center", key="sx_acoes"):
    gerar = st.button("Gerar arquivos", type="primary", icon=":material/description:")
    arqs = SS.get("sint_arquivos")
    if arqs and not gerar:
        st.download_button("Baixar tudo (.zip)", ss.pacote_zip(arqs), icon=":material/download:",
                           file_name=f"Sínteses {INI:%d.%m} a {FIM:%d.%m.%Y}.zip", mime="application/zip")

if gerar:
    arquivos, emails = {}, {}
    with st.spinner("Montando o Word de cada cliente..."):
        for c in abas:
            bl = []
            for i, b in enumerate(bullets[c]):
                if SS.get(f"sb_{c}_{i}_on", True):
                    bl.append({**b, "titulo": SS.get(f"sb_{c}_{i}_t", b["titulo"]),
                               "texto": SS.get(f"sb_{c}_{i}_x", b["texto"])})
            cl = [x for i, x in enumerate(clipping.get(c, [])) if SS.get(f"sc_{c}_{i}", True)]
            novas = [p for j, p in enumerate(_novas_de(c)) if SS.get(f"sp_{c}_{j}", True)]
            atos = [a for j, a in enumerate(dou_por_cli.get(c, [])) if SS.get(f"sd_{c}_{j}", True)]
            movs = [m for j, m in enumerate(_movs_de(c)) if SS.get(f"sm_{c}_{j}", True)]
            modelo = (MODELO_IDEC if c == "IDEC" else MODELO).read_bytes()
            nome = ss.nome_arquivo(c, INI, FIM)
            arquivos[nome] = ss.gerar_docx(modelo, c, PERIODO, bl, cl, novas, movs, atos)
            arquivos[nome.replace(".docx", " - anexo.docx")] = ss.gerar_docx(
                modelo, c, PERIODO, [], None, novas, movs, atos, so_anexo=True)
            emails[c] = ss.html_email(c, PERIODO, bl, cl)
            arquivos[nome.replace(".docx", " - email.html")] = emails[c].encode("utf8")
    if ss.pdf_disponivel():
        with st.spinner("Convertendo para PDF..."):
            arquivos.update(ss.docx_para_pdf({k: v for k, v in arquivos.items() if k.endswith(".docx")}, str(FONTES)))
    SS["sint_arquivos"], SS["sint_emails"] = arquivos, emails
    st.rerun()

arqs = SS.get("sint_arquivos")
if arqs:
    tem_pdf = any(k.endswith(".pdf") for k in arqs)
    with st.container(key="sx_entregas"):
        larg = [0.34, 0.24, 0.24, 0.18]
        with st.container(key="lin_cab"):
            for col, t in zip(st.columns(larg, vertical_alignment="center"), ["Cliente", "Síntese", "Anexo", "Email"]):
                col.markdown(f'<div class="sx-th">{t}</div>', unsafe_allow_html=True)
        for k, c in enumerate(abas):
            nome = ss.nome_arquivo(c, INI, FIM)
            anexo = nome.replace(".docx", " - anexo.docx")
            n_on = sum(1 for i in range(len(bullets[c])) if SS.get(f"sb_{c}_{i}_on", True))
            n_mov = sum(1 for j in range(len(_movs_de(c))) if SS.get(f"sm_{c}_{j}", True))
            with st.container(key=f"lin_{k}"):
                c0, c1, c2, c3 = st.columns(larg, vertical_alignment="center")
                c0.markdown(f'<p class="sx-cli">{esc(ss.CLIENTES[c]["titulo"])}<span>{plural(n_on, "bullet", "bullets")} · '
                            f'{plural(n_mov, "movimentação", "movimentações")}</span></p>', unsafe_allow_html=True)
                for col, base, rot in ((c1, nome, "sin"), (c2, anexo, "anx")):
                    with col, st.container(horizontal=True, gap="small"):
                        if base in arqs:
                            st.download_button("Word", arqs[base], file_name=base, mime=DOCX, key=f"dl_{k}_{rot}_w",
                                               icon=":material/description:")
                        pdf = base.replace(".docx", ".pdf")
                        if pdf in arqs:
                            st.download_button("PDF", arqs[pdf], file_name=pdf, mime="application/pdf",
                                               key=f"dl_{k}_{rot}_p", icon=":material/picture_as_pdf:")
                corpo = (SS.get("sint_emails") or {}).get(c)
                if corpo:
                    with c3, st.popover("Ver email", icon=":material/mail:"):
                        st.html(f'<div class="sx-email">{corpo.split("<body", 1)[-1].split(">", 1)[-1].rsplit("</body>", 1)[0]}</div>')
    if not tem_pdf:
        st.markdown('<p class="sx-nota">O PDF não está disponível neste servidor; baixe o Word e exporte pelo Word ou pelo Docs.</p>',
                    unsafe_allow_html=True)
    st.markdown('<p class="sx-nota">Email: abra "Ver email", selecione o texto e cole no Wix; os links vão junto.</p>',
                unsafe_allow_html=True)

_etapas()
