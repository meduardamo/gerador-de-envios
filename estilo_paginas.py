"""Visual comum às páginas do gerador, no molde da Síntese da Semana.

Vai junto do CSS_MENU, que toda página carrega depois do próprio CSS: assim a
faixa vinho (`ge-hero`) vira cabeçalho marinho sobre o gelo, o filete de seção
(`ge-rule`) vira título com quadrado de cor, e botões, rótulos, abas e pílulas
seguem os painéis de transição e apuração, sem mexer na lógica de cada página.
"""

GELO = "#F4F3EF"
MARINHO = "#192D4E"
VINHO = "#962E4D"
BORDA = "#DADAD4"
MUDO = "#4A4A4A"
ROTULO = "#4E5A6E"

CSS_PAGINAS = f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');
/* base de toda página: fundo gelo, Montserrat, sem cabeçalho nem rodapé do Streamlit */
html, body, [data-testid="stAppViewContainer"] {{ background: {GELO} !important; }}
[data-testid="stAppViewContainer"] > section > div {{ background: {GELO}; }}
* {{ box-sizing: border-box; }}
body, p, span, div, label, input, select, textarea {{ font-family: 'Montserrat', sans-serif !important; }}
[data-testid="stHeader"], [data-testid="stDecoration"] {{ display: none; }}
footer, #MainMenu {{ display: none !important; }}
[data-testid="stSidebar"] {{ background: {GELO} !important; border-right: 1px solid {BORDA} !important; }}
[data-testid="stSidebar"] * {{ font-family: 'Montserrat', sans-serif !important; font-size: 13px !important; }}
span.material-symbols-rounded, span.material-symbols-outlined, span.material-icons,
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {{ font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    letter-spacing: normal !important; text-transform: none !important; }}
[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) {{ display: none; }}
/* logo no topo da barra lateral, acima do menu */
[data-testid="stSidebarHeader"] {{ height: auto !important; padding-top: 22px !important; padding-bottom: 6px !important; }}
[data-testid="stSidebarLogo"], [data-testid="stSidebarHeader"] img {{ height: 64px !important; width: auto !important; max-width: 100% !important; }}
.block-container, [data-testid="stMainBlockContainer"] {{ padding-top: 1.8rem !important; }}

/* cabeçalho: sem faixa, título marinho grande com rótulo vinho em cima */
.ge-hero {{ background: transparent !important; display: flex !important; align-items: flex-end !important;
    justify-content: flex-start !important; gap: 14px; flex-wrap: wrap; padding: 0 0 14px !important;
    margin: 0 0 18px !important; border-bottom: 1px solid {BORDA} !important; }}
.ge-hero-title {{ color: {MARINHO} !important; font-size: clamp(28px, 3vw, 38px) !important; font-weight: 800 !important;
    line-height: 1.2 !important; letter-spacing: -0.01em !important; }}
.ge-hero-title::before {{ content: "EixoGov"; display: block; font-size: 11px; font-weight: 700;
    letter-spacing: .14em; text-transform: uppercase; color: {VINHO}; margin-bottom: 6px; line-height: 1.4; }}
.ge-hero-logo {{ display: none !important; }}
.ge-hero-selo {{ margin: 0 0 6px !important; padding: 3px 11px !important; border: 1px solid {VINHO} !important;
    border-radius: 999px; color: {VINHO} !important; font-size: 11px !important; font-weight: 700 !important; }}
.ge-hero-sub {{ margin-left: auto; color: {MUDO}; font-size: 13px; line-height: 1.6; text-align: right; padding-bottom: 6px; }}

/* título de seção: quadrado vinho e nome em marinho; vazio vira só um fio */
.ge-rule {{ display: flex !important; align-items: center; gap: 8px; border-top: 0 !important; padding-top: 0 !important;
    color: {MARINHO} !important; font-size: 19px !important; font-weight: 700 !important; letter-spacing: 0 !important;
    text-transform: none !important; margin: 26px 0 10px !important; line-height: 1.3; }}
.ge-rule::before {{ content: ""; width: 14px; height: 14px; border-radius: 4px; background: {VINHO}; flex: none; }}
.ge-rule:empty {{ display: block !important; border-top: 1px solid {BORDA} !important; margin: 16px 0 !important; height: 0; }}
.ge-rule:empty::before {{ display: none; }}

