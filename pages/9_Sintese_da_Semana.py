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
:root { --eixo-vinho: #962E4D; }
html, body, [data-testid="stAppViewContainer"] { background: #F4F3EF !important; }
[data-testid="stAppViewContainer"] > section > div { background: #F4F3EF; }
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1320px !important; padding: 0 2rem 3rem !important; background: #F4F3EF; }
* { box-sizing: border-box; }
body, p, span, div, label, input, select, textarea { font-family: 'Montserrat', sans-serif !important; }
[data-testid="stHeader"] { display: none; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stSidebar"] { background: #F4F3EF !important; border-right: 1px solid #DADAD4 !important; }
[data-testid="stSidebar"] * { font-family: 'Montserrat', sans-serif !important; font-size: 13px !important; }
/* Streamlit usa texto com fonte Material para ícones; não sobrescreva essa fonte. */
span.material-symbols-rounded, span.material-symbols-outlined, span.material-icons,
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    letter-spacing: normal !important; text-transform: none !important;
}
footer { display: none !important; }
#MainMenu { display: none !important; }
[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] > button, [data-testid="stDownloadButton"] > button {
    font-size: 11px !important; font-weight: 500 !important; letter-spacing: 0.1em !important;
    text-transform: uppercase !important; border-radius: 0 !important;
    border: 1px solid #962E4D !important; background: transparent !important;
    color: #962E4D !important; padding: 5px 14px !important;
    transition: background 0.15s, color 0.15s !important;
}
[data-testid="stButton"] button:hover, [data-testid="stFormSubmitButton"] > button:hover,
[data-testid="stDownloadButton"] > button:hover { background: #962E4D !important; color: #fff !important; }
/* ação principal (gerar e baixar) cheia, como o download do Gerador de Gráficos */
[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"], [data-testid="stDownloadButton"] > button {
    background: #962E4D !important; color: #fff !important; font-weight: 700 !important; }
[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"]:hover,
[data-testid="stDownloadButton"] > button:hover { background: #7A2640 !important; border-color: #7A2640 !important; }
[data-testid="stSelectbox"] > label {
    font-size: 11px !important; font-weight: 700 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important; color: #767672 !important;
}
.ge-hero { background: #962E4D; display: flex; align-items: center; padding: 36px 48px; margin: 0 -2rem 32px -2rem; }
.ge-hero-title { font-family: 'Montserrat', sans-serif; font-size: 48px; font-weight: 800; color: #fff; line-height: 1; letter-spacing: -0.01em; }
.ge-rule { font-size: 17px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: #962E4D; border-top: 2px solid #962E4D; padding-top: 10px; margin: 28px 0 6px; }
[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid #DADAD4 !important; gap: 0 !important; }
[data-testid="stTabs"] [role="tab"] {
    font-size: 12px !important; font-weight: 600 !important; letter-spacing: 0.04em !important;
    color: #767672 !important; padding: 12px 22px 11px !important; border-bottom: 2px solid transparent !important;
    background: transparent !important; border-radius: 0 !important;
}
[data-testid="stTabs"] [role="tab"] p { font-size: 13px !important; font-weight: 600 !important; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: #962E4D !important; border-bottom-color: #962E4D !important; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p { color: #962E4D !important; }
/* clientes: botões de alternar no lugar de seis caixas */
[data-testid="stButtonGroup"] button {
    border-radius: 999px !important; border: 1px solid #DADAD4 !important; background: #fff !important;
    color: #767672 !important; font-size: 11.5px !important; padding: 2px 9px !important; min-height: 26px !important;
}
[data-testid="stButtonGroup"] button p { font-size: 11.5px !important; font-weight: 600 !important; }
/* os sete clientes numa linha só, alinhados à direita */
[data-testid="stElementContainer"]:has(> [data-testid="stButtonGroup"]), [data-testid="stButtonGroup"] { width: 100% !important; }
[data-testid="stButtonGroup"] [role="toolbar"] { width: 100% !important; max-width: none !important; gap: 4px !important; justify-content: flex-end !important; }
[data-testid="stButtonGroup"] button[kind="pillsActive"], [data-testid="stButtonGroup"] button[aria-pressed="true"] {
    background: #962E4D !important; border-color: #962E4D !important; color: #fff !important;
}
[data-testid="stButtonGroup"] button[kind="pillsActive"] p, [data-testid="stButtonGroup"] button[aria-pressed="true"] p { color: #fff !important; }
.ag-resumo { font-size: 14px; color: #111; line-height: 1.7; margin: 4px 0 2px; }
.ag-resumo b { font-weight: 700; }
.ag-sub { font-size: 12.5px; color: #767672; margin: 0 0 8px; }
.ag-org { font-size: 16px; font-weight: 700; color: #192D4E; margin: 34px 0 6px; line-height: 1.4; }
.ag-org.ag-primeira { margin-top: 14px; }
.ag-org a { color: #192D4E; text-decoration: none; }
.ag-org a:hover { text-decoration: underline; }
.ag-org span { font-weight: 500; color: #767672; font-size: 13px; }
.ag-tit { font-size: 14px; font-weight: 700; margin: 0; line-height: 1.45;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ag-tit a { color: #962E4D; text-decoration: none; }
.ag-tit a:hover { text-decoration: underline; }
.ag-ementa { font-size: 13px; color: #333; margin: 3px 0 0; line-height: 1.5;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.ag-meta { font-size: 12px; color: #767672; margin: 4px 0 0; }
.ag-conv { font-size: 12px; color: #767672; margin: 4px 0 0; line-height: 1.5;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ag-conv b, .ag-meta b { font-weight: 600; color: #333; }
.ag-org span.ag-tag { display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    color: #fff; background: #962E4D; border-radius: 3px; padding: 1px 7px; margin-left: 6px; vertical-align: 2px; }
.ag-fora .ag-tit a, .ag-fora .ag-tit { color: #9A9A95; text-decoration: line-through; }
.ag-fora .ag-ementa { color: #9A9A95; }
.ag-nota { font-size: 12.5px; color: #767672; margin: 4px 0 0; }
.ag-tit span.ag-novo { display: inline-block; font-size: 10.5px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    color: #192D4E; border: 1px solid #192D4E; border-radius: 3px; padding: 0 6px; margin-right: 6px; vertical-align: 1px; }
/* chave "só os novos" em vinho, não no vermelho padrão */
.st-key-ag_novos label:has(input:checked) > div:first-of-type { background-color: #962E4D !important; }
/* download por cliente em contorno; o zip com todos fica cheio */
.st-key-ag_por_cliente [data-testid="stDownloadButton"] > button {
    background: transparent !important; color: #962E4D !important; font-weight: 500 !important; }
.st-key-ag_por_cliente [data-testid="stDownloadButton"] > button:hover { background: #962E4D !important; color: #fff !important; }
.ag-fim { border-top: 1px solid #DADAD4; margin: 36px 0 18px; }
.ag-fio { border-bottom: 1px solid #DADAD4; margin: 10px 0 12px; }
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
GEMINI_API_KEY = (st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")).strip()
GEMINI_MODEL = "gemini-3.6-flash"
DOU_SHEET_ID = (st.secrets.get("DOU_CLIENTES_SHEET_ID") or os.getenv("DOU_CLIENTES_SHEET_ID", "")).strip()
SS = st.session_state


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
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    return gspread.authorize(Credentials.from_service_account_info(creds, scopes=scopes))


def _segunda(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


# ========= SIDEBAR =========
with st.sidebar:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, use_container_width=True)
    hoje = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    padrao = _segunda(hoje) - dt.timedelta(days=7) if hoje.weekday() < 4 else _segunda(hoje)
    seg = _segunda(st.date_input("Semana (qualquer dia dela)", value=padrao, format="DD/MM/YYYY"))
    INI, FIM = seg, seg + dt.timedelta(days=4)
    PERIODO = ss.periodo_extenso(INI, FIM)
    st.caption(PERIODO)
    quinzenal = st.toggle("Incluir ASBAI e Desiderata (quinzenais)", value=False)
    authenticator.logout("Sair", "sidebar")

st.markdown('<div class="ge-hero"><div class="ge-hero-title">Síntese da Semana</div></div>',
            unsafe_allow_html=True)

CLIS = [c for c, v in ss.CLIENTES.items() if quinzenal or not v.get("quinzenal")]

# ========= 1. DIVISÃO SEMANAL =========
st.markdown('<div class="ge-rule">1. Divisão semanal</div>', unsafe_allow_html=True)
st.markdown('<p class="ag-sub">No Docs: Arquivo &gt; Fazer download &gt; Microsoft Word (.docx). '
            'O PDF também serve, mas sem a tabela de novas proposições.</p>', unsafe_allow_html=True)
arq = st.file_uploader("Divisão semanal - Saúde", type=["docx", "pdf"], label_visibility="collapsed")
if arq is not None and SS.get("sint_arquivo") != (arq.name, arq.size):
    SS["sint_arquivo"] = (arq.name, arq.size)
    SS["sint_div"] = ss.ler_divisao(arq.getvalue(), arq.name)
    for k in ("sint_noticias", "sint_bullets", "sint_dou", "sint_arquivos"):
        SS.pop(k, None)

div = SS.get("sint_div")
if not div:
    st.stop()

nots = div["noticias"]
st.markdown(f'<p class="ag-resumo"><b>{len(nots)}</b> notícias em '
            f'<b>{len({n["secao"] for n in nots})}</b> seções e <b>{len(div["proposicoes"])}</b> '
            f'novas proposições.</p>', unsafe_allow_html=True)
with st.expander("Ver as notícias por seção"):
    for sec in dict.fromkeys(n["secao"] for n in nots):
        st.markdown(f"**{_html.escape(sec)}**")
        for n in nots:
            if n["secao"] == sec:
                st.markdown(f"- {n['url']}")

# ========= 2. BULLETS =========
st.markdown('<div class="ge-rule">2. Bullets por cliente</div>', unsafe_allow_html=True)
escolhidos = st.pills("Clientes", CLIS, default=CLIS, selection_mode="multi", label_visibility="collapsed")

if st.button("Ler notícias e gerar bullets", type="primary"):
    if not GEMINI_API_KEY:
        st.error("Faltou a GEMINI_API_KEY nos Secrets.")
        st.stop()
    with st.spinner("Baixando as notícias..."):
        SS["sint_noticias"] = ss.baixar_todas(nots)
    client = genai.Client(api_key=GEMINI_API_KEY)
    bullets, erros = {}, {}
    with st.spinner(f"Gerando bullets de {len(escolhidos)} clientes..."):
        def _um(c):
            try:
                return c, ss.gerar_bullets(client, GEMINI_MODEL, c, SS["sint_noticias"]), None
            except Exception as e:  # noqa: BLE001
                return c, [], f"{type(e).__name__}: {e}"[:300]
        with ThreadPoolExecutor(5) as ex:
            for c, bl, err in ex.map(_um, escolhidos):
                bullets[c] = bl
                if err:
                    erros[c] = err
    SS["sint_bullets"], SS["sint_erros"] = bullets, erros
    for k in list(SS.keys()):
        if str(k).startswith(("sb_", "sc_", "sd_")):
            del SS[k]

noticias = SS.get("sint_noticias")
if noticias is None:
    st.stop()

falhas = [n for n in noticias if n.get("erro")]
if falhas:
    with st.expander(f"{len(falhas)} notícia(s) não foram lidas e ficaram de fora"):
        for n in falhas:
            st.markdown(f"- {n['url']} ({n['erro']})")
for c, e in SS.get("sint_erros", {}).items():
    st.error(f"{c}: {e}")

clipping = ss.clipping_por_cliente(noticias)
bullets = SS.get("sint_bullets", {})
abas = [c for c in bullets]
if not abas:
    st.stop()

# movimentações e DOU por cliente
dou_por_cli = {}
if DOU_SHEET_ID and "sint_dou" not in SS:
    with st.spinner("Lendo o DOU da raspagem..."):
        try:
            gc = _gc()
            brutos = {c: ss.ler_dou_cliente(gc, DOU_SHEET_ID, c, INI, FIM) for c in abas}
            todos = {a["link"]: a for v in brutos.values() for a in v}
            with ThreadPoolExecutor(8) as ex:
                completos = dict(zip(todos, ex.map(ss.completar_ato_dou, todos.values())))
            SS["sint_dou"] = {c: [completos[a["link"]] for a in v] for c, v in brutos.items()}
        except Exception as e:  # noqa: BLE001
            SS["sint_dou"] = {}
            st.warning(f"Não consegui ler o DOU da raspagem: {e}")
dou_por_cli = SS.get("sint_dou", {})

tabs = st.tabs([f"{ss.CLIENTES[c]['titulo']} ({len(bullets[c])})" for c in abas])
for c, tab in zip(abas, tabs):
    with tab:
        if clipping.get(c):
            st.markdown('<div class="ag-org ag-primeira">Clipping da semana</div>', unsafe_allow_html=True)
            for i, cl in enumerate(clipping[c]):
                st.checkbox(f"{cl['titulo']} - {cl['lide'][:180]}", value=True, key=f"sc_{c}_{i}")
        for sec in ss.secoes_do_cliente(c):
            doses = [(i, b) for i, b in enumerate(bullets[c]) if b["secao"] == sec]
            if not doses:
                continue
            rot = sec if c == "IDEC" else f"Destaques {sec}"
            st.markdown(f'<div class="ag-org">{_html.escape(rot)}</div>', unsafe_allow_html=True)
            for i, b in doses:
                col1, col2 = st.columns([0.06, 0.94])
                with col1:
                    st.checkbox("incluir", value=True, key=f"sb_{c}_{i}_on", label_visibility="collapsed")
                with col2:
                    st.text_input("Título", value=b["titulo"], key=f"sb_{c}_{i}_t", label_visibility="collapsed")
                    st.text_area("Texto", value=b["texto"], key=f"sb_{c}_{i}_x", height=90,
                                 label_visibility="collapsed")
                    docs = "".join(f' · <a href="{_html.escape(d["url"])}">{_html.escape(d["nome"])}</a>'
                                   for d in b.get("documentos", []))
                    st.markdown(f'<p class="ag-meta"><a href="{_html.escape(b["url"])}">fonte</a> · '
                                f'{_html.escape(b.get("tema", ""))}{docs}</p>', unsafe_allow_html=True)
        if not bullets[c]:
            st.markdown('<p class="ag-nota">Nenhuma notícia da semana com relação direta com os temas do cliente.</p>',
                        unsafe_allow_html=True)

        novas = [p for p in div["proposicoes"] if c in [x for x, _ in p["clientes"]]]
        if novas:
            st.markdown('<div class="ag-org">Novas proposições</div>', unsafe_allow_html=True)
            for j, p in enumerate(novas):
                duvida = any(x == c and d for x, d in p["clientes"])
                st.checkbox(f"{p['proposicao']} - {p['ementa'][:160]}" + ("  (marcado com ?)" if duvida else ""),
                            value=not duvida, key=f"sp_{c}_{j}")

        st.markdown('<div class="ag-org">Movimentações da semana</div>', unsafe_allow_html=True)
        url_m = ss.url_matriz_inteligov(c, INI, FIM)
        if url_m:
            st.markdown(f'<p class="ag-sub">Abra a <a href="{url_m}" target="_blank">Matriz do Inteligov já filtrada</a>, '
                        'clique em XLS e suba o arquivo aqui.</p>', unsafe_allow_html=True)
            xls = st.file_uploader("XLS do Inteligov", type=["xls", "xlsx"], key=f"sm_{c}",
                                   label_visibility="collapsed")
            if xls is not None:
                try:
                    SS[f"movs_{c}"] = ss.ler_movimentacoes(xls.getvalue(), xls.name)
                    st.caption(f"{len(SS[f'movs_{c}'])} proposições com andamento na semana.")
                except Exception as e:  # noqa: BLE001
                    st.error(f"Não consegui ler o arquivo: {e}")
        else:
            st.markdown('<p class="ag-nota">Cliente sem matriz no Inteligov.</p>', unsafe_allow_html=True)

        atos = dou_por_cli.get(c, [])
        st.markdown('<div class="ag-org">Novas publicações (DOU)</div>', unsafe_allow_html=True)
        if not DOU_SHEET_ID:
            st.markdown('<p class="ag-nota">DOU_CLIENTES_SHEET_ID não configurado.</p>', unsafe_allow_html=True)
        for j, a in enumerate(atos):
            st.checkbox(f"{a['ato']} ({a.get('orgao', '')}) - {a['resumo'][:150]}", value=True, key=f"sd_{c}_{j}")


# ========= 3. WORD E EMAIL =========
st.markdown('<div class="ag-fim"></div>', unsafe_allow_html=True)
st.markdown('<div class="ge-rule">3. Word e corpo do email</div>', unsafe_allow_html=True)

if st.button("Gerar Word e email", type="primary"):
    arquivos = {}
    for c in abas:
        bl = []
        for i, b in enumerate(bullets[c]):
            if SS.get(f"sb_{c}_{i}_on", True):
                bl.append({**b, "titulo": SS.get(f"sb_{c}_{i}_t", b["titulo"]),
                           "texto": SS.get(f"sb_{c}_{i}_x", b["texto"])})
        cl = [x for i, x in enumerate(clipping.get(c, [])) if SS.get(f"sc_{c}_{i}", True)]
        novas = [p for j, p in enumerate([p for p in div["proposicoes"] if c in [x for x, _ in p["clientes"]]])
                 if SS.get(f"sp_{c}_{j}", True)]
        atos = [a for j, a in enumerate(dou_por_cli.get(c, [])) if SS.get(f"sd_{c}_{j}", True)]
        movs = SS.get(f"movs_{c}", [])
        modelo = (MODELO_IDEC if c == "IDEC" else MODELO).read_bytes()
        nome = ss.nome_arquivo(c, INI, FIM)
        arquivos[nome] = ss.gerar_docx(modelo, c, PERIODO, bl, cl, novas, movs, atos)
        arquivos[nome.replace(".docx", " - anexo.docx")] = ss.gerar_docx(
            modelo, c, PERIODO, [], None, novas, movs, atos, so_anexo=True)
        arquivos[nome.replace(".docx", " - email.html")] = ss.html_email(c, PERIODO, bl, cl).encode("utf8")
    SS["sint_arquivos"] = arquivos

arqs = SS.get("sint_arquivos")
if arqs:
    st.download_button("Baixar tudo (.zip)", ss.pacote_zip(arqs),
                       file_name=f"Sínteses {INI:%d.%m} a {FIM:%d.%m.%Y}.zip", mime="application/zip")
    st.markdown('<p class="ag-sub">Por cliente: a síntese completa, o anexo (proposições, movimentações e DOU, '
                'para o PDF do botão) e o corpo do email. Abra o .html no navegador, selecione tudo e cole no Wix: '
                'os links vão junto.</p>', unsafe_allow_html=True)
    with st.container(key="ag_por_cliente"):
        cols = st.columns(3)
        for k, (nome, dados) in enumerate(arqs.items()):
            mime = "text/html" if nome.endswith(".html") else \
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            cols[k % 3].download_button(nome.replace("Síntese da Semana - ", ""), dados, file_name=nome,
                                        mime=mime, key=f"dl_{k}")
