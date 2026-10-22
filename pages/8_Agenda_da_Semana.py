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
    color: #767672 !important; font-size: 12px !important; padding: 2px 12px !important; min-height: 28px !important;
}
[data-testid="stButtonGroup"] button p { font-size: 12px !important; font-weight: 600 !important; }
[data-testid="stButtonGroup"] button[kind="pillsActive"], [data-testid="stButtonGroup"] button[aria-pressed="true"] {
    background: #962E4D !important; border-color: #962E4D !important; color: #fff !important;
}
[data-testid="stButtonGroup"] button[kind="pillsActive"] p, [data-testid="stButtonGroup"] button[aria-pressed="true"] p { color: #fff !important; }
.ag-resumo { font-size: 14px; color: #111; line-height: 1.7; margin: 4px 0 2px; }
.ag-resumo b { font-weight: 700; }
.ag-sub { font-size: 12.5px; color: #767672; margin: 0 0 8px; }
.ag-org { font-size: 15px; font-weight: 700; color: #192D4E; margin: 22px 0 2px; }
.ag-org a { color: #192D4E; text-decoration: none; }
.ag-org a:hover { text-decoration: underline; }
.ag-org span { font-weight: 500; color: #767672; font-size: 13px; }
.ag-tit { font-size: 14px; font-weight: 700; margin: 0; line-height: 1.45; }
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
LOGO_PATH = "logo_eixo_gov_magenta.png"
PASTA_SEMANAS = Path("agenda/semanas")
MODELO = Path("modelos/agenda_semana_modelo.docx")
SELECAO_SHEET_ID = (st.secrets.get("AGENDA_SHEET_ID") or os.getenv("AGENDA_SHEET_ID", "")).strip()
SELECAO_ABA = "Seleção"


# ========= SELEÇÃO SALVA (planilha "Eixo | Agenda da Semana") =========
# Uma linha por item marcado: Semana | Item | Dia | Colegiado | Proposição ou evento |
# Clientes | Salvo por | Salvo em. Várias pessoas marcam a mesma semana, então cada
# salvamento grava só os itens que aquela pessoa mudou, por cima do que está na planilha.

def _carregar_google_creds_dict():
    if "GOOGLE_SHEETS_CREDS" in st.secrets:
        return dict(st.secrets["GOOGLE_SHEETS_CREDS"])

    if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
        raw = st.secrets["GOOGLE_CREDENTIALS_JSON"]
        if isinstance(raw, str):
            return json.loads(raw)
        return dict(raw)

    creds_json = os.getenv("GOOGLE_SHEETS_CREDS", "") or os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_json:
        return None

    return json.loads(creds_json)


@st.cache_resource
def _aba_selecao():
    if not SELECAO_SHEET_ID:
        raise RuntimeError("AGENDA_SHEET_ID não configurado nos Secrets")
    creds = _carregar_google_creds_dict()
    if not creds:
        raise RuntimeError("Credencial do Google não configurada.")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    gc = gspread.authorize(Credentials.from_service_account_info(creds, scopes=scopes))
    return gc.open_by_key(SELECAO_SHEET_ID).worksheet(SELECAO_ABA)


def _clientes(celula: str) -> set[str]:
    return {c.strip() for c in str(celula or "").split(",") if c.strip() in ag.CLIENTES}


def _ler_planilha(sid: str) -> tuple[dict[str, set[str]], dict[str, int]]:
    salvo, linha_de = {}, {}
    for n, linha in enumerate(_aba_selecao().get_all_values()[1:], start=2):
        linha = (linha + [""] * 8)[:8]
        if linha[0] == sid:
            salvo[linha[1]] = _clientes(linha[5])
            linha_de[linha[1]] = n
    return salvo, linha_de


def _ler_selecao(sid: str) -> dict[str, list[str]]:
    salvo, _ = _ler_planilha(sid)
    return {k: [c for c in ag.CLIENTES if c in v] for k, v in salvo.items() if v}


def _salvar_selecao(sid: str, semana: dict, base: dict, atual: dict, quem: str) -> dict[str, list[str]]:
    """Grava o que mudou desde `base` e devolve a seleção da equipe já mesclada."""
    salvo, linha_de = _ler_planilha(sid)
    por_id = {i["id"]: i for i in semana["itens"]}
    agora = dt.datetime.now(ZoneInfo("America/Recife")).strftime("%d/%m/%Y %H:%M")
    trocas, novas = [], []
    for iid in set(base) | set(atual):
        antes, depois = set(base.get(iid, [])), set(atual.get(iid, []))
        if antes == depois:
            continue
        # tira o que esta pessoa desmarcou e soma o que marcou; o resto é de quem salvou antes
        final = (salvo.get(iid, set()) - (antes - depois)) | (depois - antes)
        salvo[iid] = final
        it = por_id.get(iid, {})
        dia = dt.date.fromisoformat(it["dia"]).strftime("%d/%m/%Y") if it.get("dia") else ""
        linha = [sid, iid, dia, ag.nome_colegiado(it.get("colegiado", "")), it.get("titulo", ""),
                 ", ".join(c for c in ag.CLIENTES if c in final), quem, agora]
        if iid in linha_de:
            trocas.append({"range": f"A{linha_de[iid]}:H{linha_de[iid]}", "values": [linha]})
        else:
            novas.append(linha)
    ws = _aba_selecao()
    if trocas:
        ws.batch_update(trocas, value_input_option="RAW")
    if novas:
        ws.append_rows(novas, value_input_option="RAW")
    return {k: [c for c in ag.CLIENTES if c in v] for k, v in salvo.items() if v}


def _chave(sid: str, item_id: str) -> str:
    return f"ag_{sid}_{item_id}"


def _marcar_caixas(sid: str, itens: list[dict], selecao: dict) -> None:
    for it in itens:
        st.session_state[_chave(sid, it["id"])] = list(selecao.get(it["id"], []))


def _selecao_na_tela(sid: str, itens: list[dict], base: dict) -> dict[str, list[str]]:
    out = {}
    for it in itens:
        if it.get("situacao"):
            # reunião cancelada não tem botão; fica o que estava salvo, para não apagar o registro
            if base.get(it["id"]):
                out[it["id"]] = list(base[it["id"]])
            continue
        marcados = [c for c in ag.CLIENTES if c in (st.session_state.get(_chave(sid, it["id"])) or [])]
        if marcados:
            out[it["id"]] = marcados
    return out


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
semanas = _semanas_salvas()

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
        'Pauta da <strong>Câmara</strong> e do <strong>Senado</strong>, coletada toda segunda cedo. '
        'Marque os clientes de cada item e gere a <strong>Agenda da Semana</strong> em Word, '
        'um arquivo por cliente. A seleção salva é a mesma para toda a equipe.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    atualizar = st.button("↻ Buscar pauta de novo", use_container_width=True, key="ag_atualizar",
                          help="A pauta muda ao longo da semana. Busca de novo na Câmara e no Senado.")
    recarregar = st.button("↻ Ver seleção da equipe", use_container_width=True, key="ag_recarregar",
                           help="Traz o que a equipe salvou desde que você abriu a página. "
                                "Marcações suas ainda não salvas são descartadas.")
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** ({st.session_state.get('username', '')})")
    authenticator.logout("Sair", "sidebar")


# ========= MAIN =========
st.markdown('<div class="ge-hero"><div class="ge-hero-title">Agenda da Semana</div></div>',
            unsafe_allow_html=True)

if semanas:
    sid = st.selectbox("Semana", semanas, format_func=_rotulo_semana, key="ag_semana")
else:
    seg, _ = ag.semana_seguinte(dt.date.today() - dt.timedelta(days=7))
    sid = seg.isoformat()

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
    st.info(f"Ainda não há pauta salva. Use “Buscar pauta de novo” para a semana de {_rotulo_semana(sid)}.")
    st.stop()

for erro in semana.get("erros") or []:
    st.warning(f"Parte da pauta não veio. {erro}")

itens = semana["itens"]
if not itens:
    st.info("A pauta desta semana ainda não foi publicada. Tente “Buscar pauta de novo” mais tarde.")
    st.stop()

# As escolhas nascem com a seleção salva. Depois de salvar, a página recarrega com a
# seleção mesclada (ag_aplicar), porque widget já desenhado não aceita valor novo.
chave_base = f"ag_base_{sid}"
aplicar = st.session_state.pop("ag_aplicar", None)
if aplicar and aplicar[0] == sid:
    st.session_state[chave_base] = aplicar[1]
    _marcar_caixas(sid, itens, aplicar[1])
elif chave_base not in st.session_state or recarregar:
    try:
        salvo = _ler_selecao(sid)
    except Exception as e:
        salvo = st.session_state.get(chave_base, {})
        st.warning(f"Não consegui ler a seleção salva da equipe ({e}).")
    st.session_state[chave_base] = salvo
    _marcar_caixas(sid, itens, salvo)

# ── resumo da semana ─────────────────────────────────────────────────────────
dias_com = [d for d in semana["dias"] if any(i["dia"] == d for i in itens)]
dias_sem = [d for d in semana["dias"] if d not in dias_com]
base = st.session_state.get(chave_base, {})
por_cliente = {c: sum(1 for v in base.values() if c in v) for c in ag.CLIENTES}
marcados = " · ".join(f"{c} {n}" for c, n in por_cliente.items() if n) or "nenhum item ainda"


def _lista_e(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " e " + xs[-1]


def _curto(iso: str) -> str:
    return ag.DIAS_SEMANA[dt.date.fromisoformat(iso).weekday()].split("-")[0].lower()


ativos = [i for i in itens if not i.get("situacao")]
fora = len(itens) - len(ativos)
st.markdown(
    f'<p class="ag-resumo"><b>{len(ativos)} itens</b> na pauta'
    + (f' e {fora} em reunião cancelada ou adiada' if fora else "")
    + (f', sem pauta na {_lista_e([_curto(d) for d in dias_sem])}' if dias_sem else "")
    + f'. Seleção da equipe: {marcados}.</p>'
    f'<p class="ag-sub">Pauta coletada em {semana.get("coletadoEm", "")}.</p>',
    unsafe_allow_html=True,
)

for tipo, msg in st.session_state.pop("ag_msg", []):
    getattr(st, tipo)(msg)

if st.session_state.get("ag_pacote") and st.session_state["ag_pacote"][0] == sid:
    _, pacote, contagem = st.session_state["ag_pacote"]
    st.download_button(
        f"⬇ Baixar {len(contagem)} {'documento' if len(contagem) == 1 else 'documentos'} (.zip) · "
        + " · ".join(f"{c} {n}" for c, n in contagem.items()),
        data=pacote,
        file_name=f"Agenda da Semana {semana['periodo']}.zip",
        mime="application/zip",
        use_container_width=True,
        key="ag_baixar",
    )


# ── seleção ──────────────────────────────────────────────────────────────────
def _item(it: dict) -> None:
    texto, escolha = st.columns([3, 2], gap="large")
    with texto:
        meta = [f"<b>{r}:</b> {_html.escape(it[k])}" for r, k in (("Autoria", "autor"), ("Relatoria", "relator")) if it.get(k)]
        ementa = it.get("ementa") if it.get("ementa") and it["ementa"] != it["titulo"] else ""
        conv = "; ".join(it.get("convidados") or [])
        st.markdown(
            f'<div class="{"ag-fora" if it.get("situacao") else ""}">'
            f'<p class="ag-tit">{_a(it["titulo"], it.get("tituloLink"))}</p>'
            + (f'<p class="ag-ementa" title="{_html.escape(ementa)}">{_html.escape(ementa)}</p>' if ementa else "")
            + (f'<p class="ag-meta">{" · ".join(meta)}</p>' if meta else "")
            + (f'<p class="ag-conv" title="{_html.escape(conv)}"><b>Convidados:</b> {_html.escape(conv)}</p>' if conv else "")
            + "</div>",
            unsafe_allow_html=True,
        )
    with escolha:
        if it.get("situacao"):
            antes = base.get(it["id"]) or []
            st.markdown(
                f'<p class="ag-nota">Reunião {it["situacao"].lower()}, fica fora do Word.'
                + (f' Estava marcada para {_html.escape(_lista_e(antes))}.' if antes else "") + "</p>",
                unsafe_allow_html=True,
            )
        else:
            st.pills("Clientes", ag.CLIENTES, selection_mode="multi", key=_chave(sid, it["id"]),
                     label_visibility="collapsed")
    st.markdown('<div class="ag-fio"></div>', unsafe_allow_html=True)


# Tudo dentro de um formulário: marcar um cliente não recarrega a página.
with st.form("ag_form", border=False):
    a1, a2, _ = st.columns([1, 1, 2])
    salvar = a1.form_submit_button("Salvar seleção", use_container_width=True)
    gerar = a2.form_submit_button("Salvar e gerar Word", use_container_width=True)

    abas = st.tabs([f"{_dia_extenso(d)} · {sum(1 for i in itens if i['dia'] == d)}" for d in dias_com])
    for aba, dia in zip(abas, dias_com):
        with aba:
            do_dia = [i for i in itens if i["dia"] == dia]
            for casa, casa_nome in ag.CASAS[:2]:
                da_casa = [i for i in do_dia if i["casa"] == casa]
                if not da_casa:
                    continue
                st.markdown(f'<div class="ge-rule">{casa_nome}</div>', unsafe_allow_html=True)
                reuniao = None
                for it in da_casa:
                    if it["reuniaoLink"] != reuniao:
                        reuniao = it["reuniaoLink"]
                        detalhe = " · ".join(x for x in (it.get("reuniao") or it.get("rotulo"), it.get("hora")) if x)
                        tag = f'<span class="ag-tag">{it["situacao"]}</span>' if it.get("situacao") else ""
                        st.markdown(
                            f'<div class="ag-org">{_a(ag.nome_colegiado(it["colegiado"]), reuniao)}'
                            f' <span>· {_html.escape(detalhe)}</span>{tag}</div>',
                            unsafe_allow_html=True,
                        )
                    _item(it)

    b1, b2, _ = st.columns([1, 1, 2])
    salvar = b1.form_submit_button("Salvar seleção", use_container_width=True, key="ag_salvar_fim") or salvar
    gerar = b2.form_submit_button("Salvar e gerar Word", use_container_width=True, key="ag_gerar_fim") or gerar

if salvar or gerar:
    msgs = []
    atual = _selecao_na_tela(sid, itens, st.session_state.get(chave_base, {}))
    try:
        selecao = _salvar_selecao(sid, semana, st.session_state.get(chave_base, {}), atual,
                                  st.session_state.get("name") or st.session_state.get("username") or "")
        msgs.append(("success", "Seleção salva. A tela mostra também o que o resto da equipe salvou."))
    except Exception as e:
        selecao = atual
        msgs.append(("error", f"Não consegui salvar na planilha ({e}). Os documentos usam só o que está na sua tela."))
    st.session_state.pop("ag_pacote", None)
    if gerar:
        if not selecao:
            msgs.append(("warning", "Nenhum item marcado."))
        elif not MODELO.exists():
            msgs.append(("error", "O modelo do Word não está no repositório."))
        else:
            pacote, contagem = ag.gerar_pacote(MODELO.read_bytes(), semana, selecao)
            if contagem:
                st.session_state["ag_pacote"] = (sid, pacote, contagem)
            sairam = [i["titulo"] for i in itens if i.get("situacao") and selecao.get(i["id"])]
            if sairam:
                msgs.append(("info", f"Ficaram fora do Word por reunião cancelada ou adiada: {_lista_e(sairam)}."))
            if not contagem:
                msgs.append(("warning", "Todos os itens marcados são de reunião cancelada ou adiada."))
    st.session_state["ag_aplicar"] = (sid, selecao)
    st.session_state["ag_msg"] = msgs
    st.rerun()
