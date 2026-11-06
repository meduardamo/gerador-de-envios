from __future__ import annotations

import datetime as dt
import html as _html
import json
import os
import unicodedata
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import gspread
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials

import agenda_semana_core as ag
import importlib
from estilo_paginas import MARINHO, VINHO, cabecalho, chip, esc, explica, resumo, secao, vazio

# o Streamlit Cloud às vezes mantém o módulo velho depois de um push; recarrega a cada rodada
ag = importlib.reload(ag)


from base_pagina import exigir_login, iniciar

iniciar("Agenda da Semana")

# Base da página (fundo, fonte, cabeçalho do Streamlit escondido) e o que é só da Agenda:
# cartão branco por reunião, pílulas de cliente menores e à direita, texto de cada item.
# Botões, abas, pílulas, chave e títulos vêm do CSS_PAGINAS (carregado depois, no CSS_MENU).
st.markdown("""<style>
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1320px !important; padding: 1.8rem 2.5rem 4rem !important; background: #F4F3EF; }
.st-key-ag_barra { gap: 24px !important; margin-bottom: 4px; }
.ag-clis { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 13px; color: #4A4A4A; margin: 0 0 12px; }
.ag-clis .r { font-size: 0.72rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: #4E5A6E; margin-right: 4px; }
.st-key-ag_entrega { background: #fff; border: 1px solid #DADAD4; border-radius: 8px; padding: 16px 20px; gap: 12px !important; }
.st-key-ag_entrega [data-testid="stMarkdownContainer"] p { margin-bottom: 0 !important; }
.st-key-ag_novos { min-height: 40px; justify-content: center; }
.st-key-ag_filtro { margin: 4px 0 2px; gap: 12px !important; }
div.st-key-ag_filtro div[data-testid="stMultiSelect"] div[data-testid="stMultiSelectTagsContainer"] { flex-wrap: wrap !important; height: auto !important; max-height: none !important; overflow: visible !important; row-gap: 4px; padding: 4px 0 !important; }
div.st-key-ag_filtro div[data-testid="stMultiSelect"] div:has(> div[data-testid="stMultiSelectTagsContainer"]), div.st-key-ag_filtro div[data-testid="stMultiSelect"] div:has(> div > div[data-testid="stMultiSelectTagsContainer"]) { height: auto !important; max-height: none !important; }
p.ag-sb { font-size: 12px !important; color: #4A4A4A !important; line-height: 1.55 !important; margin: 0 0 12px !important; }
/* texto da coleta centrado na altura das caixas de Área e Semana (o -16px do markdown é compensado) */
.st-key-ag_barra p.ag-coleta { font-size: 12.5px; color: #4A4A4A; line-height: 1.5; height: 38px; margin: 0 0 17px !important; display: flex; flex-direction: column; justify-content: center; }
[data-testid="stMain"] div[data-testid="stForm"]:has(.st-key-ag_salvar_fim) { border: 0 !important; background: transparent !important; padding: 0 !important; }
.st-key-ag_acoes, .st-key-ag_acoes_fim { gap: 10px !important; }
.st-key-ag_acoes { margin: 2px 0 6px; }
[data-testid="stMain"] .st-key-ag_acoes [data-testid="stTextInput"] > label p { font-size: 0.72rem !important; font-weight: 600 !important; letter-spacing: .04em !important; text-transform: uppercase !important; color: #4E5A6E !important; }
.st-key-ag_acoes_fim { margin-top: 18px; padding-top: 16px; border-top: 1px solid #DADAD4; }
div[class*="st-key-ag_casa_"] [data-testid="stExpander"] details { border: 0 !important; background: transparent !important; }
div[class*="st-key-ag_casa_"] [data-testid="stExpander"] summary { padding: 18px 0 8px !important; gap: 8px; background: transparent !important; }
div[class*="st-key-ag_casa_"] [data-testid="stExpander"] summary:hover, div[class*="st-key-ag_casa_"] [data-testid="stExpander"] summary:focus-visible { background: transparent !important; }
div[class*="st-key-ag_casa_"] [data-testid="stExpander"] summary::before { content: ""; width: 14px; height: 14px; border-radius: 4px; flex: none; background: #192D4E; order: -1; }
div.st-key-ag_casa_SF [data-testid="stExpander"] summary::before, div[class*="st-key-ag_casa_SF"] [data-testid="stExpander"] summary::before { background: #962E4D; }
div[class*="st-key-ag_casa_"] [data-testid="stExpander"] summary p { font-size: 15.5px !important; font-weight: 700 !important; color: #192D4E !important; }
div[class*="st-key-ag_casa_"] [data-testid="stExpander"] summary p span { font-size: 13px; font-weight: 400; color: #6B6B6B !important; margin-left: 2px; }
div[class*="st-key-ag_casa_"] [data-testid="stExpander"] summary:hover p { color: #962E4D !important; }
div[class*="st-key-ag_casa_"] [data-testid="stExpanderDetails"] { padding: 0 !important; }
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
authenticator = exigir_login()


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


# A caixa de cada item tem uma chave por área: ao trocar de área, a caixa da outra
# área nasce de novo da seleção salva, só com os clientes dela.
def _chave(sid: str, area: str, item_id: str) -> str:
    return f"ag_{sid}_{area}_{item_id}"


def _da_area(clientes, area: str) -> list[str]:
    return [c for c in ag.AREAS[area] if c in (clientes or [])]


def _marcar_caixas(sid: str, area: str, itens: list[dict], selecao: dict) -> None:
    for it in itens:
        for a in ag.AREAS:
            st.session_state.pop(_chave(sid, a, it["id"]), None)
        st.session_state[_chave(sid, area, it["id"])] = _da_area(selecao.get(it["id"]), area)


def _selecao_na_tela(sid: str, area: str, itens: list[dict], base: dict) -> dict[str, list[str]]:
    """O que está na tela para os clientes da área, somado aos clientes das outras áreas como estavam salvos."""
    out = {}
    for it in itens:
        tela = set(_da_area(st.session_state.get(_chave(sid, area, it["id"])), area))
        outras = {c for c in base.get(it["id"], []) if c not in ag.AREAS[area]}
        marcados = [c for c in ag.CLIENTES if c in tela | outras]
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
    return f"{ag.DIAS_SEMANA[d.weekday()]} ({d:%d/%m})"


# ========= SIDEBAR =========
semanas = _semanas_salvas()

with st.sidebar:
    # st.caption na sidebar ganha fio em cima (CSS comum, feito para a linha do usuário); aqui é texto solto
    st.markdown('<p class="ag-sb">Pauta coletada segunda e terça às 7h. '
                'A seleção salva vale para toda a equipe.</p>', unsafe_allow_html=True)
    atualizar = st.button("Buscar pauta de novo", icon=":material/refresh:", width="stretch",
                          key="ag_atualizar",
                          help="A pauta muda ao longo da semana. Busca de novo na Câmara e no Senado.")
    recarregar = st.button("Ver seleção da equipe", icon=":material/group:", width="stretch",
                           key="ag_recarregar",
                           help="Traz o que a equipe salvou desde que você abriu a página. "
                                "Marcações suas ainda não salvas são descartadas.")
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** ({st.session_state.get('username', '')})")
    authenticator.logout("Sair", "sidebar")


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


# ========= MAIN =========
cabecalho("Agenda da Semana",
          "Pauta da Câmara e do Senado: marque os clientes de cada item e gere a agenda em Word, um arquivo por cliente.")

AREAS = list(ag.AREAS)
# ?area=educacao no endereço abre direto na área (para cada equipe salvar o seu link)
_area_url = str(st.query_params.get("area", "")).lower()
_area_ini = next((i for i, a in enumerate(AREAS) if a.lower().startswith(_area_url[:3])), 0) if _area_url else 0
with st.container(horizontal=True, vertical_alignment="bottom", key="ag_barra"):
    area = st.selectbox("Área", AREAS, index=_area_ini, key="ag_area", width=200,
                        help="Mostra só os clientes da área. A pauta é a mesma para todas.")
    if semanas:
        sid = st.selectbox("Semana", semanas, format_func=_rotulo_semana, key="ag_semana", width=360)
    else:
        seg, _ = ag.semana_seguinte(dt.date.today() - dt.timedelta(days=7))
        sid = seg.isoformat()
    lugar_coleta = st.empty()  # preenchido depois que a semana é lida
CLIS = ag.AREAS[area]

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
    _marcar_caixas(sid, area, itens, aplicar[1])
elif chave_base not in st.session_state or recarregar or atualizar:
    try:
        salvo = _ler_selecao(sid)
    except Exception as e:
        salvo = st.session_state.get(chave_base, {})
        st.warning(f"Não consegui ler a seleção salva da equipe ({e}). "
                   "Use Ver seleção da equipe, na barra lateral, para tentar de novo.")
    st.session_state[chave_base] = salvo
    _marcar_caixas(sid, area, itens, salvo)

# ── resumo da semana ─────────────────────────────────────────────────────────
dias_com = [d for d in semana["dias"] if any(i["dia"] == d for i in itens)]
dias_sem = [d for d in semana["dias"] if d not in dias_com]
base = st.session_state.get(chave_base, {})
por_cliente = {c: sum(1 for v in base.values() if c in v) for c in CLIS}
n_marc = sum(1 for v in base.values() if _da_area(v, area))


def _lista_e(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " e " + xs[-1]


def _curto(iso: str) -> str:
    return ag.DIAS_SEMANA[dt.date.fromisoformat(iso).weekday()].split("-")[0].lower()


def _quando(coleta: str, artigo: bool = False) -> str:
    """'03/11 13:44' -> 'terça-feira, 03/11, às 13:44' (com artigo: 'na terça-feira, ...')."""
    try:
        data, hora = coleta.split()
        dia, mes = (int(x) for x in data.split("/"))
        ano = int(sid[:4]) + (1 if mes < int(sid[5:7]) else 0)
        d = dt.date(ano, mes, dia)
    except (ValueError, AttributeError):
        return coleta
    nome = ag.DIAS_SEMANA[d.weekday()].lower()
    txt = f"{nome}, {data}, às {hora}"
    return (("no " if d.weekday() >= 5 else "na ") + txt) if artigo else txt


ativos = [i for i in itens if not i.get("situacao")]
fora = len(itens) - len(ativos)
novos = ag.novos_desde_segunda(semana)
pacote_pronto = bool(st.session_state.get("ag_pacote")) and st.session_state["ag_pacote"][:2] == (sid, area)


resumo(
    [(len(itens), "item na pauta" if len(itens) == 1 else "itens na pauta")]
    + ([(fora, "cancelado ou adiado" if fora == 1 else "cancelados ou adiados", True)] if fora else [])
    + ([(len(novos), "novo desde segunda" if len(novos) == 1 else "novos desde segunda")] if novos else [])
    + [(n_marc, "marcado" if n_marc == 1 else "marcados")]
)
lugar_coleta.markdown(
    f'<p class="ag-coleta">Coletada {esc(_quando(semana.get("coletadoEm", ""), artigo=True))}.</p>',
    unsafe_allow_html=True,
)

msgs_vindas = st.session_state.pop("ag_msg", [])
for tipo, msg in msgs_vindas:
    getattr(st, tipo)(msg)
# quem clicou no botão do fim da página continua lá embaixo depois de recarregar
if msgs_vindas and pacote_pronto:
    st.toast("Word pronto. Os botões de baixar estão no alto da página.", icon=":material/download:")
elif any(t == "success" for t, _ in msgs_vindas):
    st.toast("Seleção salva.", icon=":material/check:")

if pacote_pronto:
    _, _, pacote, arquivos, contagem, atualizacao = st.session_state["ag_pacote"]
    extra = f" (atualização {dt.date.fromisoformat(atualizacao):%d.%m})" if atualizacao else ""
    secao("Word pronto",
          _plural(len(contagem), "cliente", "clientes")
          + (f" · atualização {dt.date.fromisoformat(atualizacao):%d/%m}" if atualizacao else ""),
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
            cols = st.columns(len(CLIS))
            for col, (nome, dados), (cli, n) in zip(cols, arquivos.items(), contagem.items()):
                col.download_button(f"{cli} · {n}", data=dados, file_name=nome, width="stretch",
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
        st.pills("Clientes", CLIS, selection_mode="multi", key=_chave(sid, area, it["id"]),
                 label_visibility="collapsed")
        if it.get("situacao"):
            st.markdown(f'<p class="ag-nota">Reunião {esc(it["situacao"].lower())}, fica fora do Word.</p>',
                        unsafe_allow_html=True)
    if fio:
        st.markdown('<div class="ag-fio"></div>', unsafe_allow_html=True)


COR_CASA = {"CD": MARINHO, "SF": VINHO}

AJUDA_SALVAR = ("Marcar um cliente não grava nada. Salvar seleção grava só o que você mudou, por cima do que "
                "o resto da equipe já salvou, e registra no histórico.")
AJUDA_GERAR = "Grava a seleção e monta um Word por cliente da área."

# ── o que entrou depois de segunda ───────────────────────────────────────────
# a chave fica na linha dos filtros; o valor da rodada anterior decide a lista de comissões
so_novos = bool(novos) and bool(st.session_state.get(f"ag_so_novos_{sid}"))

# ── filtro por comissão (só a tela; o Word continua com tudo o que está marcado) ──
def _comissao(it: dict) -> str:
    nome = ag.nome_colegiado(it["colegiado"])
    if len(nome) > 80:  # comissão especial traz a ementa inteira no nome; fica o começo e a sigla
        sigla = nome[nome.rfind(" ("):] if nome.endswith(")") else ""
        nome = nome[:70].rsplit(" ", 1)[0] + "…" + sigla
    return f'{nome} · {"Câmara" if it["casa"] == "CD" else "Senado"}'


comissoes = sorted({_comissao(i) for i in itens if not so_novos or i["id"] in novos},
                   key=lambda c: (c.rsplit(" · ", 1)[1] != "Câmara", c.startswith("Plenário"), c))
filtro_key = f"ag_comissoes_{sid}_{area}"
if filtro_key in st.session_state:  # comissão que sumiu da pauta (ou da chave de novos) sai do filtro
    st.session_state[filtro_key] = [c for c in st.session_state[filtro_key] if c in comissoes]
else:  # a página abre com as comissões da área e os Plenários
    st.session_state[filtro_key] = sorted(
        {_comissao(i) for i in itens if ag.comissao_da_area(i["casa"], i["colegiado"], area)} & set(comissoes),
        key=comissoes.index)


def _sem_acento(t: str) -> str:
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def _texto_item(it: dict) -> str:
    partes = [it.get(k) or "" for k in ("titulo", "ementa", "autor", "relator", "rotulo", "reuniao")]
    return _sem_acento(" ".join(partes + [ag.nome_colegiado(it["colegiado"])] + list(it.get("convidados") or [])))


with st.container(horizontal=True, vertical_alignment="top", key="ag_filtro"):
    busca = st.text_input(
        "Buscar", key=f"ag_busca_{sid}", placeholder="Buscar número, autor ou palavra", width=280,
        label_visibility="collapsed",
    )
    filtro = st.multiselect(
        "Comissões", comissoes, key=filtro_key, placeholder="Todas as comissões",
        label_visibility="collapsed",
        # "Comissão de Saúde (CSAUDE) · Câmara" aparece como "Saúde (CSAUDE) · Câmara"
        format_func=lambda c: c.removeprefix("Comissão de ").removeprefix("Comissão do ").removeprefix("Comissão da "),
    )
    if novos:
        with st.container(width="content", key="ag_novos"):
            st.toggle(
                "Só os novos", key=f"ag_so_novos_{sid}",
                help=f"Só o que entrou na pauta depois da coleta de "
                     f"{_quando(semana.get('coletadoSegunda', '')) or 'segunda'}. "
                     "O Word sai só com esses itens, num arquivo de atualização.",
            )
termos = _sem_acento(busca).split()

# Com a chave de novos, o filtro ou a busca, os outros itens saem da tela. O Streamlit esquece o valor
# de widget que não foi desenhado, então quem volta à tela nasce de novo da seleção salva.
universo = [i for i in itens if not so_novos or i["id"] in novos]
visiveis = [i for i in universo if (not filtro or _comissao(i) in filtro)
            and all(t in _texto_item(i) for t in termos)]
if len(visiveis) < len(universo):
    # a busca também acha o que está fora das comissões escolhidas; avisa para não parecer que não existe
    achados_fora = sum(1 for i in universo if filtro and _comissao(i) not in filtro
                       and all(t in _texto_item(i) for t in termos)) if termos else 0
    explica(f"{len(visiveis)} de {_plural(len(universo), 'item novo' if so_novos else 'item', 'itens novos' if so_novos else 'itens')} na tela."
            + (f" A busca acha mais {achados_fora} em outras comissões." if achados_fora else "")
            + " O Word sai com tudo o que está marcado.")
for it in visiveis:
    if _chave(sid, area, it["id"]) not in st.session_state:
        st.session_state[_chave(sid, area, it["id"])] = _da_area(base.get(it["id"]), area)
dias_vis = [d for d in dias_com if any(i["dia"] == d for i in visiveis)]

# O nome fica num cookie do navegador e volta preenchido na próxima visita.
COOKIE_QUEM = "ag_quem"
if "ag_quem" not in st.session_state:
    try:
        _cookie = st.context.cookies.get(COOKIE_QUEM)
    except Exception:
        _cookie = None
    if isinstance(_cookie, str) and _cookie:
        st.session_state["ag_quem"] = unquote(_cookie)
_gravar_quem = st.session_state.pop("ag_gravar_quem", None)
if _gravar_quem is not None:
    components.html(
        "<script>window.parent.document.cookie = " + json.dumps(COOKIE_QUEM + "=")
        + " + encodeURIComponent(" + json.dumps(_gravar_quem) + ") + '; path=/; max-age=31536000; SameSite=Lax';"
        + "</script>",
        height=0,
    )

# Tudo dentro de um formulário: marcar um cliente não recarrega a página.
with st.form("ag_form", border=False):
    with st.container(horizontal=True, vertical_alignment="bottom", key="ag_acoes"):
        st.text_input("Seu nome", key="ag_quem", placeholder="Seu nome", width=200,
                      label_visibility="collapsed")
        salvar = st.form_submit_button("Salvar seleção", icon=":material/save:", help=AJUDA_SALVAR)
        gerar = st.form_submit_button("Salvar e gerar Word", type="primary", icon=":material/description:",
                                      help=AJUDA_GERAR)

    if not dias_vis:
        vazio("Nenhum item para mostrar. Limpe a busca e o filtro de comissões ou desligue a chave de "
              "itens novos para ver a pauta completa.")
    else:
        abas = st.tabs([f"{_dia_extenso(d)} · {sum(1 for i in visiveis if i['dia'] == d)}" for d in dias_vis])
        for aba, dia in zip(abas, dias_vis):
            with aba:
                do_dia = [i for i in visiveis if i["dia"] == dia]
                for casa, casa_nome in ag.CASAS[:2]:
                    da_casa = [i for i in do_dia if i["casa"] == casa]
                    if not da_casa:
                        continue
                    # uma reunião por cartão; itens seguidos da mesma reunião ficam juntos
                    grupos: list[list[dict]] = []
                    for it in da_casa:
                        if grupos and grupos[-1][-1]["reuniaoLink"] == it["reuniaoLink"]:
                            grupos[-1].append(it)
                        else:
                            grupos.append([it])
                    # A Casa abre e fecha: com a Câmara fechada o Senado sobe para o topo da aba.
                    with st.container(key=f"ag_casa_{casa}_{dia}"), \
                            st.expander(f"{casa_nome} :gray[{_plural(len(da_casa), 'item', 'itens')}]", expanded=True):
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
    atual = {k: v for k, v in base.items() if k not in ids_vis} | _selecao_na_tela(sid, area, visiveis, base)
    try:
        login = st.session_state.get("name") or st.session_state.get("username") or ""
        nome = (st.session_state.get("ag_quem") or "").strip()
        if nome:
            st.session_state["ag_gravar_quem"] = nome
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
        if not any(_da_area(v, area) for v in selecao.values()):
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
                                                         atualizacao=atualizacao, clientes=CLIS)
            if contagem:
                st.session_state["ag_pacote"] = (sid, area, pacote, arquivos, contagem, atualizacao)
            sairam = [i["titulo"] for i in itens if i.get("situacao") and _da_area(selecao.get(i["id"]), area)]
            if sairam:
                msgs.append(("info", f"Ficaram fora do Word por reunião cancelada ou adiada: {_lista_e(sairam)}."))
            if not contagem:
                msgs.append(("warning", "Nenhum item novo está marcado. Marque os clientes nos itens novos ou desligue a chave." if so_novos else
                             "Todos os itens marcados são de reunião cancelada ou adiada."))
    st.session_state["ag_aplicar"] = (sid, selecao)
    st.session_state["ag_msg"] = msgs
    st.rerun()
