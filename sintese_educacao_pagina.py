"""Parte de educação da página Síntese da Semana (ISG, IU e FMCSV).

Usa o CSS e a régua de etapas da página da saúde; a lógica fica em sintese_educacao_core.
"""
from __future__ import annotations

import datetime as dt
import html as _html
import importlib
import re
from pathlib import Path

import streamlit as st

import sintese_educacao_core as se
import sintese_semana_core as ss
from estilo_paginas import chip, esc, etapas, secao

se = importlib.reload(se)  # o Streamlit Cloud às vezes mantém o módulo velho depois de um push

SS = st.session_state
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MODELOS = Path("modelos")
FONTES = Path("fontes")
CLIS = list(se.CLIENTES)
NOME_SECAO = {"CENÁRIO ELEITORAL": "Cenário eleitoral", "LEGISLATIVO": "Legislativo", "EXECUTIVO": "Executivo",
              "JUDICIÁRIO": "Judiciário", "NOTÍCIAS": "Notícias", "DIÁRIO OFICIAL DA UNIÃO": "Diário Oficial da União"}
CHAVES = ("edu_doc", "edu_doc_ref", "edu_itens", "edu_erros", "edu_arquivos", "edu_emails", "edu_semana")
PREFIXOS = ("ei_", "ep_", "ed_")


def limpar():
    for k in CHAVES:
        SS.pop(k, None)
    for k in [k for k in list(SS.keys()) if str(k).startswith(PREFIXOS)]:
        SS.pop(k, None)


def _zerar_resultados():
    for k in ("edu_itens", "edu_erros", "edu_arquivos", "edu_emails"):
        SS.pop(k, None)
    for k in [k for k in list(SS.keys()) if str(k).startswith(PREFIXOS)]:
        SS.pop(k, None)


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


@st.cache_data(ttl=600, show_spinner=False)
def _pasta(pasta_id: str):
    return se.listar_pasta(pasta_id)


def _clientes_do_item(i: int, it: dict) -> list[str]:
    return SS.get(f"ei_{i}_cli", it["clientes"])


def _itens_do_cliente(itens: list[dict], c: str) -> list[dict]:
    out = []
    for i, it in enumerate(itens):
        if c not in _clientes_do_item(i, it):
            continue
        out.append({**it, "titulo": SS.get(f"ei_{i}_tit", it["titulo"]),
                    "paragrafos": [p.strip() for p in SS.get(f"ei_{i}_txt", "\n\n".join(it["paragrafos"])).split("\n\n")
                                   if p.strip()], "_i": i})
    return out


def _props_do_cliente(props: list[dict], c: str) -> list[dict]:
    return [p for j, p in enumerate(props) if c in SS.get(f"ep_{j}", p["clientes"] or CLIS)]


def _popover_email(corpo: str, cid: str):
    conteudo = corpo.split("<body", 1)[-1].split(">", 1)[-1].rsplit("</body>", 1)[0]
    st.html(f"""
    <div style="display:flex; justify-content:flex-end; margin-bottom:12px;">
      <button id="btn_{cid}" type="button" style="background:#192D4E;color:#fff;border:none;border-radius:4px;
        padding:6px 12px;font-size:13px;font-weight:600;cursor:pointer;">Copiar email formatado</button>
    </div>
    <div id="cnt_{cid}" class="sx-email">{conteudo}</div>
    <script>
    (function() {{
      function setup() {{
        const btn = document.getElementById("btn_{cid}");
        const cnt = document.getElementById("cnt_{cid}");
        if (!btn || !cnt) {{ setTimeout(setup, 40); return; }}
        btn.onclick = function() {{
          const h = cnt.innerHTML, t = cnt.innerText || cnt.textContent;
          let ok = false;
          try {{
            const l = function(e) {{ e.clipboardData.setData("text/html", h); e.clipboardData.setData("text/plain", t); e.preventDefault(); }};
            document.addEventListener("copy", l); ok = document.execCommand("copy"); document.removeEventListener("copy", l);
          }} catch(e) {{}}
          if (!ok && navigator.clipboard && window.ClipboardItem) {{
            navigator.clipboard.write([new ClipboardItem({{"text/html": new Blob([h], {{type: "text/html"}}),
              "text/plain": new Blob([t], {{type: "text/plain"}})}})]).then(sucesso);
            return;
          }}
          if (ok) sucesso(); else btn.innerText = "Erro ao copiar";
          function sucesso() {{
            btn.innerText = "Copiado!"; btn.style.background = "#265C4B";
            setTimeout(function() {{ btn.innerText = "Copiar email formatado"; btn.style.background = "#192D4E"; }}, 2500);
          }}
        }};
      }}
      setup();
    }})();
    </script>""", unsafe_allow_javascript=True)


