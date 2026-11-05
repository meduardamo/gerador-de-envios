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
import io
import json
import os
import sys
import zipfile
import zlib
from pathlib import Path

import streamlit as st

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
    nome_de_urna_alerta,
    compilar_alerta_pesquisa,
    encurtar_link,
    gerar_texto_alerta_pesquisa,
    normalizar_link,
    padronizar_itens_alerta,
    rotulo_partido_alerta,
    combinar_cenarios,
)
from graficos_pesquisa_core import (
    ESCALAS_EXPORT,
    LOGO_PADRAO,
    ficha_incompleta,
    gerar_grafico_pesquisa,
    periodo_campo_br,
    resolucao,
    montserrat_disponivel,
    rodape_padrao,
    slug_arquivo,
    titulo_padrao,
)
from estilo_paginas import (
    MARINHO,
    cabecalho,
    esc,
    explica,
    resumo,
    secao,
    vazio,
)

from base_pagina import exigir_login, iniciar

iniciar("Alerta de Pesquisa")

st.markdown("""<style>
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1320px !important; padding: 1.8rem 2.5rem 4rem !important; background: #F4F3EF; }
div[class*="st-key-ap_caixa"] { background: #fff; border: 1px solid #DADAD4; border-radius: 8px; padding: 16px 20px; }
div[class*="st-key-ap_caixa"] [data-testid="stImage"] img { border-radius: 4px; }
.ap-th { font-size: 0.69rem; font-weight: 600; letter-spacing: .03em; text-transform: uppercase; color: #4E5A6E; padding-bottom: 2px; }
.st-key-ap_caixa_itens [data-testid="stHorizontalBlock"] { align-items: center; }
</style>""", unsafe_allow_html=True)


# ── autenticação ──────────────────────────────────────────────────────────────

authenticator = exigir_login()



# ── configurações ─────────────────────────────────────────────────────────────

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
# Os cores não importam Streamlit: a chave dos Secrets entra por aqui.
definir_api_key(GEMINI_API_KEY)

BRT = timezone(timedelta(hours=-3))
LOGO_PATH = str(ROOT_DIR / "logo_eixo_gov_magenta.png")
LEITURA_PDF = [
    "Auto (texto se tiver; imagem se for scan)",
    "Texto (PyMuPDF)",
    "Imagem (Gemini visão)",
]

CHAVES_PESQUISA = ("alerta_payload", "alerta_texto", "alerta_png",
                   "alerta_cenario_op", "alerta_cenario_visto")

# Widgets cujo valor inicial é derivado do cenário escolhido. O Streamlit ignora
# o valor padrão de um widget que já existe na sessão: sem apagar estas chaves,
# trocar de cenário mantinha na tela o título, o rodapé e o texto do cenário
# anterior — era isso que fazia o gráfico sair "de governador" depois de mudar
# para senador.
CHAVES_DERIVADAS = ("alerta_titulo", "alerta_rodape", "alerta_titulo_envio",
                    "alerta_texto", "alerta_texto_edit")

# Liberação manual de ficha incompleta. Vale para uma pesquisa só: pesquisa nova
# entra travada de novo, senão o "publicar assim mesmo" de ontem soltaria a
# ficha da extração de hoje sem ninguém olhar.
CHAVE_FORCAR_FICHA = "alerta_ficha_forcar"


def _parece_votos_validos(itens: list[dict]) -> bool:
    """Marcação inicial da caixa "votos válidos".

    É palpite de partida, não medida: sem branco, nulo ou indeciso na lista e
    com a soma fechando em 100%, a peça costuma estar na base de válidos. Não
    prova nada — o instituto pode ter publicado o total e simplesmente não ter
    divulgado os não válidos — e por isso a caixa continua sendo de quem monta.
    """
    if not itens or any(i.get("tipo") == "nao_valido" for i in itens):
        return False
    return sum(float(i.get("percentual") or 0) for i in itens) >= 97


def _travar_por_ficha(payload: dict) -> list[str]:
    """Campos da ficha que estão barrando o download e o texto. Vazio quando a
    ficha está completa ou quando ela liberou na mão."""
    if st.session_state.get(CHAVE_FORCAR_FICHA):
        return []
    return ficha_incompleta(payload)


