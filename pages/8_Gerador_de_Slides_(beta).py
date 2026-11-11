"""
Gerador de Slides (BETA): o conteúdo entra em texto ou arquivo e sai .pptx no
modelo institucional da Eixo, para abrir no PowerPoint ou importar no Canva e
no Google Slides.

Em teste: a página avisa que não é para uso em material de cliente ainda.

Divisão de trabalho:
- O Gemini só distribui o conteúdo nos layouts do molde e encurta o texto
  para caber (gerador_slides_core.estruturar). Não desenha nada.
- O que ele devolve cai nos campos abaixo, onde quem monta revisa, troca a
  ordem, tira ou acrescenta slide.
- O arquivo sai por código (gerador_slides_core.gerar_pptx), copiando os
  slides do molde e trocando só o texto.

Esta página não grava nada em planilha nenhuma.
"""

import io
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from gerador_slides_core import CAMPOS, LAYOUTS, NOMES, estruturar, gerar_pptx
from polling_extracao_core import definir_api_key, extrair_texto_pdf_bytes
from estilo_paginas import MARINHO, cabecalho, explica, secao, vazio

from base_pagina import exigir_login, iniciar

iniciar("Gerador de Slides (beta)")

st.markdown("""<style>
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1100px !important; padding: 1.8rem 2.5rem 4rem !important; background: #F4F3EF; }
.st-key-gs_cx_fonte, .st-key-gs_cx_baixar { background: #fff; border: 1px solid #DADAD4; border-radius: 8px; padding: 16px 18px; gap: .6rem; }
.gs-beta { display: inline-block; background: #962E4D; color: #fff; font-size: 11px; font-weight: 700; letter-spacing: .08em; padding: 2px 8px; border-radius: 4px; margin-bottom: 6px; }
</style>""", unsafe_allow_html=True)

authenticator = exigir_login()

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
definir_api_key(GEMINI_API_KEY)

ORDEM = list(LAYOUTS)


# ── estado ───────────────────────────────────────────────────────────────────
# gs_slides: [{"id", "layout"}]; o texto de cada campo mora em
# st.session_state[f"gs_{id}_{campo}"], que é a chave do próprio widget.

def _novo(layout: str, campos: dict | None = None):
    sid = uuid.uuid4().hex[:8]
    for chave, _, _ in CAMPOS[layout]:
        v = (campos or {}).get(chave, [] if chave == "itens" else "")
        st.session_state[f"gs_{sid}_{chave}"] = "\n".join(v) if isinstance(v, list) else str(v or "")
    return {"id": sid, "layout": layout}


def _slides():
    return st.session_state.setdefault("gs_slides", [])


def _mover(i: int, d: int):
    s = _slides()
    j = i + d
    if 0 <= j < len(s):
        s[i], s[j] = s[j], s[i]
    st.session_state.pop("gs_arquivo", None)


def _remover(i: int):
    _slides().pop(i)
    st.session_state.pop("gs_arquivo", None)


def _adicionar():
    _slides().append(_novo(st.session_state.get("gs_novo_layout") or "texto"))
    st.session_state.pop("gs_arquivo", None)


def _limpar():
    for k in [k for k in st.session_state if str(k).startswith("gs_")]:
        del st.session_state[k]


def _ler_arquivo(arq) -> str:
    dados = arq.getvalue()
    nome = arq.name.lower()
    if nome.endswith(".pdf"):
        return extrair_texto_pdf_bytes(dados) or ""
    if nome.endswith(".docx"):
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(dados)).paragraphs)
    return dados.decode("utf-8", errors="ignore")


def _campos(item) -> dict:
    out = {}
    for chave, _, _ in CAMPOS[item["layout"]]:
        v = st.session_state.get(f"gs_{item['id']}_{chave}", "")
        out[chave] = [x.strip() for x in v.split("\n") if x.strip()] if chave == "itens" else v
    return out


# ── cabeçalho e lateral ─────────────────────────────────────────────────────

cabecalho("Gerador de Slides",
          "O conteúdo entra em texto ou arquivo e sai .pptx no modelo institucional da Eixo, "
          "para abrir no PowerPoint ou importar no Canva e no Google Slides.",
          kicker="Ferramenta · BETA")
st.warning("**Página em teste (BETA).** Ainda não use em material de cliente nem de divulgação: "
           "o modelo e os textos estão sendo conferidos pela Comunicação.")

with st.sidebar:
    st.markdown("---")
    st.button("Limpar tudo", on_click=_limpar, width="stretch")
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** "
               f"({st.session_state.get('username', '')})")
    authenticator.logout("Sair", "sidebar")


# ── 1. conteúdo ─────────────────────────────────────────────────────────────

secao("1. Conteúdo", explicacao="O Gemini distribui o conteúdo nos layouts do modelo e encurta o texto "
      "para caber. Ele não inventa número nem nome; confira tudo no passo 2.")
explica("Cole o texto ou suba um arquivo. Pode ser um rascunho, um roteiro ou um documento pronto.")

