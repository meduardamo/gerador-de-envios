"""
Gerador de Gráficos: uma tabela entra e sai peça na identidade da casa (linha,
barras, barras empilhadas ou tabela), em PNG e SVG, com e sem logo.

A página tem dois passos e a ordem deles é a ordem de quem usa: 1. Dados,
2. Peça. Em cada passo o que todo mundo mexe fica à vista (dados, tipo, título)
e o ajuste fino fica recolhido. A prévia acompanha a rolagem.

Divisão de trabalho:
- O Gemini só lê tabela de PDF, imagem ou texto (gerador_graficos_extracao) e
  o que ele lê cai no editor para conferência. Não calcula nem desenha.
- O tipo sugerido vem de regra (gerador_graficos_core.sugerir_tipo).
- O desenho mora em gerador_graficos_core, que segue o gráfico do Alerta de
  Pesquisa.

Esta página não grava nada em planilha nenhuma.
"""

import inspect
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from graficos_pesquisa_core import ESCALAS_EXPORT, montserrat_disponivel
from gerador_graficos_core import (
    IDENTIDADES,
    MAX_SERIES,
    ROTULOS,
    TAMANHOS,
    TIPOS,
    UNIDADES,
    gerar_peca,
    serie_percentual,
    series_da_tabela,
    slug_arquivo,
    sugerir_tipo,
)
from gerador_graficos_extracao import (
    MAX_PAGINAS,
    extrair_de_pdf,
    extrair_tabela,
    numeros_fora_da_fonte,
)
from polling_extracao_core import definir_api_key

st.set_page_config(page_title="Gerador de Gráficos", layout="wide")

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
/* A prévia acompanha a rolagem enquanto a pessoa mexe nos controles. */
[data-testid="stColumn"]:has(.gg-previa) { position: sticky; top: 1rem; align-self: flex-start; }
/* O tema do app não define cor primária, e o vermelho padrão do Streamlit
   briga com a marca. Aqui os controles de destaque usam vinho e marinho. */