def _limpar(limpar_fonte: bool = False):
    alvos = list(CHAVES_PESQUISA) + list(CHAVES_DERIVADAS) + [CHAVE_FORCAR_FICHA]
    if limpar_fonte:
        alvos += ["alerta_texto_fonte", "alerta_texto_pendente", "alerta_url",
                  "alerta_pdf"]
    for chave in alvos:
        st.session_state.pop(chave, None)
    # Itens e soma de cenários apontam para a extração anterior: índice guardado
    # aqui pode nem existir na pesquisa nova.
    for chave in [k for k in st.session_state
                  if k.startswith(("alerta_item_", "alerta_comb_",
                                   "alerta_modo_comb_", "alerta_validos"))]:
        st.session_state.pop(chave, None)


@st.cache_data(show_spinner=False, ttl=3600)
def _link_curto(url: str) -> str:
    """Encurta no TinyURL, igual ao Gerador de Envios. Em cache porque a prévia
    do envio é remontada a cada interação da página, e sem isso cada clique
    viraria uma chamada de rede."""
    return encurtar_link(url)


def _marca_da_logo() -> list:
    """Tamanho e data do arquivo da logo, para entrar na assinatura do zip."""
    try:
        info = os.stat(LOGO_PADRAO)
        return [info.st_size, int(info.st_mtime)]
    except OSError:
        return []


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


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


# Rótulos de tela para valores internos. O valor do widget continua o mesmo
# (é ele que vai para a extração e para a ficha); só muda o que aparece.
ROTULO_LEITURA = {
    LEITURA_PDF[0]: "Automático (texto; imagem se for digitalizado)",
    LEITURA_PDF[1]: "Texto do PDF",
    LEITURA_PDF[2]: "Imagem das páginas (lê gráfico de barra)",
}
ROTULO_TURNO = {"t1": "1º turno", "t2": "2º turno"}
ROTULO_TIPO = {"candidato": "Candidato", "nao_valido": "Branco, nulo ou NS/NR"}


cabecalho("Alerta de Pesquisa",
          "Da pesquisa colada ou do PDF do instituto ao gráfico pronto e ao texto "
          "do alerta. Nada é gravado nas matrizes.")

