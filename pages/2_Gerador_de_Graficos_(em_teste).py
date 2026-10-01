"""
Gerador de Gráficos: uma tabela entra e sai peça na identidade da EixoGov (linha,
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
    DUAS_SERIES,
    ESQUEMAS,
    IDENTIDADES,
    MAX_SERIES,
    MAX_TONS,
    ROTULOS,
    TAMANHOS,
    TIPOS,
    UMA_SERIE,
    UNIDADES,
    gerar_peca,
    par_execucao,
    parecem_etapas,
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

st.set_page_config(page_title="Gerador de Gráficos (em teste)", layout="wide")

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
/* Selo ao lado do título enquanto a página está em teste. Tirar daqui, do
   hero e do nome do arquivo quando ela for liberada. */
.ge-hero-selo { margin-left: 18px; padding: 6px 12px; border: 1.5px solid #fff; color: #fff; font-size: 13px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; }
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

LOGO_PATH = str(ROOT_DIR / "logo_eixo_gov_magenta.png")

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
# Os cores não importam Streamlit: a chave dos Secrets entra por aqui.
definir_api_key(GEMINI_API_KEY)

_EX_217M = {
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

_UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
        "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
        "SP", "SE", "TO"]
_SITUACOES = ["Tem lei", "Em tramitação", "Sem norma"]

# Um exemplo por tipo, para a pessoa ver em que formato a tabela precisa estar.
# Fora o da Ação 217M, os números são inventados e o título diz isso: exemplo
# fictício não pode sair daqui parecendo dado.
EXEMPLOS = {
    "linha": _EX_217M, "barras": _EX_217M, "execucao": _EX_217M, "tabela": _EX_217M,
    "variacao": {
        "colunas": ["Ano", "Variação"],
        "linhas": [["2022", "12,4"], ["2023", "-8,1"], ["2024", "3,2"],
                   ["2025", "-15,6"], ["2026", "6,0"]],
        "titulo": "Variação anual da dotação (exemplo fictício)",
        "subtitulo": "Em relação ao ano anterior", "rodape": "", "unidade": "%",
    },
    "tempo": {
        "colunas": ["Data", "Marco"],
        "linhas": [
            ["12/03/2026", "Apresentação do projeto na Câmara dos Deputados."],
            ["02/04/2026", "Despacho às comissões de Educação e de Finanças e Tributação."],
            ["18/06/2026", "Parecer do relator pela aprovação, com substitutivo."],
            ["20/08/2026", "Aprovado na comissão de mérito."],
        ],
        "titulo": "Tramitação do projeto (exemplo fictício)",
        "subtitulo": "", "rodape": "", "unidade": "Número",
    },
    "ranking": {
        "colunas": ["Tema", "Proposições"],
        "linhas": [["Educação", "42"], ["Saúde", "37"], ["Segurança pública", "29"],
                   ["Meio ambiente", "18"], ["Cultura", "9"],
                   ["Ciência e tecnologia", "6"]],
        "titulo": "Proposições por tema (exemplo fictício)",
        "subtitulo": "Número de proposições apresentadas", "rodape": "",
        "unidade": "Número",
    },
    "dois": {
        "colunas": ["Região", "2022", "2026"],
        "linhas": [["Norte", "31,5", "35,2"], ["Nordeste", "48,0", "44,1"],
                   ["Centro-Oeste", "27,3", "27,9"], ["Sudeste", "39,8", "46,0"],
                   ["Sul", "35,1", "30,4"]],
        "titulo": "Indicador por região, 2022 e 2026 (exemplo fictício)",
        "subtitulo": "", "rodape": "", "unidade": "%",
    },
    "cem": {
        "colunas": ["Cargo", "Mulheres", "Homens"],
        "linhas": [["Deputado federal", "3400", "6900"], ["Senador", "70", "170"],
                   ["Governador", "40", "180"]],
        "titulo": "Candidaturas por gênero e cargo (exemplo fictício)",
        "subtitulo": "Participação de cada grupo no total do cargo", "rodape": "",
        "unidade": "Número",
    },
    "empilhadas": {
        "colunas": ["Órgão", "Pessoal", "Custeio", "Investimento"],
        "linhas": [["Órgão A", "120,5", "80,2", "30,1"], ["Órgão B", "150,0", "140,3", "22,8"],
                   ["Órgão C", "40,2", "210,7", "5,4"], ["Órgão D", "18,9", "35,0", "96,3"]],
        "titulo": "Despesa por órgão e grupo (exemplo fictício)",
        "subtitulo": "", "rodape": "", "unidade": "R$ milhões",
    },
    "hemiciclo": {
        "colunas": ["Posição", "Votos"],
        "linhas": [["Sim", "280"], ["Não", "150"], ["Abstenção", "12"],
                   ["Ausente", "71"]],
        "titulo": "Placar da votação (exemplo fictício)",
        "subtitulo": "Câmara dos Deputados, 513 cadeiras", "rodape": "",
        "unidade": "Número",
    },
    "mapa": {
        "colunas": ["UF", "Situação"],
        "linhas": [[uf, _SITUACOES[i % 3]] for i, uf in enumerate(_UFS)],
        "titulo": "Legislação estadual por UF (exemplo fictício)",
        "subtitulo": "", "rodape": "", "unidade": "Número",
    },
    "numero": {
        "colunas": ["Indicador", "Valor"],
        "linhas": [["Proposições monitoradas", "285"], ["Em tramitação", "142"],
                   ["Aprovadas no ano", "12"]],
        "titulo": "Monitoramento legislativo (exemplo fictício)",
        "subtitulo": "", "rodape": "", "unidade": "Número",
    },
    "matriz": {
        "colunas": ["Tema", "Partido A", "Partido B", "Partido C", "Partido D"],
        "linhas": [["Educação", "12", "4", "9", "1"], ["Saúde", "7", "11", "3", ""],
                   ["Segurança", "2", "15", "6", "8"],
                   ["Meio ambiente", "9", "1", "", "5"]],
        "titulo": "Proposições por tema e partido (exemplo fictício)",
        "subtitulo": "", "rodape": "", "unidade": "Número",
    },
}

FONTES = {
    "colar": ":material/content_paste: Colar ou digitar",
    "ia": ":material/auto_awesome: Ler de PDF, imagem ou texto",
    "arquivo": ":material/upload_file: Planilha (.xlsx ou .csv)",
}

# Escolha em dois níveis: primeiro a pergunta que a peça responde, depois a
# forma. Catorze botões numa fileira só não se leem.
GRUPOS = {
    "Evolução no tempo": ["linha", "variacao", "tempo"],
    "Comparação": ["barras", "ranking", "dois", "execucao"],
    "Composição": ["cem", "empilhadas", "hemiciclo"],
    "Território": ["mapa"],
    "Número e detalhe": ["numero", "matriz", "tabela"],
}
GRUPO_DE = {tipo: grupo for grupo, tipos in GRUPOS.items() for tipo in tipos}

ICONES_TIPO = {
    "linha": ":material/show_chart:",
    "variacao": ":material/swap_vert:",
    "tempo": ":material/timeline:",
    "barras": ":material/bar_chart:",
    "ranking": ":material/sort:",
    "dois": ":material/compare_arrows:",
    "execucao": ":material/align_vertical_bottom:",
    "cem": ":material/percent:",
    "empilhadas": ":material/stacked_bar_chart:",
    "hemiciclo": ":material/groups:",
    "mapa": ":material/grid_view:",
    "numero": ":material/pin:",
    "matriz": ":material/grid_on:",
    "tabela": ":material/table:",
}

# O que cada tipo responde e em que formato a tabela precisa estar.
TIPO_SERVE = {
    "linha": ("Trajetória: como cada valor mudou de um período para o outro.",
              "Primeira coluna: os períodos. Demais: uma série por coluna."),
    "variacao": ("Subiu ou caiu, e quanto: barras para cima e para baixo a partir do zero.",
                 "Primeira coluna: período ou item. Segunda: a variação, com sinal de menos quando cai."),
    "tempo": ("Em que pé está: os marcos em ordem, com data e descrição.",
              "Primeira coluna: a data. Segunda: o texto do marco."),
    "barras": ("Comparação lado a lado: valores de poucas séries em cada categoria.",
               "Primeira coluna: as categorias. Demais: uma série por coluna (até 6)."),
    "ranking": ("Quem tem mais: itens ordenados do maior para o menor, com um em destaque se quiser.",
                "Primeira coluna: os itens. Segunda: o valor."),
    "dois": ("O que mudou entre dois momentos: dois pontos ligados em cada linha.",
             "Primeira coluna: os itens. Duas colunas de valor: antes e depois."),
    "execucao": ("Quanto do previsto foi realizado: a barra do realizado fica dentro da barra do previsto, com o percentual em cima.",
                 "Primeira coluna: os períodos ou itens. Duas colunas de valor: previsto e realizado."),
    "cem": ("Como cada linha se divide: partes em percentual, somando 100%.",
            "Primeira coluna: os itens. Demais: as partes (o percentual é calculado aqui)."),
    "empilhadas": ("Composição em valor: partes que somadas formam um total.",
                   "Primeira coluna: os itens. Demais: as partes."),
    "hemiciclo": ("Quem compõe a Casa: um ponto por cadeira, agrupado.",
                  "Primeira coluna: grupo, partido ou posição. Segunda: número de cadeiras (até 6 grupos)."),
    "mapa": ("Como está em cada UF: os 27 estados em quadrados iguais.",
             "Primeira coluna: sigla ou nome da UF. Segunda: um número ou uma categoria."),
    "numero": ("O número que importa: de um a quatro números grandes, com legenda.",
               "Primeira coluna: a legenda. Segunda: o número."),
    "matriz": ("Onde se concentra: linhas por colunas, com a célula mais escura onde o valor é maior.",
               "Primeira coluna: as linhas. Demais: as colunas da matriz."),
    "tabela": ("Todos os números, para quem precisa do valor exato.",
               "Qualquer tabela."),
}

# Rótulo do seletor de coluna nos tipos que usam uma coluna só.
ROTULO_COLUNA = {"tempo": "Coluna do texto", "hemiciclo": "Coluna das cadeiras",
                 "mapa": "Coluna do mapa"}

MIMES_IMAGEM = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp"}

# O que descreve de onde veio a tabela atual. Some quando a tabela é trocada.
CHAVES_ORIGEM = ("gg_origem", "gg_fora", "gg_fonte_imgs", "gg_fonte_com_texto")


def _pedir_tipo(tipo: str) -> None:
    """Deixa pedido o tipo que a página deve abrir. Quem aplica é o seletor,
    na hora de ser desenhado: o seletor de forma muda de opções conforme o
    grupo, e o Streamlit descarta o valor gravado direto na chave de um widget
    cujas opções mudaram."""
    st.session_state["gg_tipo_pedido"] = tipo
    st.session_state["gg_grupo"] = GRUPO_DE[tipo]


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
    tipo, _, _ = sugerir_tipo(df.iloc[:, 0].tolist(), df.shape[1] - 1)
    _pedir_tipo(tipo)
    for chave in ("gg_erro",) + CHAVES_ORIGEM:
        st.session_state.pop(chave, None)


# Campos de texto da peça. O valor vive em dois lugares: na chave do widget e
# numa cópia fora de widget (gg_guardado). O Streamlit apaga da sessão a chave
# de todo widget que não foi desenhado na última execução, e isso acontece
# sempre que a pessoa abre outra página do app: na volta, a tabela (que não é
# chave de widget) estava lá e o título, o subtítulo e o rodapé tinham sumido.
CAMPOS_TEXTO = ("gg_titulo", "gg_subtitulo", "gg_rodape", "gg_unidade")


def _definir_textos(titulo="", subtitulo="", rodape="", unidade="Número") -> None:
    valores = (titulo, subtitulo, rodape,
               unidade if unidade in UNIDADES else "Número")
    for chave, valor in zip(CAMPOS_TEXTO, valores):
        st.session_state[chave] = valor
    st.session_state["gg_guardado"] = dict(zip(CAMPOS_TEXTO, valores))


def _restaurar_da_volta() -> None:
    """Repõe o que o Streamlit apagou enquanto a pessoa estava em outra página.

    O campo de colunas é desenhado em toda execução desta página, antes de
    qualquer parada: se a chave dele sumiu, é porque a pessoa saiu e voltou.
    """
    if "gg_colunas" in st.session_state:
        return
    guardado = st.session_state.get("gg_guardado", {})
    for chave in CAMPOS_TEXTO:
        if chave in guardado:
            st.session_state[chave] = guardado[chave]
    # A tabela volta com as edições que estavam na tela, não com a versão de
    # antes delas: o editor também é widget e perde as edições na saída.
    st.session_state["gg_base"] = st.session_state["gg_atual"]
    st.session_state["gg_v"] += 1
    st.session_state["gg_colunas"] = ", ".join(st.session_state["gg_atual"].columns)
    if st.session_state.get("gg_tipo") in GRUPO_DE:
        _pedir_tipo(st.session_state["gg_tipo"])


def _carregar_exemplo(tipo: str = "linha") -> None:
    """Põe na tabela o exemplo daquele tipo e deixa o tipo escolhido."""
    exemplo = EXEMPLOS[tipo]
    _definir_base(pd.DataFrame(exemplo["linhas"], columns=exemplo["colunas"]))
    _definir_textos(exemplo["titulo"], exemplo["subtitulo"], exemplo["rodape"],
                    exemplo["unidade"])
    _pedir_tipo(tipo)


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
    if tipo in GRUPO_DE:
        _pedir_tipo(tipo)
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
else:
    _restaurar_da_volta()


# Escolhas do download. A chave é o pedaço que vai no nome do arquivo.
SAIDA_FUNDO = {"fundo-branco": "Branco", "sem-fundo": "Sem fundo"}
SAIDA_LOGO = {"com-logo": "Com logo", "sem-logo": "Sem logo"}
SAIDA_FORMATO = {"png": "PNG", "svg": "SVG"}
MIMES_SAIDA = {"png": "image/png", "svg": "image/svg+xml"}


@st.cache_data(show_spinner=False, max_entries=6)
def _arquivos(assinatura: str) -> bytes:
    """Os arquivos pedidos no download: um só sai direto, mais de um sai em
    zip. Em cache pela assinatura, como no Alerta de Pesquisa: o
    download_button precisa dos bytes prontos a cada rerun."""
    cfg = json.loads(assinatura)
    prontos = [
        (nome, gerar_peca(cfg["tipo"], cfg["categorias"], cfg["series"],
                          incluir_logo=logo == "com-logo", formato=formato,
                          fundo_transparente=fundo == "sem-fundo",
                          escala=cfg["escala"], **cfg["opcoes"]))
        for nome, fundo, logo, formato in cfg["arquivos"]
    ]
    if len(prontos) == 1:
        return prontos[0][1]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_saida:
        for nome, dados in prontos:
            zip_saida.writestr(nome, dados)
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

st.markdown('<div class="ge-hero"><div class="ge-hero-title">Gerador de Gráficos</div>'
            '<div class="ge-hero-selo">Em teste</div></div>',
            unsafe_allow_html=True)
st.caption("Página em teste: o desenho das peças ainda está sendo ajustado. "
           "Confira a peça antes de usar em material de cliente.")

# Mesma lateral das outras páginas: logo, o que a página faz, usuário e sair.
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
        'Traga uma tabela e gere <strong>gráfico</strong> ou '
        '<strong>tabela</strong> na identidade da EixoGov, em PNG e SVG.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    if not montserrat_disponivel():
        st.warning("Montserrat não encontrada em fontes/. A peça sai fora da "
                   "tipografia da EixoGov.")
    st.markdown("---")
    # Sem help: com tooltip o Streamlit embrulha o botão e ele perde o
    # estilo dos outros botões da lateral.
    st.button("Limpar tudo", on_click=_limpar_tabela, use_container_width=True)
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** "
               f"({st.session_state.get('username', '')})")
    if _auth_cfg:
        authenticator.logout("Sair", "sidebar")

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
    b1, b2 = st.columns([1.5, 4])
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

t1, t3 = st.columns([4.6, 1.2], vertical_alignment="bottom")
t1.text_input("Colunas (separadas por vírgula)", key="gg_colunas",
              on_change=_aplicar_colunas,
              help="Edite para renomear, acrescentar ou tirar colunas. Linhas "
                   "você acrescenta direto na tabela.")
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
           "traço fica sem valor. Asterisco junto do número aparece na tabela. "
           "Cada forma do passo 2 diz como a tabela precisa estar e tem um "
           "exemplo para carregar.")

categorias, series, avisos = series_da_tabela(list(editado.columns),
                                              editado.values.tolist())

# ── 2. peça ──────────────────────────────────────────────────────────────────

st.markdown('<div class="ge-rule">2. Peça</div>', unsafe_allow_html=True)

# O tipo é a decisão principal do passo: fica sozinho, acima dos controles e da
# prévia. Primeiro a pergunta, depois a forma.
sugerido, _, motivo = sugerir_tipo(categorias, len(series))
grupo = st.segmented_control("O que a peça mostra", list(GRUPOS), key="gg_grupo") \
    or GRUPO_DE[sugerido]
formas = GRUPOS[grupo]
# Um seletor de forma por grupo (a chave leva o grupo): cada grupo lembra a
# forma que estava escolhida nele, e um pedido de tipo entra por aqui.
chave_forma = f"gg_forma_{grupo}"
pedido = st.session_state.pop("gg_tipo_pedido", None)
if pedido in formas:
    st.session_state[chave_forma] = pedido
tipo = st.segmented_control(
    "Forma", formas, key=chave_forma, default=formas[0],
    format_func=lambda t: f"{ICONES_TIPO[t]} {TIPOS[t]}") or formas[0]
# Cópia fora de widget, para quem precisa saber o tipo atual num callback.
st.session_state["gg_tipo"] = tipo

serve, formato_dados = TIPO_SERVE[tipo]
g1, g2 = st.columns([3, 1], vertical_alignment="center")
g1.markdown(f'<div class="gg-passo" style="margin:2px 0 4px">{serve}<br>'
            f'<b>Como a tabela precisa estar:</b> {formato_dados}</div>',
            unsafe_allow_html=True)
g2.button("Carregar exemplo desta forma", on_click=_carregar_exemplo,
          args=(tipo,), use_container_width=True)

# Linha do tempo lê texto, e o mapa aceita categoria: nesses dois a célula que
# não é número não é erro.
if avisos and tipo not in ("tempo", "mapa"):
    st.warning("Não entendi como número, e ficou sem valor: " + "; ".join(avisos[:8])
               + ("; e outros." if len(avisos) > 8 else "."))

if not categorias or not series:
    st.info("Preencha a tabela no passo 1, ou carregue o exemplo desta forma.")
    st.stop()

# Empilhar soma as séries. A ferramenta não sabe se a soma faz sentido para
# estes dados (PLOA + dotação + pago, por exemplo, não é total de nada).
nomes = [s["nome"] for s in series]
if tipo in ("empilhadas", "cem") and parecem_etapas(nomes):
    st.warning("Estas séries parecem etapas do mesmo valor (dotação, empenhado, "
               "pago). Empilhadas, elas se somam e o total não significa nada. "
               "Para isso use Previsto x realizado ou Barras.")

col_ctl, col_prev = st.columns([1, 2], gap="large")
versao = st.session_state["gg_v"]

with col_ctl:
    esquema, destaque, limite = "categorias", "", 0
    orientacao, rotulos, eixo_zero = "vertical", "", True

    # ── quais colunas entram ────────────────────────────────────────────────
    if tipo in DUAS_SERIES:
        if len(series) < 2:
            st.info(f"{TIPOS[tipo]} precisa de duas colunas de valor na tabela.")
            st.stop()
        if tipo == "execucao":
            padrao_a, padrao_b = par_execucao(nomes)
            rot_a, rot_b = "Previsto (barra larga)", "Realizado (barra de dentro)"
        else:
            padrao_a, padrao_b = nomes[0], nomes[-1]
            rot_a, rot_b = "Antes", "Depois"
        x1, x2 = st.columns(2)
        nome_a = x1.selectbox(rot_a, nomes, index=nomes.index(padrao_a),
                              key=f"gg_a_{versao}_{tipo}")
        nome_b = x2.selectbox(rot_b, nomes, index=nomes.index(padrao_b),
                              key=f"gg_b_{versao}_{tipo}")
        if nome_a == nome_b:
            st.info("Escolha duas colunas diferentes.")
            st.stop()
        selecao = [series[nomes.index(nome_a)], series[nomes.index(nome_b)]]
    elif tipo in UMA_SERIE:
        nome = nomes[0] if len(nomes) == 1 else st.selectbox(
            ROTULO_COLUNA.get(tipo, "Coluna de valores"), nomes,
            key=f"gg_uma_{versao}_{tipo}")
        selecao = [series[nomes.index(nome)]]
    else:
        todas = tipo in ("tabela", "matriz")
        escolhidas = st.multiselect(
            "Colunas" if todas else "Séries no gráfico",
            nomes, default=nomes if todas else nomes[:MAX_SERIES],
            # A lista de séries muda com a tabela e o padrão muda com o tipo;
            # chave fixa prenderia a seleção antiga.
            key=f"gg_series_{versao}_{todas}")
        selecao = [s for s in series if s["nome"] in escolhidas]

    # ── cor ─────────────────────────────────────────────────────────────────
    if tipo in ("linha", "barras", "empilhadas", "cem") and len(selecao) >= 2:
        # Destaque só existe na linha: em barra, várias séries no mesmo cinza
        # não se distinguem. Tons de uma cor só até três séries: com mais, os
        # tons vizinhos se confundem.
        opcoes_cor = [e for e in ESQUEMAS
                      if (e != "destaque" or tipo == "linha")
                      and (e != "tons" or len(selecao) <= MAX_TONS)]
        etapas = (parecem_etapas([s["nome"] for s in selecao])
                  and len(selecao) <= MAX_TONS)
        # Na participação, duas ou três partes do mesmo todo leem melhor em
        # tons de uma cor.
        em_tons = etapas or (tipo == "cem" and len(selecao) <= MAX_TONS)
        esquema = st.selectbox(
            "Cores", opcoes_cor, format_func=ESQUEMAS.get,
            index=opcoes_cor.index("tons" if em_tons else "categorias"),
            key=f"gg_esquema_{versao}_{tipo}_{em_tons}",
            help="Tons de uma cor: até três séries que são etapas ou partes da "
                 "mesma coisa (com mais, os tons se confundem). "
                 "Destaque: uma série é o assunto e as outras são contexto. "
                 "Uma cor por série: coisas diferentes, sem ordem entre si.")
        if esquema == "destaque":
            nomes_sel = [s["nome"] for s in selecao]
            destaque = st.selectbox("Série em destaque", nomes_sel,
                                    index=nomes_sel.index(par_execucao(nomes_sel)[1]),
                                    key=f"gg_destaque_{versao}")

    # ── o que é próprio de cada forma ───────────────────────────────────────
    if tipo == "ranking":
        r1, r2 = st.columns(2)
        itens_rank = [c for c, v in zip(categorias, selecao[0]["valores"])
                      if v is not None]
        escolha = r1.selectbox("Item em destaque", ["Nenhum"] + itens_rank,
                               key=f"gg_rank_dest_{versao}",
                               help="O item escolhido fica na cor da marca e os "
                                    "outros em cinza. Sem destaque, todas as "
                                    "barras saem na cor da marca.")
        destaque = "" if escolha == "Nenhum" else escolha
        limite = r2.number_input("Mostrar só os primeiros", min_value=0,
                                 max_value=max(1, len(itens_rank)), value=0,
                                 key=f"gg_rank_lim_{versao}",
                                 help="Zero mostra todos.")
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
    if tipo in ("barras", "empilhadas", "variacao"):
        # À vista, e não dentro dos ajustes: deitar a barra muda a peça inteira.
        # Ponto de partida: tempo na primeira coluna fica em pé (o tempo corre
        # da esquerda para a direita); composição entre categorias fica
        # deitada, que é como se lê nome de órgão ou de programa; barra comum
        # deita quando os nomes são longos ou muitos.
        tipo_sug, orient_sug, _ = sugerir_tipo(categorias, 2)
        if tipo_sug == "linha":
            padrao = "vertical"
        elif tipo in ("empilhadas", "variacao"):
            padrao = "horizontal"
        else:
            padrao = orient_sug
        orientacao = st.radio(
            "Orientação", ["vertical", "horizontal"], horizontal=True,
            index=["vertical", "horizontal"].index(padrao),
            format_func={"vertical": "Em pé", "horizontal": "Deitada"}.get,
            key=f"gg_orientacao_{versao}_{tipo}")

    st.markdown('<div class="gg-grupo">Texto da peça</div>', unsafe_allow_html=True)
    titulo = st.text_input("Título", key="gg_titulo")
    subtitulo = st.text_input("Subtítulo", key="gg_subtitulo",
                              placeholder="O que é, período e unidade")
    rodape = st.text_area("Rodapé (fonte e notas)", key="gg_rodape", height=70)

    unidade, casas = st.session_state.get("gg_unidade", "Número"), 1
    if tipo != "tempo":
        st.markdown('<div class="gg-grupo">Números</div>', unsafe_allow_html=True)
        # Contagem (proposições, cadeiras, UFs) não tem casa decimal: o padrão
        # acompanha o dado, e a pessoa muda se quiser.
        numeros = [v for s in selecao for v in s["valores"] if v is not None]
        inteiros = bool(numeros) and all(float(v).is_integer() for v in numeros)
        u1, u2 = st.columns(2)
        unidade = u1.selectbox("Unidade", list(UNIDADES), key="gg_unidade")
        casas = u2.selectbox("Casas decimais", [0, 1, 2], index=0 if inteiros else 1,
                             key=f"gg_casas_{versao}_{inteiros}")

    if tipo in ROTULOS:
        with st.expander("Ajustes do gráfico"):
            rotulos = st.radio("Rótulos de valor", list(ROTULOS[tipo]),
                               format_func=ROTULOS[tipo].get,
                               key=f"gg_rotulos_{tipo}",
                               help="Com muitas barras o número sobe deitado "
                                    "sobre a barra. Para número exato de "
                                    "muitas séries, a Tabela lê melhor.")
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
                               help="Em tabela, matriz, linha do tempo, número "
                                    "em destaque e barras deitadas vale só a "
                                    "largura: a altura acompanha o conteúdo.")

st.session_state["gg_guardado"] = {chave: st.session_state.get(chave, "")
                                   for chave in CAMPOS_TEXTO}

opcoes = {
    "titulo": titulo, "subtitulo": subtitulo, "rodape": rodape,
    "rotulo_categoria": editado.columns[0], "unidade": unidade, "casas": casas,
    "orientacao": orientacao, "rotulos": rotulos, "eixo_zero": eixo_zero,
    "esquema": esquema, "destaque": destaque, "limite": int(limite),
    "identidade": identidade, "tamanho": tamanho,
}

with col_prev:
    st.markdown('<div class="gg-previa"></div>', unsafe_allow_html=True)
    if not selecao:
        st.info("Escolha ao menos uma série.")
        st.stop()

    # A prévia mostra a primeira combinação escolhida para o download, então o
    # que está na tela é um dos arquivos que vão sair. Os seletores ficam
    # embaixo da imagem, e por isso são lidos da sessão antes de desenhar.
    fundos = st.session_state.get("gg_saida_fundo", ["fundo-branco"])
    logos = st.session_state.get("gg_saida_logo", ["com-logo", "sem-logo"])
    try:
        st.image(gerar_peca(tipo, categorias, selecao,
                            incluir_logo="com-logo" in logos or not logos,
                            fundo_transparente=bool(fundos) and "fundo-branco" not in fundos,
                            **opcoes), use_container_width=True)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:
        st.error(f"Falha ao gerar a peça: {exc}")
        st.stop()

    st.markdown('<div class="gg-grupo">Baixar</div>', unsafe_allow_html=True)
    s1, s2, s3 = st.columns(3)
    with s1:
        st.segmented_control(
            "Fundo", list(SAIDA_FUNDO), format_func=SAIDA_FUNDO.get,
            selection_mode="multi", default=["fundo-branco"], key="gg_saida_fundo",
            help="Sem fundo assenta direto em slide ou documento. O texto "
                 "continua escuro, então pede fundo claro.")
    with s2:
        st.segmented_control(
            "Logo", list(SAIDA_LOGO), format_func=SAIDA_LOGO.get,
            selection_mode="multi", default=["com-logo", "sem-logo"],
            key="gg_saida_logo")
    with s3:
        formatos = st.segmented_control(
            "Formato", list(SAIDA_FORMATO), format_func=SAIDA_FORMATO.get,
            selection_mode="multi", default=["png", "svg"], key="gg_saida_formato",
            help="PNG para WhatsApp, slide e documento. SVG é vetor, para "
                 "quem vai editar depois.") or []

    # Ordem fixa, igual à dos seletores, seja qual for a ordem do clique.
    fundos = [f for f in SAIDA_FUNDO if f in fundos]
    logos = [l for l in SAIDA_LOGO if l in logos]
    formatos = [f for f in SAIDA_FORMATO if f in formatos]

    escala = 2
    if "png" in formatos:
        escala = st.radio(
            "Tamanho do PNG", list(ESCALAS_EXPORT), horizontal=True,
            index=list(ESCALAS_EXPORT).index(2), key="gg_escala",
            format_func=lambda e: f"{e}× {ESCALAS_EXPORT[e]}")

    arquivos = [(slug_arquivo(titulo, tipo, formato, f"{logo}_{fundo}"),
                 fundo, logo, formato)
                for fundo in fundos for logo in logos for formato in formatos]
    if not arquivos:
        st.info("Marque pelo menos uma opção de fundo, de logo e de formato.")
        st.stop()

    assinatura = json.dumps({
        "logo": _marca_da_logo(identidade), "tipo": tipo,
        "categorias": categorias, "series": selecao, "opcoes": opcoes,
        "escala": escala, "arquivos": arquivos,
    }, sort_keys=True, ensure_ascii=False)
    if len(arquivos) == 1:
        nome, _, _, formato = arquivos[0]
        st.download_button(
            f"Baixar {SAIDA_FORMATO[formato]}", _arquivos(assinatura),
            file_name=nome, mime=MIMES_SAIDA[formato],
            use_container_width=True, type="primary")
        st.caption(nome)
    else:
        st.download_button(
            f"Baixar {len(arquivos)} arquivos (.zip)", _arquivos(assinatura),
            file_name=slug_arquivo(titulo, tipo, "zip"), mime="application/zip",
            use_container_width=True, type="primary")
        st.caption("Uma opção marcada em cada grupo baixa o arquivo direto, "
                   "sem zip.")