[data-testid="stDownloadButton"] > button {
    background: #962E4D !important; border: 1px solid #962E4D !important; color: #fff !important;
    border-radius: 0 !important; font-size: 12px !important; font-weight: 700 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important; padding: 10px 14px !important;
}
[data-testid="stDownloadButton"] > button:hover { background: #7A2640 !important; border-color: #7A2640 !important; }
[data-baseweb="tag"] { background: #192D4E !important; border-radius: 0 !important; }
[data-testid="stButtonGroup"] button[data-variant="segmented_control"] {
    border-radius: 0 !important; padding: 8px 16px !important;
}
[data-testid="stButtonGroup"] button[data-variant="segmented_control"][data-selected="true"] {
    background: #962E4D !important; border-color: #962E4D !important; color: #fff !important;
}
[data-testid="stButtonGroup"] button[data-variant="segmented_control"][data-selected="true"] * { color: #fff !important; }
.gg-passo { font-size: 13px; color: #767672; margin: -8px 0 14px; }
.gg-grupo { font-size: 11px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #192D4E; margin: 18px 0 6px; padding-bottom: 5px; border-bottom: 1px solid #DADAD4; }
.ge-rule { font-size: 17px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: #962E4D; border-top: 2px solid #962E4D; padding-top: 10px; margin: 24px 0 16px; }
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

# O campo branco do login vem daqui, e tem que ser desenhado antes do gate:
# sem ninguém logado o gate chama st.stop() e nada depois dele roda.
from ui_login import CSS_LOGIN
st.markdown(CSS_LOGIN, unsafe_allow_html=True)

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
    st.stop()



# ── configurações ─────────────────────────────────────────────────────────────

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
# Os cores não importam Streamlit: a chave dos Secrets entra por aqui.
definir_api_key(GEMINI_API_KEY)

EXEMPLO = {
    "colunas": ["Ano", "PLOA", "Dotação inicial", "Dotação atual",
                "Empenhado", "Pago"],
    "linhas": [
        ["2023", "225,5", "276,4", "430,6", "430,5", "312,7"],
        ["2024", "445,0", "382,2", "428,4", "428,4", "384,7"],
        ["2025", "369,0", "350,8", "395,8", "395,8", "392,9"],
        ["2026", "333,3", "308,8", "308,8", "262,6*", "262,6*"],
        ["2027", "308,8", "", "", "", ""],
    ],
    "titulo": "Ação 217M: evolução orçamentária",
    "subtitulo": "Criança Feliz, 2023 a 2027, em R$ milhões",
    "rodape": "* Execução de 2026 considerada até 14 de setembro de 2026.",
    "unidade": "R$ milhões",
}

FONTES = {
    "colar": ":material/content_paste: Colar ou digitar",
    "ia": ":material/auto_awesome: Ler de PDF, imagem ou texto",
    "arquivo": ":material/upload_file: Planilha (.xlsx ou .csv)",
}

ICONES_TIPO = {
    "linha": ":material/show_chart:",
    "barras": ":material/bar_chart:",
    "empilhadas": ":material/stacked_bar_chart:",
    "tabela": ":material/table:",
}

MIMES_IMAGEM = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp"}

# O que descreve de onde veio a tabela atual. Some quando a tabela é trocada.
CHAVES_ORIGEM = ("gg_origem", "gg_fora", "gg_fonte_imgs", "gg_fonte_com_texto")


def _definir_base(df: pd.DataFrame) -> None:
    """Troca a tabela inteira. A versão entra na chave do editor: sem isso o
    Streamlit reaplicaria na tabela nova as edições feitas na anterior.

    Tabela nova também recoloca o tipo no ponto de partida sugerido para ela,
    porque o tipo escolhido para a tabela anterior não diz nada sobre esta.
    """
    df = df.fillna("").astype(str)
    st.session_state["gg_base"] = df
    st.session_state["gg_atual"] = df
    st.session_state["gg_v"] = st.session_state.get("gg_v", 0) + 1
    st.session_state["gg_colunas"] = ", ".join(df.columns)
    tipo, orientacao, _ = sugerir_tipo(df.iloc[:, 0].tolist(), df.shape[1] - 1)
    st.session_state["gg_tipo"] = tipo
    st.session_state["gg_orientacao"] = orientacao
    for chave in ("gg_erro",) + CHAVES_ORIGEM:
        st.session_state.pop(chave, None)


def _definir_textos(titulo="", subtitulo="", rodape="", unidade="Número") -> None:
    st.session_state["gg_titulo"] = titulo
    st.session_state["gg_subtitulo"] = subtitulo
    st.session_state["gg_rodape"] = rodape
    st.session_state["gg_unidade"] = unidade if unidade in UNIDADES else "Número"


def _carregar_exemplo() -> None:
    _definir_base(pd.DataFrame(EXEMPLO["linhas"], columns=EXEMPLO["colunas"]))
    _definir_textos(EXEMPLO["titulo"], EXEMPLO["subtitulo"], EXEMPLO["rodape"],
                    EXEMPLO["unidade"])


def _limpar_tabela() -> None:
    _definir_base(pd.DataFrame([["", "", ""] for _ in range(4)],
                               columns=["Categoria", "Série 1", "Série 2"]))
    _definir_textos()


def _nomes_unicos(nomes: list[str]) -> list[str]:
    """Cabeçalho vazio ou repetido quebraria o editor e a legenda."""
    vistos, saida = set(), []
    for i, nome in enumerate(nomes):
        nome = str(nome).strip() or ("Categoria" if i == 0 else f"Série {i}")
        base, n = nome, 2
        while nome in vistos:
            nome, n = f"{base} ({n})", n + 1
        vistos.add(nome)
        saida.append(nome)
    return saida


def _usar_colado() -> None:
    texto = st.session_state.get("gg_colado") or ""
    linhas = [l for l in texto.splitlines() if l.strip()]
    if len(linhas) < 2:
        st.session_state["gg_erro"] = ("Cole pelo menos duas linhas: o cabeçalho "
                                       "e uma linha de dados.")
        return
    # Sheets, Excel e tabela do Docs colam com tab. Ponto e vírgula cobre CSV
    # brasileiro; dois espaços ou mais, tabela copiada de PDF.
    if any("\t" in l for l in linhas):
        partir = lambda l: l.split("\t")
    elif ";" in linhas[0]:
        partir = lambda l: l.split(";")
    else:
        partir = lambda l: re.split(r"\s{2,}", l.strip())
    tabela = [[c.strip() for c in partir(l)] for l in linhas]
    largura = max(len(l) for l in tabela)
    if largura < 2:
        st.session_state["gg_erro"] = (
            "Não achei colunas no texto colado. Copie as células direto da "
            "planilha, ou use Ler de PDF, imagem ou texto.")
        return
    tabela = [l + [""] * (largura - len(l)) for l in tabela]
    _definir_base(pd.DataFrame(tabela[1:], columns=_nomes_unicos(tabela[0])))


def _celula_texto(valor) -> str:
    """Número de planilha vira texto em formato brasileiro, que é o que o
    leitor de números espera: 308.8 -> '308,8'."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        return str(int(valor)) if valor.is_integer() else f"{valor:.10g}".replace(".", ",")
    return str(valor).strip()


def _usar_arquivo() -> None:
    arquivo = st.session_state.get("gg_arquivo")
    if arquivo is None:
        st.session_state["gg_erro"] = "Escolha um arquivo antes."
        return
    try:
        if arquivo.name.lower().endswith((".xlsx", ".xlsm")):
            df = pd.read_excel(arquivo, dtype=object)
        else:
            bruto = arquivo.getvalue()
            try:
                texto = bruto.decode("utf-8-sig")
            except UnicodeDecodeError:
                texto = bruto.decode("latin-1")
            df = pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str)
    except Exception as exc:
        st.session_state["gg_erro"] = f"Não consegui ler o arquivo: {exc}"
        return
    if df.shape[1] < 2:
        st.session_state["gg_erro"] = "O arquivo precisa de pelo menos duas colunas."
        return
    df.columns = _nomes_unicos([str(c) for c in df.columns])
    _definir_base(df.apply(lambda coluna: coluna.map(_celula_texto)))


def _aplicar_colunas() -> None:
    """Renomeia, cria ou tira colunas a partir da lista digitada, sem perder o
    que já foi editado. Mesma quantidade de nomes = renomeação por posição;
    quantidade diferente = casa pelo nome, e coluna nova entra vazia."""
    nomes = _nomes_unicos([n for n in (st.session_state.get("gg_colunas") or "").split(",")
                           if n.strip()])
    atual = st.session_state.get("gg_atual")
    if len(nomes) < 2 or atual is None:
        st.session_state["gg_erro"] = ("A tabela precisa de pelo menos duas colunas: "
                                       "a categoria e uma série.")
        st.session_state["gg_colunas"] = ", ".join(atual.columns) if atual is not None else ""
        return
    # Mexer em coluna não muda de onde a tabela veio: o aviso de conferência
    # da leitura por Gemini continua valendo.
    origem = {c: st.session_state.get(c) for c in CHAVES_ORIGEM}
    tipo = st.session_state.get("gg_tipo")
    if len(nomes) == len(atual.columns):
        novo = atual.copy()
        novo.columns = nomes
    else:
        novo = pd.DataFrame({n: (atual[n] if n in atual.columns else "") for n in nomes},
                            index=atual.index)
    _definir_base(novo)
    st.session_state["gg_tipo"] = tipo
    for chave, valor in origem.items():
        if valor is not None:
            st.session_state[chave] = valor


def _ler_com_gemini() -> None:
    """Lê a tabela da fonte e joga no editor. Roda no corpo da página, não em
    callback, para o spinner aparecer enquanto o modelo responde."""
    arquivo = st.session_state.get("gg_ia_arquivo")
    texto = (st.session_state.get("gg_ia_texto") or "").strip()
    pedido = st.session_state.get("gg_ia_pedido") or ""
    imagens, texto_fonte = [], texto
    if arquivo is not None:
        dados = arquivo.getvalue()
        extensao = arquivo.name.lower().rsplit(".", 1)[-1]
        if extensao == "pdf":
            tabela, texto_fonte = extrair_de_pdf(
                dados, st.session_state.get("gg_ia_paginas") or "1", pedido)
        else:
            imagens = [(dados, MIMES_IMAGEM.get(extensao, "image/png"))]
            tabela = extrair_tabela(texto=texto, imagens=imagens, pedido=pedido)
    else:
        tabela = extrair_tabela(texto=texto, pedido=pedido)

    _definir_base(pd.DataFrame(tabela["linhas"],
                               columns=_nomes_unicos(tabela["colunas"])))
    _definir_textos(tabela["titulo"], "", tabela["nota"], tabela["unidade"])
    st.session_state["gg_origem"] = "ia"
    st.session_state["gg_fonte_com_texto"] = bool(texto_fonte.strip())
    st.session_state["gg_fora"] = numeros_fora_da_fonte(tabela, texto_fonte)
    st.session_state["gg_fonte_imgs"] = [d for d, _ in imagens]


if "gg_base" not in st.session_state:
    _carregar_exemplo()


@st.cache_data(show_spinner=False, max_entries=6)
def _pacote(assinatura: str) -> bytes:
    """Zip com a mesma peça em quatro arquivos: PNG e SVG, com e sem logo.
    Em cache pela assinatura, como no Alerta de Pesquisa: o download_button
    precisa dos bytes prontos a cada rerun."""
    cfg = json.loads(assinatura)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_saida:
        for sufixo, com_logo in (("com-logo", True), ("sem-logo", False)):
            for formato in ("png", "svg"):
                zip_saida.writestr(
                    cfg["nomes"][f"{sufixo}_{formato}"],
                    gerar_peca(cfg["tipo"], cfg["categorias"], cfg["series"],
                               incluir_logo=com_logo, formato=formato,
                               escala=cfg["escala"], **cfg["opcoes"]))
    return buffer.getvalue()


def _marca_da_logo(identidade: str) -> list:
    """Tamanho e data do arquivo da logo, para a troca da marca invalidar o zip
    em cache sem depender de reiniciar o app."""
    try:
        info = os.stat(IDENTIDADES[identidade]["logo"])
        return [info.st_size, int(info.st_mtime)]
    except OSError:
        return []


# ── página ───────────────────────────────────────────────────────────────────

st.markdown('<div class="ge-hero"><div class="ge-hero-title">Gerador de Gráficos</div></div>',
            unsafe_allow_html=True)

if not montserrat_disponivel():
    st.warning("A fonte Montserrat não foi encontrada em fontes/. A peça vai sair "
               "fora da tipografia da casa.")

# ── 1. dados ─────────────────────────────────────────────────────────────────

st.markdown('<div class="ge-rule">1. Dados</div>'
            '<div class="gg-passo">Traga a tabela por um dos três caminhos. Ela '
            'aparece logo abaixo, onde dá para corrigir qualquer célula.</div>',
            unsafe_allow_html=True)

fonte = st.segmented_control("Como os dados entram", list(FONTES),
                             format_func=FONTES.get, default="colar",
                             key="gg_fonte", label_visibility="collapsed") or "colar"

if fonte == "colar":
    st.text_area("Copie as células no Sheets, Excel ou Docs (com o cabeçalho) e cole aqui",
                 key="gg_colado", height=110,
                 placeholder="Ano\tPLOA\tPago\n2023\t225,5\t312,7\n2024\t445,0\t384,7")
    b1, b2 = st.columns([1, 4])
    b1.button("Usar dados colados", on_click=_usar_colado, use_container_width=True)
    b2.caption("Ou digite direto na tabela abaixo.")
elif fonte == "ia":
    st.caption("O Gemini transcreve a tabela de um PDF, de um print ou de um texto "
               "corrido. Ele só lê: não calcula nem completa célula vazia. Confira "
               "os números na tabela antes de baixar a peça.")
    f1, f2 = st.columns(2)
    with f1:
        arquivo_ia = st.file_uploader("PDF ou imagem",
                                      type=["pdf", "png", "jpg", "jpeg", "webp"],
                                      key="gg_ia_arquivo")
        if arquivo_ia is not None and arquivo_ia.name.lower().endswith(".pdf"):
            st.text_input("Páginas do PDF", "1", key="gg_ia_paginas",
                          help=f"Uma página (3) ou um intervalo (2-4), até "
                               f"{MAX_PAGINAS} páginas.")
    with f2:
        st.text_area("Ou cole o texto da fonte", key="gg_ia_texto", height=110)
        st.text_input("Qual tabela ler (opcional)", key="gg_ia_pedido",
                      placeholder="Ex.: a tabela da Ação 219E")
    tem_fonte = arquivo_ia is not None or bool((st.session_state.get("gg_ia_texto") or "").strip())
    if not GEMINI_API_KEY:
        st.error("GEMINI_API_KEY não configurada nos Secrets: a leitura por "
                 "Gemini está desligada. Os outros dois caminhos funcionam.")
    elif st.button("Ler tabela", disabled=not tem_fonte):
        with st.spinner("Lendo a tabela…"):
            try:
                _ler_com_gemini()
            except Exception as exc:
                st.session_state["gg_erro"] = f"Não consegui ler a tabela: {exc}"
            else:
                st.rerun()
else:
    st.file_uploader("Primeira aba, cabeçalho na primeira linha",
                     type=["xlsx", "xlsm", "csv"], key="gg_arquivo")
    st.button("Usar arquivo", on_click=_usar_arquivo)

if st.session_state.get("gg_erro"):
    st.error(st.session_state["gg_erro"])

if st.session_state.get("gg_origem") == "ia":
    fora = st.session_state.get("gg_fora") or []
    if fora:
        st.warning("Tabela lida pelo Gemini. Estes números não aparecem no texto "
                   "da fonte, confira primeiro: " + "; ".join(fora[:12])
                   + ("; e outros." if len(fora) > 12 else "."))
    elif st.session_state.get("gg_fonte_com_texto"):
        st.info("Tabela lida pelo Gemini. Todos os números existem no texto da "
                "fonte; confira se cada um está na linha e na coluna certas.")
    else:
        st.info("Tabela lida pelo Gemini a partir de imagem. Não há texto para "
                "conferir por código: confira cada número contra a fonte.")
    if st.session_state.get("gg_fonte_imgs"):
        with st.expander("Ver a fonte ao lado da tabela"):
            for imagem in st.session_state["gg_fonte_imgs"]:
                st.image(imagem, use_container_width=True)

t1, t2, t3 = st.columns([3.2, 1.4, 1.2], vertical_alignment="bottom")
t1.text_input("Colunas (separadas por vírgula)", key="gg_colunas",
              on_change=_aplicar_colunas,
              help="Edite para renomear, acrescentar ou tirar colunas. Linhas "
                   "você acrescenta direto na tabela.")
t2.button("Carregar exemplo", on_click=_carregar_exemplo, use_container_width=True)
t3.button("Limpar tabela", on_click=_limpar_tabela, use_container_width=True)

base = st.session_state["gg_base"]
editado = st.data_editor(
    base, num_rows="dynamic", hide_index=True, use_container_width=True,
    key=f"gg_editor_{st.session_state['gg_v']}",
    column_config={c: st.column_config.TextColumn(c) for c in base.columns},
).fillna("").astype(str)
st.session_state["gg_atual"] = editado
st.caption("A primeira coluna é a categoria (ano, órgão, UF) e cada outra coluna é "
           "uma série. Número em formato brasileiro (1.234,5). Célula vazia ou com "
           "traço fica sem valor. Asterisco junto do número aparece na tabela.")

categorias, series, avisos = series_da_tabela(list(editado.columns),
                                              editado.values.tolist())
if avisos:
    st.warning("Não entendi como número, e ficou sem valor: " + "; ".join(avisos[:8])
               + ("; e outros." if len(avisos) > 8 else "."))

# ── 2. peça ──────────────────────────────────────────────────────────────────

st.markdown('<div class="ge-rule">2. Peça</div>', unsafe_allow_html=True)

if not categorias or not any(v is not None for s in series for v in s["valores"]):
    st.info("Preencha a tabela acima para ver a peça.")
    st.stop()

# O tipo é a decisão principal do passo: fica sozinho, acima dos controles e da
# prévia, e não dentro da coluna de ajustes.
sugerido, _, motivo = sugerir_tipo(categorias, len(series))
tipo = st.segmented_control(
    "Tipo de peça", list(TIPOS), key="gg_tipo", label_visibility="collapsed",
    format_func=lambda t: f"{ICONES_TIPO[t]} {TIPOS[t]}") or sugerido
st.markdown(f'<div class="gg-passo" style="margin-top:2px">Ponto de partida para '
            f'estes dados: {TIPOS[sugerido]}, porque {motivo}.</div>',
            unsafe_allow_html=True)

col_ctl, col_prev = st.columns([1, 1.7], gap="large")

with col_ctl:
    nomes = [s["nome"] for s in series]
    escolhidas = st.multiselect(
        "Colunas na tabela" if tipo == "tabela" else "Séries no gráfico",
        nomes, default=nomes if tipo == "tabela" else nomes[:MAX_SERIES],
        # A lista de séries muda com a tabela e o padrão muda com o tipo;
        # chave fixa prenderia a seleção antiga.
        key=f"gg_series_{st.session_state['gg_v']}_{tipo == 'tabela'}")
    selecao = [s for s in series if s["nome"] in escolhidas]

    if tipo == "tabela" and len(series) >= 2:
        if st.checkbox("Acrescentar coluna de percentual", key="gg_pct",
                       help="Divide uma coluna pela outra, linha a linha. Sai "
                            "em %, com uma casa decimal."):
            p1, p2 = st.columns(2)
            num = p1.selectbox("Numerador", nomes, key="gg_pct_num",
                               index=nomes.index("Pago") if "Pago" in nomes else 0)
            den = p2.selectbox("Denominador", nomes, key="gg_pct_den",
                               index=nomes.index("Empenhado") if "Empenhado" in nomes
                               else min(1, len(nomes) - 1))
            nome_pct = st.text_input("Nome da coluna", f"{num} / {den}",
                                     key=f"gg_pct_nome_{num}_{den}")
            selecao.append(serie_percentual(nome_pct, series[nomes.index(num)],
                                            series[nomes.index(den)]))

    st.markdown('<div class="gg-grupo">Texto da peça</div>', unsafe_allow_html=True)
    titulo = st.text_input("Título", key="gg_titulo")
    subtitulo = st.text_input("Subtítulo", key="gg_subtitulo",
                              placeholder="O que é, período e unidade")
    rodape = st.text_area("Rodapé (fonte e notas)", key="gg_rodape", height=70)

    st.markdown('<div class="gg-grupo">Números</div>', unsafe_allow_html=True)
    u1, u2 = st.columns(2)
    unidade = u1.selectbox("Unidade", list(UNIDADES), key="gg_unidade")
    casas = u2.selectbox("Casas decimais", [0, 1, 2], index=1, key="gg_casas")

    orientacao, rotulos, eixo_zero = "vertical", "", True
    if tipo != "tabela":
        with st.expander("Ajustes do gráfico"):
            if tipo in ("barras", "empilhadas"):
                orientacao = st.radio("Orientação", ["vertical", "horizontal"],
                                      horizontal=True, key="gg_orientacao")
            rotulos = st.radio("Rótulos de valor", list(ROTULOS[tipo]),
                               format_func=ROTULOS[tipo].get,
                               key=f"gg_rotulos_{tipo}")
            if tipo == "linha":
                eixo_zero = st.checkbox(
                    "Eixo começa no zero", True, key="gg_zero",
                    help="Desligado, o eixo aperta em volta dos valores e a "
                         "variação parece maior do que é. Barra sempre começa "
                         "no zero.")

    with st.expander("Marca e formato"):
        identidade = st.radio("Marca", list(IDENTIDADES), horizontal=True,
                              key="gg_identidade")
        tamanho = st.selectbox("Tamanho", list(TAMANHOS), key="gg_tamanho",
                               help="Na tabela vale só a largura: a altura "
                                    "acompanha o número de linhas.")
        incluir_logo = st.checkbox(
            "Logo na prévia", True, key="gg_logo",
            help="Só muda a prévia: o arquivo baixado sai sempre nas duas "
                 "versões, com e sem logo.")
        fundo_transparente = st.checkbox(
            "Fundo transparente", False, key="gg_fundo",
            help="Sai sem fundo, para assentar em slide. O texto continua "
                 "escuro, então pede fundo claro.")

opcoes = {
    "titulo": titulo, "subtitulo": subtitulo, "rodape": rodape,
    "rotulo_categoria": editado.columns[0], "unidade": unidade, "casas": casas,
    "orientacao": orientacao, "rotulos": rotulos, "eixo_zero": eixo_zero,
    "identidade": identidade, "tamanho": tamanho,
    "fundo_transparente": fundo_transparente,
}

with col_prev:
    st.markdown('<div class="gg-previa"></div>', unsafe_allow_html=True)
    if not selecao:
        st.info("Escolha ao menos uma série.")
        st.stop()
    try:
        st.image(gerar_peca(tipo, categorias, selecao, incluir_logo=incluir_logo,
                            **opcoes), use_container_width=True)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:
        st.error(f"Falha ao gerar a peça: {exc}")
        st.stop()

    e1, e2 = st.columns([2, 1], vertical_alignment="bottom")
    escala = e1.radio(
        "Tamanho do PNG", list(ESCALAS_EXPORT), horizontal=True,
        index=list(ESCALAS_EXPORT).index(2), key="gg_escala",
        format_func=lambda e: f"{e}× {ESCALAS_EXPORT[e]}")

    nomes_arq = {f"{suf}_{fmt}": slug_arquivo(titulo, tipo, fmt, suf)
                 for suf in ("com-logo", "sem-logo") for fmt in ("png", "svg")}
    assinatura = json.dumps({
        "logo": _marca_da_logo(identidade), "tipo": tipo,
        "categorias": categorias, "series": selecao, "opcoes": opcoes,
        "escala": escala, "nomes": nomes_arq,
    }, sort_keys=True, ensure_ascii=False)
    e2.download_button(
        "Baixar tudo (.zip)", _pacote(assinatura),
        file_name=slug_arquivo(titulo, tipo, "zip"),
        mime="application/zip", use_container_width=True, type="primary",
        help="Quatro arquivos: PNG e SVG, cada um com e sem a logo")
    st.caption("O zip traz PNG e SVG, cada um com e sem logo. O SVG é vetor: a "
               "escala não muda nada nele.")
