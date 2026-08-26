"""Folha de estilo da tela de login, a mesma nas oito páginas do painel.

O gate de autenticação chama `st.stop()` quando ninguém entrou, então tudo o
que a tela de login mostra tem que ser desenhado antes dele. As páginas já
faziam isso com a folha da própria página, e o campo de texto ficava com o
cinza padrão do Streamlit em todas menos em Recandidaturas, que estilizava os
seus inputs por conta própria. Aqui o campo branco vira regra única.

As regras são presas ao `stForm` porque é dentro de um `st.form` que o
streamlit-authenticator desenha o login: assim a busca e os demais campos de
cada página seguem com o estilo que já tinham.

Uso, imediatamente antes do gate:

    st.markdown(CSS_LOGIN, unsafe_allow_html=True)
"""
from __future__ import annotations

VINHO = "#962E4D"
BORDA = "#DADAD4"
TINTA = "#111111"

CSS_LOGIN = f"""<style>
[data-testid="stForm"] [data-testid="stTextInput"] input,
[data-testid="stForm"] [data-baseweb="base-input"] {{
    background: #FFFFFF !important;
    color: {TINTA} !important;
}}
[data-testid="stForm"] [data-testid="stTextInput"] input {{
    border: 1px solid {BORDA} !important;
    border-radius: 8px !important;
    min-height: 42px !important;
    font-size: 13px !important;
}}
[data-testid="stForm"] [data-testid="stTextInput"] input:focus {{
    border-color: {VINHO} !important;
    box-shadow: 0 0 0 1px {VINHO} !important;
}}
</style>"""