with st.sidebar:
    st.markdown(
        '<div style="border-left:3px solid #962E4D;padding:10px 12px;'
        'margin:10px 0 0 0;background:transparent;">'
        '<p style="font-family:Montserrat,sans-serif;font-size:12.5px;'
        'color:#111;line-height:1.65;margin:0;">'
        'Cole a pesquisa ou suba o PDF do instituto: a página extrai os números, '
        'monta o <strong>gráfico</strong> no padrão da casa e escreve o '
        '<strong>texto do alerta</strong>. Não grava nada nas matrizes.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    if not montserrat_disponivel():
        st.warning("A fonte Montserrat não está instalada no app. O gráfico sai "
                   "em outra fonte, fora da tipografia da casa.")
    st.markdown("---")
    if st.button("Limpar tudo", width="stretch",
                 help="Zera a pesquisa da tela (texto, extração, gráfico e alerta) "
                      "pra começar do zero"):
        _limpar(limpar_fonte=True)
        st.rerun()
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** "
               f"({st.session_state.get('username', '')})")
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

    secao("Material da pesquisa",
          explicacao="Cole a notícia, o release ou o texto lido do PDF. O Gemini "
                     "separa o instituto, a ficha técnica e os cenários com o "
                     "número de cada nome. Tudo pode ser corrigido na revisão.")
    with st.container(key="ap_caixa_material"):
        col_txt, col_cfg = st.columns([2, 1], gap="large")

        with col_txt:
            st.text_area(
                "Texto da notícia, release ou PDF lido",
                key="alerta_texto_fonte", height=240,
                placeholder="Cole aqui o material da pesquisa…",
            )
            url_original = st.text_input(
                "Link da fonte (opcional)", key="alerta_url",
                placeholder="https://…",
                help="Vai para o texto do alerta. Dá para trocar depois, na aba 4.")

        with col_cfg:
            secao("Foco da extração", cor=MARINHO, menor=True,
                  explicacao="Use quando o material traz mais de uma pesquisa ou "
                             "mais de uma disputa. Em branco, a extração pega tudo "
                             "o que encontrar.")
            explica("Opcional. Deixe em branco se o material tiver uma pesquisa só.")
            foco_cargo = st.selectbox(
                "Cargo", [""] + POLLING_MANUAL_CARGOS, key="alerta_foco_cargo",
                format_func=lambda c: c.capitalize() if c else "Qualquer cargo")
            foco_uf = st.selectbox(
                "UF", [""] + ["BR"] + UFS, key="alerta_foco_uf",
                format_func=lambda u: ("Qualquer UF" if not u else
                                       "BR (nacional)" if u == "BR" else u))
            foco_turno = st.selectbox(
                "Turno", [""] + POLLING_MANUAL_TURNOS, key="alerta_foco_turno",
                format_func=lambda t: ROTULO_TURNO.get(t, t) if t else "Qualquer turno")

    with st.expander("Só tem o PDF? Leia o relatório do instituto aqui",
                     icon=":material/picture_as_pdf:"):
        pdf = st.file_uploader("Relatório do instituto", type=["pdf"], key="alerta_pdf")
        if pdf:
            import fitz
            with fitz.open(stream=pdf.getvalue(), filetype="pdf") as doc:
                n_pag = doc.page_count
            explica(f"{_plural(n_pag, 'página', 'páginas')}. Recorte só as páginas "
                    "dos resultados: com o PDF inteiro, o modo automático tende a "
                    "ler como texto e devolver número sem nome de candidato.")
            c1, c2, c3 = st.columns(3)
            modo = c1.selectbox("Modo de leitura", LEITURA_PDF, key="alerta_modo_pdf",
                                format_func=lambda m: ROTULO_LEITURA.get(m, m))
            p_ini = c2.number_input("Página inicial", 1, n_pag, 1, key="alerta_pag_ini")
            p_fim = c3.number_input("Página final", 1, n_pag, min(n_pag, 4),
                                    key="alerta_pag_fim")
            if st.button("Ler o PDF e colar no texto", icon=":material/description:"):
                paginas = list(range(int(p_ini) - 1, int(p_fim)))
                with st.spinner("Lendo o PDF…"):
                    try:
                        st.session_state["alerta_texto_pendente"] = _processar_pdf(
                            pdf.getvalue(), modo, paginas)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Não foi possível ler o PDF ({exc}). Tente outro "
                                 "modo de leitura ou um recorte menor de páginas.")

    if st.button("Extrair dados da pesquisa", type="primary"):
        if not (st.session_state.get("alerta_texto_fonte") or "").strip():
            st.error("Cole o texto da pesquisa ou leia um PDF primeiro.")
        else:
            with st.spinner("Lendo a pesquisa com o Gemini…"):
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
                    st.error(f"A extração falhou ({exc}). Tente de novo; se repetir, "
                             "cole só o trecho com os resultados ou use o foco da "
                             "extração.")

    if st.session_state.get("alerta_payload"):
        _pl = st.session_state["alerta_payload"]
        _cens = _pl.get("cenarios") or []
        _nomes = sum(len(c.get("itens") or []) for c in _cens)
        resumo([((_pl.get("instituto") or "Instituto não identificado"), ""),
                (len(_cens), "cenários" if len(_cens) != 1 else "cenário"),
                (_nomes, "linhas extraídas" if _nomes != 1 else "linha extraída")])
        explica("Próximo passo: conferir nomes, números e ficha técnica na aba "
                "2. Revisão.")


payload = st.session_state.get("alerta_payload")
itens_editados: list[dict] = []
cenario_final: dict = {}
votos_validos = False
AVISO_SEM_DADOS = ("Ainda não há pesquisa extraída. Cole o material na aba 1. Dados "
                   "e clique em Extrair dados da pesquisa.")
AVISO_SEM_ITENS = ("Nenhum nome marcado na revisão. Marque ao menos um na aba "
                   "2. Revisão para liberar esta etapa.")