/* botões: contorno neutro arredondado; a ação principal em vinho cheio */
[data-testid="stAppViewContainer"] [data-testid="stButton"] button, [data-testid="stAppViewContainer"] [data-testid="stDownloadButton"] > button,
[data-testid="stMain"] [data-testid="stFormSubmitButton"] > button, [data-testid="stMain"] [data-testid="stPopover"] button {{
    border-radius: 8px !important; border: 1px solid {BORDA} !important; background: #fff !important;
    color: {MARINHO} !important; font-weight: 600 !important; letter-spacing: 0 !important; text-transform: none !important;
    padding: 6px 14px !important; min-height: 36px !important; box-shadow: none !important; }}
[data-testid="stAppViewContainer"] [data-testid="stButton"] button p, [data-testid="stAppViewContainer"] [data-testid="stDownloadButton"] button p,
[data-testid="stMain"] [data-testid="stFormSubmitButton"] button p, [data-testid="stMain"] [data-testid="stPopover"] button p {{
    font-size: 13px !important; font-weight: 600 !important; color: inherit !important; letter-spacing: 0 !important;
    text-transform: none !important; }}
[data-testid="stAppViewContainer"] [data-testid="stButton"] button:hover, [data-testid="stAppViewContainer"] [data-testid="stDownloadButton"] > button:hover,
[data-testid="stMain"] [data-testid="stFormSubmitButton"] > button:hover, [data-testid="stMain"] [data-testid="stPopover"] button:hover {{
    border-color: {MARINHO} !important; background: #fff !important; color: {MARINHO} !important; }}
[data-testid="stMain"] button[kind="primary"], [data-testid="stMain"] button[kind="primaryFormSubmit"],
[data-testid="stMain"] [data-testid="stBaseButton-primary"], [data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"] {{
    background: {VINHO} !important; border-color: {VINHO} !important; color: #fff !important; }}
[data-testid="stMain"] button[kind="primary"]:hover, [data-testid="stMain"] button[kind="primaryFormSubmit"]:hover,
[data-testid="stMain"] [data-testid="stBaseButton-primary"]:hover, [data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
    background: #7A2640 !important; border-color: #7A2640 !important; color: #fff !important; }}

/* barra lateral: dois fios, o que fecha o menu e o que abre o bloco do usuário; o resto separado por espaço */
[data-testid="stSidebar"] div[style*="border-left"] {{ border: 0 !important; border-radius: 0 !important; background: transparent !important;
    padding: 4px 0 0 !important; margin: 8px 0 0 !important; }}
[data-testid="stSidebar"] div[style*="border-left"] p {{ font-size: 12.5px !important; line-height: 1.65 !important; color: #222 !important; }}
[data-testid="stSidebar"] div[style*="border-left"] strong {{ color: {MARINHO}; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ border-top: 1px solid {BORDA}; padding-top: 14px; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{ font-size: 12px !important; color: {MUDO} !important; }}
[data-testid="stSidebar"] hr {{ margin: 8px 0 !important; height: 0 !important; border: 0 !important; background: none !important; }}

/* rótulos de campo e caixas */
[data-testid="stMain"] [data-testid="stWidgetLabel"] p {{ font-size: 0.72rem !important; font-weight: 600 !important;
    letter-spacing: .04em !important; text-transform: uppercase !important; color: {ROTULO} !important; }}
[data-testid="stMain"] [data-testid="stCheckbox"] [data-testid="stWidgetLabel"] p, [data-testid="stMain"] label:has(input[role="switch"]) p,
[data-testid="stMain"] [data-testid="stRadio"] [role="radiogroup"] p {{ text-transform: none !important; letter-spacing: 0 !important;
    font-size: 13px !important; font-weight: 500 !important; color: {MARINHO} !important; }}
[data-testid="stMain"] div[data-baseweb="input"], [data-testid="stMain"] div[data-baseweb="select"] > div,
[data-testid="stMain"] div[data-baseweb="textarea"] {{ border-radius: 8px !important; border-color: {BORDA} !important; }}
[data-testid="stMain"] div[data-testid="stForm"] {{ border: 1px solid {BORDA} !important; border-radius: 8px !important; background: #fff !important; }}
[data-testid="stMain"] [data-testid="stFileUploaderDropzone"] {{ background: #fff !important; border: 1px dashed #B9B5AA !important; border-radius: 8px !important; }}
[data-testid="stMain"] [data-testid="stExpander"] details {{ border: 1px solid {BORDA} !important; border-radius: 8px !important; background: #fff !important; }}
[data-testid="stMain"] [data-testid="stExpander"] summary p {{ font-size: 13px !important; font-weight: 600 !important; color: {MARINHO} !important;
    text-transform: none !important; letter-spacing: 0 !important; }}
label:has(input[role="switch"]:checked) > div:first-of-type {{ background-color: {VINHO} !important; }}

/* pílulas: a escolhida em marinho */
[data-testid="stMain"] [data-testid="stButtonGroup"] button {{ border: 1px solid {BORDA} !important; border-radius: 999px !important;
    background: #fff !important; box-shadow: none !important; padding: 4px 14px !important; min-height: 34px; }}
[data-testid="stMain"] [data-testid="stButtonGroup"] button p {{ font-size: 12.5px !important; font-weight: 500 !important; color: {MARINHO} !important; }}
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-pressed="true"], [data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-checked="true"],
[data-testid="stMain"] [data-testid="stButtonGroup"] button[kind="pillsActive"], [data-testid="stMain"] [data-testid="stButtonGroup"] button[kind="segmented_controlActive"] {{
    background: {MARINHO} !important; border-color: {MARINHO} !important; }}
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-pressed="true"] p, [data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-checked="true"] p,
[data-testid="stMain"] [data-testid="stButtonGroup"] button[kind="pillsActive"] p, [data-testid="stMain"] [data-testid="stButtonGroup"] button[kind="segmented_controlActive"] p {{
    color: #fff !important; font-weight: 600 !important; }}

/* abas: filete vinho na escolhida */
[data-testid="stTabs"] [role="tablist"] {{ border-bottom: 1px solid {BORDA} !important; gap: 0 !important; }}
[data-testid="stTabs"] [role="tab"] {{ padding: 10px 18px 9px !important; border-bottom: 2px solid transparent !important;
    background: transparent !important; border-radius: 0 !important; text-transform: none !important; letter-spacing: 0 !important; }}
[data-testid="stTabs"] [role="tab"] p {{ font-size: 13px !important; font-weight: 500 !important; color: {MUDO} !important;
    text-transform: none !important; letter-spacing: 0 !important; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ border-bottom-color: {VINHO} !important; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p {{ color: {MARINHO} !important; font-weight: 700 !important; }}
[data-testid="stTabs"] div[data-baseweb="tab-highlight"], [data-testid="stTabs"] .react-aria-SelectionIndicator {{ background-color: {VINHO} !important; }}

[data-testid="stExpanderIcon"], [data-testid="stIconMaterial"], span.material-symbols-rounded {{ font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important; letter-spacing: normal !important; text-transform: none !important; }}
[data-testid="stAppViewContainer"] :is([data-testid="stTextAreaRootElement"], [data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], [data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"], [data-testid="stDateInput"] [role="group"]):not(:focus-within) {{ border-color: {BORDA} !important; }}
[data-testid="stAppViewContainer"] [data-testid="stButtonGroup"] [data-testid="stTooltipIcon"] button {{ border: 0 !important; padding: 0 !important; background: transparent !important; box-shadow: none !important; min-height: 0 !important; }}
[data-testid="stMain"] [data-testid="stButtonGroup"] div:has(> button) {{ column-gap: 6px !important; }}
[data-testid="stAppViewContainer"] [data-testid="stButtonGroup"] button {{ min-width: max-content !important; }}
[data-testid="stAppViewContainer"] [data-testid="stButtonGroup"] button p {{ overflow: visible !important; text-overflow: clip !important; white-space: nowrap !important; }}
[data-testid="stMultiSelect"] span[role="button"] {{ background: {MARINHO} !important; color: #fff !important; border-radius: 6px !important; }}
/* peças de página (as mesmas da Síntese da Semana) */
.eg-cab {{ padding: 0 0 14px; border-bottom: 1px solid {BORDA}; margin: 0 0 18px; }}
.eg-cab .k {{ font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: {VINHO}; margin-bottom: 6px; }}
.eg-cab .tit {{ color: {MARINHO}; font-weight: 800; font-size: clamp(28px, 3vw, 38px); line-height: 1.2; letter-spacing: -0.01em; }}
.eg-cab .sub {{ color: {MUDO}; font-size: 13.5px; font-weight: 500; margin-top: 6px; line-height: 1.55; }}
.eg-secao {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 26px 0 8px; }}
.eg-secao .q {{ width: 14px; height: 14px; border-radius: 4px; flex: none; }}
.eg-secao .t {{ color: {MARINHO}; font-weight: 700; font-size: 19px; }}
.eg-secao .n {{ color: {MUDO}; font-size: 13px; }}
.eg-secao.menor .t {{ font-size: 15.5px; }}
.eg-info {{ display: inline-flex; align-items: center; justify-content: center; width: 17px; height: 17px; border-radius: 50%; background: {MARINHO};
    color: #fff; font-size: 11px; font-weight: 700; cursor: help; position: relative; line-height: 1; flex-shrink: 0; }}
.eg-info:hover, .eg-info:focus {{ background: {VINHO}; outline: none; }}
.eg-info .eg-bolha {{ display: none; position: absolute; bottom: calc(100% + 8px); left: 0; background: #fff; border: 1px solid {BORDA}; border-radius: 6px;
    padding: 11px 15px; width: 340px; font-size: 12px; font-weight: 400; line-height: 1.6; color: #111; z-index: 9999;
    box-shadow: 0 4px 16px rgba(0,0,0,0.10); white-space: normal; pointer-events: none; text-transform: none; letter-spacing: 0; }}
.eg-info:hover .eg-bolha, .eg-info:focus .eg-bolha {{ display: block; }}
[data-testid="stTabs"], [data-baseweb="tab-panel"] {{ overflow: visible !important; }}
p.eg-explica, .eg-explica {{ color: {MUDO} !important; font-size: 13px !important; line-height: 1.5 !important; margin: 0 0 10px !important; }}
.eg-explica a {{ color: {VINHO}; }}
.eg-resumo {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px 18px; background: #fff; border: 1px solid {BORDA}; border-radius: 8px;
    padding: 11px 16px; font-size: 13px; color: {MUDO}; margin: 10px 0 8px; }}
.eg-resumo b {{ color: {MARINHO}; font-size: 16px; font-weight: 800; margin-right: 3px; font-variant-numeric: tabular-nums; }}
.eg-resumo .sep {{ color: #D5D2CA; }}
.eg-resumo .alerta b {{ color: #B4532A; }}
.eg-nums {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin: 14px 0 4px; }}
.eg-num {{ background: #fff; border: 1px solid {BORDA}; border-radius: 8px; padding: 12px 16px; }}
.eg-num .v {{ display: flex; align-items: center; gap: 8px; font-size: 24px; font-weight: 800; color: {MARINHO}; line-height: 1.1; font-variant-numeric: tabular-nums; }}
.eg-num .v i {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; }}
.eg-num .d {{ font-size: 12px; color: {MUDO}; margin-top: 3px; }}
.eg-chip {{ display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 600; white-space: nowrap; background: #ECEAE4; color: #3A3A3A; line-height: 1.6; }}
.eg-chip.data {{ background: #F2E4E9; color: #7A2640; }}
.eg-chip.org {{ background: #E4E9F1; color: {MARINHO}; }}
.eg-chip.ok {{ background: #DDEFE6; color: #1F5E43; }}
.eg-chip.alerta {{ background: #F6E9BF; color: #5C4700; }}
.eg-chip.erro {{ background: #F6DEDA; color: #8A2A1E; }}
.eg-vazio {{ background: #fff; border: 1px dashed #CFCBC1; border-radius: 8px; padding: 12px 16px; font-size: 13px; color: {MUDO}; }}
.eg-caixa {{ background: #fff; border: 1px solid {BORDA}; border-radius: 8px; padding: 16px 20px; }}
.eg-etapas {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); background: #fff; border: 1px solid {BORDA}; border-radius: 8px; margin: 10px 0 4px; }}
.eg-etapa {{ display: flex; gap: 12px; padding: 14px 18px; align-items: flex-start; }}
.eg-etapa + .eg-etapa {{ border-left: 1px solid {BORDA}; }}
.eg-etapa .m {{ flex: 0 0 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800; }}
.eg-etapa.feita .m {{ background: #1F5E43; color: #fff; }}
.eg-etapa.atual .m {{ background: {VINHO}; color: #fff; }}
.eg-etapa.aberta .m {{ border: 2px dashed #A9A9A4; color: #8A8A8A; }}
.eg-etapa .r {{ font-size: 13.5px; font-weight: 700; color: #111; line-height: 1.3; }}
.eg-etapa.aberta .r {{ color: {MUDO}; font-weight: 600; }}
.eg-etapa .d {{ font-size: 12px; color: {MUDO}; margin-top: 3px; line-height: 1.4; }}
</style>"""



# ─── Peças de página (usar estas em vez de HTML solto, para todas as abas ficarem iguais) ───
import html as _html


def _md(conteudo: str):
    import streamlit as st
    st.markdown(conteudo, unsafe_allow_html=True)


def esc(texto) -> str:
    return _html.escape(str(texto if texto is not None else "").strip())


def info(texto: str) -> str:
    """Ícone (i) com a explicação ao passar o mouse."""
    return f'<span class="eg-info" tabindex="0" role="note">i<span class="eg-bolha">{esc(texto)}</span></span>' if texto else ""


# Grupo de cada aba, na ordem do menu: aparece em cima do título.
GRUPOS = {
    "Gerador de Envios": "Dia a dia",
    "Notícias": "Dia a dia",
    "Gerador de Resumos": "Dia a dia",
    "Agenda da Semana": "Entrega semanal",
    "Síntese da Semana": "Entrega semanal · Saúde",
    "Gerador de Gráficos": "Ferramenta",
    "Alerta de Pesquisa": "Ferramenta",
    "Automações": "Consulta",
}


def cabecalho(titulo: str, sub: str = "", kicker: str | None = None):
    kicker = GRUPOS.get(titulo, "EixoGov") if kicker is None else kicker
    _md(f'<div class="eg-cab"><div class="k">{esc(kicker)}</div><div class="tit">{esc(titulo)}</div>'
        + (f'<div class="sub">{esc(sub)}</div>' if sub else "") + "</div>")


def secao(titulo: str, contagem: str = "", cor: str = VINHO, explicacao: str = "", menor: bool = False):
    q = f'<span class="q" style="background:{cor}"></span>' if cor else ""
    n = f'<span class="n">{esc(contagem)}</span>' if contagem else ""
    _md(f'<div class="eg-secao{" menor" if menor else ""}">{q}<span class="t">{esc(titulo)}</span>{n}{info(explicacao)}</div>')


def explica(texto: str):
    _md(f'<p class="eg-explica">{esc(texto)}</p>')


def resumo(itens):
    """itens: (número, rótulo) ou (número, rótulo, True) para destacar em alerta."""
    partes = []
    for it in itens:
        n, rot, alerta = (it + (False,))[:3]
        partes.append(f'<span class="{"alerta" if alerta else ""}"><b>{esc(n)}</b>{esc(rot)}</span>')
    _md('<div class="eg-resumo">' + '<span class="sep">|</span>'.join(partes) + "</div>")


def numeros(itens):
    """itens: (cor, valor, rótulo)."""
    _md('<div class="eg-nums">' + "".join(
        f'<div class="eg-num"><div class="v"><i style="background:{c}"></i>{esc(v)}</div><div class="d">{esc(d)}</div></div>'
        for c, v, d in itens) + "</div>")


def chip(texto, tipo: str = "") -> str:
    """tipo: '', 'data', 'org', 'ok', 'alerta', 'erro'."""
    return f'<span class="eg-chip {tipo}">{esc(texto)}</span>' if texto else ""


def vazio(texto: str):
    _md(f'<div class="eg-vazio">{esc(texto)}</div>')


def etapas(itens, alvo=None):
    """itens: (estado, título, descrição), estado em 'feita', 'atual', 'aberta'. `alvo`: um st.empty() opcional."""
    conteudo = '<div class="eg-etapas">' + "".join(
        f'<div class="eg-etapa {e}"><div class="m">{"✓" if e == "feita" else i}</div>'
        f'<div><div class="r">{esc(r)}</div><div class="d">{esc(d)}</div></div></div>'
        for i, (e, r, d) in enumerate(itens, 1)) + "</div>"
    (alvo or __import__("streamlit")).markdown(conteudo, unsafe_allow_html=True)


# No st.markdown, linha em branco ou comentário quebram o bloco de HTML e o resto do CSS
# vira texto na tela: vai numa linha só, sem comentários.
import re as _re
CSS_PAGINAS = _re.sub(r"\s+", " ", _re.sub(r"/\*.*?\*/", "", CSS_PAGINAS, flags=_re.S)).strip()