def render(INI: dt.date, FIM: dt.date, gemini_key: str, gemini_modelo: str, pasta_id: str):
    if SS.get("edu_semana") != INI:  # trocou a semana: o doc é outro
        limpar()
        SS["edu_semana"] = INI
    periodo = se.periodo_curto(INI, FIM)
    etapas_ph = st.empty()

    def _etapas():
        doc, itens, arqs = SS.get("edu_doc"), SS.get("edu_itens"), SS.get("edu_arquivos")
        etapas([
            ("feita" if doc else "atual", "Doc de links",
             f'{_plural(len(doc["itens"]), "item", "itens")}, {_plural(len(doc["proposicoes"]), "proposição", "proposições")}'
             if doc else "O doc da semana na pasta z_links educação"),
            ("feita" if itens else ("atual" if doc else "aberta"), "Resumos e clientes",
             _plural(len(itens), "item resumido", "itens resumidos") if itens
             else "O Gemini resume cada link e separa ISG, IU e FMCSV"),
            ("feita" if arqs else ("atual" if itens else "aberta"), "Word, PDF e email",
             "ISG, IU e FMCSV prontos para baixar" if arqs else "Síntese completa e 1 notícia por eixo para o Wix"),
        ], etapas_ph)

    def _parar():
        _etapas()
        st.stop()

    # ========= 1. DOC DE LINKS =========
    secao("1. Doc de links da semana", cor="#962E4D",
          explicacao="O doc 'Links educação - dd.mm a dd.mm' da pasta z_links educação. A página acha o da semana "
                     "escolhida; se não achar, cole o link do doc. Ele precisa estar aberto para quem tem o link.")
    achado = None
    if pasta_id:
        try:
            achado = se.doc_da_semana(_pasta(pasta_id), INI)
        except Exception as e:  # noqa: BLE001
            st.warning(f"Não consegui listar a pasta dos links ({type(e).__name__}). Cole o link do doc abaixo.")
    if achado:
        st.markdown(f'<p class="eg-explica">Doc da semana: <a href="{esc(achado["link"])}" target="_blank">'
                    f'{esc(achado["nome"])}</a></p>', unsafe_allow_html=True)
    colado = st.text_input("Link do doc", placeholder="https://docs.google.com/document/d/...",
                           help="Só precisa colar se a página não achou o doc da semana ou se for outro doc.",
                           key="edu_link")
    ref = se.id_do_doc(colado) if colado.strip() else (achado or {}).get("id", "")
    if not ref:
        st.markdown('<p class="eg-explica">Não achei o doc desta semana na pasta. Cole o link dele acima.</p>',
                    unsafe_allow_html=True)
        _parar()
    if SS.get("edu_doc_ref") != ref or st.button("Ler o doc de novo", help="Depois de mexer no doc"):
        try:
            with st.spinner("Lendo o doc..."):
                SS["edu_doc"] = se.ler_doc(se.baixar_doc(ref))
            SS["edu_doc_ref"] = ref
            _zerar_resultados()
        except Exception as e:  # noqa: BLE001
            SS.pop("edu_doc", None)
            st.error(str(e) if isinstance(e, RuntimeError) else f"Erro ao ler o doc: {type(e).__name__}: {e}")
    doc = SS.get("edu_doc")
    if not doc:
        _parar()
    itens_doc, props = doc["itens"], doc["proposicoes"]
    if not itens_doc and not props:
        st.warning("O doc não tem links embaixo de LEGISLATIVO, EXECUTIVO, JUDICIÁRIO, NOTÍCIAS ou DIÁRIO OFICIAL DA UNIÃO.")
        _parar()
    por_secao = {}
    for it in itens_doc:
        por_secao[it["secao"]] = por_secao.get(it["secao"], 0) + 1
    partes = [f'<span><b>{n}</b>{esc(NOME_SECAO[s].lower())}</span>' for s, n in por_secao.items()]
    partes.append(f'<span><b>{len(props)}</b>{"nova proposição" if len(props) == 1 else "novas proposições"}</span>')
    n_eq = sum(1 for it in itens_doc if it["paragrafos_equipe"])
    if n_eq:
        partes.append(f'<span><b>{n_eq}</b>{"já resumido" if n_eq == 1 else "já resumidos"} pela equipe</span>')
    st.markdown('<div class="eg-resumo">' + '<span class="sep">|</span>'.join(partes) + "</div>", unsafe_allow_html=True)

    # ========= 2. RESUMOS =========
    secao("2. Resumos e clientes", cor="#962E4D",
          explicacao="Cada link é baixado e resumido pelo Gemini. O que a equipe já escreveu no doc fica como está. "
                     "IU recebe tudo; ISG, tudo menos clima; FMCSV, primeira infância e pautas gerais da educação básica. "
                     "'FMCSV:', 'ISG:' ou 'IU:' no começo do item no doc manda só para aquele cliente.")
    if st.button("Ler links e gerar resumos", type="primary" if not SS.get("edu_itens") else "secondary"):
        if not gemini_key:
            st.error("Faltou a GEMINI_API_KEY nos Secrets.")
            _parar()
        from google import genai
        with st.spinner("Baixando os links..."):
            baixados = se.baixar_todos(itens_doc)
        with st.spinner(f"Gerando os resumos de {_plural(len(baixados), 'item', 'itens')}..."):
            prontos, erros = se.gerar(genai.Client(api_key=gemini_key), gemini_modelo, baixados)
        _zerar_resultados()
        SS["edu_itens"] = prontos
        SS["edu_erros"] = erros + [f"Não li {it['url']} ({it['erro']})" for it in baixados if it.get("erro")]
        st.rerun()
    itens = SS.get("edu_itens")
    if itens is None:
        _parar()
    erros = SS.get("edu_erros") or []
    if erros:
        with st.container(key="sb_falha"), st.expander(_plural(len(erros), "aviso", "avisos")):
            for e in erros:
                st.markdown(f"- {e}")

    for sec in se.SECOES:
        doses = [(i, it) for i, it in enumerate(itens) if it["secao"] == sec]
        if not doses:
            continue
        secao(NOME_SECAO[sec], contagem=str(len(doses)), cor="#192D4E", menor=True)
        for i, it in doses:
            with st.container(key=f"it_edu_{i}"):
                col1, col2 = st.columns([0.74, 0.26], vertical_alignment="top")
                with col2, st.container(key=f"ac_edu_{i}"):
                    st.pills("Clientes", CLIS, default=it["clientes"], selection_mode="multi",
                             key=f"ei_{i}_cli", label_visibility="collapsed")
                    with st.popover("Editar", icon=":material/edit:"):
                        st.text_input("Título", value=it["titulo"], key=f"ei_{i}_tit")
                        st.text_area("Parágrafos (linha em branco separa)", value="\n\n".join(it["paragrafos"]),
                                     height=220, key=f"ei_{i}_txt")
                on = bool(_clientes_do_item(i, it))
                tit = SS.get(f"ei_{i}_tit", it["titulo"])
                pars = [p for p in SS.get(f"ei_{i}_txt", "\n\n".join(it["paragrafos"])).split("\n\n") if p.strip()]
                chips = [chip("texto da equipe", "ok") if it["da_equipe"] else ""]
                if it["marcas"]:
                    chips.append(chip("marcado no doc: " + ", ".join(it["marcas"]), "org"))
                elif it["clima"]:
                    chips.append(chip("clima", "alerta"))
                if it.get("primeira_infancia"):
                    chips.append(chip("trecho de primeira infância na FMCSV", "data"))
                corpo = (f'<div class="sx-top">{"".join(chips)}</div>' if any(chips) else "") + \
                        f'<p class="sx-h"><a href="{esc(it["url"])}" target="_blank">{esc(tit)}</a></p>' + \
                        "".join(f'<p class="sx-txt" style="margin-top:6px !important">{esc(p)}</p>' for p in pars)
                if it.get("primeira_infancia"):
                    corpo += f'<p class="sx-meta">Só na FMCSV: {esc(it["primeira_infancia"])}</p>'
                with col1:
                    st.markdown(f'<div class="{"" if on else "sx-fora"}">{corpo}</div>', unsafe_allow_html=True)

    if props:
        secao("Novas proposições", contagem=str(len(props)), cor="#192D4E", menor=True,
              explicacao="Da tabela NOVAS PROPOSIÇÕES do doc. Vão para os três clientes, a menos que a tabela diga o cliente.")
        for j, p in enumerate(props):
            with st.container(key=f"it_edup_{j}"):
                col1, col2 = st.columns([0.74, 0.26], vertical_alignment="top")
                with col2:
                    st.pills("Clientes", CLIS, default=p["clientes"] or CLIS, selection_mode="multi",
                             key=f"ep_{j}", label_visibility="collapsed")
                link = f'<a href="{esc(p["link"])}" target="_blank">{esc(p["proposicao"])}</a>' if p["link"] else esc(p["proposicao"])
                col1.markdown(f'<p class="sx-h">{link}</p><p class="sx-ementa">{esc(p["ementa"])}</p>'
                              + (f'<p class="sx-meta">{esc(p["autor"])}</p>' if p["autor"] else ""),
                              unsafe_allow_html=True)

    # ========= 3. ENTREGA =========
    secao("3. Word, PDF e email", cor="#962E4D",
          explicacao="O PDF leva a síntese completa. O email do Wix leva 1 notícia de cada eixo (Legislativo, "
                     "Executivo e Notícias gerais); escolha qual abaixo.")
    destaques: dict[str, dict[str, dict]] = {}
    abas = st.tabs(CLIS)
    for c, aba in zip(CLIS, abas):
        meus = _itens_do_cliente(itens, c)
        destaques[c] = {}
        with aba:
            st.markdown(f'<p class="eg-explica">{_plural(len(meus), "item", "itens")} e '
                        f'{_plural(len(_props_do_cliente(props, c)), "proposição", "proposições")} na síntese.</p>',
                        unsafe_allow_html=True)
            cols = st.columns(len(se.EIXOS_EMAIL))
            for col, eixo in zip(cols, se.EIXOS_EMAIL):
                opcoes = [m for m in meus if m["secao"] == eixo]
                with col:
                    if not opcoes:
                        st.caption(f"{NOME_SECAO[eixo]}: nada nesta semana")
                        continue
                    esc_i = st.selectbox(f"Email: {NOME_SECAO[eixo]}", range(len(opcoes)),
                                         format_func=lambda k, o=opcoes: o[k]["titulo"][:90], key=f"ed_{c}_{eixo}")
                    destaques[c][eixo] = opcoes[esc_i]

    if st.button("Montar Word, PDF e email", type="primary"):
        arquivos, emails = {}, {}
        with st.spinner("Montando os arquivos..."):
            for c in CLIS:
                modelo = (MODELOS / se.CLIENTES[c]["modelo"]).read_bytes()
                nome = se.nome_arquivo(c, INI, FIM)
                arquivos[nome] = se.gerar_docx(modelo, c, periodo, _itens_do_cliente(itens, c), _props_do_cliente(props, c))
                emails[c] = se.html_email(c, periodo, destaques[c])
                arquivos[nome.replace(".docx", " - email.html")] = emails[c].encode("utf8")
        if ss.pdf_disponivel():
            with st.spinner("Convertendo para PDF..."):
                arquivos.update(ss.docx_para_pdf({k: v for k, v in arquivos.items() if k.endswith(".docx")}, str(FONTES)))
        SS["edu_arquivos"], SS["edu_emails"] = arquivos, emails
        st.rerun()

    arqs = SS.get("edu_arquivos")
    if arqs:
        with st.container(key="sx_entregas"):
            larg = [0.34, 0.40, 0.26]
            with st.container(key="lin_cab"):
                for col, t in zip(st.columns(larg, vertical_alignment="center"), ["Cliente", "Síntese", "Email (Wix)"]):
                    col.markdown(f'<div class="sx-th">{t}</div>', unsafe_allow_html=True)
            for k, c in enumerate(CLIS):
                nome = se.nome_arquivo(c, INI, FIM)
                with st.container(key=f"lin_edu_{k}"):
                    c0, c1, c2 = st.columns(larg, vertical_alignment="top")
                    n_it = len(_itens_do_cliente(itens, c))
                    c0.markdown(f'<p class="sx-cli">{esc(c)}<span>{_plural(n_it, "item", "itens")}</span></p>',
                                unsafe_allow_html=True)
                    with c1, st.container(horizontal=True, gap="small"):
                        if nome in arqs:
                            st.download_button("Word", arqs[nome], file_name=nome, mime=DOCX, key=f"dle_{k}_w",
                                               icon=":material/description:")
                        pdf = nome.replace(".docx", ".pdf")
                        if pdf in arqs:
                            st.download_button("PDF", arqs[pdf], file_name=pdf, mime="application/pdf",
                                               key=f"dle_{k}_p", icon=":material/picture_as_pdf:")
                    corpo = (SS.get("edu_emails") or {}).get(c)
                    if corpo:
                        with c2, st.popover("Ver email", icon=":material/mail:"):
                            _popover_email(corpo, f"edu_{k}")
        if not any(k.endswith(".pdf") for k in arqs):
            st.markdown('<p class="sx-nota">O PDF não está disponível neste servidor; baixe o Word e exporte pelo Word ou pelo Docs.</p>',
                        unsafe_allow_html=True)
        st.markdown('<p class="sx-nota">Email: abra "Ver email", clique em "Copiar email formatado" e cole no Wix; '
                    'depois anexe o PDF.</p>', unsafe_allow_html=True)
    _etapas()
