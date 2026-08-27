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
:root {{ --eixo-vinho: {EIXO["vinho"]}; }}
html, body, [data-testid="stAppViewContainer"] {{ background: {EIXO["gelo"]} !important; }}
[data-testid="stAppViewContainer"] > section > div {{ background: {EIXO["gelo"]}; }}
.block-container, [data-testid="stMainBlockContainer"] {{
    max-width: 1400px !important; padding: 0 2rem 3rem !important; background: {EIXO["gelo"]};
}}
* {{ box-sizing: border-box; }}
body, p, span, div, label, input, select, textarea {{ font-family: 'Montserrat', sans-serif !important; }}
[data-testid="stHeader"] {{ display: none; }}
[data-testid="stDecoration"] {{ display: none; }}
[data-testid="stSidebar"] {{ background: {EIXO["gelo"]} !important; border-right: 1px solid {EIXO["borda"]} !important; }}
[data-testid="stSidebar"] * {{ font-family: 'Montserrat', sans-serif !important; font-size: 13px !important; }}
/* Streamlit usa texto com fonte Material para ícones; não sobrescreva essa fonte. */
span.material-symbols-rounded, span.material-symbols-outlined, span.material-icons,
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {{
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    letter-spacing: normal !important; text-transform: none !important;
}}
footer {{ display: none !important; }}
#MainMenu {{ display: none !important; }}
[data-testid="stButton"] > button {{
    font-size: 11px !important; font-weight: 500 !important; letter-spacing: 0.1em !important;
    text-transform: uppercase !important; border-radius: 0 !important;
    border: 1px solid {EIXO["vinho"]} !important; background: transparent !important;
    color: {EIXO["vinho"]} !important; padding: 5px 14px !important;
    transition: background 0.15s, color 0.15s !important;
}}
[data-testid="stButton"] > button:hover {{ background: {EIXO["vinho"]} !important; color: #fff !important; }}
[data-testid="stSidebar"] [data-testid="stButton"] > button {{
    border: 1px solid {EIXO["vinho"]} !important; color: {EIXO["vinho"]} !important;
}}
[data-testid="stSidebar"] [data-testid="stButton"] > button:hover {{
    background: {EIXO["vinho"]} !important; color: #fff !important;
}}
[data-testid="stRadio"] > label, [data-testid="stSelectbox"] > label,
[data-testid="stMultiSelect"] > label, [data-testid="stTextInput"] > label,
[data-testid="stNumberInput"] > label, [data-testid="stTextArea"] > label {{
    font-size: 11px !important; font-weight: 700 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important;
    color: {EIXO["subtexto"]} !important;
}}
[data-testid="stTabs"] [role="tablist"] {{ border-bottom: 1px solid {EIXO["borda"]} !important; gap: 0 !important; }}
[data-testid="stTabs"] [role="tab"] {{
    font-size: 11px !important; font-weight: 500 !important; letter-spacing: 0.12em !important;
    text-transform: uppercase !important; color: {EIXO["subtexto"]} !important;
    padding: 10px 20px 9px !important; border-bottom: 2px solid transparent !important;
    background: transparent !important; border-radius: 0 !important;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
    color: {EIXO["vinho"]} !important; border-bottom-color: {EIXO["vinho"]} !important;
}}
.ge-rule {{
    font-size: 12px; font-weight: 700; letter-spacing: 0.14em;
    text-transform: uppercase; color: {EIXO["vinho"]};
    border-top: 1.5px solid {EIXO["vinho"]};
    padding-top: 8px; margin: 16px 0 12px;
}}
/* Tabela de automações */
.at-wrap {{ width: 100%; background: #fff; border: 1px solid {EIXO["borda"]}; overflow-x: auto; margin-top: 8px; }}
.at-table {{ width: 100%; border-collapse: collapse; font-family: 'Montserrat', sans-serif; font-size: 12.5px; }}
.at-table thead th {{
    background: {EIXO["vinho"]}; color: #fff; font-size: 10px; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase; padding: 11px 14px; text-align: left;
    white-space: nowrap;
}}
.at-table tbody tr {{ border-bottom: 1px solid {EIXO["borda"]}; }}
.at-table tbody tr:last-child {{ border-bottom: none; }}
.at-table tbody tr:nth-child(even) {{ background: {EIXO["gelo"]}; }}
.at-table tbody tr:hover {{ background: #f0e8eb; }}
.at-table tbody td {{
    padding: 9px 14px; color: {EIXO["tinta"]}; vertical-align: top; line-height: 1.5;
    max-width: 320px; word-wrap: break-word;
}}
.at-table td a {{
    color: {EIXO["vinho"]}; text-decoration: none; font-weight: 500;
    border-bottom: 1px solid {EIXO["borda"]};
}}
.at-table td a:hover {{ border-bottom-color: {EIXO["vinho"]}; }}
.at-badge {{
    display: inline-block; padding: 1px 7px; font-size: 10px; font-weight: 700;
    letter-spacing: 0.06em; text-transform: uppercase;
    background: {EIXO["vinho"]}; color: #fff; border-radius: 0; margin-right: 4px;
}}
.at-meta {{
    font-family: 'Montserrat', sans-serif; font-size: 11.5px;
    color: {EIXO["subtexto"]}; margin-bottom: 10px;
}}
.at-details summary {{ list-style: none; cursor: pointer; }}
.at-details summary::-webkit-details-marker {{ display: none; }}
.at-details summary::marker {{ content: ""; }}
.at-leia-mais {{ color: {EIXO["vinho"]}; font-size: 11px; font-weight: 600; white-space: nowrap; }}
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
        st.warning(f"Google Sheets não configurado: {e}")
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _listar_abas(sheet_id: str) -> list[str]:
    gc = _get_gc()
    if not gc or not sheet_id:
        return []
    try:
        return [ws.title for ws in gc.open_by_key(sheet_id).worksheets()]
    except Exception as e:
        st.error(f"Erro ao listar abas: {e}")
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
        st.error(f"Erro ao carregar aba '{aba}': {e}")
        return pd.DataFrame()


def _secret(key: str, default: str = "") -> str:
    return str(st.secrets.get(key) or os.getenv(key, default) or default)


# ─── Automações configuradas via Secrets ──────────────────────────────────────
# Adicione nos Secrets do Streamlit:
#   AUTOMACAO_1_SHEET_ID = "1-sUNFrPbs7ljfUvt45yR2AKQmzGKxaGOnDhzH-Ny6YM"
#   AUTOMACAO_1_NOME     = "Monitor Legislativo"
#   AUTOMACAO_2_SHEET_ID = "1IEVYNRM4VFKDsQlOhymXu-TTSeZTRa04ZeUvXPAXILs"
#   AUTOMACAO_2_NOME     = "DOU"
#   AUTOMACAO_3_SHEET_ID = "1dQ4IRP7TQnzQ-Bnzd3hKcmaQwzIfGRCMlfs-1WxpxjQ"
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
        return f'<a href="{safe}" target="_blank" rel="noopener">↗ link</a>'
    if col in _EXPAND_COLS:
        paragrafos = [_html.escape(p.strip()) for p in raw.split('\n') if p.strip()]
        if not paragrafos:
            return '<span style="color:#DADAD4;">—</span>'
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
            f'<span class="at-leia-mais">↓ Leia mais</span>'
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
            f"<td>{_render_cell(str(col), str(val))}</td>"
            for col, val in zip(df.columns, row)
        )
        rows += f"<tr>{cells}</tr>"
    return (
        f'<div class="at-wrap">'
        f'<table class="at-table">'
        f'<thead><tr>{headers}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>'
    )


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
            sufixo = f"{partido}-{uf}" if partido and uf else partido or uf
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
        st.image("Marca_eixo_vetor_Logo horizontal magenta.png", use_container_width=True)
    except Exception:
        st.caption("Logo não encontrada.")
    st.markdown(
        f'<div style="border-left:3px solid {EIXO["vinho"]};padding:10px 12px;'
        f'margin:10px 0 0 0;background:transparent;">'
        f'<p style="font-family:Montserrat,sans-serif;font-size:12.5px;'
        f'color:{EIXO["tinta"]};line-height:1.65;margin:0;">'
        f'Resultados das <strong>automações de monitoramento</strong> por cliente.'
        f'</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("↻ Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.caption(
        f"Usuário: **{st.session_state.get('name', '')}** "
        f"({st.session_state.get('username', '')})"
    )
    if _auth_cfg:
        authenticator.logout("Sair", "sidebar")


# ─── Hero banner ─────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:{EIXO['vinho']};display:flex;align-items:center;
            justify-content:space-between;padding:36px 48px;margin:0 -2rem 32px -2rem;">
  <div style="font-family:'Montserrat',sans-serif;font-size:48px;font-weight:800;
              color:#fff;line-height:1;letter-spacing:-0.01em;">Automações</div>
  <div style="font-family:'Montserrat',sans-serif;font-size:13px;color:rgba(255,255,255,0.7);
              text-align:right;line-height:1.6;">
    DOU · Monitor Legislativo · Coletor de Notícias
  </div>
</div>
""", unsafe_allow_html=True)


# ─── Tabs das 3 automações ────────────────────────────────────────────────────
tabs = st.tabs([a["nome"] for a in AUTOMACOES])

for tab, automacao in zip(tabs, AUTOMACOES):
    with tab:
        sheet_id = automacao["sheet_id"]
        nome     = automacao["nome"]
        idx      = AUTOMACOES.index(automacao) + 1

        if not sheet_id:
            st.markdown(
                f'<div style="background:#fff;border:1px solid {EIXO["borda"]};'
                f'padding:24px 28px;margin-top:8px;">'
                f'<p style="font-family:Montserrat,sans-serif;font-size:13px;'
                f'color:{EIXO["subtexto"]};margin:0;">'
                f'Configure <code>AUTOMACAO_{idx}_SHEET_ID</code> nos Secrets '
                f'do Streamlit para conectar esta automação.'
                f'</p></div>',
                unsafe_allow_html=True,
            )
            continue

        with st.spinner(f"Carregando abas…"):
            abas = _listar_abas(sheet_id)

        if not abas:
            st.warning("Nenhuma aba encontrada ou erro de acesso à planilha.")
            continue

        # ── Seleção de cliente + reload ───────────────────────────────────────
        col_sel, col_btn = st.columns([5, 1])
        with col_sel:
            cliente = st.selectbox("Cliente", abas, key=f"cli_{sheet_id}")
        with col_btn:
            st.markdown("<div style='margin-top:26px;'></div>", unsafe_allow_html=True)
            if st.button("↻", key=f"rl_{sheet_id}", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        # ── Carregar e transformar ────────────────────────────────────────────
        with st.spinner(f"Carregando {cliente}…"):
            df = _carregar_aba(sheet_id, cliente)

        if df.empty:
            st.info("Nenhum dado encontrado nesta aba.")
            continue

        df = _transformar_df(df)

        # ── Ordenar mais recente → mais antigo ────────────────────────────────
        col_data_nome = _detectar_col_data(df)
        if col_data_nome:
            df["__data_ord"] = _parse_datas(df[col_data_nome])
            df = df.sort_values("__data_ord", ascending=False, na_position="last")

        # ── Filtros: busca + período + alinhamento ────────────────────────────
        col_busca_ui, col_periodo_ui, col_alin_ui = st.columns([2, 2.5, 2])
        with col_busca_ui:
            busca = st.text_input(
                "Filtrar",
                placeholder="Buscar por palavra-chave…",
                key=f"busca_{sheet_id}",
            )

        df_exib = df.copy()

        if col_data_nome and "__data_ord" in df.columns and df["__data_ord"].notna().any():
            d_min = df["__data_ord"].dropna().min().date()
            d_max = df["__data_ord"].dropna().max().date()
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
                    sel_alin = st.multiselect(
                        "Alinhamento",
                        options=opts_alin,
                        default=opts_alin,
                        key=f"alin_{sheet_id}",
                    )
                if sel_alin:
                    df_exib = df_exib[df_exib[col_alin].isin(sel_alin)]
                else:
                    df_exib = df_exib.iloc[0:0]  # nenhum selecionado → vazio

        # Remover coluna auxiliar de ordenação antes de exibir
        df_exib  = df_exib.drop(columns=["__data_ord"], errors="ignore")
        df_total = df.drop(columns=["__data_ord"], errors="ignore")

        st.markdown('<div class="ge-rule"></div>', unsafe_allow_html=True)

        df_exib = _filtrar(df_exib, busca)

        # ── Meta + Download (mesma linha, acima da tabela) ───────────────────
        total_str = (
            f'de {len(df_total)} '
            if len(df_exib) != len(df_total) else ""
        )
        csv = df_exib.to_csv(index=False).encode("utf-8")

        col_meta, col_dl = st.columns([3, 1])
        with col_meta:
            st.markdown(
                f'<p class="at-meta" style="margin-top:8px;">'
                f'<strong style="color:{EIXO["tinta"]};">{len(df_exib)}</strong> '
                f'{total_str}'
                f'registro{"s" if len(df_exib) != 1 else ""} · '
                f'{len(df_total.columns)} coluna{"s" if len(df_total.columns) != 1 else ""}'
                f'</p>',
                unsafe_allow_html=True,
            )
        with col_dl:
            st.download_button(
                label=f"⬇ Baixar seleção ({len(df_exib)})",
                data=csv,
                file_name=f"{nome}_{cliente}.csv",
                mime="text/csv",
                key=f"dl_{sheet_id}_{cliente}",
                use_container_width=True,
            )

        if df_exib.empty:
            st.info("Nenhum resultado para os filtros aplicados.")
        else:
            st.markdown(_render_table(df_exib), unsafe_allow_html=True)
