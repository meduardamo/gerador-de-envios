"""
Gerador de Gráficos: uma tabela entra (digitada, colada do Sheets ou enviada em
arquivo) e sai peça na identidade da casa: linha, barras, barras empilhadas ou
tabela, em PNG e SVG, com e sem logo.

O desenho mora em gerador_graficos_core, que segue o gráfico do Alerta de
Pesquisa. Esta página só recolhe os dados e as escolhas; não grava nada em
planilha nenhuma.
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
)

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


# ── modelos de partida ───────────────────────────────────────────────────────

MODELOS = {
    "Execução orçamentária (exemplo: Ação 217M)": {
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
    },
    "Em branco": {
        "colunas": ["Categoria", "Série 1", "Série 2"],
        "linhas": [["", "", ""] for _ in range(4)],
        "titulo": "", "subtitulo": "", "rodape": "", "unidade": "Número",
    },
}


def _definir_base(df: pd.DataFrame) -> None:
    """Troca a tabela inteira. A versão entra na chave do editor: sem isso o
    Streamlit reaplicaria na tabela nova as edições feitas na anterior."""
    df = df.fillna("").astype(str)
    st.session_state["gg_base"] = df
    st.session_state["gg_atual"] = df
    st.session_state["gg_v"] = st.session_state.get("gg_v", 0) + 1
    st.session_state["gg_colunas"] = ", ".join(df.columns)
    st.session_state.pop("gg_erro", None)


def _carregar_modelo() -> None:
    modelo = MODELOS[st.session_state.get("gg_modelo") or next(iter(MODELOS))]
    _definir_base(pd.DataFrame(modelo["linhas"], columns=modelo["colunas"]))
    for campo in ("titulo", "subtitulo", "rodape", "unidade"):
        st.session_state[f"gg_{campo}"] = modelo[campo]


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
        st.session_state["gg_erro"] = ("Não achei colunas no texto colado. Copie "
                                       "as células direto da planilha.")
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
    if len(nomes) == len(atual.columns):
        novo = atual.copy()
        novo.columns = nomes
    else:
        novo = pd.DataFrame({n: (atual[n] if n in atual.columns else "") for n in nomes},
                            index=atual.index)
    _definir_base(novo)


if "gg_base" not in st.session_state:
    _carregar_modelo()


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

st.markdown('<div class="ge-rule">1. Dados</div>', unsafe_allow_html=True)
st.caption("A primeira coluna é a categoria (ano, órgão, UF). Cada outra coluna é "
           "uma série. Número em formato brasileiro: 1.234,5. Célula vazia ou com "
           "traço fica sem valor, e o asterisco digitado junto do número aparece "
           "na tabela.")

d1, d2 = st.columns([1, 1])
with d1:
    st.selectbox("Modelo de partida", list(MODELOS), key="gg_modelo",
                 on_change=_carregar_modelo,
                 help="Trocar o modelo substitui a tabela, o título e o rodapé.")
    st.text_input("Colunas (separadas por vírgula)", key="gg_colunas",
                  on_change=_aplicar_colunas,
                  help="Edite para renomear, acrescentar ou tirar colunas. "
                       "Linhas você acrescenta direto na tabela.")
with d2:
    with st.expander("Colar do Sheets, Excel ou Docs"):
        st.text_area("Copie as células com o cabeçalho e cole aqui",
                     key="gg_colado", height=120)
        st.button("Usar dados colados", on_click=_usar_colado)
    with st.expander("Enviar arquivo (.xlsx ou .csv)"):
        st.file_uploader("Primeira aba, cabeçalho na primeira linha",
                         type=["xlsx", "xlsm", "csv"], key="gg_arquivo")
        st.button("Usar arquivo", on_click=_usar_arquivo)

if st.session_state.get("gg_erro"):
    st.error(st.session_state["gg_erro"])

base = st.session_state["gg_base"]
editado = st.data_editor(
    base, num_rows="dynamic", hide_index=True, use_container_width=True,
    key=f"gg_editor_{st.session_state['gg_v']}",
    column_config={c: st.column_config.TextColumn(c) for c in base.columns},
).fillna("").astype(str)
st.session_state["gg_atual"] = editado

categorias, series, avisos = series_da_tabela(list(editado.columns),
                                              editado.values.tolist())
if avisos:
    st.warning("Não entendi como número, e ficou sem valor: " + "; ".join(avisos[:8])
               + ("; e outros." if len(avisos) > 8 else "."))

st.markdown('<div class="ge-rule">2. Peça</div>', unsafe_allow_html=True)

if not categorias or not series:
    st.info("Preencha a tabela acima para ver a peça.")
    st.stop()

col_ctl, col_prev = st.columns([1, 1.7])

with col_ctl:
    tipo = st.radio("Tipo", list(TIPOS), format_func=TIPOS.get, horizontal=True,
                    key="gg_tipo")
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

    titulo = st.text_input("Título", key="gg_titulo")
    subtitulo = st.text_input("Subtítulo", key="gg_subtitulo")
    rodape = st.text_area("Rodapé (fonte e notas)", key="gg_rodape", height=80)

    u1, u2 = st.columns(2)
    unidade = u1.selectbox("Unidade", list(UNIDADES), key="gg_unidade")
    casas = u2.selectbox("Casas decimais", [0, 1, 2], index=1, key="gg_casas")

    orientacao, rotulos, eixo_zero = "vertical", "", True
    if tipo in ("barras", "empilhadas"):
        orientacao = st.radio("Orientação", ["vertical", "horizontal"],
                              horizontal=True, key="gg_orientacao")
    if ROTULOS[tipo]:
        rotulos = st.radio("Rótulos de valor", list(ROTULOS[tipo]),
                           format_func=ROTULOS[tipo].get, key=f"gg_rotulos_{tipo}")
    if tipo == "linha":
        eixo_zero = st.checkbox(
            "Eixo começa no zero", True, key="gg_zero",
            help="Desligado, o eixo aperta em volta dos valores e a variação "
                 "parece maior do que é. Barra sempre começa no zero.")

    i1, i2 = st.columns(2)
    identidade = i1.radio("Marca", list(IDENTIDADES), key="gg_identidade")
    tamanho = i2.selectbox("Tamanho", list(TAMANHOS), key="gg_tamanho",
                           help="Na tabela vale só a largura: a altura acompanha "
                                "o número de linhas.")
    incluir_logo = st.checkbox(
        "Logo na prévia", True, key="gg_logo",
        help="Só muda a prévia: o arquivo baixado sai sempre nas duas versões, "
             "com e sem logo.")
    fundo_transparente = st.checkbox(
        "Fundo transparente", False, key="gg_fundo",
        help="Sai sem fundo, para assentar em slide. O texto continua escuro, "
             "então pede fundo claro.")

opcoes = {
    "titulo": titulo, "subtitulo": subtitulo, "rodape": rodape,
    "rotulo_categoria": editado.columns[0], "unidade": unidade, "casas": casas,
    "orientacao": orientacao, "rotulos": rotulos, "eixo_zero": eixo_zero,
    "identidade": identidade, "tamanho": tamanho,
    "fundo_transparente": fundo_transparente,
}

with col_prev:
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

    e1, e2 = st.columns([2, 1])
    escala = e1.radio(
        "Tamanho do PNG", list(ESCALAS_EXPORT), horizontal=True,
        index=list(ESCALAS_EXPORT).index(2), key="gg_escala",
        format_func=lambda e: f"{e}× {ESCALAS_EXPORT[e]}")
    e1.caption("O SVG é vetor: a escala não muda nada nele.")

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
    e2.caption("PNG e SVG, com e sem logo.")
