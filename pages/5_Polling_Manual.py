from datetime import datetime
from difflib import get_close_matches
import hashlib
import inspect
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import fitz
import gspread
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from polling_manual_core import (
    CLASSIFICACAO_INSTITUTOS,
    append_log_resultados_manual,
    carregar_df_da_aba,
    classificar_instituto,
    garantir_aba,
    gerar_poll_id,
    gerar_scenario_id,
    normalizar_data_campo_segura,
    normalizar_disputa_t2,
    normalizar_instituto,
    normalizar_partido,
    normalizar_scenario_label_t1,
    obter_metodologia,
    registro_tse_valido,
    salvar_tudo,
)


st.set_page_config(page_title="Polling manual", layout="wide")

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
[data-testid="stButton"] > button {
    font-size: 11px !important; font-weight: 500 !important; letter-spacing: 0.1em !important;
    text-transform: uppercase !important; border-radius: 0 !important;
    border: 1px solid #962E4D !important; background: transparent !important;
    color: #962E4D !important; padding: 5px 14px !important;
    transition: background 0.15s, color 0.15s !important;
}
[data-testid="stButton"] > button:hover { background: #962E4D !important; color: #fff !important; }
[data-testid="stSidebar"] [data-testid="stButton"] > button { border: 1px solid #962E4D !important; color: #962E4D !important; }
[data-testid="stSidebar"] [data-testid="stButton"] > button:hover { background: #962E4D !important; color: #fff !important; }
[data-testid="stRadio"] > label, [data-testid="stSelectbox"] > label,
[data-testid="stMultiSelect"] > label, [data-testid="stTextInput"] > label,
[data-testid="stNumberInput"] > label, [data-testid="stTextArea"] > label {
    font-size: 11px !important; font-weight: 700 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important; color: #767672 !important;
}
[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid #DADAD4 !important; gap: 0 !important; }
[data-testid="stTabs"] [role="tab"] {
    font-size: 11px !important; font-weight: 500 !important; letter-spacing: 0.12em !important;
    text-transform: uppercase !important; color: #767672 !important;
    padding: 10px 20px 9px !important; border-bottom: 2px solid transparent !important;
    background: transparent !important; border-radius: 0 !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: #962E4D !important; border-bottom-color: #962E4D !important; }
.ge-hero { background: #962E4D; display: flex; align-items: center; padding: 36px 48px; margin: 0 -2rem 32px -2rem; }
.ge-hero-title { font-family: 'Montserrat', sans-serif; font-size: 48px; font-weight: 800; color: #fff; line-height: 1; letter-spacing: -0.01em; }
.ge-rule { font-size: 12px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #962E4D; border-top: 1.5px solid #962E4D; padding-top: 8px; margin: 20px 0 14px; }
</style>""", unsafe_allow_html=True)


# ── autenticação ──────────────────────────────────────────────────────────────

def _load_auth_config():
    if "AUTH_CONFIG" in st.secrets:
        return yaml.load(st.secrets["AUTH_CONFIG"], Loader=SafeLoader)

    config_path = ROOT_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
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

sig = inspect.signature(authenticator.login)
params = sig.parameters

try:
    if "location" in params:
        login_result = authenticator.login(location="main")
    else:
        login_result = authenticator.login("Login", "main")
except TypeError:
    login_result = authenticator.login("Login", "main")

if isinstance(login_result, (tuple, list)) and len(login_result) == 3:
    name, authentication_status, username = login_result
else:
    authentication_status = st.session_state.get("authentication_status", None)
    name = st.session_state.get("name", "")
    username = st.session_state.get("username", "")

if authentication_status is False:
    st.error("Usuário ou senha inválidos.")
    st.stop()

if authentication_status is None:
    st.info("Faça login para continuar.")
    st.stop()


# ── configurações ─────────────────────────────────────────────────────────────

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
MATRIZ_T1_SPREADSHEET_ID = (
    st.secrets.get("MATRIZ_T1_SHEET_ID")
    or st.secrets.get("POLLINGDATA_T1_SHEET_ID")
    or st.secrets.get("POLLINGDATA_SHEET_ID")
    or st.secrets.get("SPREADSHEET_ID_POLLINGDATA")
    or st.secrets.get("POLLING_SHEET_ID")
    or os.getenv("MATRIZ_T1_SHEET_ID", "")
    or os.getenv("POLLINGDATA_T1_SHEET_ID", "")
    or os.getenv("POLLINGDATA_SHEET_ID", "")
    or os.getenv("SPREADSHEET_ID_POLLINGDATA", "")
    or os.getenv("POLLING_SHEET_ID", "")
)
MATRIZ_T2_SPREADSHEET_ID = (
    st.secrets.get("MATRIZ_T2_SHEET_ID")
    or st.secrets.get("POLLINGDATA_T2_SHEET_ID")
    or st.secrets.get("SPREADSHEET_ID_POLLINGDATA_T2")
    or os.getenv("MATRIZ_T2_SHEET_ID", "")
    or os.getenv("POLLINGDATA_T2_SHEET_ID", "")
    or os.getenv("SPREADSHEET_ID_POLLINGDATA_T2", "")
)
# Planilha "Eleições 2026 - Fluxo de Pesquisa e Coleta dos Dados" (aba
# 'relatorios'), a mesma fila que o eixo-eleicoes usa em relatorios_pipeline.py.
# Opcional: sem esse secret, o Polling Manual funciona igual, só não fecha o
# loop com a fila (ver marcar_topline_extraida_manual).
SPREADSHEET_ID_RELATORIOS = (
    st.secrets.get("SPREADSHEET_ID_RELATORIOS")
    or os.getenv("SPREADSHEET_ID_RELATORIOS", "")
).strip()
LOGO_PATH = str(ROOT_DIR / "Marca_eixo_vetor_Logo horizontal magenta.png")

UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]
LEITURA_PDF = [
    "Auto (texto se tiver; imagem se for scan)",
    "Texto (PyMuPDF)",
    "Imagem (Gemini visão)",
]
POLLING_MANUAL_CARGOS = ["governador", "senador", "presidente"]
POLLING_MANUAL_TURNOS = ["t1", "t2"]
POLLING_MANUAL_TIPOS_RESULTADO = ["candidato", "nao_valido"]
MODOS_COLETA = [
    "",
    "Presencial",
    "Telefônica",
    "Telefônica (CATI)",
    "Telefônica (IVR)",
    "Online",
    "Misto",
]
OUTRO_MODO_COLETA = "Outro…"
ORIGEM_DADO_MANUAL = "polling_manual"
VERSAO_CATALOGO_INSTITUTOS = "2026-07-14-2"


def planilha_destino_polling(turno: str) -> tuple[str, str]:
    turno_norm = normalizar_texto_simples(turno).lower()
    if turno_norm == "t2":
        return MATRIZ_T2_SPREADSHEET_ID.strip(), "Matriz T2"
    return MATRIZ_T1_SPREADSHEET_ID.strip(), "Matriz T1"


def normalizar_texto_simples(valor) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def normalizar_chave_dedup_manual(valor) -> str:
    texto = unicodedata.normalize("NFKD", normalizar_texto_simples(valor))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.lower()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")


def chave_instituto_catalogo(valor) -> str:
    """Chave sem acento/caixa para buscar o nome canônico nas matrizes."""
    return normalizar_chave_dedup_manual(valor).replace("-", "")


def registro_tse_valido(valor: str) -> bool:
    texto = normalizar_texto_simples(valor).lower()
    return texto not in ("", "sem registro", "sem_registro", "semregistro", "nan", "none")


def gerar_chave_polling_registro(uf, cargo, turno, registro_tse) -> str:
    registro = normalizar_texto_simples(registro_tse).upper()
    if not registro_tse_valido(registro):
        return ""

    return "|".join([
        "registro",
        normalizar_chave_dedup_manual(uf).upper(),
        normalizar_chave_dedup_manual(cargo),
        normalizar_chave_dedup_manual(turno),
        registro,
    ])


def gerar_chave_polling_fallback(ano, uf, cargo, turno, instituto, data_campo) -> str:
    instituto_key = normalizar_chave_dedup_manual(instituto)
    data_key = normalizar_texto_simples(data_campo)
    if not instituto_key or not data_key:
        return ""

    return "|".join([
        "fallback",
        normalizar_texto_simples(ano),
        normalizar_chave_dedup_manual(uf).upper(),
        normalizar_chave_dedup_manual(cargo),
        normalizar_chave_dedup_manual(turno),
        instituto_key,
        data_key,
    ])


def normalizar_percentual_simples(valor) -> float | None:
    s = normalizar_texto_simples(valor).replace("%", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def normalizar_inteiro_simples(valor) -> int | None:
    s = normalizar_texto_simples(valor)
    if not s:
        return None
    s = re.sub(r"[^\d]", "", s)
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def limitar_inteiro(valor, minimo: int, maximo: int, padrao: int) -> int:
    n = normalizar_inteiro_simples(valor)
    if n is None:
        return padrao
    return max(minimo, min(maximo, n))


def limitar_float(valor, minimo: float, maximo: float, padrao: float) -> float:
    n = normalizar_percentual_simples(valor)
    if n is None:
        return padrao
    return max(minimo, min(maximo, float(n)))


def extrair_json_de_texto_bruto(texto: str) -> dict:
    bruto = (texto or "").strip()
    if not bruto:
        raise RuntimeError("O Gemini não retornou JSON.")

    bruto = re.sub(r"^```json\s*", "", bruto, flags=re.IGNORECASE)
    bruto = re.sub(r"^```\s*", "", bruto)
    bruto = re.sub(r"\s*```$", "", bruto)
    decoder = json.JSONDecoder()

    for match in re.finditer(r"\{", bruto):
        ini = match.start()
        try:
            obj, _ = decoder.raw_decode(bruto[ini:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    raise RuntimeError("Não foi possível localizar um objeto JSON válido na resposta do Gemini.")


@st.cache_resource
def get_gemini_client():
    if not GEMINI_API_KEY.strip():
        raise RuntimeError("Configure a GEMINI_API_KEY nos Secrets ou nas variáveis de ambiente.")
    return genai.Client(api_key=GEMINI_API_KEY)


def gerar_conteudo_gemini(model: str, contents, *, tentativas: int = 3, backoff_inicial: float = 1.5):
    """Chama o Gemini com retry/backoff. Lança RuntimeError se todas as
    tentativas falharem ou se o conteúdo retornado vier vazio."""
    import time

    client = get_gemini_client()
    ultimo_erro: Exception | None = None

    for tentativa in range(1, tentativas + 1):
        try:
            try:
                config = types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=8000)
                )
                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except Exception:
                # Algumas versões do SDK não aceitam ThinkingConfig; tenta sem.
                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                )

            if getattr(resp, "text", None):
                return resp

            ultimo_erro = RuntimeError("Gemini retornou resposta vazia.")
        except Exception as exc:
            ultimo_erro = exc

        if tentativa < tentativas:
            time.sleep(backoff_inicial * (2 ** (tentativa - 1)))

    raise RuntimeError(
        f"Falha ao chamar o Gemini após {tentativas} tentativas: {ultimo_erro}"
    )


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
def get_polling_sheets_client():
    creds_dict = _carregar_google_creds_dict()
    if not creds_dict:
        return None

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(credentials)


@st.cache_data(ttl=600, show_spinner=False)
def carregar_catalogo_institutos_matrizes(versao_catalogo: str) -> tuple[dict, str]:
    """Lê T1/T2 como fonte canônica dos nomes e das classificações.

    A chave é insensível a caixa e acentos, mas o valor conserva exatamente a
    grafia gravada nas matrizes. O dicionário local só é usado como fallback
    quando a conexão com as planilhas estiver indisponível.
    """
    client = get_polling_sheets_client()
    catalogo = {}

    if client:
        for spreadsheet_id in [MATRIZ_T1_SPREADSHEET_ID.strip(), MATRIZ_T2_SPREADSHEET_ID.strip()]:
            if not spreadsheet_id:
                continue
            try:
                aba_pesquisas = client.open_by_key(spreadsheet_id).worksheet("pesquisas")
                df = carregar_df_da_aba(aba_pesquisas)
            except Exception:
                continue

            if df.empty or "instituto" not in df.columns:
                continue

            for _, linha in df.iterrows():
                # Aplica apenas aliases já deliberados (por exemplo, Mídia
                # Inteligência em Pesquisa -> Ideia Inteligência) antes de
                # formar o catálogo a partir das matrizes.
                instituto = normalizar_instituto(linha.get("instituto", ""))
                if not instituto:
                    continue
                chave = chave_instituto_catalogo(instituto)
                classificacao = normalizar_texto_simples(linha.get("classificacao_instituto", ""))
                atual = catalogo.get(chave)
                if atual is None:
                    catalogo[chave] = {
                        "instituto": instituto,
                        "classificacao": classificacao,
                    }
                elif not atual.get("classificacao") and classificacao:
                    atual["classificacao"] = classificacao

    if catalogo:
        return catalogo, "T1 e T2"

    # Mantém a página utilizável durante uma indisponibilidade temporária das
    # matrizes, mas não trata esse fallback como fonte canônica.
    return {
        chave_instituto_catalogo(instituto): {
            "instituto": instituto,
            "classificacao": classificar_instituto(instituto),
        }
        for instituto in CLASSIFICACAO_INSTITUTOS
    }, "dicionário local temporário"


def aplicar_grafia_canonica_do_instituto():
    """Troca, no callback do widget, uma grafia conhecida pela forma de T1/T2."""
    catalogo = st.session_state.get("polling_catalogo_institutos", {})
    valor = normalizar_texto_simples(st.session_state.get("polling_meta_instituto", ""))
    entrada = catalogo.get(chave_instituto_catalogo(valor))
    if entrada and valor != entrada["instituto"]:
        st.session_state["polling_meta_instituto"] = entrada["instituto"]


def extrair_texto_pdf_bytes(pdf_bytes: bytes, page_indices: list[int] | None = None) -> str:
    partes = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        pages = page_indices if page_indices is not None else list(range(doc.page_count))
        for idx in pages:
            if idx < 0 or idx >= doc.page_count:
                continue
            raw = doc.load_page(idx).get_text("text") or ""
            raw = raw.replace("-\n", "").replace("\n", " ")
            raw = re.sub(r"\s{2,}", " ", raw).strip()
            if raw:
                partes.append(raw)
    return " ".join(partes).strip()


def render_pdf_page_png(pdf_bytes: bytes, page_index: int, zoom: float = 3.0) -> bytes:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_index = max(0, min(page_index, doc.page_count - 1))
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")


def extrair_pdf_imagem_padrao(imagens_png: list[bytes]) -> str:
    prompt = """Você está lendo imagens de uma pesquisa eleitoral brasileira.
Extraia o texto principal de todas as páginas.
Preserve nomes, datas, números, percentuais e registro TSE exatamente como aparecem.
Ignore menus, rodapés e elementos decorativos.
Retorne apenas o texto extraído em prosa limpa, sem markdown."""

    parts = [prompt]
    for img in imagens_png:
        parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))

    resp = gerar_conteudo_gemini(GEMINI_MODEL, parts)
    return normalizar_texto_simples(getattr(resp, "text", "") or "")


def processar_pdf_polling_manual(
    pdf_bytes: bytes,
    modo: str,
    page_indices: list[int],
    atualizar_etapa=None,
) -> tuple[str, str]:
    n_paginas = len(page_indices)

    def informar(mensagem: str):
        if atualizar_etapa:
            atualizar_etapa(mensagem)

    def _renderizar_imagens():
        imagens, preview = [], None
        informar(f"Renderizando {n_paginas} página(s) como imagem…")
        progresso = st.progress(0, text=f"Renderizando página 0 de {n_paginas}")
        for posicao, idx in enumerate(page_indices, start=1):
            img = render_pdf_page_png(pdf_bytes, idx, zoom=3.0)
            imagens.append(img)
            if preview is None:
                preview = img
            progresso.progress(
                int(posicao * 100 / n_paginas),
                text=f"Renderizando página {posicao} de {n_paginas}",
            )
        progresso.empty()
        st.session_state["polling_pdf_preview_png"] = preview
        return imagens

    if modo == "Texto (PyMuPDF)":
        informar(f"Lendo a camada de texto de {n_paginas} página(s)…")
        txt = extrair_texto_pdf_bytes(pdf_bytes, page_indices=page_indices)
        st.session_state["polling_pdf_preview_png"] = None
        if txt:
            return txt, f"Texto nativo (PyMuPDF): {n_paginas} página(s) lida(s) diretamente do PDF."
        return "PDF sem texto extraível (possível scan).", (
            f"Texto nativo (PyMuPDF): não havia camada de texto nas {n_paginas} página(s)."
        )

    if modo == "Imagem (Gemini visão)":
        imagens = _renderizar_imagens()
        informar(f"Enviando {n_paginas} página(s) renderizada(s) para o Gemini Vision…")
        return extrair_pdf_imagem_padrao(imagens), (
            f"Imagem (Gemini Vision): {n_paginas} página(s) renderizada(s) e lida(s) como imagem."
        )

    informar(f"Verificando a camada de texto de {n_paginas} página(s)…")
    txt = extrair_texto_pdf_bytes(pdf_bytes, page_indices=page_indices)
    if txt and len(txt.strip()) >= 800:
        st.session_state["polling_pdf_preview_png"] = None
        informar("Camada de texto encontrada; não foi necessário usar imagens.")
        return txt, (
            f"Automático: texto nativo encontrado em {n_paginas} página(s); Gemini Vision não foi usado."
        )

    informar("Texto nativo ausente ou insuficiente; mudando para leitura por imagem.")
    imagens = _renderizar_imagens()
    informar(f"Enviando {n_paginas} página(s) renderizada(s) para o Gemini Vision…")
    return extrair_pdf_imagem_padrao(imagens), (
        f"Automático: texto nativo insuficiente; {n_paginas} página(s) lida(s) como imagem pelo Gemini Vision."
    )


def classificar_tipo_resultado_manual(nome: str, tipo_informado: str = "") -> str:
    tipo = normalizar_texto_simples(tipo_informado).lower()
    if tipo in POLLING_MANUAL_TIPOS_RESULTADO:
        return tipo

    nome_norm = normalizar_texto_simples(nome).lower()
    marcadores = [
        "branco", "nulo", "nulos", "ns/nr", "nsnr",
        "não sabe", "nao sabe", "indeciso", "indecisos", "nenhum",
    ]
    if any(tag in nome_norm for tag in marcadores):
        return "nao_valido"

    return "candidato"


def normalizar_payload_polling(payload: dict) -> dict:
    payload = payload or {}
    cenarios = payload.get("cenarios") or []
    cargo = normalizar_texto_simples(payload.get("cargo")).lower() or "governador"
    turno = normalizar_texto_simples(payload.get("turno")).lower() or "t1"
    uf = normalizar_texto_simples(payload.get("uf")).upper() or "BR"
    instituto = normalizar_instituto(normalizar_texto_simples(payload.get("instituto")))

    cenarios_norm = []
    for idx, cenario in enumerate(cenarios, start=1):
        label = normalizar_texto_simples(cenario.get("scenario_label") or cenario.get("cenario") or idx)
        itens_raw = cenario.get("itens") or cenario.get("resultados") or []
        itens_norm = []

        for item in itens_raw:
            candidato = normalizar_texto_simples(
                item.get("candidato") or item.get("nome") or item.get("opcao") or item.get("candidato_partido")
            )
            partido = normalizar_partido(item.get("partido"))
            percentual = normalizar_percentual_simples(item.get("percentual"))
            tipo = classificar_tipo_resultado_manual(candidato, item.get("tipo", ""))

            if not candidato and percentual is None:
                continue

            itens_norm.append({
                "candidato": candidato,
                "partido": partido,
                "percentual": percentual,
                "tipo": tipo,
            })

        # Cenário pode trazer turno próprio (material com T1 e T2 juntos);
        # cai pro turno do payload quando o cenário não especificar o dele.
        turno_cenario = normalizar_texto_simples(cenario.get("turno")).lower()
        if turno_cenario not in POLLING_MANUAL_TURNOS:
            turno_cenario = turno

        # Para T2, a identidade persistida vem dos dois candidatos. Rótulos
        # determinísticos evitam conteúdo alucinado ou herdado na revisão.
        if turno_cenario == "t2":
            label = f"Segundo turno — cenário {idx}"

        cenarios_norm.append({
            "scenario_label": label or str(idx),
            "turno": turno_cenario,
            "itens": itens_norm,
        })

    return {
        "cargo": cargo,
        "turno": turno,
        "uf": uf,
        "instituto": instituto,
        "registro_tse": normalizar_texto_simples(payload.get("registro_tse")),
        "data_campo": normalizar_texto_simples(payload.get("data_campo")),
        "amostra": normalizar_inteiro_simples(payload.get("amostra")),
        "margem_erro": normalizar_percentual_simples(payload.get("margem_erro")),
        "confianca": normalizar_inteiro_simples(payload.get("confianca")),
        "modo": normalizar_texto_simples(payload.get("modo")),
        # A metodologia é cadastrada por instituto no arquivo central.
        "metodologia": "",
        "fonte_url_original": normalizar_texto_simples(payload.get("fonte_url_original")),
        "observacoes": normalizar_texto_simples(payload.get("observacoes")),
        "pendencias": payload.get("pendencias") or [],
        "cenarios": cenarios_norm or [{"scenario_label": "1", "turno": turno, "itens": []}],
    }


def carregar_payload_polling_no_state(payload: dict):
    payload = normalizar_payload_polling(payload)

    for chave in list(st.session_state.keys()):
        if chave.startswith((
            "polling_editor_",
            "polling_scenario_label_",
            "polling_scenario_desc_",
            "polling_scenario_turno_",
            "polling_meta_",
        )):
            del st.session_state[chave]

    st.session_state["polling_manual_payload"] = payload
    st.session_state["polling_meta_cargo"] = payload["cargo"] if payload["cargo"] in POLLING_MANUAL_CARGOS else "governador"
    st.session_state["polling_meta_turno"] = payload["turno"] if payload["turno"] in POLLING_MANUAL_TURNOS else "t1"
    st.session_state["polling_meta_uf"] = payload["uf"] if payload["uf"] in (["BR"] + UFS) else "BR"
    st.session_state["polling_meta_instituto"] = payload["instituto"]
    st.session_state["polling_meta_registro"] = payload["registro_tse"]
    st.session_state["polling_meta_data"] = payload["data_campo"]
    st.session_state["polling_meta_amostra"] = payload["amostra"] or 0
    st.session_state["polling_meta_margem"] = limitar_float(payload["margem_erro"], 0.0, 100.0, 0.0)
    confianca_extraida = normalizar_inteiro_simples(payload["confianca"])
    st.session_state["polling_meta_confianca"] = (
        str(confianca_extraida) if confianca_extraida is not None else ""
    )
    st.session_state["polling_meta_modo"] = payload.get("modo", "")
    st.session_state["polling_meta_metodologia"] = payload.get("metodologia", "")
    st.session_state["polling_meta_observacoes"] = payload["observacoes"]
    st.session_state["polling_manual_duplicatas"] = None
    st.session_state["polling_manual_resultado"] = None
    st.session_state["polling_pdf_preview_png"] = None
    return payload


MESES_PT_NUMERO = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def corrigir_metadados_explicitos_da_fonte(payload: dict, texto_fonte: str) -> dict:
    """Prefere metadados declarados textualmente à inferência do modelo.

    Esta checagem não faz outra chamada ao Gemini: apenas corrige confiança e
    data final de coleta quando elas estão inequívocas no material de origem.
    """
    payload = dict(payload or {})
    texto = normalizar_texto_simples(texto_fonte)

    confianca = re.search(
        r"(?:nível|nivel)\s+de\s+confiança\s*(?:de|:)?\s*(\d{1,3}(?:[,.]\d+)?)\s*%",
        texto,
        flags=re.IGNORECASE,
    )
    if confianca:
        try:
            valor = float(confianca.group(1).replace(",", "."))
            if 0 <= valor <= 100:
                payload["confianca"] = int(valor) if valor.is_integer() else valor
        except ValueError:
            pass
    else:
        # Não deixe uma inferência do modelo virar "95" se a fonte colada não
        # informou confiança. A interface agora mantém esse campo em branco.
        payload["confianca"] = None

    # Aya Bancah é parceiro de divulgação; a realização desta série é do
    # PoderData. Isso também impede a reutilização de um instituto anterior.
    if re.search(r"\bpoderdata\s*/\s*aya(?:\s+bancah)?\b", texto, flags=re.IGNORECASE):
        payload["instituto"] = "PoderData"

    intervalo = re.search(
        r"(?:entre\s+(?:os\s+)?dias?\s+)?\d{1,2}(?:º|o)?"
        r"(?:\s+de\s+[a-záàâãéêíóôõúç]+)?\s*(?:a|até|e|-)\s*"
        r"(\d{1,2})(?:º|o)?\s+de\s+"
        r"(janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)",
        texto,
        flags=re.IGNORECASE,
    )
    if intervalo:
        anos = re.findall(r"(?<!\d)(20\d{2})(?!\d)", " ".join([
            texto,
            normalizar_texto_simples(payload.get("registro_tse")),
            normalizar_texto_simples(payload.get("data_campo")),
        ]))
        if anos:
            mes_chave = unicodedata.normalize("NFKD", intervalo.group(2).lower())
            mes_chave = "".join(ch for ch in mes_chave if not unicodedata.combining(ch))
            try:
                payload["data_campo"] = datetime(
                    int(anos[0]), MESES_PT_NUMERO[mes_chave], int(intervalo.group(1))
                ).strftime("%Y-%m-%d")
            except (KeyError, ValueError):
                pass

    return payload


def extrair_dados_polling_gemini(
    texto_fonte: str,
    url_original: str = "",
    *,
    escopo: dict | None = None,
) -> dict:
    """Extrai dados estruturados via Gemini.

    Args:
        texto_fonte: texto cru da pesquisa (notícia, PDF OCR, release).
        url_original: URL da fonte para preencher fonte_url_original.
        escopo: dict opcional com filtros de foco:
            cargo, uf, turno, instituto (strings; "" = sem filtro)
            instrucoes (string livre adicional)
    """
    escopo = escopo or {}
    cargo_alvo = normalizar_texto_simples(escopo.get("cargo")).lower()
    uf_alvo = normalizar_texto_simples(escopo.get("uf")).upper()
    turno_alvo = normalizar_texto_simples(escopo.get("turno")).lower()
    instituto_alvo = normalizar_texto_simples(escopo.get("instituto"))
    instrucoes_livres = normalizar_texto_simples(escopo.get("instrucoes"))

    # Monta seção de restrições só se algo foi definido. turno NÃO é restrição
    # de exclusão (ver bloco separado abaixo) — cargo/uf/instituto continuam
    # obrigatórios quando informados.
    restricoes = []
    if cargo_alvo:
        restricoes.append(f"- cargo = {cargo_alvo}")
    if uf_alvo:
        restricoes.append(f"- uf = {uf_alvo}")
    if instituto_alvo:
        restricoes.append(f"- instituto = {instituto_alvo}")

    bloco_escopo = ""
    if restricoes or turno_alvo or instrucoes_livres:
        partes = []
        if restricoes:
            partes.append("FOCO DA EXTRAÇÃO (restrições obrigatórias):")
            partes.extend(restricoes)
            partes.append(
                "Extraia APENAS o bloco que casa com essas restrições. "
                "Ignore qualquer outro estado, cargo ou instituto que apareça no material."
            )
            partes.append(
                "Se o material NÃO contém um bloco que case com essas restrições, "
                "retorne cenarios=[] e adicione em pendencias um aviso claro do que faltou "
                "(ex.: \"Não encontrei pesquisa de presidente na BA no material fornecido\")."
            )
        if turno_alvo:
            partes.append(
                f"TURNO-ALVO = {turno_alvo} é uma PRIORIDADE, não um filtro de exclusão: "
                "extraia normalmente os cenários desse turno, mas se o material também trouxer, "
                "para o MESMO cargo/uf/instituto, um cenário do OUTRO turno claramente identificado "
                "(ver regra de classificação de turno abaixo), extraia esse também em vez de "
                "descartar — cada cenário tem seu próprio campo 'turno', então os dois convivem na "
                "mesma resposta. Não deixe de extrair o turno-alvo pedido só porque achou também o "
                "outro."
            )
        if instrucoes_livres:
            partes.append(f"INSTRUÇÕES ADICIONAIS DO USUÁRIO: {instrucoes_livres}")
        bloco_escopo = "\n".join(partes) + "\n\n"

    prompt = f"""
Você recebe o texto completo de uma notícia, release ou PDF de uma pesquisa eleitoral brasileira.
Extraia os dados estruturados para inserção em planilha.

{bloco_escopo}REGRAS:
- Responda somente com JSON válido.
- Não invente dados ausentes. Use string vazia ou null.
- data_campo deve ser a data FINAL da coleta, em YYYY-MM-DD. Quando a fonte
  informar um intervalo (ex.: "1º a 5 de julho"), use o último dia (dia 5),
  nunca o primeiro. Se a fonte não informar a data final de coleta, use a data
  de divulgação como fallback e registre em observacoes: "data de divulgação
  usada como data_campo; período de coleta não informado".
- confianca deve ser somente o percentual explicitamente informado como nível de
  confiança (ex.: "nível de confiança de 95%" = 95). Nunca presuma 100 ou 95
  quando a fonte não informar esse dado; nesse caso use null.
- cargo deve ser governador, senador ou presidente.
- turno deve ser t1 ou t2.
- uf deve estar em caixa alta. Para presidente use BR.
- instituto é quem realizou a pesquisa, não o veículo que a publicou nem
  parceiro só de divulgação. Na série "PoderData/Aya", use "PoderData": Aya
  Bancah é parceiro de divulgação.
- percentual deve ser numérico, sem %.
- tipo deve ser candidato ou nao_valido.
- Use nao_valido para branco/nulo, indecisos, ns/nr e equivalentes.
- modo é o MÉTODO DE COLETA da pesquisa (ex.: "Presencial", "Telefônica (CATI)",
  "Telefônica (IVR)", "Online", "Misto"). Use string vazia se não houver indicação.
- SÓ EXTRAIA PERGUNTA ESTIMULADA (com lista de nomes apresentada ao entrevistado).
  NUNCA extraia uma tabela/gráfico rotulado "espontânea" ou "espontâneas"
  (resposta aberta, sem lista de nomes) — isso NUNCA vira cenário, mesmo que
  seja a única opção disponível para aquele cargo. É comum o documento NUNCA
  usar a palavra "estimulada" em lugar nenhum: nesse caso, a tabela estimulada
  é identificada por ELIMINAÇÃO — é a que NÃO tem "espontânea" no título/rótulo.
  Se toda tabela do cargo estiver rotulada como espontânea (nenhuma estimulada
  disponível), não crie cenário para esse cargo e registre em pendencias.
- Se o mesmo cargo tiver mais de uma tabela estimulada (não-espontânea) —
  ex.: uma com todos os candidatos e outra com lista reduzida ("considerando
  apenas estes N candidatos..."), ou perguntas de 1º e 2º voto quando o cargo
  elege mais de um nome (ex.: dois senadores) — NÃO escolha só uma nem some os
  números: crie um cenário separado para cada tabela, com scenario_label que
  descreva a diferença (ex.: "Estimulada", "Estimulada - 5 candidatos",
  "1º voto", "2º voto").
- CLASSIFICAÇÃO DE TURNO: use t2 quando a própria pergunta, título ou
  cabeçalho da tabela/gráfico disser explicitamente "segundo turno", "2º
  turno", "2° turno" ou equivalente inequívoco. Além disso, EXCLUSIVAMENTE
  para presidente e governador (únicos cargos com 2º turno de verdade no
  sistema eleitoral brasileiro), uma tabela estimulada com EXATAMENTE dois
  nomes de candidato (mais NH/BR/NULO e NS/NR, sem nenhum outro candidato) é
  t2 mesmo sem menção explícita — é a forma mais comum de reportar simulação
  de 2º turno. NÃO aplique essa contagem para senador (nunca tem 2º turno, ver
  regra própria abaixo) nem para uma tabela de rejeição/aprovação/comparação
  entre dois nomes que não seja pergunta de intenção de voto.
- CADA CENÁRIO TEM SEU PRÓPRIO CAMPO "turno" (t1 ou t2), classificado pela
  regra literal acima. Não existe um turno único pra resposta inteira: se o
  material trouxer, pro mesmo cargo/uf/instituto, tanto o campo completo de
  1º turno quanto uma simulação de 2º turno EXPLICITAMENTE identificada,
  extraia OS DOIS como cenários separados na mesma resposta, cada um com seu
  turno correto — não descarte um pra "focar" só no outro, mesmo que
  TURNO-ALVO tenha sido informado (ver regra de FOCO DA EXTRAÇÃO acima). Não
  use inferência eleitoral pra completar confrontos que o material não trouxer.
- Para t2, cada confronto direto deve ser um cenário separado.
- SENADOR NUNCA TEM SEGUNDO TURNO: eleição de senador no Brasil não tem 2º
  turno (decide por maioria simples no 1º turno). Mesmo que o relatório traga
  uma pergunta chamada "simulação de 2º turno para Senador" ou um confronto
  direto de dois nomes para esse cargo, IGNORE essa pergunta por completo, não
  crie cenário nenhum para ela. Vale só para senador; presidente e governador
  continuam normalmente.
- SENADOR COM 1º/2º VOTO SEPARADOS: se o relatório trouxer tabelas separadas
  para senador de 2 vagas ("1º voto", "2º voto" e/ou "média do 1º e 2º voto"),
  crie um cenário separado para cada uma que existir, preservando o dado bruto
  exatamente como publicado (cada tabela soma ~100% sozinha). NÃO calcule
  média, NÃO some, NÃO junte as tabelas.
- Se o relatório indicar que o entrevistado podia citar/votar em mais de um
  nome no mesmo cenário (comum pra senador de 2 vagas relatado numa tabela só,
  não separada em "1º/2º voto") e os percentuais somarem perto de 200% em vez
  de 100%, NÃO tente corrigir nem dividir os números — extraia como está e
  registre em observacoes que os percentuais somam ~200% (voto múltiplo por
  entrevistado nesse cenário).
- IGNORE páginas de SÍNTESE/RESUMO/DESTAQUE (capa de capítulo, "principais
  leituras", "síntese", cards de highlight com 1 ou 2 números grandes tipo
  "36% × 36%"): elas repetem números de cenários que já aparecem completos em
  outra página, e extraí-las cria cenários fragmentados/duplicados. Só extraia
  da tabela ou gráfico COMPLETO, com a lista de candidatos.
- LISTA SEM CONTEXTO NÃO É CENÁRIO: se aparecer uma lista de nomes+percentuais
  sem pergunta ou título identificável, não invente um cenário pra ela — pode
  ser o final de uma tabela de rejeição ou de outra pergunta. Só extraia
  quando conseguir identificar qual pergunta a tabela responde.
- Quando uma tabela trouxer as colunas "Porcentual" e "Porcentagem válida",
  escolha UMA base só. Como o JSON consolida branco/nulo/NS/NR em "nao_valido",
  use a coluna "Porcentual" para candidatos E inválidos. Não misture
  "Porcentagem válida" dos candidatos com "Porcentual" dos inválidos. Só use
  "Porcentagem válida" se não houver nenhum item "nao_valido" no cenário.

FORMATO:
{{
  "cargo": "",
  "turno": "",
  "uf": "",
  "instituto": "",
  "registro_tse": "",
  "data_campo": "",
  "amostra": null,
  "margem_erro": null,
  "confianca": null,
  "modo": "",
  "fonte_url_original": "{url_original}",
  "observacoes": "",
  "pendencias": [],
  "cenarios": [
    {{
      "scenario_label": "",
      "turno": "",
      "itens": [
        {{
          "candidato": "",
          "partido": "",
          "percentual": null,
          "tipo": "candidato"
        }}
      ]
    }}
  ]
}}
"turno" no nível raiz = turno predominante do material (fallback pra cenário
que não preencher o próprio); "turno" dentro de cada cenário é obrigatório
sempre que houver mais de um turno no material (ver regra acima) — nesse caso
preencha os dois, raiz E cada cenário.

TEXTO FONTE:
{texto_fonte}
""".strip()

    resp = gerar_conteudo_gemini(GEMINI_MODEL, prompt)
    payload = extrair_json_de_texto_bruto(getattr(resp, "text", "") or "")
    payload = corrigir_metadados_explicitos_da_fonte(payload, texto_fonte)
    return normalizar_payload_polling(payload)


def montar_dataframes_polling_manual(
    payload: dict,
    fonte_url: str,
    fonte_url_original: str,
    classificacao_canonica: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cargo = normalizar_texto_simples(payload.get("cargo")).lower()
    turno = normalizar_texto_simples(payload.get("turno")).lower()
    uf = normalizar_texto_simples(payload.get("uf")).upper()
    instituto = normalizar_instituto(normalizar_texto_simples(payload.get("instituto")))
    registro_tse = normalizar_texto_simples(payload.get("registro_tse")).upper()
    data_campo = normalizar_data_campo_segura(normalizar_texto_simples(payload.get("data_campo")))
    amostra = normalizar_inteiro_simples(payload.get("amostra"))
    margem_erro = normalizar_percentual_simples(payload.get("margem_erro"))
    confianca = normalizar_inteiro_simples(payload.get("confianca"))
    horario_raspagem = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ano: deriva de data_campo (YYYY-MM-DD); fallback para ano atual
    ano_calc = datetime.now().year
    if data_campo and len(data_campo) >= 4 and data_campo[:4].isdigit():
        try:
            ano_calc = int(data_campo[:4])
        except ValueError:
            pass

    # modo: o que o Gemini extraiu do material (método de coleta); vazio se ausente
    modo_payload = normalizar_texto_simples(payload.get("modo"))
    # Metodologia vem exclusivamente do cadastro central do instituto, nunca
    # de texto livre nem de inferência do Gemini.
    metodologia = obter_metodologia(instituto)

    block_hash = hashlib.sha1(
        f"manual|{uf}|{cargo}|{turno}|{instituto}|{registro_tse}|{data_campo}".encode("utf-8", errors="ignore")
    ).hexdigest()[:10]

    fonte_url_original_final = normalizar_texto_simples(fonte_url_original) or normalizar_texto_simples(
        payload.get("fonte_url_original")
    )
    classificacao = normalizar_texto_simples(classificacao_canonica) or classificar_instituto(instituto)
    exige_registro = ano_calc == 2026
    if exige_registro and not registro_tse_valido(registro_tse):
        raise ValueError("Registro TSE é obrigatório para pesquisas de 2026.")

    pesquisas_rows = []
    resultados_rows = []
    scenario_ids_vistos = set()

    for idx, cenario in enumerate(payload.get("cenarios") or [], start=1):
        itens = cenario.get("itens") or []
        # Cenário pode trazer turno próprio (material com T1 e T2 juntos, ex.:
        # confronto de 2º turno embutido num relatório majoritariamente T1) —
        # cai pro turno do payload quando o cenário não especificar o dele.
        turno_cenario = normalizar_texto_simples(cenario.get("turno")).lower() or turno
        disputa = ""
        if turno_cenario == "t2":
            # T2 só é uma disputa binária. Não escolha os dois primeiros em
            # silêncio quando uma extração vier com três candidatos válidos.
            candidatos_validos = []
            chaves_candidatos = set()
            for item in itens:
                candidato = normalizar_texto_simples(item.get("candidato"))
                tipo_item = classificar_tipo_resultado_manual(candidato, item.get("tipo", ""))
                chave_candidato = candidato.casefold()
                if (
                    candidato
                    and tipo_item == "candidato"
                    and chave_candidato not in chaves_candidatos
                ):
                    candidatos_validos.append(candidato)
                    chaves_candidatos.add(chave_candidato)

            if len(candidatos_validos) != 2:
                raise ValueError(
                    f"Cenário {idx}: T2 exige exatamente dois candidatos válidos; "
                    f"encontrei {len(candidatos_validos)}. Revise o tipo de cada opção."
                )

            disputa = normalizar_disputa_t2(
                cenario.get("disputa") or cenario.get("scenario_label"),
                itens,
            )
            if not disputa:
                raise ValueError(
                    f"Cenário {idx}: informe exatamente dois candidatos válidos para formar a disputa de T2."
                )
            scenario_label = "NA"
        else:
            scenario_label = normalizar_scenario_label_t1(cenario.get("scenario_label"), idx)

        poll_id = gerar_poll_id(
            uf, instituto, registro_tse, data_campo, cargo, turno_cenario, block_hash,
            disputa=disputa,
            exigir_registro=exige_registro,
        )
        scenario_id = gerar_scenario_id(poll_id, scenario_label)
        if scenario_id in scenario_ids_vistos:
            raise ValueError(
                f"Cenário {idx}: duplicado após a padronização ({scenario_id}). Revise o rótulo ou os candidatos."
            )
        scenario_ids_vistos.add(scenario_id)
        fonte_url_final = normalizar_texto_simples(fonte_url) or f"manual://streamlit/{poll_id}"

        pesquisas_rows.append({
            "scenario_id": scenario_id,
            "poll_id": poll_id,
            "ano": ano_calc,
            "uf": uf,
            "cargo": cargo,
            "turno": turno_cenario,
            "disputa": disputa,
            "instituto": instituto,
            "classificacao_instituto": classificacao,
            "registro_tse": registro_tse,
            "data_campo": data_campo,
            "modo": modo_payload,
            "amostra": amostra,
            "margem_erro": margem_erro,
            "confianca": confianca,
            "scenario_label": scenario_label,
            "fonte_url": fonte_url_final,
            "fonte_url_original": fonte_url_original_final,
            "horario_raspagem": horario_raspagem,
            "metodologia": metodologia,
            "origem": ORIGEM_DADO_MANUAL,
        })

        for item in itens:
            candidato = normalizar_texto_simples(item.get("candidato"))
            partido = normalizar_partido(item.get("partido"))
            percentual = normalizar_percentual_simples(item.get("percentual"))
            tipo = classificar_tipo_resultado_manual(candidato, item.get("tipo", ""))

            if not candidato or percentual is None:
                continue

            candidato_partido = candidato if tipo == "nao_valido" else (f"{candidato} ({partido})" if partido else candidato)

            resultados_rows.append({
                "scenario_id": scenario_id,
                "poll_id": poll_id,
                "ano": ano_calc,
                "uf": uf,
                "cargo": cargo,
                "turno": turno,
                "disputa": disputa,
                "data_campo": data_campo,
                "instituto": instituto,
                "classificacao_instituto": classificacao,
                "registro_tse": registro_tse,
                "scenario_label": scenario_label,
                "candidato": candidato,
                "partido": partido,
                "candidato_partido": candidato_partido,
                "tipo": tipo,
                "percentual": percentual,
                "fonte_url": fonte_url_final,
                "horario_raspagem": horario_raspagem,
                "origem": ORIGEM_DADO_MANUAL,
            })

    return pd.DataFrame(pesquisas_rows), pd.DataFrame(resultados_rows)


def marcar_topline_extraida_manual(gc, df_p: pd.DataFrame) -> tuple[int, list[str]]:
    """Fecha o loop com a fila 'relatorios' do eixo-eleicoes: quando um relatório
    não tem ficha de instituto cadastrada, relatorios_pipeline.py grava
    '⚠️ REGISTRE NO POLLING MANUAL' em 'Topline extraída?' e NUNCA mais toca
    nessa linha — fica sinalizada como pendente pra sempre, mesmo depois de
    lançada aqui manualmente. Isso marca 'sim' + data nas linhas correspondentes
    (por Registro TSE + Cargo). Silencioso por design: se a planilha não
    estiver configurada ou a linha não for encontrada, não interrompe o
    salvamento da pesquisa — só devolve avisos pra exibir.

    Retorna (quantidade de linhas atualizadas, lista de avisos).
    """
    avisos: list[str] = []
    if not SPREADSHEET_ID_RELATORIOS or df_p is None or df_p.empty:
        return 0, avisos

    pares = {
        (normalizar_texto_simples(r.get("registro_tse")).upper(),
         normalizar_texto_simples(r.get("cargo")).lower())
        for _, r in df_p.iterrows()
        if normalizar_texto_simples(r.get("registro_tse"))
    }
    if not pares:
        return 0, avisos

    try:
        sh = gc.open_by_key(SPREADSHEET_ID_RELATORIOS)
        ws = sh.worksheet("relatorios")
        valores = ws.get_all_values()
    except Exception as exc:
        avisos.append(f"não consegui abrir a fila de relatórios: {exc}")
        return 0, avisos
    if len(valores) < 2:
        return 0, avisos

    header = valores[0]
    try:
        i_registro = header.index("Registro TSE")
        i_cargo = header.index("Cargo")
        i_flag = header.index("Topline extraída?")
        i_data = header.index("Data da extração de topline")
        i_erro = header.index("Erro na extração de topline")
    except ValueError as exc:
        avisos.append(f"fila de relatórios sem a coluna esperada ({exc})")
        return 0, avisos

    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    updates = []
    encontrados = set()
    for row_i, row in enumerate(valores[1:], start=2):
        registro = normalizar_texto_simples(row[i_registro] if i_registro < len(row) else "").upper()
        cargo = normalizar_texto_simples(row[i_cargo] if i_cargo < len(row) else "").lower()
        if (registro, cargo) not in pares:
            continue
        encontrados.add((registro, cargo))
        updates.extend([
            gspread.Cell(row_i, i_flag + 1, "sim"),
            gspread.Cell(row_i, i_data + 1, agora),
            gspread.Cell(row_i, i_erro + 1, ""),
        ])

    if updates:
        ws.update_cells(updates, value_input_option="USER_ENTERED")

    for registro, cargo in (pares - encontrados):
        avisos.append(f"não achei linha na fila de relatórios pra {registro} ({cargo})")

    return len(encontrados), avisos


def montar_log_resultados_manual(df_r: pd.DataFrame, username: str, nome_usuario: str) -> pd.DataFrame:
    if df_r is None or df_r.empty:
        return pd.DataFrame()

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    batch_id = f"manual-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    df_log = df_r.copy()
    df_log["manual_batch_id"] = batch_id
    df_log["manual_usuario"] = normalizar_texto_simples(username)
    df_log["manual_nome"] = normalizar_texto_simples(nome_usuario)
    df_log["manual_salvo_em"] = agora
    df_log["manual_origem"] = "streamlit"
    return df_log


def buscar_duplicatas_polling_manual(gc, spreadsheet_id: str, df_p: pd.DataFrame) -> pd.DataFrame:
    if df_p is None or df_p.empty:
        return pd.DataFrame()

    sh = gc.open_by_key(spreadsheet_id)
    aba_pesquisas = garantir_aba(sh, "pesquisas", rows=50000, cols=35)
    df_existente = carregar_df_da_aba(aba_pesquisas)
    if df_existente.empty:
        return pd.DataFrame()

    df_novo = df_p.copy()
    for df in [df_novo, df_existente]:
        for col in ["scenario_id", "poll_id", "ano", "uf", "cargo", "turno", "instituto", "registro_tse", "data_campo"]:
            if col not in df.columns:
                df[col] = ""

        df["_chave_registro"] = df.apply(
            lambda row: gerar_chave_polling_registro(
                row.get("uf", ""),
                row.get("cargo", ""),
                row.get("turno", ""),
                row.get("registro_tse", ""),
            ),
            axis=1,
        )
        df["_chave_fallback"] = df.apply(
            lambda row: gerar_chave_polling_fallback(
                row.get("ano", ""),
                row.get("uf", ""),
                row.get("cargo", ""),
                row.get("turno", ""),
                row.get("instituto", ""),
                row.get("data_campo", ""),
            ),
            axis=1,
        )

    chaves_novas = {
        "scenario_id": set(df_novo["scenario_id"].astype(str).str.strip()) - {""},
        "poll_id": set(df_novo["poll_id"].astype(str).str.strip()) - {""},
        "registro": set(df_novo["_chave_registro"].astype(str).str.strip()) - {""},
        "fallback": set(df_novo["_chave_fallback"].astype(str).str.strip()) - {""},
    }

    registros_validos_novos = any(registro_tse_valido(v) for v in df_novo["registro_tse"].tolist())
    matches = []
    for _, row in df_existente.iterrows():
        motivos = []
        if normalizar_texto_simples(row.get("scenario_id")) in chaves_novas["scenario_id"]:
            motivos.append("mesmo cenário")
        if normalizar_texto_simples(row.get("poll_id")) in chaves_novas["poll_id"]:
            motivos.append("mesmo poll_id")
        if normalizar_texto_simples(row.get("_chave_registro")) in chaves_novas["registro"]:
            motivos.append("mesmo registro TSE")
        if normalizar_texto_simples(row.get("_chave_fallback")) in chaves_novas["fallback"]:
            motivo_fallback = "mesmo instituto, data e escopo"
            if registros_validos_novos and not registro_tse_valido(row.get("registro_tse", "")):
                motivo_fallback += " (existente sem registro)"
            motivos.append(motivo_fallback)

        if motivos:
            matches.append({
                "motivo": "; ".join(dict.fromkeys(motivos)),
                "scenario_id": row.get("scenario_id", ""),
                "poll_id": row.get("poll_id", ""),
                "uf": row.get("uf", ""),
                "cargo": row.get("cargo", ""),
                "turno": row.get("turno", ""),
                "instituto": row.get("instituto", ""),
                "registro_tse": row.get("registro_tse", ""),
                "data_campo": row.get("data_campo", ""),
                "fonte_url": row.get("fonte_url", ""),
                "origem": row.get("origem", ""),
            })

    if not matches:
        return pd.DataFrame()

    return pd.DataFrame(matches).drop_duplicates().reset_index(drop=True)


def render_editor_cenarios_polling(cenarios: list[dict], turno: str) -> list[dict]:
    cenarios_editados = []

    for idx, cenario in enumerate(cenarios, start=1):
        turno_salvo = normalizar_texto_simples(cenario.get("turno")).lower()
        if turno_salvo not in POLLING_MANUAL_TURNOS:
            turno_salvo = turno

        col_titulo, col_turno = st.columns([0.8, 0.2])
        with col_titulo:
            st.markdown(f"##### Cenário {idx}")
        with col_turno:
            turno_cenario = st.selectbox(
                "Turno deste cenário",
                POLLING_MANUAL_TURNOS,
                index=POLLING_MANUAL_TURNOS.index(turno_salvo),
                key=f"polling_scenario_turno_{idx}",
                label_visibility="collapsed",
            )
        if turno_cenario != turno:
            st.caption(
                f"⚠️ Este cenário está marcado como {turno_cenario}, diferente do turno "
                f"principal da pesquisa ({turno}) — material com T1 e T2 juntos. Vai pra "
                f"planilha de {turno_cenario.upper()} ao salvar."
            )

        if turno_cenario == "t1":
            scenario_label = st.text_input(
                "Rótulo do cenário (T1)",
                value=cenario.get("scenario_label", str(idx)),
                key=f"polling_scenario_label_{idx}",
            )
        else:
            # No T2, a chave gravada é a disputa normalizada pelos dois
            # candidatos, e não um rótulo digitado.
            scenario_label = f"Segundo turno — cenário {idx}"

        df_itens = pd.DataFrame(cenario.get("itens") or [])
        if df_itens.empty:
            df_itens = pd.DataFrame([{"candidato": "", "partido": "", "percentual": None, "tipo": "candidato"}])

        for coluna in ["candidato", "partido", "percentual", "tipo"]:
            if coluna not in df_itens.columns:
                df_itens[coluna] = None if coluna == "percentual" else ""

        editado = st.data_editor(
            df_itens[["candidato", "partido", "percentual", "tipo"]],
            key=f"polling_editor_{idx}",
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            column_config={
                "candidato": st.column_config.TextColumn("Candidato / opção"),
                "partido": st.column_config.TextColumn("Partido"),
                "percentual": st.column_config.NumberColumn("Percentual", min_value=0.0, max_value=100.0, step=0.1),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=POLLING_MANUAL_TIPOS_RESULTADO),
            },
        )

        itens = []
        for _, row in editado.iterrows():
            candidato = normalizar_texto_simples(row.get("candidato"))
            percentual = normalizar_percentual_simples(row.get("percentual"))
            if not candidato and percentual is None:
                continue
            itens.append({
                "candidato": candidato,
                "partido": normalizar_partido(row.get("partido")),
                "percentual": percentual,
                "tipo": classificar_tipo_resultado_manual(candidato, row.get("tipo")),
            })

        cenarios_editados.append({
            "scenario_label": normalizar_texto_simples(scenario_label) or str(idx),
            "turno": turno_cenario,
            "itens": itens,
        })

    return cenarios_editados


for k, v in [
    ("polling_manual_texto_fonte", ""),
    ("polling_manual_payload", None),
    ("polling_manual_resultado", None),
    ("polling_manual_duplicatas", None),
    ("polling_pdf_preview_png", None),
    ("polling_pdf_resumo", ""),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# A troca de pesquisa precisa começar com controles limpos. Esta seção roda
# antes de qualquer widget, pois o Streamlit não permite alterar o estado de
# um widget depois de ele ter sido criado na execução atual.
if st.session_state.pop("polling_reiniciar_controles_apos_extracao", False):
    for chave in [
        "polling_foco_cargo",
        "polling_foco_uf",
        "polling_foco_turno",
        "polling_foco_instituto",
        "polling_foco_instrucoes",
        "polling_pdf_uploader",
        "polling_modo_pdf",
        "polling_pag_ini",
        "polling_pag_fim",
    ]:
        st.session_state.pop(chave, None)

if "polling_manual_url_pendente" in st.session_state:
    st.session_state["polling_manual_url_original"] = st.session_state.pop(
        "polling_manual_url_pendente"
    )

# O campo principal já pode ter sido criado quando o botão de PDF é acionado.
# Por isso, a extração fica pendente e só é copiada para o widget nesta nova
# execução, antes de qualquer widget ser montado.
if "polling_manual_texto_pendente" in st.session_state:
    st.session_state["polling_manual_texto_fonte"] = st.session_state.pop(
        "polling_manual_texto_pendente"
    )
    st.session_state["polling_pdf_flash"] = (
        "Texto do PDF carregado no campo principal. "
        f"{st.session_state.get('polling_pdf_resumo', '')}"
    ).strip()


# ── sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    try:
        st.image(LOGO_PATH, use_container_width=True)
    except Exception:
        st.caption("Logo não encontrada.")
    st.markdown(
        '<div style="border-left:3px solid #962E4D;padding:10px 12px;'
        'margin:10px 0 0 0;background:#fff;border-radius:0 4px 4px 0;">'
        '<p style="font-family:Montserrat,sans-serif;font-size:12.5px;'
        'color:#111;line-height:1.65;margin:0;">'
        'Cadastre pesquisas antigas ou recentes que ainda não entraram no '
        '<strong>PollingData</strong>.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    if not MATRIZ_T1_SPREADSHEET_ID.strip() or not MATRIZ_T2_SPREADSHEET_ID.strip():
        faltantes = []
        if not MATRIZ_T1_SPREADSHEET_ID.strip():
            faltantes.append("T1")
        if not MATRIZ_T2_SPREADSHEET_ID.strip():
            faltantes.append("T2")
        st.warning(f"Matriz(es) sem ID configurado: {', '.join(faltantes)}.")
    st.markdown("---")
    if st.button("↻ Recarregar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** ({st.session_state.get('username', '')})")
    if _auth_cfg:
        authenticator.logout("Sair", "sidebar")


st.markdown(
    '<div class="ge-hero"><div class="ge-hero-title">Polling Manual</div></div>',
    unsafe_allow_html=True,
)

mensagem_identificacao = st.session_state.pop("polling_manual_flash", "")
if mensagem_identificacao:
    st.success(mensagem_identificacao)

mensagem_pdf = st.session_state.pop("polling_pdf_flash", "")
if mensagem_pdf:
    st.success(mensagem_pdf)

if not MATRIZ_T1_SPREADSHEET_ID.strip() or not MATRIZ_T2_SPREADSHEET_ID.strip():
    st.warning("Configure os IDs das matrizes T1 e T2 para habilitar todos os destinos.")

col1, col2 = st.columns([1.25, 1])

with col1:
    st.text_area(
        "Texto completo da notícia / PDF OCR",
        key="polling_manual_texto_fonte",
        height=300,
        placeholder="Cole aqui o texto completo da pesquisa.",
    )

with col2:
    url_original = st.text_input("URL original (opcional)", key="polling_manual_url_original")

    with st.expander("Extrair texto de PDF", expanded=False):
        pdf_file = st.file_uploader("Upload do PDF da pesquisa", type=["pdf"], key="polling_pdf_uploader")
        if pdf_file is not None:
            pdf_bytes = pdf_file.getvalue()
            with fitz.open(stream=pdf_bytes, filetype="pdf") as d:
                total_pages = d.page_count

            modo_pdf = st.selectbox("Modo de leitura do PDF", LEITURA_PDF, key="polling_modo_pdf")
            pagina_ini = int(st.number_input("Pág. inicial", min_value=1, max_value=total_pages, value=1, key="polling_pag_ini"))
            pagina_fim = int(
                st.number_input("Pág. final", min_value=1, max_value=total_pages, value=total_pages, key="polling_pag_fim")
            )
            if pagina_fim < pagina_ini:
                pagina_fim = pagina_ini

            if st.button("Ler PDF para texto bruto", use_container_width=True):
                qtd_paginas = pagina_fim - pagina_ini + 1
                try:
                    with st.status(
                        f"Preparando leitura de {qtd_paginas} página(s)…",
                        expanded=True,
                    ) as status_leitura:
                        etapas_exibidas = set()

                        def atualizar_etapa(mensagem: str):
                            status_leitura.update(label=mensagem, state="running")
                            if mensagem not in etapas_exibidas:
                                status_leitura.write(mensagem)
                                etapas_exibidas.add(mensagem)

                        texto_pdf, resumo_pdf = processar_pdf_polling_manual(
                            pdf_bytes=pdf_bytes,
                            modo=modo_pdf,
                            page_indices=list(range(pagina_ini - 1, pagina_fim)),
                            atualizar_etapa=atualizar_etapa,
                        )
                        status_leitura.update(label="Leitura concluída.", state="complete", expanded=False)
                    # Não altere polling_manual_texto_fonte aqui: ele já foi criado
                    # como widget nesta execução. A cópia ocorre antes dos widgets no rerun.
                    st.session_state["polling_manual_texto_pendente"] = texto_pdf
                    st.session_state["polling_pdf_resumo"] = resumo_pdf
                    st.rerun()
                except Exception:
                    st.error(
                        "Não foi possível concluir a leitura do PDF. "
                        "Tente reduzir o intervalo de páginas ou trocar o modo de leitura."
                    )

            if st.session_state.get("polling_pdf_preview_png"):
                st.image(
                    st.session_state["polling_pdf_preview_png"],
                    caption="Prévia da primeira página renderizada",
                    use_container_width=True,
                )

    with st.expander("Refinar extração (opcional)", expanded=False):
        st.caption(
            "Use quando o material tem várias pesquisas e você quer só uma fatia "
            "(ex.: pegar só presidente na BA, ignorando outros estados)."
        )
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            foco_cargo = st.selectbox(
                "Cargo-alvo",
                ["(auto-detectar)"] + POLLING_MANUAL_CARGOS,
                key="polling_foco_cargo",
            )
        with f2:
            foco_uf = st.selectbox(
                "UF-alvo",
                ["(auto-detectar)", "BR"] + UFS,
                key="polling_foco_uf",
            )
        with f3:
            foco_turno = st.selectbox(
                "Turno-alvo",
                ["(auto-detectar)"] + POLLING_MANUAL_TURNOS,
                key="polling_foco_turno",
            )
        with f4:
            foco_instituto = st.text_input(
                "Instituto-alvo",
                key="polling_foco_instituto",
                placeholder="Ex.: Quaest",
            )
        foco_instrucoes = st.text_area(
            "Instruções adicionais",
            key="polling_foco_instrucoes",
            height=70,
            placeholder='Ex.: "Pegar só o cenário sem o Ratinho Junior" ou "Usar o segundo bloco da página 3".',
        )

    if st.button("Identificar pesquisa com Gemini", use_container_width=True):
        texto_fonte = st.session_state.get("polling_manual_texto_fonte", "")
        if not normalizar_texto_simples(texto_fonte):
            st.error("Cole o texto completo ou extraia o PDF antes de identificar a pesquisa.")
        else:
            # Se o texto mudou e o campo de URL ainda é exatamente o da última
            # pesquisa, ele é resíduo de tela — não pode acompanhar a nova.
            texto_atual = normalizar_texto_simples(texto_fonte)
            texto_anterior = st.session_state.get("polling_manual_ultimo_texto", "")
            url_anterior = st.session_state.get("polling_manual_ultima_url", "")
            url_para_extracao = normalizar_texto_simples(url_original)
            if texto_atual != texto_anterior and url_para_extracao and url_para_extracao == url_anterior:
                url_para_extracao = ""

            escopo = {
                "cargo": "" if foco_cargo == "(auto-detectar)" else foco_cargo,
                "uf": "" if foco_uf == "(auto-detectar)" else foco_uf,
                "turno": "" if foco_turno == "(auto-detectar)" else foco_turno,
                "instituto": foco_instituto,
                "instrucoes": foco_instrucoes,
            }
            tem_foco = any(v for v in escopo.values())

            with st.spinner("Lendo o conteúdo e estruturando a pesquisa..."):
                try:
                    payload = extrair_dados_polling_gemini(
                        texto_fonte,
                        url_original=url_para_extracao,
                        escopo=escopo,
                    )
                except RuntimeError as exc:
                    st.error(f"Não consegui identificar a pesquisa: {exc}")
                    st.info("Tente novamente em alguns segundos ou ajuste o texto e refaça.")
                else:
                    payload["fonte_url_original"] = (
                        url_para_extracao or payload.get("fonte_url_original", "")
                    )

                    # Detecta caso "filtro definido mas Gemini não achou nada"
                    cenarios_vazios = not any(
                        (c.get("itens") or []) for c in (payload.get("cenarios") or [])
                    )
                    if tem_foco and cenarios_vazios:
                        st.error(
                            "⚠️ O Gemini não encontrou no material um bloco que case com "
                            "os filtros que você definiu. Veja as pendências abaixo, "
                            "ajuste o foco ou cole outro material."
                        )
                        for pend in payload.get("pendencias") or []:
                            st.warning(pend)
                    else:
                        carregar_payload_polling_no_state(payload)
                        st.session_state["polling_manual_ultimo_texto"] = texto_atual
                        st.session_state["polling_manual_ultima_url"] = payload["fonte_url_original"]
                        st.session_state["polling_manual_url_pendente"] = payload["fonte_url_original"]
                        st.session_state["polling_reiniciar_controles_apos_extracao"] = True
                        st.session_state["polling_manual_flash"] = (
                            "Pesquisa identificada. Revise os campos abaixo antes de salvar."
                        )
                        st.rerun()

payload = st.session_state.get("polling_manual_payload")
if payload:
    payload = normalizar_payload_polling(payload)

    st.markdown("#### Dados extraídos")
    meta1, meta2, meta3 = st.columns(3)
    with meta1:
        cargo = st.selectbox(
            "Cargo",
            POLLING_MANUAL_CARGOS,
            key="polling_meta_cargo",
        )

        # T1 e T2 são a fonte canônica dos institutos. O seletor aceita um
        # texto novo, mas confere por uma chave insensível a caixa e acentos.
        catalogo_institutos, origem_catalogo_institutos = carregar_catalogo_institutos_matrizes(
            VERSAO_CATALOGO_INSTITUTOS
        )
        st.session_state["polling_catalogo_institutos"] = catalogo_institutos
        institutos_conhecidos = sorted(
            {entrada["instituto"] for entrada in catalogo_institutos.values()},
            key=str.casefold,
        )
        sugerido = normalizar_texto_simples(payload.get("instituto", ""))
        entrada_sugerida = catalogo_institutos.get(chave_instituto_catalogo(sugerido))
        if entrada_sugerida:
            sugerido = entrada_sugerida["instituto"]
        valor_widget_instituto = normalizar_texto_simples(
            st.session_state.get("polling_meta_instituto", "")
        )
        entrada_widget = catalogo_institutos.get(
            chave_instituto_catalogo(valor_widget_instituto)
        )
        if (
            entrada_widget
            and valor_widget_instituto != entrada_widget["instituto"]
        ):
            # O widget ainda não foi criado nesta execução; é seguro alinhar
            # a grafia exibida ao valor canônico da matriz.
            st.session_state["polling_meta_instituto"] = entrada_widget["instituto"]
        opcoes_inst = [""] + institutos_conhecidos
        if sugerido and sugerido not in opcoes_inst:
            opcoes_inst.append(sugerido)
        instituto = st.selectbox(
            "Instituto",
            opcoes_inst,
            index=None,
            key="polling_meta_instituto",
            placeholder="Selecione ou digite o instituto",
            accept_new_options=True,
            on_change=aplicar_grafia_canonica_do_instituto,
        )
        entrada_instituto = catalogo_institutos.get(chave_instituto_catalogo(instituto))
        instituto_canonico = (
            entrada_instituto["instituto"]
            if entrada_instituto
            else normalizar_instituto(instituto or "")
        )
        classificacao_canonica = (
            entrada_instituto.get("classificacao", "") if entrada_instituto else ""
        )
        if instituto_canonico and not entrada_instituto:
            sugestoes_chave = get_close_matches(
                chave_instituto_catalogo(instituto_canonico),
                list(catalogo_institutos),
                n=3,
                cutoff=0.62,
            )
            sugestoes = [catalogo_institutos[chave]["instituto"] for chave in sugestoes_chave]
            st.caption(
                "Confira a grafia: este nome não está no catálogo canônico de T1 e T2."
            )
            if sugestoes:
                st.caption("Possíveis correspondências nas matrizes: " + ", ".join(sugestoes) + ".")
        elif origem_catalogo_institutos != "T1 e T2":
            st.caption("Catálogo de T1/T2 indisponível no momento; usando o dicionário local temporariamente.")

        amostra = st.number_input("Amostra", min_value=0, step=1, key="polling_meta_amostra")
    with meta2:
        turno = st.selectbox(
            "Turno",
            POLLING_MANUAL_TURNOS,
            key="polling_meta_turno",
        )
        registro_tse = st.text_input("Registro TSE", key="polling_meta_registro")
        margem_erro = st.number_input(
            "Margem de erro (%)",
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            key="polling_meta_margem",
        )
    with meta3:
        uf = st.selectbox(
            "UF",
            ["BR"] + UFS,
            key="polling_meta_uf",
        )
        data_campo = st.text_input("Data do campo (YYYY-MM-DD)", key="polling_meta_data")
        confianca = st.text_input(
            "Confiança (%)",
            key="polling_meta_confianca",
            placeholder="Ex.: 95",
        )

    modo_extraido = normalizar_texto_simples(payload.get("modo"))
    opcoes_modo = MODOS_COLETA + [OUTRO_MODO_COLETA]
    if modo_extraido in MODOS_COLETA:
        indice_modo = opcoes_modo.index(modo_extraido)
    elif modo_extraido:
        indice_modo = opcoes_modo.index(OUTRO_MODO_COLETA)
    else:
        indice_modo = 0
    modo_escolhido = st.selectbox(
        "Modo de coleta",
        opcoes_modo,
        index=indice_modo,
        key="polling_meta_modo_sel",
    )
    if modo_escolhido == OUTRO_MODO_COLETA:
        modo_pesquisa = st.text_input(
            "Outro modo de coleta",
            key="polling_meta_modo",
            placeholder="Ex.: WhatsApp, presencial e online…",
        )
    else:
        modo_pesquisa = modo_escolhido

    if "polling_meta_observacoes" not in st.session_state:
        st.session_state["polling_meta_observacoes"] = payload.get("observacoes", "")
    observacoes = st.text_area(
        "Observações da extração",
        key="polling_meta_observacoes",
        height=90,
    )

    for pendencia in payload.get("pendencias") or []:
        st.warning(pendencia)

    st.markdown("#### Cenários e candidatos")
    if st.button("Adicionar cenário em branco"):
        payload_atual = normalizar_payload_polling(st.session_state.get("polling_manual_payload") or payload)
        payload_atual["cenarios"].append({
            "scenario_label": str(len(payload_atual["cenarios"]) + 1),
            "turno": turno,
            "itens": [],
        })
        st.session_state["polling_manual_payload"] = payload_atual
        st.rerun()

    cenarios_fonte = normalizar_payload_polling(st.session_state.get("polling_manual_payload") or payload)["cenarios"]
    cenarios_editados = render_editor_cenarios_polling(cenarios_fonte, turno)

    st.markdown("#### Salvar")
    duplicatas_alerta = st.session_state.get("polling_manual_duplicatas")
    forcar_salvar = False
    if isinstance(duplicatas_alerta, pd.DataFrame) and not duplicatas_alerta.empty:
        st.warning(
            "Encontrei pesquisa(s) parecida(s) já salvas. Revise antes de gravar para evitar duplicidade."
        )
        st.dataframe(
            duplicatas_alerta[
                [
                    "motivo",
                    "uf",
                    "cargo",
                    "turno",
                    "instituto",
                    "registro_tse",
                    "data_campo",
                    "poll_id",
                    "fonte_url",
                    "origem",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
        col_cancelar, col_forcar = st.columns(2)
        with col_cancelar:
            if st.button("Cancelar e revisar", use_container_width=True, key="polling_dup_cancelar"):
                st.session_state["polling_manual_duplicatas"] = None
                st.rerun()
        with col_forcar:
            forcar_salvar = st.button(
                "Salvar mesmo assim",
                use_container_width=True,
                key="polling_dup_forcar",
                type="primary",
                help="Use só se conferiu que não é a mesma pesquisa.",
            )

    salvar_clicado = st.button("Salvar pesquisa na planilha", use_container_width=True, key="polling_salvar")
    if salvar_clicado or forcar_salvar:
        erros = []
        if not normalizar_texto_simples(instituto):
            erros.append("Preencha o instituto.")
        if not normalizar_texto_simples(data_campo):
            erros.append("Preencha a data do campo.")
        confianca_normalizada = normalizar_inteiro_simples(confianca)
        if normalizar_texto_simples(confianca) and (
            confianca_normalizada is None or not 1 <= confianca_normalizada <= 100
        ):
            erros.append("Confiança deve ser um percentual inteiro entre 1 e 100 ou ficar em branco.")
        data_campo_normalizada = normalizar_data_campo_segura(normalizar_texto_simples(data_campo))
        if data_campo_normalizada.startswith("2026") and not registro_tse_valido(registro_tse):
            erros.append("Registro TSE é obrigatório para pesquisas de 2026.")
        if sum(len(cenario.get("itens") or []) for cenario in cenarios_editados) == 0:
            erros.append("Inclua pelo menos um resultado em algum cenário.")

        if erros:
            for erro in erros:
                st.error(erro)
        else:
            gc = get_polling_sheets_client()
            fonte_url_original_atual = normalizar_texto_simples(payload.get("fonte_url_original"))
            if not gc:
                st.error("Credenciais do Google Sheets não encontradas.")
            else:
                payload_final = {
                    "cargo": cargo,
                    "turno": turno,
                    "uf": uf,
                    "instituto": instituto_canonico,
                    "registro_tse": registro_tse,
                    "data_campo": data_campo,
                    "amostra": amostra or None,
                    "margem_erro": margem_erro or None,
                    "confianca": confianca_normalizada,
                    "modo": modo_pesquisa,
                    "metodologia": "",
                    "fonte_url_original": fonte_url_original_atual,
                    "observacoes": observacoes,
                    "cenarios": cenarios_editados,
                }
                df_p, df_r = montar_dataframes_polling_manual(
                    payload=payload_final,
                    fonte_url="",
                    fonte_url_original=fonte_url_original_atual,
                    classificacao_canonica=classificacao_canonica,
                )

                # Um material pode trazer T1 e T2 juntos (cenário com turno próprio,
                # ver montar_dataframes_polling_manual) — cada turno vai pra uma
                # planilha diferente, então agrupa e salva um destino por vez.
                turnos_presentes = sorted(df_p["turno"].dropna().unique().tolist()) if not df_p.empty else []
                grupos = []
                destino_invalido = False
                for turno_grupo in turnos_presentes:
                    spreadsheet_destino, nome_destino = planilha_destino_polling(turno_grupo)
                    if not spreadsheet_destino:
                        st.error(f"Falta configurar o ID da {nome_destino} (necessário pro cenário de {turno_grupo}).")
                        destino_invalido = True
                        continue
                    grupos.append((
                        turno_grupo, spreadsheet_destino, nome_destino,
                        df_p[df_p["turno"] == turno_grupo].reset_index(drop=True),
                        df_r[df_r["turno"] == turno_grupo].reset_index(drop=True) if not df_r.empty else df_r,
                    ))

                if destino_invalido:
                    pass  # erro(s) já exibido(s) acima; não salva nada até configurar
                elif not grupos:
                    st.error("Nenhum cenário válido para salvar.")
                else:
                    with st.spinner("Conferindo possíveis duplicatas na planilha..."):
                        duplicatas_por_grupo = []
                        try:
                            for turno_grupo, spreadsheet_destino, _, df_p_g, _ in grupos:
                                dup = buscar_duplicatas_polling_manual(gc, spreadsheet_destino, df_p_g)
                                if not dup.empty:
                                    duplicatas_por_grupo.append(dup)
                        except Exception as exc:
                            st.error(f"Não foi possível conferir duplicatas antes de salvar: {exc}")
                            st.stop()

                    if duplicatas_por_grupo and not forcar_salvar:
                        st.session_state["polling_manual_duplicatas"] = pd.concat(
                            duplicatas_por_grupo, ignore_index=True)
                        st.error(
                            "Possível duplicata encontrada. Revise o alerta acima e use "
                            "“Salvar mesmo assim” se quiser gravar as duas entradas."
                        )
                        st.rerun()

                    with st.spinner("Salvando na planilha e atualizando o BI..."):
                        total_pesquisas = total_resultados = total_log = total_fila = 0
                        avisos_fila_total: list[str] = []
                        destinos_salvos: list[str] = []
                        for turno_grupo, spreadsheet_destino, nome_destino, df_p_g, df_r_g in grupos:
                            df_r_log = montar_log_resultados_manual(df_r_g, username=username, nome_usuario=name)
                            linhas_log = append_log_resultados_manual(gc, spreadsheet_destino, df_r_log)
                            salvar_tudo(gc, spreadsheet_destino, df_p_g, df_r_g)
                            linhas_fila, avisos_fila = marcar_topline_extraida_manual(gc, df_p_g)
                            total_pesquisas += len(df_p_g)
                            total_resultados += len(df_r_g)
                            total_log += linhas_log
                            total_fila += linhas_fila
                            avisos_fila_total.extend(avisos_fila)
                            destinos_salvos.append(f"{nome_destino} ({len(df_p_g)} cenário(s))")

                        st.session_state["polling_manual_payload"] = payload_final
                        st.session_state["polling_manual_duplicatas"] = None
                        st.session_state["polling_manual_resultado"] = {
                            "pesquisas": total_pesquisas,
                            "resultados": total_resultados,
                            "resultados_manual": total_log,
                            "destino": " + ".join(destinos_salvos),
                            "linhas_fila": total_fila,
                            "avisos_fila": avisos_fila_total,
                        }
                        st.success(
                            f"Pesquisa salva com sucesso em {' e '.join(destinos_salvos)}. "
                            f"{total_pesquisas} cenário(s), {total_resultados} resultado(s) "
                            f"e {total_log} linha(s) no histórico `resultados_manual`."
                        )
                        if total_fila:
                            st.caption(f"Também marquei {total_fila} linha(s) como concluída na fila de relatórios.")
                        for aviso in avisos_fila_total:
                            st.caption(f"⚠️ Fila de relatórios: {aviso}")
                    if linhas_fila:
                        st.caption(f"Também marquei {linhas_fila} linha(s) como concluída na fila de relatórios.")
                    for aviso in avisos_fila:
                        st.caption(f"⚠️ Fila de relatórios: {aviso}")

resultado = st.session_state.get("polling_manual_resultado")
if resultado:
    st.info(
        f"Último salvamento ({resultado.get('destino', 'matriz')}): {resultado['pesquisas']} linha(s) em `pesquisas` e "
        f"{resultado['resultados']} linha(s) em `resultados` e "
        f"{resultado.get('resultados_manual', 0)} linha(s) em `resultados_manual`."
    )