with aba_revisao:
    if not payload:
        vazio(AVISO_SEM_DADOS)
    else:
        cenarios = payload.get("cenarios") or []
        rotulos_cen = [
            f"{i + 1}. {c.get('scenario_label') or i + 1} "
            f"({(c.get('cargo') or '').capitalize()} {(c.get('uf') or '')} "
            f"{(c.get('turno') or '').upper()})"
            for i, c in enumerate(cenarios)
        ]
        # A média entra como MAIS UMA opção do seletor de cenário, do lado dos
        # cenários publicados. Senado de 2 vagas é o caso: parte dos institutos
        # entrega o consolidado numa pergunta só (AtlasIntel), parte publica dois
        # ou três cenários estimulados (Quaest) e a leitura da disputa é a média
        # deles. Só existe média dentro do mesmo cargo/UF/turno: relatório com
        # presidente e governador juntos não tem média que faça sentido.
        grupos: dict[tuple, list[int]] = {}
        for i, c in enumerate(cenarios):
            grupos.setdefault(((c.get("cargo") or ""), (c.get("uf") or ""),
                               (c.get("turno") or "")), []).append(i)
        # Só 1º turno: cenário de 2º turno é confronto entre nomes diferentes
        # (Cadu x Álvaro, Cadu x Allyson), e média entre confrontos não existe.
        medias = {f"m{n}": indices
                  for n, ((_, _, turno_gr), indices) in enumerate(grupos.items())
                  if len(indices) > 1 and turno_gr != "t2"}

        def _rotulo_opcao(opcao: str) -> str:
            if opcao.startswith("c"):
                return rotulos_cen[int(opcao[1:])]
            indices = medias[opcao]
            c0 = cenarios[indices[0]]
            return (f"Média dos cenários {', '.join(str(i + 1) for i in indices)} "
                    f"({(c0.get('cargo') or '').capitalize()} {(c0.get('uf') or '')} "
                    f"{(c0.get('turno') or '').upper()})")

        # Média primeiro: quando ela existe, é a leitura da disputa, e o cenário
        # avulso vira a exceção que se escolhe de propósito.
        opcoes = list(medias) + [f"c{i}" for i in range(len(cenarios))]
        escolha = opcoes[0] if opcoes else "c0"

        secao("Cenário", _plural(len(cenarios), "cenário extraído", "cenários extraídos"),
              explicacao="Quando há mais de um cenário da mesma disputa no 1º turno, "
                         "a média deles vem primeiro: é a leitura da disputa. Escolha "
                         "um cenário avulso só quando for esse o recorte da peça.")
        combinar, modo_comb = [], "media"
        with st.container(key="ap_caixa_cenario"):
            if len(opcoes) > 1:
                escolha = st.selectbox("Cenário", opcoes, format_func=_rotulo_opcao,
                                       key="alerta_cenario_op")
            elif cenarios:
                explica(f"Cenário único: {_rotulo_opcao(escolha)}.")
            else:
                explica("A extração não encontrou cenário com números. Volte à aba "
                        "1. Dados e confira o material colado.")

            if escolha in medias:
                grupo = medias[escolha]
                chave_comb = f"alerta_comb_{escolha}"
                # Sobra de uma extração anterior derrubaria a página no cenarios[i].
                if chave_comb in st.session_state:
                    st.session_state[chave_comb] = [
                        i for i in st.session_state[chave_comb] if i in grupo]
                c_sel, c_modo = st.columns([2, 1])
                with c_sel:
                    combinar = st.multiselect(
                        "Cenários na média", grupo, default=grupo,
                        format_func=lambda i: rotulos_cen[i], key=chave_comb,
                        help="Tire da conta o cenário que não for variação da mesma "
                             "pergunta.")
                with c_modo:
                    modo_comb = st.radio(
                        "Como combinar", ["media", "soma"], horizontal=True,
                        format_func=lambda m: ("Média" if m == "media"
                                               else "Soma (1º + 2º voto)"),
                        key=f"alerta_modo_comb_{escolha}",
                        help="Média divide cada nome só pelos cenários em que ele "
                             "aparece, então quem está em um cenário só não é diluído. "
                             "Soma serve quando os cenários são o 1º e o 2º voto da "
                             "mesma pergunta e a leitura é o total (~200%).",
                    )
                if not combinar:
                    st.error("Marque ao menos um cenário para a média.")
                    combinar = list(grupo)
                idx = combinar[0]
            else:
                idx = int(escolha[1:]) if escolha.startswith("c") else 0

        # Cargo, UF, turno e ficha saem do primeiro cenário da média: são iguais
        # no grupo inteiro, é o que define o grupo.
        cenario = cenarios[idx] if cenarios else {"itens": []}

        # Trocar de cenário (ou de combinação) tem que zerar título, rodapé e
        # texto: o Streamlit preserva o valor do widget pela chave, e sem isso a
        # tela fica com a peça do cenário anterior.
        combo = (escolha, tuple(combinar), modo_comb)
        if st.session_state.get("alerta_cenario_visto") != combo:
            st.session_state["alerta_cenario_visto"] = combo
            for chave in CHAVES_DERIVADAS:
                st.session_state.pop(chave, None)

        # O título da seção diz se a ficha fecha, e isso só se sabe depois dos
        # campos: o lugar é guardado aqui e preenchido abaixo.
        titulo_ficha = st.empty()
        with st.container(key="ap_caixa_ficha"):
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
            d3.text_input("Como sai no gráfico", periodo_txt, disabled=True)
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

            faltando = ficha_incompleta(payload)
            if faltando:
                st.error("Falta " + ", ".join(faltando) + " na ficha. O rodapé "
                         "sairia sem esses campos, por isso o download do gráfico "
                         "e o texto do alerta ficam travados até completar.")
                st.checkbox(
                    "Publicar assim mesmo, com a ficha incompleta",
                    key=CHAVE_FORCAR_FICHA,
                    help="Marque só quando o próprio relatório do instituto não "
                         "traz o campo. Confira o PDF antes. Amostra, margem, "
                         "confiança e datas de campo também estão na ficha "
                         "registrada no [PesqEle](https://pesqele.tse.jus.br), "
                         "buscando pelo registro TSE.")
        with titulo_ficha.container():
            secao("Ficha técnica",
                  "completa" if not faltando else
                  _plural(len(faltando), "campo faltando", "campos faltando"),
                  explicacao="Sai no rodapé do gráfico e no texto do alerta. Campo "
                             "vazio não aparece no rodapé, por isso a peça só é "
                             "liberada com a ficha completa.")

        if combinar:
            fonte = [cenarios[i] for i in combinar]
            itens_base = combinar_cenarios(fonte, modo=modo_comb)
            explica_itens = (
                ("Média nome a nome, dividida só pelos cenários em que cada um "
                 "aparece." if modo_comb == "media" else
                 "Soma dos cenários, nome a nome.") +
                " Corrigir um número dentro de um cenário refaz a conta aqui. "
                "Desmarque para tirar do gráfico e do texto.")
            # Número corrigido no cenário avulso muda a origem da conta, e o
            # Streamlit devolveria o valor velho pela chave do widget. Com a
            # origem na chave, a média volta recalculada.
            origem = json.dumps([c.get("itens") for c in fonte], sort_keys=True,
                                ensure_ascii=False, default=str)
            marca = f"-{zlib.crc32(origem.encode('utf-8')):x}"
        else:
            itens_base = cenario.get("itens") or []
            marca = ""
            explica_itens = ("Desmarque para tirar do gráfico e do texto. O que você "
                             "corrigir aqui entra na média dos cenários.")

        secao("Nomes e percentuais",
              _plural(len(itens_base), "linha", "linhas"),
              explicacao="O nome sai na forma da peça: nome de urna, partido "
                         "abreviado e sem cargo ou profissão na frente.")
        explica(explica_itens)

        # A combinação entra na chave do widget: chave repetida faria o Streamlit
        # manter o número do cenário anterior no campo.
        cmb = "-".join([escolha] + [str(i) for i in combinar] + [modo_comb]) + marca
        with st.container(key="ap_caixa_itens"):
            if itens_base:
                h = st.columns([0.5, 3, 1.2, 1.2, 1.6])
                for col, rot in zip(h, ["", "Nome", "Partido", "%", "Tipo"]):
                    col.markdown(f'<div class="ap-th">{esc(rot)}</div>',
                                 unsafe_allow_html=True)
            else:
                vazio("Este cenário veio sem nomes. Escolha outro cenário ou volte "
                      "à aba 1. Dados e extraia de novo.")
            for i, item in enumerate(itens_base):
                c_on, c_nome, c_part, c_pct, c_tipo = st.columns([0.5, 3, 1.2, 1.2, 1.6])
                ligado = c_on.checkbox("Incluir", True, key=f"alerta_item_on_{cmb}_{i}",
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
                                        format_func=lambda t: ROTULO_TIPO.get(t, t),
                                        key=f"alerta_item_tipo_{cmb}_{i}",
                                        label_visibility="collapsed")
                # Correção feita no cenário avulso volta pro payload, senão a média
                # continuaria sendo calculada em cima do número errado. Na média não
                # há volta: ela é resultado, não fonte.
                if not combinar:
                    item.update({"candidato": nome, "partido": partido,
                                 "percentual": pct, "tipo": tipo})

                if ligado and normalizar_texto_simples(nome):
                    # O que ela digita aqui também sai na forma da peça: partido em
                    # nome próprio, título de urna abreviado e sem descritor de
                    # profissão ou cargo na frente do nome.
                    itens_editados.append({
                        "candidato": nome if tipo == "nao_valido"
                                     else nome_de_urna_alerta(nome),
                        "partido": rotulo_partido_alerta(partido),
                        "percentual": pct, "tipo": tipo})

        if itens_editados:
            soma = sum(i["percentual"] for i in itens_editados)
            aviso_soma = ""
            if combinar and modo_comb == "soma":
                # Dois votos por entrevistado: o total esperado é perto de 200%.
                if not 150 <= soma <= 250:
                    aviso_soma = ("A soma ficou longe dos 200% esperados de dois votos "
                                  "por entrevistado. Confira se os cenários somados são "
                                  "mesmo o 1º e o 2º voto da mesma pergunta.")
            elif combinar:
                # Média passa um pouco de 100% quando alguém aparece em um
                # cenário só, mas muito acima disso é cenário que não combina.
                if soma > 120:
                    aviso_soma = ("A média passou de 120%. Confira se os cenários "
                                  "combinados são mesmo variações da mesma pergunta.")
            elif soma > 105:
                aviso_soma = ("Soma acima de 105%. Confira se não entrou mais de um "
                              "cenário na mesma lista.")
            resumo([(len(itens_editados),
                     "nome no gráfico" if len(itens_editados) == 1 else "nomes no gráfico"),
                    (f"{soma:.1f}%".replace(".", ","), "soma dos marcados",
                     bool(aviso_soma))])
            if aviso_soma:
                st.warning(aviso_soma)
            cenario_final = dict(cenario, itens=itens_editados)
            if combinar:
                cenario_final["combinacao"] = {
                    "modo": modo_comb,
                    "cenarios": [rotulos_cen[i] for i in combinar],
                }
        elif itens_base:
            st.error("Nenhum nome marcado. Marque ao menos um para gerar o gráfico "
                     "e o texto.")


