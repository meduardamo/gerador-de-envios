from __future__ import annotations

import datetime as dt
import html as _html
import json
import os
from pathlib import Path

import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

import agenda_semana_core as ag


st.set_page_config(page_title="Agenda da Semana", layout="wide")

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
[data-testid="stButton"] > button, [data-testid="stFormSubmitButton"] > button, [data-testid="stDownloadButton"] > button {
    font-size: 11px !important; font-weight: 500 !important; letter-spacing: 0.1em !important;
    text-transform: uppercase !important; border-radius: 0 !important;
    border: 1px solid #962E4D !important; background: transparent !important;
    color: #962E4D !important; padding: 5px 14px !important;
    transition: background 0.15s, color 0.15s !important;
}
[data-testid="stButton"] > button:hover, [data-testid="stFormSubmitButton"] > button:hover,
[data-testid="stDownloadButton"] > button:hover { background: #962E4D !important; color: #fff !important; }
[data-testid="stSelectbox"] > label {
    font-size: 11px !important; font-weight: 700 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important; color: #767672 !important;
}
.ge-hero { background: #962E4D; display: flex; align-items: center; padding: 36px 48px; margin: 0 -2rem 32px -2rem; }
.ge-hero-title { font-family: 'Montserrat', sans-serif; font-size: 48px; font-weight: 800; color: #fff; line-height: 1; letter-spacing: -0.01em; }
.ge-rule { font-size: 12px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #962E4D; border-top: 1.5px solid #962E4D; padding-top: 8px; margin: 20px 0 14px; }
.ag-casa { font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #192D4E; margin: 18px 0 4px; }
.ag-org { font-size: 13px; font-weight: 700; color: #111; margin: 14px 0 6px; }
.ag-org a, .ag-tit a { color: #962E4D; text-decoration: none; border-bottom: 1px solid #DADAD4; }
.ag-tit { font-size: 13.5px; font-weight: 600; color: #111; margin: 10px 0 0; }
.ag-rot { font-size: 10px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #767672; margin-right: 8px; }
.ag-ementa { font-size: 12.5px; color: #333; margin: 2px 0 0; line-height: 1.5; }
.ag-meta { font-size: 11.5px; color: #767672; margin: 2px 0 0; }
.at-meta { font-family: 'Montserrat', sans-serif; font-size: 11.5px; color: #767672; margin-bottom: 10px; }
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
LOGO_PATH = "logo_eixo_gov_magenta.png"
PASTA_SEMANAS = Path("agenda/semanas")
MODELO = Path("modelos/agenda_semana_modelo.docx")


def _semanas_salvas() -> list[str]:
    return sorted((p.stem for p in PASTA_SEMANAS.glob("*.json")), reverse=True)


def _ler_semana(sid: str) -> dict:
    return json.loads((PASTA_SEMANAS / f"{sid}.json").read_text(encoding="utf-8"))


def _rotulo_semana(sid: str) -> str:
    ini = dt.date.fromisoformat(sid)
    return ag.periodo_extenso(ini, ini + dt.timedelta(days=4))


def _a(texto: str, url: str | None) -> str:
    t = _html.escape(texto or "")
    return f'<a href="{_html.escape(url)}" target="_blank" rel="noopener">{t}</a>' if url else t


def _dia_extenso(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{ag.DIAS_SEMANA[d.weekday()]} ({d:%d.%m})"


# ========= SIDEBAR =========
with st.sidebar:
    try:
        st.image(LOGO_PATH, use_container_width=True)
    except Exception:
        st.caption("Logo não encontrada.")
    st.markdown(
        '<div style="border-left:3px solid #962E4D;padding:10px 12px;'
        'margin:10px 0 0 0;background:transparent;">'
        '<p style="font-family:Montserrat,sans-serif;font-size:12.5px;'
        'color:#111;line-height:1.65;margin:0;">'
        'Pauta da semana da <strong>Câmara</strong> e do <strong>Senado</strong>, '
        'coletada toda segunda. Marque os clientes de cada item e baixe '
        'a <strong>Agenda da Semana</strong> em Word, um arquivo por cliente.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** ({st.session_state.get('username', '')})")
    authenticator.logout("Sair", "sidebar")


# ========= MAIN =========
st.markdown('<div class="ge-hero"><div class="ge-hero-title">Agenda da Semana</div></div>',
            unsafe_allow_html=True)

semanas = _semanas_salvas()
c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
with c1:
    if semanas:
        sid = st.selectbox("Semana", semanas, format_func=_rotulo_semana, key="ag_semana")
    else:
        seg, _ = ag.semana_seguinte(dt.date.today() - dt.timedelta(days=7))
        sid = seg.isoformat()
        st.markdown(f'<p class="at-meta">Nenhuma pauta salva ainda. Busque a semana de {_rotulo_semana(sid)}.</p>',
                    unsafe_allow_html=True)
with c2:
    atualizar = st.button("↻ Buscar pauta de novo", use_container_width=True, key="ag_atualizar",
                          help="A pauta muda ao longo da semana. Busca de novo na Câmara e no Senado.")

# a busca na hora fica só na sessão; a do workflow de segunda fica salva no repositório
vivas = st.session_state.setdefault("ag_vivas", {})
if atualizar:
    ini = dt.date.fromisoformat(sid)
    with st.spinner("Buscando a pauta na Câmara e no Senado…"):
        vivas[sid] = {**ag.coletar_semana(ini, ini + dt.timedelta(days=4)),
                      "coletadoEm": dt.datetime.now().strftime("%d/%m %H:%M")}
    st.session_state.pop("ag_pacote", None)

if sid in vivas:
    semana = vivas[sid]
elif sid in semanas:
    semana = _ler_semana(sid)
else:
    st.stop()

for erro in semana.get("erros") or []:
    st.warning(f"Parte da pauta não veio. {erro}")

itens = semana["itens"]
st.markdown(
    f'<p class="at-meta">{len(itens)} itens na pauta de {semana["periodo"]} '
    f'· coletada em {semana.get("coletadoEm", "")}</p>',
    unsafe_allow_html=True,
)

if not itens:
    st.info("A pauta desta semana ainda não foi publicada. Tente buscar de novo mais tarde.")
    st.stop()

# ── seleção ──────────────────────────────────────────────────────────────────
# Tudo dentro de um formulário: marcar uma caixa não recarrega a página.
with st.form("ag_form", border=False):
    for dia in semana["dias"]:
        do_dia = [i for i in itens if i["dia"] == dia]
        st.markdown(f'<div class="ge-rule">{_dia_extenso(dia)}</div>', unsafe_allow_html=True)
        if not do_dia:
            st.markdown('<p class="at-meta">Nada na pauta deste dia.</p>', unsafe_allow_html=True)
            continue
        for casa, casa_nome in ag.CASAS[:2]:
            da_casa = [i for i in do_dia if i["casa"] == casa]
            if not da_casa:
                continue
            st.markdown(f'<div class="ag-casa">{casa_nome}</div>', unsafe_allow_html=True)
            reuniao = None
            for it in da_casa:
                if it["reuniaoLink"] != reuniao:
                    reuniao = it["reuniaoLink"]
                    org = it["colegiado"] + (f' - {it["hora"]}' if it.get("hora") else "")
                    st.markdown(f'<div class="ag-org">{_a(org, reuniao)}</div>', unsafe_allow_html=True)
                texto, caixas = st.columns([1, 1])
                with texto:
                    meta = [f"{r}: {_html.escape(it[k])}" for r, k in
                            (("Autoria", "autor"), ("Relatoria", "relator")) if it.get(k)]
                    st.markdown(
                        f'<p class="ag-tit"><span class="ag-rot">{_html.escape(it.get("rotulo", ""))}</span>'
                        f'{_a(it["titulo"], it.get("tituloLink"))}</p>'
                        + (f'<p class="ag-ementa">{_html.escape(it["ementa"])}</p>' if it.get("ementa") and it["ementa"] != it["titulo"] else "")
                        + (f'<p class="ag-meta">{" · ".join(meta)}</p>' if meta else ""),
                        unsafe_allow_html=True,
                    )
                with caixas:
                    cols = st.columns(3) + st.columns(3)
                    for col, cli in zip(cols, ag.CLIENTES):
                        col.checkbox(cli, key=f"ag_{sid}_{it['id']}_{cli}")

    gerar = st.form_submit_button("Gerar documentos", use_container_width=True)

if gerar:
    selecao = {}
    for it in itens:
        marcados = [c for c in ag.CLIENTES if st.session_state.get(f"ag_{sid}_{it['id']}_{c}")]
        if marcados:
            selecao[it["id"]] = marcados
    if not selecao:
        st.warning("Nenhum item marcado.")
        st.session_state.pop("ag_pacote", None)
    elif not MODELO.exists():
        st.error("O modelo do Word não está no repositório.")
    else:
        pacote, contagem = ag.gerar_pacote(MODELO.read_bytes(), semana, selecao)
        st.session_state["ag_pacote"] = (sid, pacote, contagem)

if st.session_state.get("ag_pacote") and st.session_state["ag_pacote"][0] == sid:
    _, pacote, contagem = st.session_state["ag_pacote"]
    st.markdown(
        '<p class="at-meta">' + " · ".join(f"{c}: {n} {'item' if n == 1 else 'itens'}" for c, n in contagem.items())
        + "</p>",
        unsafe_allow_html=True,
    )
    st.download_button(
        f"⬇ Baixar {len(contagem)} {'documento' if len(contagem) == 1 else 'documentos'} (.zip)",
        data=pacote,
        file_name=f"Agenda da Semana {semana['periodo']}.zip",
        mime="application/zip",
        use_container_width=True,
        key="ag_baixar",
    )
