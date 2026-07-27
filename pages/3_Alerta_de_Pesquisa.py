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
import os
import sys
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
    gerar_texto_alerta_pesquisa,
)
from graficos_pesquisa_core import (
    gerar_grafico_pesquisa,
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
LEITURA_PDF = [
    "Auto (texto se tiver; imagem se for scan)",
    "Texto (PyMuPDF)",
    "Imagem (Gemini visão)",
]

CHAVES_PESQUISA = ("alerta_payload", "alerta_texto", "alerta_png", "alerta_cenario_idx")


def _limpar(limpar_fonte: bool = False):
    alvos = list(CHAVES_PESQUISA)
    if limpar_fonte:
        alvos += ["alerta_texto_fonte", "alerta_url", "alerta_pdf"]
    for chave in alvos:
        st.session_state.pop(chave, None)
    for chave in [k for k in st.session_state if k.startswith("alerta_item_")]:
        st.session_state.pop(chave, None)


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
    st.caption(f"Logado como {name or username}")
    authenticator.logout("Sair", "sidebar")
    if st.button("Limpar tudo", use_container_width=True):
        _limpar(limpar_fonte=True)
        st.rerun()

if not montserrat_disponivel():
    st.warning("Montserrat não encontrada em fontes/. O gráfico sai na fonte padrão, "
               "fora da tipografia da casa.")


# ── 1. fonte ──────────────────────────────────────────────────────────────────

st.markdown('<div class="ge-rule">1. Dados da pesquisa</div>', unsafe_allow_html=True)

col_txt, col_cfg = st.columns([2, 1])

with col_txt:
    texto_fonte = st.text_area(
        "Texto da notícia, release ou PDF lido",
        key="alerta_texto_fonte", height=210,
        placeholder="Cole aqui o material da pesquisa…",
    )
    url_original = st.text_input("Link da fonte (opcional)", key="alerta_url")

with col_cfg:
    st.caption("Foco da extração — deixe em branco se o material tiver só uma pesquisa.")
    foco_cargo = st.selectbox("Cargo", [""] + POLLING_MANUAL_CARGOS, key="alerta_foco_cargo")
    foco_uf = st.selectbox("UF", [""] + ["BR"] + UFS, key="alerta_foco_uf")
    foco_turno = st.selectbox("Turno", [""] + POLLING_MANUAL_TURNOS, key="alerta_foco_turno")

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
        p_fim = c3.number_input("Página final", 1, n_pag, min(n_pag, 4), key="alerta_pag_fim")
        if st.button("Ler PDF para texto"):
            paginas = list(range(int(p_ini) - 1, int(p_fim)))
            with st.spinner("Lendo o PDF…"):
                try:
                    st.session_state["alerta_texto_fonte"] = _processar_pdf(
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
                payload = extrair_dados_polling_gemini(
                    st.session_state["alerta_texto_fonte"],
                    url_original or "",
                    escopo={"cargo": foco_cargo, "uf": foco_uf, "turno": foco_turno},
                )
                # A matriz tolera o nome como veio; uma peça publicada não.
                # Grafia canônica (partículas em minúscula, siglas conhecidas)
                # já aqui, pra você revisar o nome que vai sair no gráfico.
                for cen in payload.get("cenarios") or []:
                    for item in cen.get("itens") or []:
                        item["candidato"] = normalizar_nome_candidato(item.get("candidato"))
                        item["partido"] = normalizar_partido(item.get("partido"))
                _limpar()
                st.session_state["alerta_payload"] = payload
                st.rerun()
            except Exception as exc:
                st.error(f"Falha na extração: {exc}")


payload = st.session_state.get("alerta_payload")
if not payload:
    st.info("Extraia os dados para liberar a revisão, o gráfico e o alerta.")
    st.stop()


# ── 2. revisão ────────────────────────────────────────────────────────────────

st.markdown('<div class="ge-rule">2. Revisão</div>', unsafe_allow_html=True)
st.caption("O que o Gemini não achou fica em branco de propósito. Complete na mão: "
           "nada aqui é preenchido por suposição.")

cenarios = payload.get("cenarios") or []
rotulos_cen = [
    f"{i + 1}. {c.get('scenario_label') or i + 1} "
    f"({(c.get('cargo') or '').capitalize()} {(c.get('uf') or '')} {(c.get('turno') or '').upper()})"
    for i, c in enumerate(cenarios)
]
idx = 0
if len(cenarios) > 1:
    idx = st.radio("Cenário", range(len(cenarios)), format_func=lambda i: rotulos_cen[i],
                   key="alerta_cenario_idx", horizontal=True)
cenario = cenarios[idx] if cenarios else {"itens": []}

m1, m2, m3, m4 = st.columns(4)
payload["instituto"] = m1.text_input("Instituto", payload.get("instituto") or "")
payload["registro_tse"] = m2.text_input("Registro TSE", payload.get("registro_tse") or "")
payload["data_campo"] = m3.text_input("Data final de campo (AAAA-MM-DD)",
                                      payload.get("data_campo") or "")
payload["amostra"] = m4.number_input("Amostra", 0, 200000,
                                     int(payload.get("amostra") or 0), step=50)
m5, m6, m7 = st.columns(3)
payload["margem_erro"] = m5.number_input(
    "Margem de erro (p.p.)", 0.0, 100.0, float(payload.get("margem_erro") or 0.0), step=0.1)
confianca_txt = m6.text_input("Nível de confiança (%)",
                              "" if payload.get("confianca") is None else str(payload["confianca"]))
payload["confianca"] = normalizar_percentual_resultado(confianca_txt)
cargo_atual = (cenario.get("cargo") or payload.get("cargo") or "governador")
uf_atual = (cenario.get("uf") or payload.get("uf") or "BR")
m7.text_input("Cargo e UF do cenário", f"{cargo_atual} · {uf_atual}", disabled=True)

if payload.get("amostra") == 0:
    payload["amostra"] = None

st.caption("Itens do cenário — desmarque para tirar do gráfico e do texto.")
itens_editados = []
for i, item in enumerate(cenario.get("itens") or []):
    c_on, c_nome, c_part, c_pct, c_tipo = st.columns([0.5, 3, 1.2, 1.2, 1.6])
    ligado = c_on.checkbox("", True, key=f"alerta_item_on_{idx}_{i}",
                           label_visibility="collapsed")
    nome = c_nome.text_input("Candidato", item.get("candidato") or "",
                             key=f"alerta_item_nome_{idx}_{i}", label_visibility="collapsed")
    partido = c_part.text_input("Partido", item.get("partido") or "",
                                key=f"alerta_item_part_{idx}_{i}", label_visibility="collapsed")
    pct = c_pct.number_input("%", 0.0, 100.0, float(item.get("percentual") or 0.0),
                             step=0.1, key=f"alerta_item_pct_{idx}_{i}",
                             label_visibility="collapsed")
    tipo_atual = item.get("tipo") or classificar_tipo_resultado_manual(nome)
    tipo = c_tipo.selectbox("Tipo", ["candidato", "nao_valido"],
                            index=0 if tipo_atual == "candidato" else 1,
                            key=f"alerta_item_tipo_{idx}_{i}", label_visibility="collapsed")
    if ligado and normalizar_texto_simples(nome):
        itens_editados.append({"candidato": nome, "partido": partido,
                               "percentual": pct, "tipo": tipo})

soma = sum(i["percentual"] for i in itens_editados)
if itens_editados:
    st.caption(f"Soma dos itens marcados: {soma:.1f}%".replace(".", ","))
    if soma > 105:
        st.warning("Soma acima de 105%. Confira se não entrou mais de um cenário na mesma lista.")

if not itens_editados:
    st.error("Nenhum item marcado. Marque ao menos um para gerar o gráfico e o texto.")
    st.stop()

cenario_final = dict(cenario, itens=itens_editados)


# ── 3. gráfico e 4. alerta ────────────────────────────────────────────────────

col_g, col_a = st.columns(2)

with col_g:
    st.markdown('<div class="ge-rule">3. Gráfico</div>', unsafe_allow_html=True)

    o1, o2 = st.columns(2)
    orientacao = o1.radio("Orientação", ["vertical", "horizontal"], horizontal=True,
                          key="alerta_orientacao")
    incluir_logo = o2.checkbox("Logo da Eixo", True, key="alerta_logo")
    escala_cheia = st.checkbox(
        "Escala de 0 a 100%", True, key="alerta_escala",
        help="Ligado, todo gráfico usa a mesma escala e dois gráficos ficam comparáveis. "
             "Desligado, o topo aperta até um pouco acima do maior valor, o que ajuda "
             "quando a disputa é fragmentada. A base fica no zero nos dois casos.")

    titulo_grafico = st.text_input("Título do gráfico",
                                   titulo_padrao(payload, cenario_final),
                                   key="alerta_titulo")
    rodape_grafico = st.text_area("Ficha técnica (rodapé)", rodape_padrao(payload),
                                  key="alerta_rodape", height=80)

    try:
        png = gerar_grafico_pesquisa(
            titulo_grafico, itens_editados, rodape_grafico,
            orientacao=orientacao, incluir_logo=incluir_logo, escala_cheia=escala_cheia,
        )
        st.image(png, use_container_width=True)
        st.download_button("Baixar PNG", png, file_name=slug_arquivo(payload, cenario_final),
                           mime="image/png", use_container_width=True)
    except Exception as exc:
        st.error(f"Falha ao gerar o gráfico: {exc}")

with col_a:
    st.markdown('<div class="ge-rule">4. Alerta</div>', unsafe_allow_html=True)

    if st.button("Gerar texto do alerta", type="primary", use_container_width=True):
        with st.spinner("Redigindo…"):
            try:
                st.session_state["alerta_texto"] = gerar_texto_alerta_pesquisa(
                    payload, cenario_final,
                    gerar_conteudo=gerar_conteudo_gemini, modelo=GEMINI_MODEL,
                )
            except Exception as exc:
                st.error(f"Falha ao gerar o texto: {exc}")

    if st.session_state.get("alerta_texto"):
        texto = st.text_area("Texto (edite à vontade)", st.session_state["alerta_texto"],
                             height=230, key="alerta_texto_edit")
        titulo_alerta = st.text_input("Título do alerta", titulo_grafico,
                                      key="alerta_titulo_envio")
        link_alerta = st.text_input("Link", st.session_state.get("alerta_url") or "",
                                    key="alerta_link_envio")

        final = compilar_alerta_pesquisa(
            texto, titulo_alerta,
            uf=(cenario_final.get("uf") or payload.get("uf") or ""),
            link=link_alerta,
            data_envio=datetime.now(BRT).strftime("%d/%m/%Y"),
        )
        st.caption("Prévia do envio")
        st.code(final, language=None)
    else:
        st.info("Os números acima já estão prontos. Clique em gerar para escrever o texto.")
