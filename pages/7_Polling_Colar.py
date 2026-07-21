"""Polling Colar — cadastra pesquisas do PollingData colando o texto da tela.

Alternativa ao Polling Manual (que sobe PDF e extrai com Gemini): aqui a pessoa
abre a pagina do PollingData, copia a secao "Dados das Pesquisas" e cola. O texto
copiado ja e exato (nao e imagem/OCR), entao nao ha erro de leitura. Nao usa token
nem raspa a API deles: le so o que ja esta na tela.

Grava nas abas pesquisas_api / resultados_api das matrizes T1 e T2, separadas das
abas oficiais pra distinguir a origem (origem="pollingdata_colar").
"""

import json
import os
from pathlib import Path

import gspread
import pandas as pd
import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

from polling_colar_core import (
    COLUNAS_PESQUISAS,
    COLUNAS_RESULTADOS,
    _cargo_uf_turno,
    montar,
    parsear,
)

ROOT_DIR = Path(__file__).resolve().parent.parent

st.set_page_config(page_title="Polling Colar", layout="wide")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
.ge-hero { background: #962E4D; display: flex; align-items: center; padding: 36px 48px; margin: 0 -2rem 24px -2rem; }
.ge-hero-title { font-family: 'Montserrat', sans-serif; font-size: 48px; font-weight: 800; color: #fff; line-height: 1; letter-spacing: -0.01em; }
.ge-rule { font-size: 17px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: #962E4D; border-top: 2px solid #962E4D; padding-top: 10px; margin: 24px 0 16px; }
.ge-aviso { background: #192D4E; color: #fff; border-left: 4px solid #962E4D; padding: 10px 14px; margin: 4px 0 14px; font-size: 12.5px; line-height: 1.5; }
</style>""", unsafe_allow_html=True)


# ── autenticação (mesmo gate das outras páginas) ──────────────────────────────
def _load_auth_config():
    if "AUTH_CONFIG" in st.secrets:
        return yaml.load(st.secrets["AUTH_CONFIG"], Loader=SafeLoader)
    cfg = ROOT_DIR / "config.yaml"
    if cfg.exists():
        return yaml.load(cfg.read_text(encoding="utf-8"), Loader=SafeLoader)
    return None


_auth_cfg = _load_auth_config()
if not _auth_cfg:
    st.error("Auth não configurado. Defina AUTH_CONFIG nos Secrets ou crie config.yaml local.")
    st.stop()

authenticator = stauth.Authenticate(
    _auth_cfg["credentials"], _auth_cfg["cookie"]["name"],
    _auth_cfg["cookie"]["key"], _auth_cfg["cookie"]["expiry_days"],
)
authenticator.login(location="main")
if not st.session_state.get("authentication_status"):
    if st.session_state.get("authentication_status") is False:
        st.error("Usuário ou senha inválidos.")
    st.stop()


# ── destino: as mesmas matrizes T1/T2 do Polling Manual ───────────────────────
def _secret(*nomes, default=""):
    for n in nomes:
        v = st.secrets.get(n) if hasattr(st, "secrets") else None
        if v:
            return str(v)
        if os.getenv(n):
            return os.getenv(n)
    return default


MATRIZ_T1 = _secret("MATRIZ_T1_SHEET_ID", "SPREADSHEET_ID_POLLINGDATA")
MATRIZ_T2 = _secret("MATRIZ_T2_SHEET_ID", "SPREADSHEET_ID_POLLINGDATA_T2")


def _sheets_client():
    raw = _secret("GOOGLE_CREDENTIALS_JSON", "GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not raw:
        return None
    info = json.loads(raw)
    if "private_key" in info and "\\n" in info["private_key"]:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds)


def _registros_existentes(gc, sheet_id):
    """(registro_tse, cargo) já na aba 'pesquisas' da matriz, pra avisar de repetição."""
    try:
        ws = gc.open_by_key(sheet_id).worksheet("pesquisas")
        valores = ws.get_all_values()
    except Exception:
        return set()
    if not valores:
        return set()
    h = {c.strip().lower(): i for i, c in enumerate(valores[0])}
    ir, ic = h.get("registro_tse"), h.get("cargo")
    if ir is None or ic is None:
        return set()
    return {(r[ir].strip().upper(), r[ic].strip().lower())
            for r in valores[1:] if len(r) > max(ir, ic) and r[ir].strip()}


# ── UI ────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.caption(f"Usuário: **{st.session_state.get('name', '')}**")
    authenticator.logout("Sair", "sidebar")
    st.markdown("---")
    st.markdown(
        "**Como usar**\n\n"
        "1. Abra a página da pesquisa no PollingData\n"
        "2. Copie a seção *Dados das Pesquisas*\n"
        "3. Cole a URL e o texto aqui\n"
        "4. Revise e grave nas matrizes")

st.markdown('<div class="ge-hero"><div class="ge-hero-title">Polling Colar</div></div>',
            unsafe_allow_html=True)
st.caption("Cola o texto do PollingData e grava direto nas matrizes T1/T2. "
           "Sem PDF, sem Gemini, sem raspagem.")

col_url, col_info = st.columns([2, 1])
with col_url:
    url = st.text_input(
        "URL da página do PollingData",
        placeholder="https://flex.pollingdata.com.br/pdvoto/2026/governador/pi/t1",
        help="É dela que saem cargo, UF e turno.")
with col_info:
    if url.strip():
        try:
            ano, cargo, uf, turno = _cargo_uf_turno(url)
            st.success(f"{cargo.capitalize()} · {uf} · {turno.upper()}")
        except SystemExit:
            st.error("URL fora do padrão .../2026/cargo/uf/t1")

texto = st.text_area(
    "Texto copiado da seção “Dados das Pesquisas”",
    height=260,
    placeholder="Cole aqui o conteúdo copiado da tabela de pesquisas.")

if st.button("Processar", use_container_width=True, type="primary"):
    st.session_state.pop("colar_resultado", None)
    if not url.strip() or not texto.strip():
        st.error("Preencha a URL e cole o texto.")
    else:
        try:
            ano, cargo, uf, turno = _cargo_uf_turno(url)
        except SystemExit as e:
            st.error(str(e))
            st.stop()
        pesquisas = parsear(texto)
        if not pesquisas:
            st.error("Não reconheci nenhuma pesquisa no texto. Confira se copiou a seção certa.")
        else:
            linhas_p, linhas_r, avisos = montar(pesquisas, ano, uf, cargo, turno, url.strip())
            st.session_state["colar_resultado"] = {
                "linhas_p": linhas_p, "linhas_r": linhas_r,
                "avisos": avisos, "turno": turno,
            }

res = st.session_state.get("colar_resultado")
if res:
    st.markdown('<div class="ge-rule">Revisão</div>', unsafe_allow_html=True)
    st.write(f"**{len(res['linhas_p'])} pesquisa(s)** · **{len(res['linhas_r'])} resultado(s)** · "
             f"vai pra Matriz **{res['turno'].upper()}**")

    for aviso in res["avisos"]:
        st.markdown(f'<div class="ge-aviso">⚠️ {aviso}</div>', unsafe_allow_html=True)

    df = pd.DataFrame(res["linhas_r"])[
        ["registro_tse", "instituto", "data_campo", "scenario_label",
         "candidato_partido", "partido", "tipo", "percentual"]]
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown('<div class="ge-rule">Gravar</div>', unsafe_allow_html=True)
    if res["avisos"]:
        st.warning("Há avisos de conferência acima (nº de colunas ≠ nº de percentuais). "
                   "Confira antes de gravar.")
    sheet_id = MATRIZ_T2 if res["turno"] == "t2" else MATRIZ_T1
    if not sheet_id:
        st.error(f"ID da matriz {res['turno'].upper()} não configurado nos Secrets.")
    else:
        gc = _sheets_client()
        # Aviso de repetição: registro TSE + cargo que já está na matriz (do
        # Polling Manual ou de um colar anterior). Não bloqueia — o dedup real,
        # por scenario_id, acontece no salvar_tudo; aqui é só um sinal pra revisar.
        if gc:
            existentes = _registros_existentes(gc, sheet_id)
            repetidos = sorted({(p["registro_tse"], p["cargo"]) for p in res["linhas_p"]
                                if (p["registro_tse"].upper(), p["cargo"].lower()) in existentes})
            if repetidos:
                st.markdown(
                    '<div class="ge-aviso">⚠️ Já existe(m) na matriz (registro + cargo): '
                    + ", ".join(f"{r} ({c})" for r, c in repetidos)
                    + ". Cenário idêntico não duplica; cenário novo do mesmo "
                    "registro é adicionado.</div>", unsafe_allow_html=True)

        if st.button(f"Gravar na Matriz {res['turno'].upper()}", use_container_width=True):
            if not gc:
                st.error("Credenciais do Google Sheets não encontradas.")
            else:
                import pandas as _pd
                from polling_manual_core import salvar_tudo
                with st.spinner("Gravando nas abas pesquisas / resultados..."):
                    salvar_tudo(gc, sheet_id,
                                _pd.DataFrame(res["linhas_p"]), _pd.DataFrame(res["linhas_r"]))
                st.success(f"Gravado: {len(res['linhas_p'])} pesquisa(s) e "
                           f"{len(res['linhas_r'])} resultado(s) na Matriz {res['turno'].upper()}. "
                           "A média móvel é reconstruída de 4 em 4 horas.")
                st.session_state.pop("colar_resultado", None)
