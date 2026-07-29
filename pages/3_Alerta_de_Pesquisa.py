"""
Alerta de Pesquisa: os dados da pesquisa entram uma vez e saem gráfico e texto.

Fecha num lugar só o que hoje é feito em dois: o gráfico era montado à parte e o
texto no Gerador de Envios. A entrada é a mesma do Polling Manual (cola texto ou
sobe PDF, o Gemini extrai, você revisa e completa o que faltar), o gráfico sai
por código em layout fixo, e o texto usa o mesmo prompt de pesquisa eleitoral do
Gerador de Envios.

Esta página não grava nada nas matrizes. Quem cadastra pesquisa continua sendo o
Polling Manual; aqui é só produção de peça de divulgação.
"""

from datetime import datetime, timedelta, timezone
import inspect
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from polling_extracao_core import (
    GEMINI_MODEL,
    POLLING_MANUAL_CARGOS,
    POLLING_MANUAL_TURNOS,
    UFS,
    classificar_tipo_resultado_manual,
    definir_api_key,
    extrair_dados_polling_gemini,
    extrair_pdf_imagem_padrao,
    extrair_texto_pdf_bytes,
    gerar_conteudo_gemini,
    normalizar_percentual_resultado,
    normalizar_texto_simples,
    render_pdf_page_png,
)
from polling_manual_core import normalizar_nome_candidato, normalizar_partido
from alerta_pesquisa_core import (
    compilar_alerta_pesquisa,
    encurtar_link,
    gerar_texto_alerta_pesquisa,
    normalizar_link,
    padronizar_itens_alerta,
    somar_cenarios,
)
from graficos_pesquisa_core import (
    ESCALAS_EXPORT,
    gerar_grafico_pesquisa,
    periodo_campo_br,
    resolucao,
    montserrat_disponivel,
    rodape_padrao,
    slug_arquivo,
    titulo_padrao,
)

st.set_page_config(page_title="Alerta de Pesquisa", layout="wide")

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
.ge-alerta-cenario {
    background: #192D4E; color: #fff; border-left: 4px solid #962E4D;
    padding: 10px 14px; margin: 4px 0 14px; font-size: 12.5px; line-height: 1.5;
}
/* Faixa de grupo cargo — turno: separa visualmente presidente/governador/
   senador e 1º/2º turno quando vêm no mesmo material. */
.ge-grupo {
    background: #192D4E; color: #fff; border-left: 6px solid #962E4D;
    padding: 13px 20px; margin: 28px 0 6px;
    font-size: 18px; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase;
}
/* Rótulo de cada cenário dentro do grupo. */
.ge-cenario-lbl {
    font-size: 14px; font-weight: 700; letter-spacing: 0.09em; text-transform: uppercase;
    color: #962E4D; margin: 16px 0 4px; padding-bottom: 6px;
    border-bottom: 1px solid #DADAD4;
}
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
# Os cores não importam Streamlit: a chave dos Secrets entra por aqui.
definir_api_key(GEMINI_API_KEY)

BRT = timezone(timedelta(hours=-3))
LOGO_PATH = str(ROOT_DIR / "Marca_eixo_vetor_Logo horizontal magenta.png")
LEITURA_PDF = [
    "Auto (texto se tiver; imagem se for scan)",
    "Texto (PyMuPDF)",
    "Imagem (Gemini visão)",
]

CHAVES_PESQUISA = ("alerta_payload", "alerta_texto", "alerta_png",
                   "alerta_cenario_idx", "alerta_cenario_visto")

# Widgets cujo valor inicial é derivado do cenário escolhido. O Streamlit ignora
# o valor padrão de um widget que já existe na sessão: sem apagar estas chaves,
# trocar de cenário mantinha na tela o título, o rodapé e o texto do cenário
# anterior — era isso que fazia o gráfico sair "de governador" depois de mudar
# para senador.
CHAVES_DERIVADAS = ("alerta_titulo", "alerta_rodape", "alerta_titulo_envio",
                    "alerta_texto", "alerta_texto_edit")


def _limpar(limpar_fonte: bool = False):
    alvos = list(CHAVES_PESQUISA) + list(CHAVES_DERIVADAS)
    if limpar_fonte:
        alvos += ["alerta_texto_fonte", "alerta_texto_pendente", "alerta_url",
                  "alerta_pdf"]
    for chave in alvos:
        st.session_state.pop(chave, None)
    # Itens e soma de cenários apontam para a extração anterior: índice guardado
    # aqui pode nem existir na pesquisa nova.
    for chave in [k for k in st.session_state
                  if k.startswith(("alerta_item_", "alerta_soma_"))]:
        st.session_state.pop(chave, None)


