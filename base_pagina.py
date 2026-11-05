"""Começo comum de toda página: configuração da aba, logo, login e estilo compartilhado.

Cada página chama `iniciar("Título")` como primeiro comando do Streamlit e, depois
do próprio CSS, `authenticator = exigir_login()`. Mudou o login, muda aqui.
"""
import os

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

RAIZ = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(RAIZ, "logo_eixo_gov_magenta.png")
ICONE = os.path.join(RAIZ, "icone_eixo.png")

# Só entra na tela de login (antes de alguém entrar): caixa estreita no centro,
# título marinho com o rótulo vinho em cima e botão vinho, como o resto do painel.
CSS_TELA_LOGIN = (
    "<style>"
    '[data-testid="stMain"] [data-testid="stForm"] { max-width: 420px; margin: 9vh auto 0 !important; padding: 30px 32px 26px !important; }'
    '[data-testid="stMain"] [data-testid="stForm"] h3 { color: #192D4E !important; font-weight: 800 !important; font-size: 28px !important; padding: 0 0 6px !important; }'
    '[data-testid="stMain"] [data-testid="stForm"] h3::before { content: "EixoGov"; display: block; font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: #962E4D; margin-bottom: 4px; }'
    '[data-testid="stMain"] [data-testid="stForm"] [data-testid="stTextInput"] > label p { font-size: 0.72rem !important; font-weight: 600 !important; letter-spacing: .04em !important; text-transform: uppercase !important; color: #4E5A6E !important; }'
    '[data-testid="stMain"] [data-testid="stForm"] [data-testid="stElementContainer"]:has([data-testid="stFormSubmitButton"]), [data-testid="stMain"] [data-testid="stForm"] [data-testid="stFormSubmitButton"] { width: 100% !important; margin-top: 6px; }'
    '[data-testid="stMain"] [data-testid="stForm"] [data-testid="stFormSubmitButton"] > button { width: 100% !important; min-height: 42px !important; background: #962E4D !important; border-color: #962E4D !important; }'
    '[data-testid="stMain"] [data-testid="stForm"] [data-testid="stFormSubmitButton"] > button p { color: #fff !important; font-weight: 700 !important; }'
    '[data-testid="stMain"] [data-testid="stForm"] [data-testid="stFormSubmitButton"] > button:hover { background: #7A2640 !important; }'
    "</style>"
)

CAMPOS_LOGIN = {"Form name": "Entrar", "Username": "Usuário", "Password": "Senha", "Login": "Entrar"}


def iniciar(titulo: str) -> None:
    """Título e ícone da aba do navegador, layout largo e a logo no topo da barra lateral."""
    st.set_page_config(page_title=titulo, page_icon=ICONE, layout="wide")
    st.logo(LOGO, size="large")


def _config_login():
    try:
        if "AUTH_CONFIG" in st.secrets:
            return yaml.load(st.secrets["AUTH_CONFIG"], Loader=SafeLoader)
    except Exception:
        pass
    for caminho in ("config.yaml", os.path.join(RAIZ, "config.yaml")):
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                return yaml.load(f, Loader=SafeLoader)
    return None


def exigir_login():
    """Desenha o login e para a página até alguém entrar. Devolve o autenticador (para o Sair)."""
    cfg = _config_login()
    if not cfg:
        st.error("O login deste painel não está configurado. Avise a equipe de dados.")
        st.stop()
    autenticador = stauth.Authenticate(
        cfg["credentials"],
        cfg["cookie"]["name"],
        cfg["cookie"]["key"],
        cfg["cookie"]["expiry_days"],
    )
    # O estilo do login e o das páginas vão antes do gate: sem ninguém logado o
    # st.stop() abaixo encerra a página e nada depois dele roda.
    from menu_paginas import CSS_MENU
    from ui_login import CSS_LOGIN
    st.markdown(CSS_LOGIN, unsafe_allow_html=True)
    st.markdown(CSS_MENU, unsafe_allow_html=True)

    if not st.session_state.get("authentication_status"):
        st.markdown(CSS_TELA_LOGIN, unsafe_allow_html=True)
    autenticador.login(location="main", fields=CAMPOS_LOGIN)
    estado = st.session_state.get("authentication_status")
    if estado is False:
        st.error("Usuário ou senha incorretos.")
        st.stop()
    if estado is None:
        st.stop()
    return autenticador