with aba_grafico:
    if not itens_editados:
        vazio(AVISO_SEM_DADOS if not payload else AVISO_SEM_ITENS)
    else:
        travando = _travar_por_ficha(payload)
        if travando:
            st.error("Falta " + ", ".join(travando) + " na ficha técnica. Complete "
                     "na aba 2. Revisão para liberar o download.")

        col_ctl, col_prev = st.columns([1, 2], gap="large")

        with col_ctl:
            secao("Ajustes", cor=MARINHO, menor=True,
                  explicacao="O gráfico sai por código, sempre no mesmo layout. "
                             "Aqui só se escolhe orientação, fundo, escala, título "
                             "e rodapé.")
            with st.container(key="ap_caixa_ajustes"):
                # Horizontal por padrão: nome de candidato é longo e cabe deitado
                # sem girar rótulo nem encolher fonte.
                orientacao = st.radio("Orientação", ["horizontal", "vertical"],
                                      key="alerta_orientacao", horizontal=True,
                                      format_func=lambda o: ("Barras deitadas"
                                                             if o == "horizontal"
                                                             else "Barras em pé"))
                incluir_logo = st.checkbox(
                    "Logo da Eixo na prévia", True, key="alerta_logo",
                    help="Só muda a prévia: o arquivo baixado sai sempre nas duas "
                         "versões, com e sem logo.")
                fundo_transparente = st.checkbox(
                    "Fundo transparente", False, key="alerta_fundo",
                    help="Desligado (padrão), o gráfico sai com fundo branco. Ligado, "
                         "sai sem fundo e assenta direto em slide ou story de "
                         "qualquer cor, mas o texto continua escuro, então pede "
                         "fundo claro.")
                escala_cheia = st.checkbox(
                    "Escala de 0 a 100%", True, key="alerta_escala",
                    help="Ligado, todo gráfico usa a mesma escala e dois gráficos ficam "
                         "comparáveis. Desligado, o topo aperta até um pouco acima do "
                         "maior valor. A base fica no zero nos dois casos.")
                # Base do número, no título. A peça de válidos e a de total
                # mostram o mesmo candidato com percentuais diferentes: sem dizer a
                # base, quem recebe as duas não tem como saber qual é qual.
                validos_padrao = _parece_votos_validos(itens_editados)
                votos_validos = st.checkbox(
                    "Votos válidos no título", validos_padrao,
                    # A composição da lista muda o padrão; chave fixa deixaria a
                    # caixa presa no que valia para o cenário anterior.
                    key=f"alerta_validos_{int(validos_padrao)}",
                    help='Escreve "(votos válidos)" no título do gráfico e do '
                         "alerta. Vem marcada quando a lista não tem branco, nulo "
                         "nem indeciso e a soma fecha em 100%. Confira no "
                         "relatório: a extração não registra em que base o "
                         "instituto publicou.")
                # Trocar a base muda o título padrão, e o Streamlit devolveria o
                # texto anterior pela chave do widget.
                if st.session_state.get("alerta_validos_visto") != votos_validos:
                    st.session_state["alerta_validos_visto"] = votos_validos
                    for chave in ("alerta_titulo", "alerta_titulo_envio"):
                        st.session_state.pop(chave, None)
                titulo_grafico = st.text_input(
                    "Título do gráfico",
                    titulo_padrao(payload, cenario_final, votos_validos),
                    key="alerta_titulo")
                # Gráfico de cenários combinados tem que dizer isso na ficha: quem
                # lê a peça precisa saber que o número não é um cenário publicado.
                COMBINACAO_RODAPE = {"media": "Média dos cenários estimulados",
                                     "soma": "1º + 2º voto somados"}
                nota_comb = COMBINACAO_RODAPE.get(
                    (cenario_final.get("combinacao") or {}).get("modo"), "")
                rodape_base = rodape_padrao(payload)
                rodape_grafico = st.text_area(
                    "Ficha técnica (rodapé)",
                    f"{rodape_base} | {nota_comb}" if nota_comb else rodape_base,
                    key="alerta_rodape", height=90)

        try:
            with col_prev:
                secao("Prévia", cor=MARINHO, menor=True)
                with st.container(key="ap_caixa_previa"):
                    st.image(gerar_grafico_pesquisa(
                        titulo_grafico, itens_editados, rodape_grafico,
                        orientacao=orientacao, incluir_logo=incluir_logo,
                        escala_cheia=escala_cheia,
                        fundo_transparente=fundo_transparente),
                        width="stretch")

            secao("Baixar o gráfico",
                  explicacao="Um zip com quatro arquivos: PNG e SVG, cada um com e "
                             "sem a logo. Quem monta card usa a versão com logo; "
                             "quem monta slide da casa, a sem.")
            with st.container(key="ap_caixa_baixar"):
                e1, e2 = st.columns([2, 1], vertical_alignment="center")
                escala = e1.radio(
                    "Tamanho do PNG", list(ESCALAS_EXPORT), horizontal=True,
                    index=list(ESCALAS_EXPORT).index(2), key="alerta_escala_export",
                    format_func=lambda e: f"{e}× {ESCALAS_EXPORT[e]}",
                )
                larg, alt = resolucao(escala)
                e1.caption(f"PNG em {larg} × {alt} px. O SVG é vetor e não muda com "
                           "o tamanho.")

                # Quem monta card usa a versão com logo; quem monta slide da casa
                # usa a sem. Baixar as duas de uma vez evita voltar aqui pra clicar
                # de novo com a caixinha desmarcada.
                nomes = {
                    f"{suf}_{fmt}": slug_arquivo(payload, cenario_final, fmt, suf)
                    for suf in ("com-logo", "sem-logo") for fmt in ("png", "svg")
                }
                assinatura = json.dumps({
                    # A logo não é argumento do desenho, é arquivo no disco, e o
                    # cache do zip vive no processo: trocar a marca sem reiniciar
                    # devolvia o pacote antigo. Marcar o arquivo na assinatura faz
                    # a troca invalidar sozinha, sem depender de alguém lembrar de
                    # mexer num número de versão na mão.
                    "logo": _marca_da_logo(),
                    "titulo": titulo_grafico, "rodape": rodape_grafico,
                    "itens": itens_editados, "orientacao": orientacao,
                    "escala_cheia": escala_cheia, "escala": escala,
                    "fundo_transparente": fundo_transparente, "nomes": nomes,
                }, sort_keys=True, ensure_ascii=False)

                # Travado, o zip nem é montado: são quatro desenhos do matplotlib
                # para um botão que ninguém pode clicar.
                if travando:
                    e2.button("Baixar tudo (.zip)", disabled=True,
                              width="stretch", type="primary",
                              icon=":material/download:",
                              help="Falta " + ", ".join(travando) + " na ficha técnica")
                    e2.caption("Complete a ficha na aba 2. Revisão.")
                else:
                    e2.download_button(
                        "Baixar tudo (.zip)", _pacote_graficos(assinatura),
                        file_name=slug_arquivo(payload, cenario_final, "zip"),
                        mime="application/zip", width="stretch", type="primary",
                        icon=":material/download:",
                        help="Quatro arquivos: PNG e SVG, cada um com e sem a logo")
                    e2.caption("PNG e SVG, com e sem logo.")
        except Exception as exc:
            st.error(f"Não foi possível gerar o gráfico ({exc}). Confira os números "
                     "e o título; se repetir, recarregue a página.")