with st.container(key="gs_cx_fonte"):
    st.text_area("Conteúdo", key="gs_texto", height=200,
                 placeholder="Ex.: o roteiro da apresentação, tópico por tópico.")
    c1, c2 = st.columns(2)
    with c1:
        arq = st.file_uploader("Ou um arquivo", type=["docx", "pdf", "txt", "md"], key="gs_arq")
    with c2:
        st.text_input("Pedido (opcional)", key="gs_pedido",
                      placeholder="Ex.: 6 slides, com capa e encerramento")
    tem = bool((st.session_state.get("gs_texto") or "").strip()) or arq is not None
    if not GEMINI_API_KEY:
        st.error("O Gemini está desligado neste servidor. Monte os slides à mão no passo 2.")
    else:
        b1, b2 = st.columns([1.5, 4], vertical_alignment="center")
        montar = b1.button("Montar slides", type="primary", disabled=not tem,
                           icon=":material/auto_awesome:", width="stretch")
        if _slides():
            with b2:
                explica("Montar de novo substitui os slides abaixo.")
        if montar:
            with st.spinner("Distribuindo o conteúdo nos slides…"):
                try:
                    conteudo = "\n\n".join(x for x in [st.session_state.get("gs_texto") or "",
                                                        _ler_arquivo(arq) if arq is not None else ""] if x.strip())
                    novos = estruturar(conteudo, st.session_state.get("gs_pedido") or "")
                except Exception as exc:
                    st.error(f"Não consegui montar os slides: {exc}")
                else:
                    st.session_state["gs_slides"] = [_novo(s["layout"], s["campos"]) for s in novos]
                    st.session_state.pop("gs_arquivo", None)
                    st.rerun()


# ── 2. revisar ──────────────────────────────────────────────────────────────

slides = _slides()
secao("2. Revisar", contagem=f"{len(slides)} slides" if slides else "",
      explicacao="Cada campo tem um limite sugerido. Passou dele, a fonte diminui para caber. "
                 "**assim** vira destaque em negrito na cor da Eixo; linha em branco separa parágrafos.")

if not slides:
    vazio("Nenhum slide ainda. Monte pelo passo 1 ou acrescente um slide abaixo.")

for i, item in enumerate(slides):
    lay = item["layout"]
    titulo = next((st.session_state.get(f"gs_{item['id']}_{k}", "") for k, _, _ in CAMPOS[lay]
                   if st.session_state.get(f"gs_{item['id']}_{k}", "").strip()), "")
    resumo_slide = re.sub(r"[*\n]+", " ", titulo)[:60]
    rotulo = f"{i + 1}. {NOMES[lay]}" + (f": {resumo_slide}" if titulo else "")
    with st.expander(rotulo, expanded=False):
        for chave, nome, lim in CAMPOS[lay]:
            k = f"gs_{item['id']}_{chave}"
            if chave in ("corpo", "itens", "subtitulo") or chave.endswith("_texto"):
                ajuda = f"Um item por linha, até {lim} caracteres cada." if chave == "itens" else f"Até {lim} caracteres."
                st.text_area(nome, key=k, height=140 if chave in ("corpo", "itens") else 90, help=ajuda)
            else:
                st.text_input(nome, key=k, help=f"Até {lim} caracteres.")
            v = st.session_state.get(k, "")
            longo = [x for x in v.split("\n") if len(x) > lim] if chave == "itens" else ([v] if len(v) > lim else [])
            if longo:
                st.caption(f"Passou do limite sugerido ({lim}); a fonte vai diminuir.")
        m1, m2, m3, _ = st.columns([1, 1, 1, 3])
        m1.button("Subir", key=f"gs_up_{item['id']}", on_click=_mover, args=(i, -1),
                  disabled=i == 0, icon=":material/arrow_upward:", width="stretch")
        m2.button("Descer", key=f"gs_dn_{item['id']}", on_click=_mover, args=(i, 1),
                  disabled=i == len(slides) - 1, icon=":material/arrow_downward:", width="stretch")
        m3.button("Tirar", key=f"gs_rm_{item['id']}", on_click=_remover, args=(i,),
                  icon=":material/delete:", width="stretch")

a1, a2 = st.columns([2, 1.2], vertical_alignment="bottom")
a1.selectbox("Acrescentar slide", ORDEM, format_func=NOMES.get, key="gs_novo_layout", index=1)
a2.button("Acrescentar", on_click=_adicionar, icon=":material/add:", width="stretch")


# ── 3. baixar ───────────────────────────────────────────────────────────────

if slides:
    secao("3. Baixar", explicacao="O .pptx abre no PowerPoint. No Canva: Criar design > Importar arquivo. "
          "No Google Slides: Arquivo > Importar slides. Confira a fonte depois de importar.")
    with st.container(key="gs_cx_baixar"):
        g1, g2 = st.columns([1.5, 4], vertical_alignment="center")
        pedido = [{"layout": it["layout"], "campos": _campos(it)} for it in slides]
        # arquivo gerado antes de mexer nos campos não vale mais
        if st.session_state.get("gs_arquivo_de") != pedido:
            st.session_state.pop("gs_arquivo", None)
        if g1.button("Gerar arquivo", type="primary", icon=":material/slideshow:", width="stretch"):
            try:
                st.session_state["gs_arquivo"] = gerar_pptx(pedido)
                st.session_state["gs_arquivo_de"] = pedido
            except Exception as exc:
                st.error(f"Não consegui gerar o arquivo: {exc}")
        if st.session_state.get("gs_arquivo"):
            g2.download_button("Baixar .pptx", st.session_state["gs_arquivo"],
                               file_name=f"slides_eixo_{date.today():%Y-%m-%d}.pptx",
                               mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                               icon=":material/download:")
        else:
            with g2:
                explica("Gere o arquivo para baixar. Mexeu nos campos, gere de novo.")