@st.cache_data(show_spinner=False, ttl=3600)
def _link_curto(url: str) -> str:
    """Encurta no TinyURL, igual ao Gerador de Envios. Em cache porque a prévia
    do envio é remontada a cada interação da página, e sem isso cada clique
    viraria uma chamada de rede."""
    return encurtar_link(url)


@st.cache_data(show_spinner=False, max_entries=6)
def _pacote_graficos(assinatura: str) -> bytes:
    """Zip com o mesmo gráfico em quatro arquivos: PNG e SVG, com e sem logo.

    A entrada é uma string JSON porque o download_button precisa dos bytes
    prontos a cada rerun, e sem cache seriam quatro desenhos do matplotlib a
    cada clique da página. Assinatura igual, arquivo servido da memória.
    """
    cfg = json.loads(assinatura)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_saida:
        for sufixo, com_logo in (("com-logo", True), ("sem-logo", False)):
            for formato in ("png", "svg"):
                zip_saida.writestr(
                    cfg["nomes"][f"{sufixo}_{formato}"],
                    gerar_grafico_pesquisa(
                        cfg["titulo"], cfg["itens"], cfg["rodape"],
                        orientacao=cfg["orientacao"], incluir_logo=com_logo,
                        escala_cheia=cfg["escala_cheia"],
                        fundo_transparente=cfg["fundo_transparente"],
                        escala=cfg["escala"], formato=formato),
                )
    return buffer.getvalue()


def _processar_pdf(pdf_bytes: bytes, modo: str, paginas: list[int]) -> str:
    """Mesma regra do Polling Manual: PDF de gráfico de barra perde o nome do
    candidato no modo texto, então o Auto cai pra imagem quando vem pouca coisa."""
    if modo == "Texto (PyMuPDF)":
        return extrair_texto_pdf_bytes(pdf_bytes, page_indices=paginas)
    if modo == "Imagem (Gemini visão)":
        return extrair_pdf_imagem_padrao(
            [render_pdf_page_png(pdf_bytes, i, zoom=3.0) for i in paginas])
    txt = extrair_texto_pdf_bytes(pdf_bytes, page_indices=paginas)
    if txt and len(txt.strip()) >= 800:
        return txt
    return extrair_pdf_imagem_padrao(
        [render_pdf_page_png(pdf_bytes, i, zoom=3.0) for i in paginas])


st.markdown('<div class="ge-hero"><div class="ge-hero-title">Alerta de Pesquisa</div></div>',
            unsafe_allow_html=True)

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
        'Cole a pesquisa ou suba o PDF do instituto e gere o '
        '<strong>gráfico</strong> e o <strong>texto do alerta</strong>.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    if not montserrat_disponivel():
        st.warning("Montserrat não encontrada em fontes/. O gráfico sai fora da "
                   "tipografia da casa.")
    st.markdown("---")
    if st.button("🧹 Limpar tudo", use_container_width=True,
                 help="Zera a pesquisa da tela (texto, extração, gráfico e alerta) "
                      "pra começar do zero"):
        _limpar(limpar_fonte=True)
        st.rerun()
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** "
               f"({st.session_state.get('username', '')})")
    if _auth_cfg:
        authenticator.logout("Sair", "sidebar")


# ── abas ──────────────────────────────────────────────────────────────────────
# Os quatro passos são abas, e não uma coluna só: a revisão de uma disputa
# grande passa de 12 linhas de formulário, e empilhado com o resto exige rolar
# a página inteira pra conferir um número. Como as abas do Streamlit renderizam
# tudo no mesmo run, o estado corre entre elas por variável comum — por isso
# nenhuma etapa usa st.stop(), que mataria as abas seguintes.

aba_dados, aba_revisao, aba_grafico, aba_alerta = st.tabs(
    ["1. Dados", "2. Revisão", "3. Gráfico", "4. Alerta"])