with aba_alerta:
    if not itens_editados:
        vazio(AVISO_SEM_DADOS if not payload else AVISO_SEM_ITENS)
    else:
        travando = _travar_por_ficha(payload)
        if travando:
            st.error("Falta " + ", ".join(travando) + " na ficha técnica. O texto "
                     "do alerta cita a ficha, então complete na aba 2. Revisão "
                     "antes de gerar.")

        tem_texto = bool(st.session_state.get("alerta_texto"))
        secao("Texto do alerta",
              explicacao="O Gemini escreve com o mesmo modelo de texto de pesquisa "
                         "eleitoral do Gerador de Envios. Os números saem só da "
                         "revisão; a matéria colada entra como contexto da disputa.")
        if st.button("Gerar outro texto" if tem_texto else "Gerar texto do alerta",
                     type="secondary" if tem_texto else "primary",
                     icon=":material/refresh:" if tem_texto else None,
                     disabled=bool(travando)):
            with st.spinner("Redigindo…"):
                try:
                    st.session_state["alerta_texto"] = gerar_texto_alerta_pesquisa(
                        payload, cenario_final,
                        gerar_conteudo=gerar_conteudo_gemini, modelo=GEMINI_MODEL,
                        # A matéria colada volta como contexto da disputa. Os
                        # números continuam saindo só da revisão.
                        texto_fonte=st.session_state.get("alerta_texto_fonte", ""),
                    )
                except Exception as exc:
                    st.error(f"Não foi possível gerar o texto ({exc}). Tente de novo "
                             "em alguns segundos.")

        if st.session_state.get("alerta_texto"):
            col_edit, col_prev = st.columns(2, gap="large")
            with col_edit:
                with st.container(key="ap_caixa_texto"):
                    texto = st.text_area("Texto (edite à vontade)",
                                         st.session_state["alerta_texto"], height=260,
                                         key="alerta_texto_edit")
                    titulo_alerta = st.text_input(
                        "Título do alerta",
                        titulo_padrao(payload, cenario_final, votos_validos),
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
                secao("Prévia do envio", cor=MARINHO, menor=True)
                explica("Pronto para copiar pelo ícone no canto da caixa.")
                st.code(compilar_alerta_pesquisa(
                    texto, titulo_alerta,
                    uf=(cenario_final.get("uf") or payload.get("uf") or ""),
                    link=link_final or "",
                    data_envio=datetime.now(BRT).strftime("%d/%m/%Y"),
                ), language=None, wrap_lines=True)
        elif not travando:
            vazio("Os números da revisão já estão prontos. Clique em Gerar texto do "
                  "alerta para escrever o texto.")
