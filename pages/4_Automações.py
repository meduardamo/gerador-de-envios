from __future__ import annotations

import json
import os
import html as _html

import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

from estilo_paginas import cabecalho, chip, resumo, secao, vazio

# ─── Config ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Automações", layout="wide")

EIXO = {
    "tinta":    "#111111",
    "vinho":    "#962E4D",
    "gelo":     "#F4F3EF",
    "borda":    "#DADAD4",
    "subtexto": "#767672",
    "amarelo":  "#E8A600",
    "marinho":  "#192D4E",
}

st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');
html, body, [data-testid="stAppViewContainer"] {{ background: {EIXO["gelo"]} !important; }}
[data-testid="stAppViewContainer"] > section > div {{ background: {EIXO["gelo"]}; }}
.block-container, [data-testid="stMainBlockContainer"] {{ max-width: 1400px !important; padding: 1.8rem 2.5rem 4rem !important; background: {EIXO["gelo"]}; }}
* {{ box-sizing: border-box; }}
body, p, span, div, label, input, select, textarea {{ font-family: 'Montserrat', sans-serif !important; }}
[data-testid="stHeader"], [data-testid="stDecoration"] {{ display: none; }}
[data-testid="stSidebar"] {{ background: {EIXO["gelo"]} !important; border-right: 1px solid {EIXO["borda"]} !important; }}
[data-testid="stSidebar"] * {{ font-family: 'Montserrat', sans-serif !important; font-size: 13px !important; }}
span.material-symbols-rounded, span.material-symbols-outlined, span.material-icons,
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {{
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    letter-spacing: normal !important; text-transform: none !important; }}
footer, #MainMenu {{ display: none !important; }}
[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) {{ display: none; }}
div[class*="st-key-at_filtros_"] {{ background: #fff; border: 1px solid {EIXO["borda"]}; border-radius: 8px; padding: 14px 18px 18px; margin: 14px 0 4px; }}
div[class*="st-key-at_res_"] .eg-resumo {{ margin: 0; height: 48px; padding-top: 0; padding-bottom: 0; flex-wrap: nowrap; overflow: hidden; }}
div[class*="st-key-at_res_"] [data-testid="stMarkdownContainer"], div[class*="st-key-at_res_"] [data-testid="stMarkdown"] {{ margin-bottom: 0 !important; }}
div[class*="st-key-at_res_"] [data-testid="stDownloadButton"] button {{ height: 48px !important; min-height: 48px !important; }}
.at-wrap {{ width: 100%; background: #fff; border: 1px solid {EIXO["borda"]}; border-radius: 8px; overflow: auto; max-height: 75vh; margin-top: 8px; }}
.at-table {{ width: 100%; border-collapse: collapse; font-family: 'Montserrat', sans-serif; font-size: 12.5px; }}
.at-table thead th {{ position: sticky; top: 0; z-index: 1; background: #fff; color: {EIXO["marinho"]}; font-size: 11px; font-weight: 700;
    letter-spacing: .04em; text-transform: uppercase; padding: 12px 14px 10px; text-align: left; white-space: nowrap;
    border-bottom: 2px solid {EIXO["marinho"]}; }}
.at-table tbody tr {{ border-bottom: 1px solid #ECEBE6; }}
.at-table tbody tr:last-child {{ border-bottom: none; }}
.at-table tbody tr:hover {{ background: #FAF9F6; }}
.at-table tbody td {{ padding: 10px 14px; color: {EIXO["tinta"]}; vertical-align: top; line-height: 1.55; max-width: 320px; word-wrap: break-word; }}
.at-table td.at-prop {{ font-weight: 700; color: {EIXO["marinho"]}; white-space: nowrap; }}
.at-table td a {{ color: {EIXO["vinho"]}; text-decoration: none; font-weight: 600; white-space: nowrap; }}
.at-table td a:hover {{ text-decoration: underline; }}
.at-details summary {{ list-style: none; cursor: pointer; }}
.at-details summary::-webkit-details-marker {{ display: none; }}
.at-details summary::marker {{ content: ""; }}
.at-leia-mais {{ color: {EIXO["vinho"]}; font-size: 11.5px; font-weight: 600; white-space: nowrap; }}
.at-details[open] .at-leia-mais {{ display: none; }}
.at-details[open] summary {{ margin-bottom: 6px; border-bottom: 1px solid {EIXO["borda"]}; padding-bottom: 6px; }}
</style>""", unsafe_allow_html=True)


# ─── Auth ────────────────────────────────────────────────────────────────────
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

if st.session_state.get("authentication_status") is False:
    st.error("Usuário ou senha inválidos.")
    st.stop()
if not st.session_state.get("authentication_status"):
    st.stop()


# ─── Google Sheets ────────────────────────────────────────────────────────────
@st.cache_resource
def _get_gc():
    try:
        if "GOOGLE_SHEETS_CREDS" in st.secrets:
            creds_dict = dict(st.secrets["GOOGLE_SHEETS_CREDS"])
        else:
            creds_json = os.getenv("GOOGLE_SHEETS_CREDS", "")
            if not creds_json:
                return None
            creds_dict = json.loads(creds_json)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"[automacoes] credencial do Google: {e}")
        st.warning("Não consegui conectar às planilhas do Google. Avise a equipe de dados.")
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _listar_abas(sheet_id: str) -> list[str]:
    gc = _get_gc()
    if not gc or not sheet_id:
        return []
    try:
        return [ws.title for ws in gc.open_by_key(sheet_id).worksheets()]
    except Exception as e:
        print(f"[automacoes] abrir planilha: {e}")
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_aba(sheet_id: str, aba: str) -> pd.DataFrame:
    gc = _get_gc()
    if not gc or not sheet_id:
        return pd.DataFrame()
    try:
        ws = gc.open_by_key(sheet_id).worksheet(aba)
        dados = ws.get_all_values()
        if not dados:
            return pd.DataFrame()
        df = pd.DataFrame(dados[1:], columns=dados[0])
        df = df.loc[:, ~df.columns.duplicated()]
        df = df.loc[:, df.columns.str.strip() != ""]
        return df
    except Exception as e:
        print(f"[automacoes] carregar {aba}: {e}")
        st.error(f"Não consegui carregar os dados de {aba}. Clique em Atualizar; se continuar, avise a equipe de dados.")
        return pd.DataFrame()


def _secret(key: str, default: str = "") -> str:
    return str(st.secrets.get(key) or os.getenv(key, default) or default)


# ─── Automações configuradas via Secrets ──────────────────────────────────────
# Adicione nos Secrets do Streamlit:
#   AUTOMACAO_1_SHEET_ID = "<id da planilha>"
#   AUTOMACAO_1_NOME     = "Monitor Legislativo"
#   AUTOMACAO_2_SHEET_ID = "<id da planilha>"
#   AUTOMACAO_2_NOME     = "DOU"
#   AUTOMACAO_3_SHEET_ID = "<id da planilha>"
#   AUTOMACAO_3_NOME     = "Coletor de Notícias"

AUTOMACOES = [
    {
        "sheet_id": _secret("AUTOMACAO_2_SHEET_ID"),
        "nome":     _secret("AUTOMACAO_2_NOME", "DOU"),
    },
    {
        "sheet_id": _secret("AUTOMACAO_1_SHEET_ID"),
        "nome":     _secret("AUTOMACAO_1_NOME", "Monitor Legislativo"),
    },
    {
        "sheet_id": _secret("AUTOMACAO_3_SHEET_ID"),
        "nome":     _secret("AUTOMACAO_3_NOME", "Coletor de Notícias"),
    },
]

# Colunas que contêm URLs — serão renderizadas como links clicáveis
_URL_COLS = {"link", "url", "Link", "URL", "Url", "Link Página", "Link Pagina", "link_pagina"}

# Colunas com texto longo — truncadas com tooltip
_LONG_COLS = {
    "ementa", "Ementa", "resumo", "Resumo", "conteúdo", "Conteúdo",
    "conteudo", "Conteudo", "palavras_chave", "Palavras Chave",
    "Justificativa", "justificativa",
}

# Colunas com "Leia mais" expansível
_EXPAND_COLS = {"Texto Completo", "texto_completo", "Conteúdo", "Conteudo", "conteudo", "conteúdo"}

_TRUNC = 180


def _render_cell(col: str, val: str) -> str:
    raw  = str(val).strip()
    safe = _html.escape(raw)
    if not safe or raw.lower() in ("none", "nan", ""):
        return ''
    if col in _URL_COLS and (raw.startswith("http://") or raw.startswith("https://")):
        return f'<a href="{safe}" target="_blank" rel="noopener">Abrir ↗</a>'
    if col in ("Alinhamento", "alinhamento"):
        baixo = raw.lower()
        tipo = "" if baixo.startswith(("não", "nao")) else ("ok" if "alinh" in baixo else "org")
        return chip(raw, tipo)
    if col in _EXPAND_COLS:
        paragrafos = [_html.escape(p.strip()) for p in raw.split('\n') if p.strip()]
        if not paragrafos:
            return ''
        if len(paragrafos) > 1:
            primeiro = paragrafos[0]
            resto    = '<br><br>'.join(paragrafos[1:])
        elif len(safe) > 400:
            primeiro = safe[:400] + '…'
            resto    = safe
        else:
            return safe
        return (
            f'<details class="at-details">'
            f'<summary>{primeiro}&nbsp;'
            f'<span class="at-leia-mais">Leia mais</span>'
            f'</summary>'
            f'<div style="margin-top:6px;line-height:1.6;">{resto}</div>'
            f'</details>'
        )
    if col in _LONG_COLS and len(safe) > _TRUNC:
        short = safe[:_TRUNC]
        return f'<span title="{safe}" style="cursor:help;">{short}…</span>'
    return safe


def _render_table(df: pd.DataFrame) -> str:
    headers = "".join(
        f'<th style="white-space:nowrap;">{_html.escape(str(c))}</th>'
        for c in df.columns
    )
    rows = ""
    for _, row in df.iterrows():
        cells = "".join(
            ('<td class="at-prop">' if str(col) == "Proposição" else "<td>")
            + f"{_render_cell(str(col), str(val))}</td>"
            for col, val in zip(df.columns, row)
        )
        rows += f"<tr>{cells}</tr>"
    # Quebra de linha dentro do HTML do st.markdown encerra o bloco (linha em branco)
    # e o resto da tabela some ou vira texto: no HTML ela não muda nada, então sai.
    return (
        f'<div class="at-wrap">'
        f'<table class="at-table">'
        f'<thead><tr>{headers}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>'
    ).replace("\r", " ").replace("\n", " ")


def _filtrar(df: pd.DataFrame, termo: str) -> pd.DataFrame:
    if not termo.strip():
        return df
    mask = df.apply(
        lambda col: col.astype(str).str.contains(termo, case=False, na=False)
    ).any(axis=1)
    return df[mask]


def _transformar_df(df: pd.DataFrame) -> pd.DataFrame:
    """Remove colunas desnecessárias e junta colunas relacionadas."""
    df = df.copy()

    # ── Colunas a remover ────────────────────────────────────────────────────
    for col in [
        "UID", "Clientes", "Temas Coautores", "Qtd Coautores", "Ingest At",
        "Autor Principal Tipo", "Coautores", "Inteiro Teor URL",
        "data_coleta", "resumo", "Resumo",
    ]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # ── Renomear "Link Página" → "Link" para ficar limpo na tabela ───────────
    for nome_orig in ("Link Página", "Link Pagina", "link_pagina"):
        if nome_orig in df.columns:
            df = df.rename(columns={nome_orig: "Link"})
            break

    # ── Juntar Sigla + Número + Ano → "Proposição" ───────────────────────────
    if all(c in df.columns for c in ["Sigla", "Número", "Ano"]):
        idx = list(df.columns).index("Sigla")
        def _prop(row):
            s = str(row["Sigla"]).strip()
            n = str(row["Número"]).strip()
            a = str(row["Ano"]).strip()
            for v in (s, n, a):
                if v.lower() in ("nan", "none", ""):
                    v = ""
            if s and n and a:
                return f"{s} {n}/{a}"
            return f"{s} {n}".strip()
        df.insert(idx, "Proposição", df.apply(_prop, axis=1))
        df = df.drop(columns=["Sigla", "Número", "Ano"])

    # ── Juntar Autor Principal + Partido + UF → "Autor" ──────────────────────
    if "Autor Principal" in df.columns:
        idx = list(df.columns).index("Autor Principal")
        def _autor(row):
            nome    = str(row.get("Autor Principal", "")).strip()
            partido = str(row.get("Autor Principal Partido", "")).strip()
            uf      = str(row.get("Autor Principal UF", "")).strip()
            for v in [nome, partido, uf]:
                if v.lower() in ("nan", "none"):
                    v = ""
            nome    = nome    if nome.lower()    not in ("nan","none","") else ""
            partido = partido if partido.lower() not in ("nan","none","") else ""
            uf      = uf      if uf.lower()      not in ("nan","none","") else ""
            if not nome:
                return ""
            sufixo = f"{partido}/{uf}" if partido and uf else partido or uf
            return f"{nome} ({sufixo})" if sufixo else nome
        df.insert(idx, "Autor", df.apply(_autor, axis=1))
        for c in ["Autor Principal", "Autor Principal Partido", "Autor Principal UF"]:
            if c in df.columns:
                df = df.drop(columns=[c])

    # ── Remover linhas "Não se aplica" em Alinhamento ────────────────────────
    for col_alin in ("Alinhamento", "alinhamento"):
        if col_alin in df.columns:
            df = df[~df[col_alin].str.strip().str.lower().isin(["não se aplica", "nao se aplica"])]
            break

    # ── Renomear colunas do Coletor de Notícias ───────────────────────────────
    renomear = {
        "data_publicacao":      "Data",
        "titulo":               "Título",
        "fonte":                "Fonte",
        "url":                  "URL",
        "palavras_por_cliente": "Palavras-chave",
        "resumo":               "Resumo",
        "texto_completo":       "Texto Completo",
    }
    df = df.rename(columns={k: v for k, v in renomear.items() if k in df.columns})

    return df


# ─── Helpers de data ─────────────────────────────────────────────────────────

def _detectar_col_data(df: pd.DataFrame) -> str | None:
    """Retorna o nome da primeira coluna que parece conter datas."""
    candidatas = [
        c for c in df.columns
        if any(t in c.lower() for t in ("data", "date", "dt_", "publicação", "publicacao"))
    ]
    return candidatas[0] if candidatas else None


def _parse_datas(serie: pd.Series) -> pd.Series:
    """Converte strings para datetime tentando formatos brasileiros e ISO."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            parsed = pd.to_datetime(serie, format=fmt, errors="coerce")
            if parsed.notna().sum() > 0:
                return parsed
        except Exception:
            pass
    return pd.to_datetime(serie, errors="coerce", dayfirst=True)


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    try:
        st.image("logo_eixo_gov_magenta.png", use_container_width=True)
    except Exception:
        st.caption("Logo não encontrada.")
    st.markdown(
        f'<div style="border-left:3px solid {EIXO["vinho"]};padding:10px 12px;'
        f'margin:10px 0 0 0;background:transparent;">'
        f'<p style="font-family:Montserrat,sans-serif;font-size:12.5px;'
        f'color:{EIXO["tinta"]};line-height:1.65;margin:0;">'
        f'O que as <strong>raspagens automáticas</strong> do DOU, do Monitor Legislativo '
        f'e do Coletor de Notícias encontraram para cada cliente, com busca, filtros e download.'
        f'</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("Atualizar dados", icon=":material/refresh:", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.caption(
        f"Usuário: **{st.session_state.get('name', '')}** "
        f"({st.session_state.get('username', '')})"
    )
    if _auth_cfg:
        authenticator.logout("Sair", "sidebar")


def _n(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


# ─── Cabeçalho ───────────────────────────────────────────────────────────────
cabecalho("Automações", "Resultados do DOU, do Monitor Legislativo e do Coletor de Notícias por cliente, "
          "com filtros e download.")


# ─── Tabs das 3 automações ────────────────────────────────────────────────────
tabs = st.tabs([a["nome"] for a in AUTOMACOES])

for tab, automacao in zip(tabs, AUTOMACOES):
    with tab:
        sheet_id = automacao["sheet_id"]
        nome     = automacao["nome"]
        idx      = AUTOMACOES.index(automacao) + 1

        if not sheet_id:
            vazio(f"{nome} ainda não está conectado a este painel. Avise a equipe de dados para fazer a ligação.")
            continue

        with st.spinner("Abrindo a planilha…"):
            abas = _listar_abas(sheet_id)

        if not abas:
            vazio(f"Não consegui abrir os resultados de {nome}. Clique em Atualizar dados na barra lateral; "
                  "se continuar, avise a equipe de dados.")
            continue

        # ── Bloco de controles: cliente, filtros e atualizar ──────────────────
        with st.container(key=f"at_filtros_{idx}"):
            col_sel, col_busca_ui, col_periodo_ui, col_btn = st.columns(
                [2, 2.4, 2, 1.1], vertical_alignment="bottom"
            )
            col_alin_ui = st.container()
        with col_sel:
            cliente = st.selectbox("Cliente", abas, key=f"cli_{sheet_id}")
        with col_btn:
            if st.button("Atualizar", icon=":material/refresh:", key=f"rl_{sheet_id}",
                         use_container_width=True, help="Busca de novo os dados da planilha"):
                st.cache_data.clear()
                st.rerun()

        # ── Carregar e transformar ────────────────────────────────────────────
        with st.spinner(f"Carregando {cliente}…"):
            df = _carregar_aba(sheet_id, cliente)

        if df.empty:
            vazio(f"Ainda não há registros de {cliente} em {nome}. Escolha outro cliente ou clique em "
                  "Atualizar se a automação rodou há pouco.")
            continue

        df = _transformar_df(df)

        # ── Ordenar mais recente → mais antigo ────────────────────────────────
        col_data_nome = _detectar_col_data(df)
        if col_data_nome:
            df["__data_ord"] = _parse_datas(df[col_data_nome])
            df = df.sort_values("__data_ord", ascending=False, na_position="last")

        # ── Filtros: busca + período + alinhamento ────────────────────────────
        with col_busca_ui:
            busca = st.text_input(
                "Buscar",
                placeholder="Palavra, nome ou número",
                key=f"busca_{sheet_id}",
            )

        df_exib = df.copy()
        ultimo = None

        if col_data_nome and "__data_ord" in df.columns and df["__data_ord"].notna().any():
            d_min = df["__data_ord"].dropna().min().date()
            d_max = df["__data_ord"].dropna().max().date()
            ultimo = d_max
            with col_periodo_ui:
                intervalo = st.date_input(
                    "Período",
                    value=(d_min, d_max),
                    min_value=d_min,
                    max_value=d_max,
                    key=f"data_{sheet_id}",
                    format="DD/MM/YYYY",
                )
            if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
                d0 = pd.Timestamp(intervalo[0])
                d1 = pd.Timestamp(intervalo[1]) + pd.Timedelta(days=1)
                df_exib = df_exib[
                    df_exib["__data_ord"].between(d0, d1, inclusive="left")
                ]

        # ── Filtro de alinhamento ─────────────────────────────────────────────
        col_alin = next(
            (c for c in ("Alinhamento", "alinhamento") if c in df.columns), None
        )
        if col_alin:
            opts_alin = sorted(
                v for v in df[col_alin].dropna().unique() if str(v).strip()
            )
            if opts_alin:
                with col_alin_ui:
                    sel_alin = st.pills(
                        "Alinhamento",
                        options=opts_alin,
                        default=opts_alin,
                        selection_mode="multi",
                        key=f"alin_{sheet_id}",
                    ) or []
                if sel_alin:
                    df_exib = df_exib[df_exib[col_alin].isin(sel_alin)]
                else:
                    df_exib = df_exib.iloc[0:0]  # nenhum selecionado → vazio

        # Remover coluna auxiliar de ordenação antes de exibir
        df_exib  = df_exib.drop(columns=["__data_ord"], errors="ignore")
        df_total = df.drop(columns=["__data_ord"], errors="ignore")

        df_exib = _filtrar(df_exib, busca)

        # ── Resultado: números + download, acima da tabela ───────────────────
        secao(cliente,
              explicacao=("Mais recentes primeiro. " if col_data_nome else "") + "Cada linha é um registro encontrado pela automação. Em textos longos, clique em "
                         "Leia mais para abrir o texto inteiro; Abrir leva à página original. O download "
                         "traz só o que está filtrado.")
        csv = df_exib.to_csv(index=False).encode("utf-8")

        with st.container(key=f"at_res_{idx}"):
            col_meta, col_dl = st.columns([3, 1], vertical_alignment="center")
        with col_meta:
            itens = [(_n(len(df_exib)), " registro mostrado" if len(df_exib) == 1 else " registros mostrados")]
            if len(df_exib) != len(df_total):
                itens.append((_n(len(df_total)), " no total"))
            if ultimo is not None:
                itens.append((ultimo.strftime("%d/%m/%Y"), " é a data do último registro"))
            resumo(itens)
        with col_dl:
            st.download_button(
                label=f"Baixar seleção ({_n(len(df_exib))})",
                icon=":material/download:",
                data=csv,
                file_name=f"{nome}_{cliente}.csv",
                mime="text/csv",
                key=f"dl_{sheet_id}_{cliente}",
                use_container_width=True,
                disabled=df_exib.empty,
            )

        if df_exib.empty:
            vazio("Nenhum registro com esses filtros. Amplie o período, limpe a busca ou marque mais opções "
                  "de alinhamento.")
        else:
            st.markdown(_render_table(df_exib), unsafe_allow_html=True)
