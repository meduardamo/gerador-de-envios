"""Folha de estilo da tela de login, a mesma em todos os painéis.

O gate de autenticação chama `st.stop()` quando ninguém entrou, então tudo o
que a tela de login mostra tem que ser desenhado antes dele. As páginas já
faziam isso com a folha da própria página, e cada app desenhava o login do seu
jeito: no painel eleitoral o campo saía com o cinza padrão do Streamlit, no
Gerador de Envios o rótulo vinha em caixa alta espaçada, que é o estilo dos
campos de trabalho daquele app. Aqui a tela de login vira uma coisa só.

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
/* O olho do campo de senha é um <span> do Material Symbols, e fica fora do
   form. Quando a folha da página força Montserrat em todo span, o ícone perde
   a fonte e imprime o nome dele ("visibility") no lugar do desenho. */
[data-testid="stIconMaterial"] {{
    font-family: 'Material Symbols Rounded' !important;
}}

/* Rótulo do campo: frase, não etiqueta. A folha do Gerador de Envios põe todo
   label em caixa alta com espaçamento, o que serve para a ficha de trabalho e
   deixa o login com cara de formulário de sistema. */
[data-testid="stForm"] [data-testid="stTextInput"] > label,
[data-testid="stForm"] [data-testid="stTextInput"] > label p {{
    font-size: 13px !important;
    font-weight: 500 !important;
    letter-spacing: 0 !important;
    text-transform: none !important;
    color: {TINTA} !important;
}}

/* A caixa branca é o wrapper do campo, não o <input>. Pintar só o input
   deixava a faixa do olho, que fica no wrapper e é mais larga, no cinza.

   São dois seletores porque os apps estão em versões diferentes do Streamlit:
   até a 1.45 o campo é BaseWeb (`data-baseweb="input"`), da 1.5x em diante é
   react-aria e o wrapper virou `stTextInputRootElement`. Manter os dois evita
   que a tela de login mude de cara quando um app atualizar antes do outro. */
[data-testid="stForm"] [data-testid="stTextInput"] div[data-baseweb="input"],
[data-testid="stForm"] [data-testid="stTextInputRootElement"] {{
    background: #FFFFFF !important;
    border: 1px solid {BORDA} !important;
    border-radius: 8px !important;
}}
[data-testid="stForm"] [data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
[data-testid="stForm"] [data-testid="stTextInputRootElement"]:focus-within {{
    border-color: {VINHO} !important;
    box-shadow: 0 0 0 1px {VINHO} !important;
}}
[data-testid="stForm"] [data-testid="stTextInput"] div[data-baseweb="base-input"] {{
    background: transparent !important;
    border: none !important;
}}
[data-testid="stForm"] [data-testid="stTextInput"] input,
[data-testid="stForm"] [data-testid="stTextInputField"] {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    min-height: 42px !important;
    font-size: 13px !important;
    color: {TINTA} !important;
}}
</style>"""