with aba_dados:
    # O Streamlit proíbe escrever na chave de um widget depois que ele existe, e
    # a leitura do PDF acontece abaixo do campo de texto. Então o resultado entra
    # numa chave pendente e é transferido aqui, antes do widget nascer.
    if "alerta_texto_pendente" in st.session_state:
        st.session_state["alerta_texto_fonte"] = st.session_state.pop(
            "alerta_texto_pendente")

    col_txt, col_cfg = st.columns([2, 1])

    with col_txt:
        st.text_area(
            "Texto da notícia, release ou PDF lido",
            key="alerta_texto_fonte", height=240,
            placeholder="Cole aqui o material da pesquisa…",
        )
        url_original = st.text_input("Link da fonte (opcional)", key="alerta_url")

    with col_cfg:
        st.caption("Foco da extração — deixe em branco se o material tiver só uma "
                   "pesquisa.")
        foco_cargo = st.selectbox("Cargo", [""] + POLLING_MANUAL_CARGOS,
                                  key="alerta_foco_cargo")
        foco_uf = st.selectbox("UF", [""] + ["BR"] + UFS, key="alerta_foco_uf")
        foco_turno = st.selectbox("Turno", [""] + POLLING_MANUAL_TURNOS,
                                  key="alerta_foco_turno")

    with st.expander("Extrair texto de PDF"):
        pdf = st.file_uploader("Relatório do instituto", type=["pdf"], key="alerta_pdf")
        if pdf:
            import fitz
            with fitz.open(stream=pdf.getvalue(), filetype="pdf") as doc:
                n_pag = doc.page_count
            st.caption(f"{n_pag} página(s). Recorte: PDF inteiro no modo Auto costuma "
                       "escolher texto e devolver número sem nome.")
            c1, c2, c3 = st.columns(3)
            modo = c1.selectbox("Modo de leitura", LEITURA_PDF, key="alerta_modo_pdf")
            p_ini = c2.number_input("Página inicial", 1, n_pag, 1, key="alerta_pag_ini")
            p_fim = c3.number_input("Página final", 1, n_pag, min(n_pag, 4),
                                    key="alerta_pag_fim")
            if st.button("Ler PDF para texto"):
                paginas = list(range(int(p_ini) - 1, int(p_fim)))
                with st.spinner("Lendo o PDF…"):
                    try:
                        st.session_state["alerta_texto_pendente"] = _processar_pdf(
                            pdf.getvalue(), modo, paginas)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Falha ao ler o PDF: {exc}")

    if st.button("Extrair dados", type="primary"):
        if not (st.session_state.get("alerta_texto_fonte") or "").strip():
            st.error("Cole o texto da pesquisa ou leia um PDF primeiro.")
        else:
            with st.spinner("Extraindo com o Gemini…"):
                try:
                    novo = extrair_dados_polling_gemini(
                        st.session_state["alerta_texto_fonte"], url_original or "",
                        escopo={"cargo": foco_cargo, "uf": foco_uf, "turno": foco_turno},
                    )
                    # A matriz tolera o nome como veio; uma peça publicada não.
                    # Aqui também entra o rótulo padrão dos não válidos
                    # (NS/NR e Brancos/Nulos), que vale só nesta página.
                    for cen in novo.get("cenarios") or []:
                        for item in cen.get("itens") or []:
                            item["candidato"] = normalizar_nome_candidato(item.get("candidato"))
                            item["partido"] = normalizar_partido(item.get("partido"))
                        cen["itens"] = padronizar_itens_alerta(cen.get("itens") or [])
                    _limpar()
                    st.session_state["alerta_payload"] = novo
                    st.rerun()
                except Exception as exc:
                    st.error(f"Falha na extração: {exc}")

    if st.session_state.get("alerta_payload"):
        st.success("Dados extraídos. Confira na aba **2. Revisão**.")


payload = st.session_state.get("alerta_payload")
itens_editados: list[dict] = []
cenario_final: dict = {}
AVISO_SEM_DADOS = "Extraia os dados na aba **1. Dados** para liberar esta etapa."


