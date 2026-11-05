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
    if not st.session_state.get("authentication_status"):
        st.markdown(css_tela_login("Nome do painel"), unsafe_allow_html=True)
    authenticator.login(location="main", fields=CAMPOS_LOGIN)

`ICONE` é o "e" da marca, para o `page_icon` do `st.set_page_config`.
"""
from __future__ import annotations

import os

VINHO = "#962E4D"
BORDA = "#DADAD4"
TINTA = "#111111"

CSS_LOGIN = f"""<style>
/* O olho do campo de senha é um <span> do Material Symbols, e fica fora do
   form. Quando a folha da página força Montserrat em todo span, o ícone perde
   a fonte e imprime o nome dele ("visibility") no lugar do desenho. O mesmo
   vale para a seta de recolher a barra lateral ("keyboard_double_arrow_left"):
   as páginas repetem `[data-testid="stSidebar"] *` em blocos que entram depois
   deste, então a regra precisa de especificidade maior para não depender da
   ordem. */
[data-testid="stIconMaterial"],
span[data-testid="stIconMaterial"],
[data-testid="stSidebar"] [data-testid="stIconMaterial"] {{
    font-family: 'Material Symbols Rounded' !important;
}}

/* A caixa do login fica na cor da página: branco é só onde se digita. O
   Gerador de Envios pinta todo `stForm` de branco, o que serve para a ficha de
   trabalho apoiada sobre o fundo e deixa o login parecendo um cartão dentro de
   outro. O `:has()` prende a regra ao form que tem campo de senha, ou seja, ao
   login, e deixa os formulários de trabalho de cada página como estão. */
[data-testid="stForm"]:has(input[type="password"]) {{
    background: transparent !important;
    border: 1px solid {BORDA} !important;
    border-radius: 8px !important;
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


# O "e" da marca na aba do navegador, no lugar da coroa do Streamlit.
ICONE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icone_eixo.png")

# Textos do formulário do streamlit-authenticator em português.
CAMPOS_LOGIN = {"Form name": "Entrar", "Username": "Usuário", "Password": "Senha", "Login": "Entrar"}


def css_tela_login(rotulo: str, topo: str = "9vh") -> str:
    """Caixa estreita no centro, nome do painel em vinho sobre o "Entrar" marinho e
    botão vinho de largura inteira. Só entra antes de alguém entrar: depois do
    login os formulários de trabalho das páginas ficam como estão.

    `topo` é a distância do alto da página; quem desenha a logo acima da caixa
    passa um valor menor.
    """
    rotulo = rotulo.replace("\\", "").replace('"', "'")
    f = '[data-testid="stForm"]:has(input[type="password"])'
    regras = [
        f'{f} {{ max-width: 420px; margin: {topo} auto 0 !important; padding: 30px 32px 26px !important; background: #fff !important; }}',
        f'{f} h3 {{ color: #192D4E !important; font-weight: 800 !important; font-size: 28px !important; padding: 0 0 6px !important; }}',
        f'{f} h3::before {{ content: "{rotulo}"; display: block; font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: {VINHO}; margin-bottom: 4px; }}',
        f'{f} [data-testid="stTextInput"] > label, {f} [data-testid="stTextInput"] > label p {{ font-size: 0.72rem !important; font-weight: 600 !important; letter-spacing: .04em !important; text-transform: uppercase !important; color: #4E5A6E !important; }}',
        f'{f} [data-testid="stElementContainer"]:has([data-testid="stFormSubmitButton"]), {f} [data-testid="stFormSubmitButton"] {{ width: 100% !important; margin-top: 6px; }}',
        f'{f} [data-testid="stFormSubmitButton"] button {{ width: 100% !important; min-height: 42px !important; background: {VINHO} !important; border-color: {VINHO} !important; }}',
        f'{f} [data-testid="stFormSubmitButton"] button p {{ color: #fff !important; font-weight: 700 !important; }}',
        f'{f} [data-testid="stFormSubmitButton"] button:hover {{ background: #7A2640 !important; border-color: #7A2640 !important; }}',
        '[data-testid="stMain"] [data-testid="stAlert"] { max-width: 420px; margin: 12px auto 0; }',
        f'{f} [data-testid="InputInstructions"] {{ display: none !important; }}',
    ]
    return "<style>" + "".join(regras) + "</style>"
