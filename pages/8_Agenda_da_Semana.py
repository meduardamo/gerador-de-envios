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
import importlib
from estilo_paginas import MARINHO, VINHO, cabecalho, chip, esc, explica, resumo, secao, vazio

# o Streamlit Cloud às vezes mantém o módulo velho depois de um push; recarrega a cada rodada
ag = importlib.reload(ag)


st.set_page_config(page_title="Agenda da Semana", layout="wide")

# Base da página (fundo, fonte, cabeçalho do Streamlit escondido) e o que é só da Agenda:
# cartão branco por reunião, pílulas de cliente menores e à direita, texto de cada item.
# Botões, abas, pílulas, chave e títulos vêm do CSS_PAGINAS (carregado depois, no CSS_MENU).
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
.st-key-ag_barra { gap: 24px !important; margin-bottom: 4px; }
.ag-clis { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 13px; color: #4A4A4A; margin: 0 0 12px; }
.ag-clis .r { font-size: 0.72rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: #4E5A6E; margin-right: 4px; }
.st-key-ag_entrega { background: #fff; border: 1px solid #DADAD4; border-radius: 8px; padding: 16px 20px; gap: 12px !important; }
.st-key-ag_entrega [data-testid="stMarkdownContainer"] p { margin-bottom: 0 !important; }
.st-key-ag_novos { margin: 0 0 6px; }
[data-testid="stMain"] div[data-testid="stForm"]:has(.st-key-ag_salvar_fim) { border: 0 !important; background: transparent !important; padding: 0 !important; }
.st-key-ag_acoes, .st-key-ag_acoes_fim { gap: 10px !important; }
.st-key-ag_acoes { margin-bottom: 6px; }
[data-testid="stMain"] .st-key-ag_acoes [data-testid="stTextInput"] > label p { font-size: 0.72rem !important; font-weight: 600 !important; letter-spacing: .04em !important; text-transform: uppercase !important; color: #4E5A6E !important; }
.st-key-ag_acoes_fim { margin-top: 18px; padding-top: 16px; border-top: 1px solid #DADAD4; }
div[class*="st-key-ag_reu_"] { background: #fff; border: 1px solid #DADAD4; border-radius: 8px; padding: 14px 18px; margin-bottom: 10px; gap: .45rem; }
div[class*="st-key-ag_reu_"] [data-testid="stMarkdownContainer"], div[class*="st-key-ag_reu_"] [data-testid="stMarkdown"] { margin-bottom: 0 !important; }
div[class*="st-key-ag_reu_"] [data-testid="stElementContainer"]:has(> [data-testid="stButtonGroup"]), div[class*="st-key-ag_reu_"] [data-testid="stButtonGroup"] { width: 100% !important; }
div[class*="st-key-ag_reu_"] [data-testid="stButtonGroup"] [role="toolbar"] { width: 100% !important; max-width: none !important; gap: 4px !important; justify-content: flex-end !important; }
div[class*="st-key-ag_reu_"] [data-testid="stButtonGroup"] button { padding: 2px 10px !important; min-height: 28px !important; }
div[class*="st-key-ag_reu_"] [data-testid="stButtonGroup"] button p { font-size: 12px !important; }
.ag-org { font-size: 15.5px; font-weight: 700; color: #192D4E; line-height: 1.4; margin: 0; }
.ag-org a, .ag-org a:visited { color: #192D4E !important; text-decoration: none !important; }
.ag-org a:hover { color: #962E4D !important; text-decoration: underline !important; text-underline-offset: 3px; }
.ag-org-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; font-size: 12.5px; color: #4A4A4A;
    margin: 3px 0 4px; padding-bottom: 10px; border-bottom: 1px solid #ECEBE6; }
.ag-top { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 5px; }
p.ag-tit { font-size: 14px !important; font-weight: 700; margin: 0 !important; line-height: 1.45 !important;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ag-tit a, .ag-tit a:visited { color: #192D4E !important; text-decoration: none !important; }
.ag-tit a:hover { color: #962E4D !important; text-decoration: underline !important; text-underline-offset: 3px; }
p.ag-ementa { font-size: 13px !important; color: #3A3A3A !important; margin: 3px 0 0 !important; line-height: 1.5 !important;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
p.ag-meta { font-size: 12px !important; color: #6A6A66 !important; margin: 5px 0 0 !important; line-height: 1.5 !important; }
p.ag-conv { font-size: 12px !important; color: #6A6A66 !important; margin: 4px 0 0 !important; line-height: 1.5 !important;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ag-conv b, .ag-meta b { font-weight: 600; color: #333; }
.ag-fora { opacity: .55; }
.ag-fora .ag-tit a, .ag-fora .ag-tit { text-decoration: line-through !important; }
p.ag-nota { font-size: 12px !important; color: #962E4D !important; font-weight: 600; margin: 4px 0 0 !important; text-align: right; }
.ag-fio { border-bottom: 1px solid #ECEBE6; margin: 6px 0 4px; }
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
        raise RuntimeError("planilha da Agenda não configurada")
    creds = _carregar_google_creds_dict()
    if not creds:
        raise RuntimeError("credencial do Google não configurada")
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


HISTORICO_ABA = "Histórico"
HISTORICO_CAB = ["Semana", "Item", "Dia", "Colegiado", "Proposição ou evento", "Antes", "Depois",
                 "Marcou", "Desmarcou", "Salvo por", "Salvo em"]


@st.cache_resource
def _aba_historico():
    planilha = _aba_selecao().spreadsheet
    try:
        return planilha.worksheet(HISTORICO_ABA)
    except gspread.WorksheetNotFound:
        ws = planilha.add_worksheet(HISTORICO_ABA, rows=1000, cols=len(HISTORICO_CAB))
        ws.append_row(HISTORICO_CAB, value_input_option="RAW")
        return ws


def _ord(clientes: set[str]) -> str:
    return ", ".join(c for c in ag.CLIENTES if c in clientes)


def _salvar_selecao(sid: str, semana: dict, base: dict, atual: dict, quem: str) -> tuple[dict[str, list[str]], list[str]]:
    """Grava o que mudou desde `base`; devolve a seleção da equipe já mesclada e os itens desmarcados."""
    salvo, linha_de = _ler_planilha(sid)
    por_id = {i["id"]: i for i in semana["itens"]}
    agora = dt.datetime.now(ZoneInfo("America/Recife")).strftime("%d/%m/%Y %H:%M")
    trocas, novas, historico, desmarcados = [], [], [], []
    for iid in set(base) | set(atual):
        antes, depois = set(base.get(iid, [])), set(atual.get(iid, []))
        if antes == depois:
            continue
        # tira o que esta pessoa desmarcou e soma o que marcou; o resto é de quem salvou antes
        anterior = set(salvo.get(iid, set()))
        final = (anterior - (antes - depois)) | (depois - antes)
        salvo[iid] = final
        it = por_id.get(iid, {})
        dia = dt.date.fromisoformat(it["dia"]).strftime("%d/%m/%Y") if it.get("dia") else ""
        linha = [sid, iid, dia, ag.nome_colegiado(it.get("colegiado", "")), it.get("titulo", ""),
                 ", ".join(c for c in ag.CLIENTES if c in final), quem, agora]
        historico.append(linha[:5] + [_ord(anterior), _ord(final), _ord(depois - antes), _ord(antes - depois),
                                      quem, agora])
        if antes - depois:
            desmarcados.append(f'{it.get("titulo") or iid} ({_ord(antes - depois)})')
        if iid in linha_de:
            trocas.append({"range": f"A{linha_de[iid]}:H{linha_de[iid]}", "values": [linha]})
        else:
            novas.append(linha)
    ws = _aba_selecao()
    if trocas:
        ws.batch_update(trocas, value_input_option="RAW")
    if novas:
        ws.append_rows(novas, value_input_option="RAW")
    if historico:
        try:
            _aba_historico().append_rows(historico, value_input_option="RAW")
        except Exception:
            pass  # o histórico não pode impedir a seleção de ser salva
    return {k: [c for c in ag.CLIENTES if c in v] for k, v in salvo.items() if v}, desmarcados


def _chave(sid: str, item_id: str) -> str:
    return f"ag_{sid}_{item_id}"


def _marcar_caixas(sid: str, itens: list[dict], selecao: dict) -> None:
    for it in itens:
        st.session_state[_chave(sid, it["id"])] = list(selecao.get(it["id"], []))


def _selecao_na_tela(sid: str, itens: list[dict], base: dict) -> dict[str, list[str]]:
    out = {}
    for it in itens:
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
        'um arquivo por cliente. A seleção salva vale para toda a equipe.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    atualizar = st.button("Buscar pauta de novo", icon=":material/refresh:", use_container_width=True,
                          key="ag_atualizar",
                          help="A pauta muda ao longo da semana. Busca de novo na Câmara e no Senado.")
    recarregar = st.button("Ver seleção da equipe", icon=":material/group:", use_container_width=True,
                           key="ag_recarregar",
                           help="Traz o que a equipe salvou desde que você abriu a página. "
                                "Marcações suas ainda não salvas são descartadas.")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** ({st.session_state.get('username', '')})")
    authenticator.logout("Sair", "sidebar")


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


# ========= MAIN =========
cabecalho("Agenda da Semana",
          "Pauta da Câmara e do Senado: marque os clientes de cada item e gere a agenda em Word, um arquivo por cliente.")

if semanas:
    with st.container(horizontal=True, vertical_alignment="bottom", key="ag_barra"):
        sid = st.selectbox("Semana", semanas, format_func=_rotulo_semana, key="ag_semana", width=360)
else:
    seg, _ = ag.semana_seguinte(dt.date.today() - dt.timedelta(days=7))
    sid = seg.isoformat()

# a busca na hora fica só na sessão; a do workflow de segunda fica salva no repositório
vivas = st.session_state.setdefault("ag_vivas", {})
if atualizar:
    ini = dt.date.fromisoformat(sid)
    with st.spinner("Buscando a pauta na Câmara e no Senado…"):
        viva = {**ag.coletar_semana(ini, ini + dt.timedelta(days=4)),
                "coletadoEm": dt.datetime.now(ZoneInfo("America/Recife")).strftime("%d/%m %H:%M")}
        hoje = dt.datetime.now(ZoneInfo("America/Recife")).date()
        anterior = _ler_semana(sid) if sid in semanas else None
        viva = ag.preservar_fontes_com_erro(viva, anterior)
        vivas[sid] = {**viva, **ag.foto_segunda(viva, anterior, hoje <= ini)}
    st.session_state.pop("ag_pacote", None)

if sid in vivas:
    semana = vivas[sid]
elif sid in semanas:
    semana = _ler_semana(sid)
else:
    vazio(f"Ainda não há pauta salva para a semana de {_rotulo_semana(sid)}. "
          "Clique em Buscar pauta de novo, na barra lateral, para trazer a pauta da Câmara e do Senado.")
    st.stop()

for erro in semana.get("erros") or []:
    st.warning(f"Parte da pauta não veio. {erro} Para tentar de novo, use Buscar pauta de novo, na barra lateral.")

itens = semana["itens"]
if not itens:
    vazio("A pauta desta semana ainda não foi publicada pela Câmara e pelo Senado. "
          "Tente Buscar pauta de novo, na barra lateral, mais tarde.")
    st.stop()

# As escolhas nascem com a seleção salva. Depois de salvar, a página recarrega com a
# seleção mesclada (ag_aplicar), porque widget já desenhado não aceita valor novo.
chave_base = f"ag_base_{sid}"
aplicar = st.session_state.pop("ag_aplicar", None)
if aplicar and aplicar[0] == sid:
    st.session_state[chave_base] = aplicar[1]
    _marcar_caixas(sid, itens, aplicar[1])
elif chave_base not in st.session_state or recarregar or atualizar:
    try:
        salvo = _ler_selecao(sid)
    except Exception as e:
        salvo = st.session_state.get(chave_base, {})
        st.warning(f"Não consegui ler a seleção salva da equipe ({e}). "
                   "Use Ver seleção da equipe, na barra lateral, para tentar de novo.")
    st.session_state[chave_base] = salvo
    _marcar_caixas(sid, itens, salvo)

# ── resumo da semana ─────────────────────────────────────────────────────────
dias_com = [d for d in semana["dias"] if any(i["dia"] == d for i in itens)]
dias_sem = [d for d in semana["dias"] if d not in dias_com]
base = st.session_state.get(chave_base, {})
por_cliente = {c: sum(1 for v in base.values() if c in v) for c in ag.CLIENTES}
n_marc = sum(1 for v in base.values() if v)


def _lista_e(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " e " + xs[-1]


def _curto(iso: str) -> str:
    return ag.DIAS_SEMANA[dt.date.fromisoformat(iso).weekday()].split("-")[0].lower()


ativos = [i for i in itens if not i.get("situacao")]
fora = len(itens) - len(ativos)
novos = ag.novos_desde_segunda(semana)
pacote_pronto = bool(st.session_state.get("ag_pacote")) and st.session_state["ag_pacote"][0] == sid


resumo(
    [(len(ativos), "item na pauta" if len(ativos) == 1 else "itens na pauta")]
    + ([(fora, "em reunião cancelada ou adiada", True)] if fora else [])
    + ([(len(novos), "novo desde segunda" if len(novos) == 1 else "novos desde segunda")] if novos else [])
    + [(n_marc, "com cliente marcado")]
)
clis = "".join(chip(f"{c} · {n}", "org") for c, n in por_cliente.items() if n)
st.markdown(
    '<div class="ag-clis"><span class="r">Seleção da equipe</span>'
    + (clis or "<span>nenhum item marcado ainda</span>")
    + "</div>",
    unsafe_allow_html=True,
)
explica(f"Pauta coletada em {semana.get('coletadoEm', '')}."
        + (f" Sem pauta na {_lista_e([_curto(d) for d in dias_sem])}." if dias_sem else ""))

msgs_vindas = st.session_state.pop("ag_msg", [])
for tipo, msg in msgs_vindas:
    getattr(st, tipo)(msg)
# quem clicou no botão do fim da página continua lá embaixo depois de recarregar
if msgs_vindas and pacote_pronto:
    st.toast("Word pronto. Os botões de baixar estão no alto da página.", icon=":material/download:")
elif any(t == "success" for t, _ in msgs_vindas):
    st.toast("Seleção salva.", icon=":material/check:")

if pacote_pronto:
    _, pacote, arquivos, contagem, atualizacao = st.session_state["ag_pacote"]
    extra = f" (atualização {dt.date.fromisoformat(atualizacao):%d.%m})" if atualizacao else ""
    secao("Word pronto",
          _plural(len(contagem), "cliente", "clientes")
          + (f" · atualização {dt.date.fromisoformat(atualizacao):%d.%m}" if atualizacao else ""),
          "#1F5E43",
          "Um documento por cliente, só com os itens marcados para ele. "
          "Item de reunião cancelada ou adiada fica de fora.")
    with st.container(key="ag_entrega"):
        st.download_button(
            f"Baixar todos{' os ' + str(len(contagem)) if len(contagem) > 1 else ''} (.zip)",
            data=pacote,
            file_name=f"Agenda da Semana {semana['periodo']}{extra}.zip",
            mime="application/zip",
            type="primary",
            icon=":material/download:",
            key="ag_baixar",
        )
        explica("Ou baixe só o de um cliente. O número é a quantidade de itens no arquivo.")
        # um botão por cliente, para baixar só o documento de um
        with st.container(key="ag_por_cliente"):
            cols = st.columns(len(ag.CLIENTES))
            for col, (nome, dados), (cli, n) in zip(cols, arquivos.items(), contagem.items()):
                col.download_button(f"{cli} · {n}", data=dados, file_name=nome, use_container_width=True,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    icon=":material/download:", key=f"ag_baixar_{cli}",
                                    help=f"{_plural(n, 'item', 'itens')} no Word de {cli}")


# ── seleção ──────────────────────────────────────────────────────────────────
def _item(it: dict, fio: bool) -> None:
    texto, escolha = st.columns([1.15, 1], gap="large", vertical_alignment="top")
    with texto:
        meta = [f"<b>{r}:</b> {esc(it[k])}" for r, k in (("Autoria", "autor"), ("Relatoria", "relator")) if it.get(k)]
        titulo = it["titulo"]
        ementa = it.get("ementa") if it.get("ementa") and it["ementa"] != titulo else ""
        if ementa and titulo in (it.get("reuniao"), it.get("rotulo")):
            # audiência do Senado: o título repetia o tipo da reunião, que já está no cabeçalho
            titulo, ementa = ementa, ""
        conv = "; ".join(it.get("convidados") or [])
        st.markdown(
            f'<div class="{"ag-fora" if it.get("situacao") else ""}">'
            + (f'<div class="ag-top">{chip("Novo desde segunda", "alerta")}</div>' if it["id"] in novos else "")
            + f'<p class="ag-tit" title="{esc(titulo)}">{_a(titulo, it.get("tituloLink"))}</p>'
            + (f'<p class="ag-ementa" title="{esc(ementa)}">{esc(ementa)}</p>' if ementa else "")
            + (f'<p class="ag-meta">{" · ".join(meta)}</p>' if meta else "")
            + (f'<p class="ag-conv" title="{esc(conv)}"><b>Convidados:</b> {esc(conv)}</p>' if conv else "")
            + "</div>",
            unsafe_allow_html=True,
        )
    with escolha:
        st.pills("Clientes", ag.CLIENTES, selection_mode="multi", key=_chave(sid, it["id"]),
                 label_visibility="collapsed")
        if it.get("situacao"):
            st.markdown(f'<p class="ag-nota">Reunião {esc(it["situacao"].lower())}, fica fora do Word.</p>',
                        unsafe_allow_html=True)
    if fio:
        st.markdown('<div class="ag-fio"></div>', unsafe_allow_html=True)


COR_CASA = {"CD": MARINHO, "SF": VINHO}

secao("Pauta por dia", f"{_plural(len(itens), 'item', 'itens')} em {_plural(len(dias_com), 'dia', 'dias')}", MARINHO,
      "Marcar um cliente não grava nada nem recarrega a página. Salvar seleção grava só o que você mudou, "
      "por cima do que o resto da equipe já salvou, e registra no histórico. Salvar e gerar Word grava e "
      "monta um arquivo por cliente.")

# ── o que entrou depois de segunda ───────────────────────────────────────────
so_novos = False
if novos:
    so_novos = st.container(key="ag_novos").toggle(
        f"Só {'o item novo' if len(novos) == 1 else f'os {len(novos)} itens novos'} desde a coleta de "
        f"{semana.get('coletadoSegunda', 'segunda')}",
        key=f"ag_so_novos_{sid}",
        help="Mostra só o que entrou na pauta depois de segunda. O Word sai só com esses itens, "
             "num arquivo de atualização.",
    )
    if so_novos:
        explica("A tela e o Word mostram só os itens novos. Os outros continuam marcados; "
                "para ver ou gerar a agenda completa, desligue a chave.")

# Com a chave de novos ligada, os outros itens saem da tela. O Streamlit esquece o valor
# de widget que não foi desenhado, então quem volta à tela nasce de novo da seleção salva.
visiveis = [i for i in itens if not so_novos or i["id"] in novos]
for it in visiveis:
    if _chave(sid, it["id"]) not in st.session_state:
        st.session_state[_chave(sid, it["id"])] = list(base.get(it["id"], []))
dias_vis = [d for d in dias_com if any(i["dia"] == d for i in visiveis)]

# Tudo dentro de um formulário: marcar um cliente não recarrega a página.
with st.form("ag_form", border=False):
    with st.container(horizontal=True, vertical_alignment="bottom", key="ag_acoes"):
        st.text_input("Seu nome", key="ag_quem", placeholder="quem está marcando", width=240,
                      help="O login é da equipe. O nome entra no histórico de cada salvamento.")
        salvar = st.form_submit_button("Salvar seleção", icon=":material/save:")
        gerar = st.form_submit_button("Salvar e gerar Word", type="primary", icon=":material/description:")

    if not dias_vis:
        vazio("Nenhum item para mostrar. Desligue a chave de itens novos para ver a pauta completa.")
    else:
        abas = st.tabs([f"{_dia_extenso(d)} · {sum(1 for i in visiveis if i['dia'] == d)}" for d in dias_vis])
        for aba, dia in zip(abas, dias_vis):
            with aba:
                do_dia = [i for i in visiveis if i["dia"] == dia]
                for casa, casa_nome in ag.CASAS[:2]:
                    da_casa = [i for i in do_dia if i["casa"] == casa]
                    if not da_casa:
                        continue
                    secao(casa_nome, _plural(len(da_casa), "item", "itens"), COR_CASA.get(casa, MARINHO), menor=True)
                    # uma reunião por cartão; itens seguidos da mesma reunião ficam juntos
                    grupos: list[list[dict]] = []
                    for it in da_casa:
                        if grupos and grupos[-1][-1]["reuniaoLink"] == it["reuniaoLink"]:
                            grupos[-1].append(it)
                        else:
                            grupos.append([it])
                    for g, grupo in enumerate(grupos):
                        it0 = grupo[0]
                        detalhe = " · ".join(x for x in (it0.get("reuniao") or it0.get("rotulo"), it0.get("hora")) if x)
                        with st.container(key=f"ag_reu_{dia}_{casa}_{g}"):
                            st.markdown(
                                f'<p class="ag-org">{_a(ag.nome_colegiado(it0["colegiado"]), it0["reuniaoLink"])}</p>'
                                f'<div class="ag-org-meta"><span>{esc(detalhe)}</span>'
                                + (chip(f"Reunião {it0['situacao'].lower()}", "erro") if it0.get("situacao") else "")
                                + "</div>",
                                unsafe_allow_html=True,
                            )
                            for k, it in enumerate(grupo):
                                _item(it, fio=k + 1 < len(grupo))

    with st.container(horizontal=True, vertical_alignment="center", key="ag_acoes_fim"):
        salvar = st.form_submit_button("Salvar seleção", icon=":material/save:", key="ag_salvar_fim") or salvar
        gerar = st.form_submit_button("Salvar e gerar Word", type="primary", icon=":material/description:",
                                      key="ag_gerar_fim") or gerar

if salvar or gerar:
    msgs = []
    base = st.session_state.get(chave_base, {})
    ids_vis = {i["id"] for i in visiveis}
    # item fora da tela fica como estava salvo
    atual = {k: v for k, v in base.items() if k not in ids_vis} | _selecao_na_tela(sid, visiveis, base)
    try:
        login = st.session_state.get("name") or st.session_state.get("username") or ""
        nome = (st.session_state.get("ag_quem") or "").strip()
        selecao, desmarcados = _salvar_selecao(sid, semana, base, atual, f"{login} ({nome})" if nome else login)
        msgs.append(("success", "Seleção salva. A tela mostra também o que o resto da equipe salvou."))
        if desmarcados:
            msgs.append(("warning", f"Este salvamento desmarcou {len(desmarcados)} "
                         f"{'item' if len(desmarcados) == 1 else 'itens'}: {'; '.join(desmarcados[:15])}"
                         + (f" e mais {len(desmarcados) - 15}" if len(desmarcados) > 15 else "")
                         + ". Se não foi de propósito, marque de novo e salve."))
    except Exception as e:
        selecao = atual
        msgs.append(("error", f"Não consegui salvar a seleção da equipe ({e}). Os documentos usam só o que está "
                     "na sua tela. Tente salvar de novo em alguns minutos."))
    st.session_state.pop("ag_pacote", None)
    if gerar:
        if not selecao:
            msgs.append(("warning", "Nenhum item marcado. Marque ao menos um cliente em algum item e gere de novo."))
        elif not MODELO.exists():
            msgs.append(("error", "O modelo do Word não foi encontrado. Avise a equipe de dados."))
        else:
            atualizacao = ""
            if so_novos:
                dia, mes = semana.get("coletadoEm", "")[:5].split("/")
                atualizacao = dt.date(int(sid[:4]), int(mes), int(dia)).isoformat()
            pacote, arquivos, contagem = ag.gerar_pacote(MODELO.read_bytes(), semana, selecao,
                                                         so_ids=novos if so_novos else None,
                                                         atualizacao=atualizacao)
            if contagem:
                st.session_state["ag_pacote"] = (sid, pacote, arquivos, contagem, atualizacao)
            sairam = [i["titulo"] for i in itens if i.get("situacao") and selecao.get(i["id"])]
            if sairam:
                msgs.append(("info", f"Ficaram fora do Word por reunião cancelada ou adiada: {_lista_e(sairam)}."))
            if not contagem:
                msgs.append(("warning", "Nenhum item novo está marcado. Marque os clientes nos itens novos ou desligue a chave." if so_novos else
                             "Todos os itens marcados são de reunião cancelada ou adiada."))
    st.session_state["ag_aplicar"] = (sid, selecao)
    st.session_state["ag_msg"] = msgs
    st.rerun()