with aba_revisao:
    if not payload:
        st.info(AVISO_SEM_DADOS)
    else:
        st.caption("O que o Gemini não achou fica em branco de propósito. Complete "
                   "na mão: nada aqui é preenchido por suposição.")

        cenarios = payload.get("cenarios") or []
        rotulos_cen = [
            f"{i + 1}. {c.get('scenario_label') or i + 1} "
            f"({(c.get('cargo') or '').capitalize()} {(c.get('uf') or '')} "
            f"{(c.get('turno') or '').upper()})"
            for i, c in enumerate(cenarios)
        ]
        idx = 0
        if len(cenarios) > 1:
            idx = st.selectbox("Cenário", range(len(cenarios)),
                               format_func=lambda i: rotulos_cen[i],
                               key="alerta_cenario_idx")
        cenario = cenarios[idx] if cenarios else {"itens": []}

        # Senado tem duas vagas e o eleitor cita dois nomes. Parte dos institutos
        # publica isso consolidado numa pergunta só (AtlasIntel: "cada
        # entrevistado citou o primeiro e o segundo votos"), parte publica o 1º e
        # o 2º voto em cenários separados (Quaest), e aí a leitura da disputa é a
        # soma dos dois. Não dá pra decidir por código qual é qual: quem lê a
        # matéria escolhe aqui.
        somar = []
        if len(cenarios) > 1:
            # Sobra de uma extração anterior com mais cenários derrubaria a
            # página no cenarios[i] logo abaixo.
            st.session_state[f"alerta_soma_{idx}"] = [
                i for i in st.session_state.get(f"alerta_soma_{idx}", [])
                if isinstance(i, int) and 0 <= i < len(cenarios) and i != idx
            ]
            somar = st.multiselect(
                "Somar com outro cenário (Senado de 2 vagas)",
                [i for i in range(len(cenarios)) if i != idx],
                format_func=lambda i: rotulos_cen[i],
                key=f"alerta_soma_{idx}",
                help="Use quando a fonte publicar o 1º e o 2º voto em cenários "
                     "separados, cada um somando ~100%. Some só o que for a mesma "
                     "pergunta repetida: cenário com lista de candidatos diferente "
                     "não é 2º voto.",
            )

        # Trocar de cenário (ou de combinação) tem que zerar título, rodapé e
        # texto: o Streamlit preserva o valor do widget pela chave, e sem isso a
        # tela fica com a peça do cenário anterior.
        combo = (idx, tuple(somar))
        if st.session_state.get("alerta_cenario_visto") != combo:
            st.session_state["alerta_cenario_visto"] = combo
            for chave in CHAVES_DERIVADAS:
                st.session_state.pop(chave, None)

        with st.expander("Ficha técnica", expanded=True):
            m1, m2, m3 = st.columns(3)
            payload["instituto"] = m1.text_input("Instituto", payload.get("instituto") or "")
            payload["registro_tse"] = m2.text_input("Registro TSE",
                                                    payload.get("registro_tse") or "")
            payload["amostra"] = m3.number_input("Amostra", 0, 200000,
                                                 int(payload.get("amostra") or 0), step=50)
            d1, d2, d3 = st.columns(3)
            payload["data_campo_inicio"] = d1.text_input(
                "Início do campo (AAAA-MM-DD)", payload.get("data_campo_inicio") or "")
            payload["data_campo"] = d2.text_input("Fim do campo (AAAA-MM-DD)",
                                                  payload.get("data_campo") or "")
            periodo_txt = periodo_campo_br(payload.get("data_campo_inicio"),
                                           payload.get("data_campo"))
            d3.text_input("Como sai no gráfico", f"Campo: {periodo_txt}" if periodo_txt
                          else "", disabled=True)
            m5, m6, m7 = st.columns(3)
            payload["margem_erro"] = m5.number_input(
                "Margem de erro (p.p.)", 0.0, 100.0,
                float(payload.get("margem_erro") or 0.0), step=0.1)
            confianca_txt = m6.text_input(
                "Nível de confiança (%)",
                "" if payload.get("confianca") is None else str(payload["confianca"]))
            payload["confianca"] = normalizar_percentual_resultado(confianca_txt)
            m7.text_input("Cargo e UF do cenário",
                          f"{cenario.get('cargo') or payload.get('cargo') or ''} · "
                          f"{cenario.get('uf') or payload.get('uf') or ''}", disabled=True)

            # O number_input não tem estado "vazio": devolve 0. Zero aqui é campo
            # em branco, não medida — sem isto o rodapé publicaria "±0 p.p.".
            if not payload.get("amostra"):
                payload["amostra"] = None
            if not payload.get("margem_erro"):
                payload["margem_erro"] = None

            FICHA = [("instituto", "instituto"), ("registro_tse", "registro TSE"),
                     ("data_campo", "data de campo"), ("amostra", "amostra"),
                     ("margem_erro", "margem de erro"), ("confianca", "nível de confiança")]
            faltando = [rot for chave, rot in FICHA if not payload.get(chave)]
            if faltando:
                st.warning("Falta " + ", ".join(faltando) +
                           ". Esses campos não entram no rodapé nem no texto.")

        if somar:
            itens_base = somar_cenarios([cenario] + [cenarios[i] for i in somar])
            st.caption("Itens do cenário somado — desmarque para tirar do gráfico "
                       "e do texto.")
        else:
            itens_base = cenario.get("itens") or []
            st.caption("Itens do cenário — desmarque para tirar do gráfico e do texto.")

        # A combinação entra na chave do widget: chave repetida faria o Streamlit
        # manter o número do cenário anterior no campo.
        cmb = "-".join(str(i) for i in [idx] + list(somar))
        for i, item in enumerate(itens_base):
            c_on, c_nome, c_part, c_pct, c_tipo = st.columns([0.5, 3, 1.2, 1.2, 1.6])
            ligado = c_on.checkbox("", True, key=f"alerta_item_on_{cmb}_{i}",
                                   label_visibility="collapsed")
            nome = c_nome.text_input("Candidato", item.get("candidato") or "",
                                     key=f"alerta_item_nome_{cmb}_{i}",
                                     label_visibility="collapsed")
            partido = c_part.text_input("Partido", item.get("partido") or "",
                                        key=f"alerta_item_part_{cmb}_{i}",
                                        label_visibility="collapsed")
            pct = c_pct.number_input("%", 0.0, 100.0, float(item.get("percentual") or 0.0),
                                     step=0.1, key=f"alerta_item_pct_{cmb}_{i}",
                                     label_visibility="collapsed")
            tipo_atual = item.get("tipo") or classificar_tipo_resultado_manual(nome)
            tipo = c_tipo.selectbox("Tipo", ["candidato", "nao_valido"],
                                    index=0 if tipo_atual == "candidato" else 1,
                                    key=f"alerta_item_tipo_{cmb}_{i}",
                                    label_visibility="collapsed")
            if ligado and normalizar_texto_simples(nome):
                itens_editados.append({"candidato": nome, "partido": partido,
                                       "percentual": pct, "tipo": tipo})

        if itens_editados:
            soma = sum(i["percentual"] for i in itens_editados)
            st.caption(f"Soma dos itens marcados: {soma:.1f}%".replace(".", ","))
            if somar:
                # Dois votos por entrevistado: o total esperado é perto de 200%.
                if not 150 <= soma <= 250:
                    st.warning("A soma ficou longe dos 200% esperados de dois votos "
                               "por entrevistado. Confira se os cenários somados são "
                               "mesmo o 1º e o 2º voto da mesma pergunta.")
            elif soma > 105:
                st.warning("Soma acima de 105%. Confira se não entrou mais de um "
                           "cenário na mesma lista.")
            cenario_final = dict(cenario, itens=itens_editados)
            if somar:
                cenario_final["soma_cenarios"] = [rotulos_cen[i]
                                                  for i in [idx] + list(somar)]
        else:
            st.error("Nenhum item marcado. Marque ao menos um para gerar o gráfico "
                     "e o texto.")


