"""Começo comum de toda página: configuração da aba, logo, login e estilo compartilhado.

Cada página chama `iniciar("Título")` como primeiro comando do Streamlit e, depois
do próprio CSS, `authenticator = exigir_login()`. A caixa de login vem do ui_login.py,
que é o mesmo em todos os painéis: mudou lá, copiar nos outros repos.
"""
import os

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

from ui_login import CAMPOS_LOGIN, CSS_LOGIN, ICONE, css_tela_login

RAIZ = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(RAIZ, "logo_eixo_gov_magenta.png")


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
    st.markdown(CSS_LOGIN, unsafe_allow_html=True)
    st.markdown(CSS_MENU, unsafe_allow_html=True)

    if not st.session_state.get("authentication_status"):
        st.markdown(css_tela_login("EixoGov"), unsafe_allow_html=True)
    autenticador.login(location="main", fields=CAMPOS_LOGIN)
    estado = st.session_state.get("authentication_status")
    if estado is False:
        st.error("Usuário ou senha incorretos.")
        st.stop()
    if estado is None:
        st.stop()
    return autenticador