with aba_grafico:
    if not itens_editados:
        st.info(AVISO_SEM_DADOS if not payload else
                "Marque ao menos um item na aba **2. Revisão**.")
    else:
        col_ctl, col_prev = st.columns([1, 2])

        with col_ctl:
            orientacao = st.radio("Orientação", ["vertical", "horizontal"],
                                  key="alerta_orientacao")
            incluir_logo = st.checkbox(
                "Logo da Eixo na prévia", True, key="alerta_logo",
                help="Só muda a prévia: o arquivo baixado sai sempre nas duas "
                     "versões, com e sem logo.")
            fundo_transparente = st.checkbox(
                "Fundo transparente", True, key="alerta_fundo",
                help="Sem o retângulo gelo por baixo, o gráfico assenta em slide "
                     "ou story de qualquer cor. O texto continua escuro, então "
                     "pede fundo claro.")
            escala_cheia = st.checkbox(
                "Escala de 0 a 100%", True, key="alerta_escala",
                help="Ligado, todo gráfico usa a mesma escala e dois gráficos ficam "
                     "comparáveis. Desligado, o topo aperta até um pouco acima do "
                     "maior valor. A base fica no zero nos dois casos.")
            titulo_grafico = st.text_input("Título do gráfico",
                                           titulo_padrao(payload, cenario_final),
                                           key="alerta_titulo")
            rodape_grafico = st.text_area("Ficha técnica (rodapé)",
                                          rodape_padrao(payload),
                                          key="alerta_rodape", height=90)

        try:
            with col_prev:
                st.image(gerar_grafico_pesquisa(
                    titulo_grafico, itens_editados, rodape_grafico,
                    orientacao=orientacao, incluir_logo=incluir_logo,
                    escala_cheia=escala_cheia,
                    fundo_transparente=fundo_transparente),
                    use_container_width=True)

            st.markdown("---")
            e1, e2 = st.columns([2, 1])
            escala = e1.radio(
                "Tamanho do PNG", list(ESCALAS_EXPORT), horizontal=True,
                index=list(ESCALAS_EXPORT).index(2), key="alerta_escala_export",
                format_func=lambda e: f"{e}× {ESCALAS_EXPORT[e]}",
            )
            larg, alt = resolucao(escala)
            e1.caption(f"Resolução: {larg} × {alt}px. O SVG é vetor: a escala não "
                       "muda nada nele.")

            # Quem monta card usa a versão com logo; quem monta slide da casa
            # usa a sem. Baixar as duas de uma vez evita voltar aqui pra clicar
            # de novo com a caixinha desmarcada.
            nomes = {
                f"{suf}_{fmt}": slug_arquivo(payload, cenario_final, fmt, suf)
                for suf in ("com-logo", "sem-logo") for fmt in ("png", "svg")
            }
            assinatura = json.dumps({
                "titulo": titulo_grafico, "rodape": rodape_grafico,
                "itens": itens_editados, "orientacao": orientacao,
                "escala_cheia": escala_cheia, "escala": escala,
                "fundo_transparente": fundo_transparente, "nomes": nomes,
            }, sort_keys=True, ensure_ascii=False)

            e2.download_button(
                "Baixar tudo (.zip)", _pacote_graficos(assinatura),
                file_name=slug_arquivo(payload, cenario_final, "zip"),
                mime="application/zip", use_container_width=True, type="primary",
                help="Quatro arquivos: PNG e SVG, cada um com e sem a logo")
            e2.caption("PNG e SVG, com e sem logo.")
        except Exception as exc:
            st.error(f"Falha ao gerar o gráfico: {exc}")


with aba_alerta:
    if not itens_editados:
        st.info(AVISO_SEM_DADOS if not payload else
                "Marque ao menos um item na aba **2. Revisão**.")
    else:
        if st.button("Gerar texto do alerta", type="primary"):
            with st.spinner("Redigindo…"):
                try:
                    st.session_state["alerta_texto"] = gerar_texto_alerta_pesquisa(
                        payload, cenario_final,
                        gerar_conteudo=gerar_conteudo_gemini, modelo=GEMINI_MODEL,
                    )
                except Exception as exc:
                    st.error(f"Falha ao gerar o texto: {exc}")

        if st.session_state.get("alerta_texto"):
            col_edit, col_prev = st.columns(2)
            with col_edit:
                texto = st.text_area("Texto (edite à vontade)",
                                     st.session_state["alerta_texto"], height=260,
                                     key="alerta_texto_edit")
                titulo_alerta = st.text_input(
                    "Título do alerta", titulo_padrao(payload, cenario_final),
                    key="alerta_titulo_envio")
                link_alerta = st.text_input("Link",
                                            st.session_state.get("alerta_url") or "",
                                            key="alerta_link_envio")
                encurtar = st.checkbox("Encurtar o link", True, key="alerta_encurtar",
                                       help="Passa pelo TinyURL, igual ao Gerador "
                                            "de Envios")

            link_final = normalizar_link(link_alerta or "")
            if link_alerta.strip() and not link_final:
                st.warning("O link parece inválido. Cole uma URL completa (http/https).")
            if link_final and encurtar:
                link_final = _link_curto(link_final)

            with col_prev:
                st.caption("Prévia do envio")
                st.code(compilar_alerta_pesquisa(
                    texto, titulo_alerta,
                    uf=(cenario_final.get("uf") or payload.get("uf") or ""),
                    link=link_final or "",
                    data_envio=datetime.now(BRT).strftime("%d/%m/%Y"),
                ), language=None)
        else:
            st.info("Os números da revisão já estão prontos. Clique em gerar para "
                    "escrever o texto.")
