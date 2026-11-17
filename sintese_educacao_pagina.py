"""Áreas Educação (ISG e IU) e Primeira Infância (FMCSV) da página Síntese da Semana.

As duas leem o mesmo doc de links e usam os mesmos resumos (o Gemini roda uma vez por semana);
cada área só mostra e entrega os clientes dela, como na Agenda da Semana.

Cada item tem uma identificação fixa (_id, tirada da seção, do link e do texto da equipe), e o resumo
fica guardado por ela em SS["edu_cache"]: reler o doc só pede ao Gemini o que é novo, e as edições
(guardadas fora dos widgets, por _id) continuam valendo.
Usa o CSS da página da saúde; a lógica fica em sintese_educacao_core.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib
import json
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
AREAS = {"Educação": ["ISG", "IU"], "Primeira Infância": ["FMCSV"]}  # mesma divisão da Agenda da Semana
NOME_SECAO = {"CENÁRIO ELEITORAL": "Cenário eleitoral", "LEGISLATIVO": "Legislativo", "EXECUTIVO": "Executivo",
              "JUDICIÁRIO": "Judiciário", "NOTÍCIAS": "Notícias", "DIÁRIO OFICIAL DA UNIÃO": "Diário Oficial da União"}
CHAVES = ("edu_doc", "edu_doc_ref", "edu_cache", "edu_erros", "edu_arquivos", "edu_emails", "edu_assin",
          "edu_semana", "edu_link")
PREFIXOS = ("ei_", "ep_", "ed_", "wei_", "wep_", "wed_")


def limpar():
    for k in CHAVES:
        SS.pop(k, None)
    for k in [k for k in list(SS.keys()) if str(k).startswith(PREFIXOS)]:
        SS.pop(k, None)


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def _de(clientes: list[str]) -> str:
    """'do ISG e do IU', 'da FMCSV'."""
    return " e ".join(("do " if c in ("ISG", "IU") else "da ") + c for c in clientes)


def _hash(obj) -> str:
    return hashlib.md5(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]


@st.cache_data(ttl=600, show_spinner=False)
def _pasta(pasta_id: str):
    return se.listar_pasta(pasta_id)


def _dar_ids(itens_doc: list[dict]) -> None:
    """Identificação que não muda quando outro item entra ou sai do doc (a marca "FMCSV:" fica de fora:
    mudar a marca muda os clientes, não pede resumo novo)."""
    vistos: dict[str, int] = {}
    for it in itens_doc:
        base = _hash([it["secao"], it["url"], it["titulo_equipe"], it["paragrafos_equipe"]])
        n = vistos.get(base, 0)
        vistos[base] = n + 1
        it["_id"] = base if n == 0 else f"{base}{n}"


def _pid(p: dict) -> str:
    return re.sub(r"\W", "", p["proposicao"]) or _hash(p)


# ─── valores guardados fora dos widgets ──────────────────────────────────────
# O Streamlit apaga o estado de um widget que não foi desenhado numa rodada (troca de área, erro ao
# reler o doc). O valor fica em SS[chave]; o widget usa a chave "w" + chave e copia no on_change.
def _campo(widget, chave: str, padrao, **kw):
    def _guardar():
        SS[chave] = SS["w" + chave]
    if widget is st.pills:
        return st.pills(default=SS.get(chave, padrao), key="w" + chave, on_change=_guardar, **kw)
    return widget(value=SS.get(chave, padrao), key="w" + chave, on_change=_guardar, **kw)


def _clientes(it: dict) -> list[str]:
    """Soma o que está marcado em cada área (a escolha numa área não mexe na outra)."""
    out = []
    for a, cs in AREAS.items():
        out += SS.get(f"ei_{it['_id']}_cli_{a}", [c for c in it["clientes"] if c in cs])
    return out


def _titulo(it: dict) -> str:
    return SS.get(f"ei_{it['_id']}_tit", it["titulo"])


def _pars(it: dict) -> list[str]:
    txt = SS.get(f"ei_{it['_id']}_txt")
    if txt is None:
        return list(it["paragrafos"])
    return [l.strip() for l in txt.splitlines() if l.strip()]


def _editado(it: dict) -> dict:
    i = it["_id"]
    return {**it, "titulo": _titulo(it), "paragrafos": _pars(it),
            "primeira_infancia": SS.get(f"ei_{i}_pi", it["primeira_infancia"]).strip(),
            "url": SS.get(f"ei_{i}_url", it["url"]).strip() or it["url"]}


def _itens_do_cliente(itens: list[dict], c: str) -> list[dict]:
    return [_editado(it) for it in itens if c in _clientes(it) and _pars(it)]


def _sem_texto(itens: list[dict], c: str) -> list[dict]:
    return [it for it in itens if c in _clientes(it) and not _pars(it)]


def _clientes_da_prop(p: dict) -> list[str]:
    out = []
    for a, cs in AREAS.items():
        out += SS.get(f"ep_{_pid(p)}_{a}", [c for c in (p["clientes"] or list(se.CLIENTES)) if c in cs])
    return out


def _props_do_cliente(props: list[dict], c: str) -> list[dict]:
    return [p for p in props if c in _clientes_da_prop(p)]


def _itens_atuais(itens_doc: list[dict]) -> list[dict]:
    """Os resumos guardados dos itens que estão no doc agora, com a marca de cliente atual do doc."""
    cache = SS.get("edu_cache") or {}
    out = []
    for it in itens_doc:
        r = cache.get(it["_id"])
        if r is None:
            continue
        marcas = it["marcas"]
        padrao = ([c for c in se.CLIENTES if c in marcas] if marcas
                  else ["IU"] + ([] if r["clima"] else ["ISG"]) + (["FMCSV"] if r["fmcsv"] else []))
        out.append({**r, "secao": it["secao"], "marcas": marcas, "clientes": padrao, "_pos": it["_pos"]})
    return out


def _assinatura(c: str, itens: list[dict], props: list[dict], dest: dict) -> str:
    """Muda quando muda algo que vai no Word ou no email do cliente (para avisar arquivo velho)."""
    return _hash([[(m["_id"], m["titulo"], m["paragrafos"], m["url"], m["primeira_infancia"] if c == "FMCSV" else "")
                   for m in _itens_do_cliente(itens, c)],
                  [p["proposicao"] for p in _props_do_cliente(props, c)],
                  {e: d["_id"] for e, d in dest.items()}])


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


def _item(it: dict, area: str, CLIS: list[str], repetidos: set, com_secao: bool = False):
    iid = it["_id"]
    pars = _pars(it)
    with st.container(key=f"it_edu_{iid}"):
        col1, col2 = st.columns([0.74, 0.26], vertical_alignment="top")
        with col2, st.container(key=f"ac_edu_{iid}"):
            _campo(st.pills, f"ei_{iid}_cli_{area}", [c for c in it["clientes"] if c in CLIS], label="Clientes",
                   options=CLIS, selection_mode="multi", label_visibility="collapsed")
            with st.popover("Escrever" if not pars else "Editar", icon=":material/edit:"):
                _campo(st.text_input, f"ei_{iid}_tit", it["titulo"], label="Título")
                _campo(st.text_area, f"ei_{iid}_txt", "\n\n".join(it["paragrafos"]), height=220,
                       label="Parágrafos (cada linha é um parágrafo)")
                if "FMCSV" in CLIS:
                    _campo(st.text_area, f"ei_{iid}_pi", it["primeira_infancia"], height=90,
                           label="Parágrafo extra só na FMCSV (apague para tirar)")
                _campo(st.text_input, f"ei_{iid}_url", it["url"], label="Link do título")
        ed = _editado(it)
        on = any(c in CLIS for c in _clientes(it)) and bool(pars)
        chips = []
        if com_secao:
            chips.append(chip(NOME_SECAO[it["secao"]]))
        if not pars:
            chips.append(chip("sem texto: fica fora da síntese até você escrever", "erro"))
        elif it.get("aviso"):
            chips.append(chip("a página tinha pouco texto: confira o resumo", "alerta"))
        if it["url"] in repetidos:
            chips.append(chip("link repetido no doc", "alerta"))
        if it["da_equipe"]:
            chips.append(chip("texto da equipe", "ok"))
        if it["marcas"]:
            chips.append(chip("marcado no doc: " + ", ".join(it["marcas"]), "org"))
        elif it["clima"]:
            chips.append(chip("clima", "alerta"))
        if ed["primeira_infancia"] and "FMCSV" in CLIS:
            chips.append(chip("trecho de primeira infância", "data"))
        tit = ed["titulo"] or re.sub(r"^https?://(www\.)?", "", ed["url"])[:90] or "(sem título nem link)"
        corpo = (f'<div class="sx-top">{"".join(chips)}</div>' if chips else "") + \
                (f'<p class="sx-h"><a href="{esc(ed["url"])}" target="_blank">{esc(tit)}</a></p>' if ed["url"]
                 else f'<p class="sx-h">{esc(tit)}</p>') + \
                "".join(f'<p class="sx-txt" style="margin-top:6px !important">{esc(p)}</p>' for p in pars)
        if not pars:
            motivo = (it.get("falha") or "").replace("não consegui ler o link (", "Não consegui ler o link: ").rstrip(")")
            corpo += (f'<p class="sx-meta">{esc(motivo[:1].upper() + motivo[1:])}. Abra o link, escreva o título e o texto '
                      f'em Escrever ou use "Tentar de novo".</p>')
        if ed["primeira_infancia"] and "FMCSV" in CLIS:
            corpo += f'<p class="sx-meta">Parágrafo extra na FMCSV: {esc(ed["primeira_infancia"])}</p>'
        with col1:
            st.markdown(f'<div class="{"" if on or not pars else "sx-fora"}">{corpo}</div>', unsafe_allow_html=True)


def render(INI: dt.date, FIM: dt.date, gemini_key: str, gemini_modelo: str, pasta_id: str, area: str = "Educação"):
    CLIS = AREAS[area]
    nomes = " e ".join(CLIS)
    if SS.get("edu_semana") != INI:  # trocou a semana: o doc é outro (e o link colado também)
        limpar()
        SS["edu_semana"] = INI
    periodo = se.periodo_curto(INI, FIM)
    etapas_ph = st.empty()
    estado = {"doc": None, "itens": None, "faltam": 0, "sem_texto": 0, "prontos": False}

    def _etapas():
        doc, itens = estado["doc"], estado["itens"]
        etapas([
            ("feita" if doc else "atual", "Doc de links",
             f'{_plural(len(doc["itens"]), "item", "itens")}, {_plural(len(doc["proposicoes"]), "proposição", "proposições")}'
             if doc else "O doc da semana na pasta z_links educação"),
            ("feita" if itens and not estado["faltam"] else ("atual" if doc else "aberta"), "Resumos e clientes",
             (_plural(len(itens) - estado["sem_texto"], "item com texto", "itens com texto")
              + (f", {estado['sem_texto']} sem texto" if estado["sem_texto"] else "")
              + (f", {estado['faltam'] - estado['sem_texto']} novos" if estado["faltam"] > estado["sem_texto"] else "")) if itens
             else f"O Gemini resume cada link e separa os clientes ({nomes})"),
            ("feita" if estado["prontos"] else ("atual" if itens else "aberta"), "Word, PDF e email",
             f"{nomes} {'prontos' if len(CLIS) > 1 else 'pronta'} para baixar" if estado["prontos"]
             else "Síntese completa e 1 notícia por eixo para o Wix"),
        ], etapas_ph)

    def _parar():
        _etapas()
        st.stop()

    # ========= 1. DOC DE LINKS =========
    secao("1. Doc de links da semana", cor="#962E4D",
          explicacao="O doc 'Links educação - dd.mm a dd.mm' da pasta z_links educação, o mesmo para Educação e "
                     "Primeira Infância. A página acha o da semana escolhida; se não achar, cole o link do doc. "
                     "Ele precisa estar aberto para quem tem o link.")
    achado = None
    if pasta_id:
        try:
            achado = se.doc_da_semana(_pasta(pasta_id), INI)
        except Exception as e:  # noqa: BLE001
            st.warning(f"Não consegui listar a pasta dos links ({type(e).__name__}). Cole o link do doc abaixo.")
    explica_ph = st.empty()
    colado = st.text_input("Link do doc", placeholder="https://docs.google.com/document/d/...",
                           help="Só precisa colar se a página não achou o doc da semana ou se for outro doc.",
                           key="edu_link")
    ref = (achado or {}).get("id", "")
    if achado and not colado.strip():
        explica_ph.markdown(f'<p class="eg-explica">Doc da semana: <a href="{esc(achado["link"])}" target="_blank">'
                            f'{esc(achado["nome"])}</a></p>', unsafe_allow_html=True)
    elif colado.strip():
        explica_ph.markdown('<p class="eg-explica">Lendo o doc do link colado'
                            + (f' (não o <a href="{esc(achado["link"])}" target="_blank">{esc(achado["nome"])}</a> '
                               f'da pasta; apague o link para voltar a ele)' if achado else "") + ".</p>",
                            unsafe_allow_html=True)
    if colado.strip():
        try:
            ref = se.id_do_doc(colado)
        except ValueError as e:
            st.error(str(e))
            _parar()
    if not ref:
        st.markdown((f'<p class="eg-explica">Não achei na pasta o doc de {esc(periodo)}. Cole o link dele acima, '
                     f'ou confira a semana escolhida.</p>') if pasta_id else
                    '<p class="eg-explica">Cole acima o link do doc de links da semana.</p>', unsafe_allow_html=True)
        _parar()
    reler = SS.get("edu_doc_ref") == ref and st.button(
        "Ler o doc de novo", help="Depois que a equipe mexer no doc. Resumos e edições dos itens que não mudaram ficam.")
    if SS.get("edu_doc_ref") != ref or reler:
        antes = {it["_id"] for it in (SS.get("edu_doc") or {}).get("itens", [])}
        try:
            with st.spinner("Lendo o doc..."):
                novo = se.ler_doc(se.baixar_doc(ref))
            _dar_ids(novo["itens"])
            SS["edu_doc"], SS["edu_doc_ref"] = novo, ref
            if reler:
                depois = {it["_id"] for it in novo["itens"]}
                ent, sai = len(depois - antes), len(antes - depois)
                st.toast("Doc relido: " + (", ".join(x for x in (
                    _plural(ent, "item novo ou mudado", "itens novos ou mudados") if ent else "",
                    _plural(sai, "item saiu", "itens saíram") if sai else "") if x) or "nada mudou nos itens") + ".")
        except Exception as e:  # noqa: BLE001
            SS.pop("edu_doc", None)
            SS.pop("edu_doc_ref", None)
            st.error(str(e) if isinstance(e, RuntimeError) else f"Erro ao ler o doc: {type(e).__name__}: {e}")
    doc = SS.get("edu_doc")
    if not doc:
        _parar()
    if any("_id" not in it for it in doc["itens"]):  # doc lido por versão anterior da página (sessão aberta)
        _dar_ids(doc["itens"])
        SS.pop("edu_cache", None)
    estado["doc"] = doc
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
    urls = [it["url"] for it in itens_doc if it["url"]]
    repetidos = {u for u in urls if urls.count(u) > 1}

    # ========= 2. RESUMOS =========
    secao("2. Resumos e clientes", cor="#962E4D",
          explicacao="Cada link é baixado e resumido pelo Gemini, uma vez para as duas áreas. O que a equipe já "
                     "escreveu no doc fica como está. IU recebe tudo; ISG, tudo menos clima; FMCSV, primeira infância e "
                     "pautas gerais da educação básica. 'FMCSV:', 'ISG:' ou 'IU:' no começo do item no doc manda só "
                     "para aquele cliente. A escolha de clientes numa área não muda a outra.")
    cache = SS.setdefault("edu_cache", {})
    novos = [it for it in itens_doc if it["_id"] not in cache]
    falhos = [it for it in itens_doc if it["_id"] in cache and cache[it["_id"]].get("falha")]
    alvo, rotulo = [], ""
    if len(novos) == len(itens_doc):
        alvo, rotulo = itens_doc, "Ler links e gerar resumos"
    elif novos or falhos:
        alvo = novos + falhos
        rotulo = (f"Resumir {_plural(len(novos), 'item novo', 'itens novos')}" if not falhos
                  else f"Tentar de novo {_plural(len(falhos), 'item sem resumo', 'itens sem resumo')}" if not novos
                  else f"Resumir {_plural(len(alvo), 'item que falta', 'itens que faltam')}")
    with st.container(horizontal=True, vertical_alignment="center"):
        clicou = bool(rotulo) and st.button(rotulo, type="primary", key="edu_gerar")
        refazer = len(novos) < len(itens_doc) and st.button(
            "Refazer todos os resumos", type="tertiary", key="edu_refazer",
            help="Pede ao Gemini de novo todos os itens. O que você editou à mão continua valendo.")
    if clicou or refazer:
        if not gemini_key:
            st.error("Faltou a GEMINI_API_KEY nos Secrets.")
            _parar()
        from google import genai
        alvo = itens_doc if refazer else alvo
        with st.spinner(f"Baixando {_plural(len(alvo), 'link', 'links')}..."):
            baixados = se.baixar_todos(alvo)
        with st.spinner(f"Gerando os resumos de {_plural(len(baixados), 'item', 'itens')}..."):
            prontos, erros = se.gerar(genai.Client(api_key=gemini_key), gemini_modelo, baixados)
        for r in prontos:
            cache[r["_id"]] = r
        SS["edu_erros"] = erros
        st.rerun()
    itens = _itens_atuais(itens_doc)
    estado["itens"] = itens or None
    estado["faltam"] = len(novos) + len(falhos)
    estado["sem_texto"] = sum(1 for it in itens if not _pars(it))
    if not itens:
        _parar()
    erros = SS.get("edu_erros") or []
    if erros:
        with st.container(key="sb_falha"), st.expander(_plural(len(erros), "erro do Gemini", "erros do Gemini")):
            for e in erros:
                st.markdown(f"- {esc(e)}")
    if novos:
        st.markdown(f'<p class="eg-explica">{_plural(len(novos), "item novo no doc ainda não foi resumido", "itens novos no doc ainda não foram resumidos")}: '
                    f'use o botão acima.</p>', unsafe_allow_html=True)

    # item sem texto ainda não tem classificação: aparece nas duas áreas para quem revisa decidir
    dentro = [it for it in itens if any(c in CLIS for c in it["clientes"]) or not it["paragrafos"]]
    fora = [it for it in itens if it not in dentro]
    for sec in se.SECOES:
        doses = [it for it in dentro if it["secao"] == sec]
        if not doses:
            continue
        secao(NOME_SECAO[sec], contagem=str(len(doses)), cor="#192D4E", menor=True)
        for it in doses:
            _item(it, area, CLIS, repetidos)
    if fora:
        with st.expander(f"{_plural(len(fora), 'item ficou', 'itens ficaram')} fora da síntese "
                         f"{_de(CLIS)} pela regra (confira e marque o que deve entrar)"):
            for it in fora:
                _item(it, area, CLIS, repetidos, com_secao=True)

    if props:
        secao("Novas proposições", contagem=str(len(props)), cor="#192D4E", menor=True,
              explicacao="Da tabela NOVAS PROPOSIÇÕES do doc. Vão para ISG, IU e FMCSV, a menos que a tabela diga o cliente.")
        for p in props:
            pid = _pid(p)
            with st.container(key=f"it_edup_{pid}"):
                col1, col2 = st.columns([0.74, 0.26], vertical_alignment="top")
                with col2:
                    _campo(st.pills, f"ep_{pid}_{area}", [c for c in (p["clientes"] or CLIS) if c in CLIS],
                           label="Clientes", options=CLIS, selection_mode="multi", label_visibility="collapsed")
                on = any(c in CLIS for c in _clientes_da_prop(p))
                link = f'<a href="{esc(p["link"])}" target="_blank">{esc(p["proposicao"])}</a>' if p["link"] else esc(p["proposicao"])
                col1.markdown(f'<div class="{"" if on else "sx-fora"}"><p class="sx-h">{link}</p>'
                              f'<p class="sx-ementa">{esc(p["ementa"])}</p>'
                              + (f'<p class="sx-meta">{esc(p["autor"])}</p>' if p["autor"] else "") + "</div>",
                              unsafe_allow_html=True)

    # ========= 3. ENTREGA =========
    secao("3. Word, PDF e email", cor="#962E4D",
          explicacao="O PDF leva a síntese completa. O email do Wix leva 1 notícia de cada eixo (Legislativo, "
                     "Executivo e Notícias gerais); escolha qual abaixo.")
    destaques: dict[str, dict[str, dict]] = {}
    for c, aba in zip(CLIS, st.tabs(CLIS) if len(CLIS) > 1 else [st.container()]):
        meus = _itens_do_cliente(itens, c)
        destaques[c] = {}
        with aba:
            st.markdown(f'<p class="eg-explica">{_plural(len(meus), "item", "itens")} e '
                        f'{_plural(len(_props_do_cliente(props, c)), "proposição", "proposições")} na síntese.</p>',
                        unsafe_allow_html=True)
            sem = _sem_texto(itens, c)
            if sem:
                st.warning(f"{_plural(len(sem), 'item sem texto fica', 'itens sem texto ficam')} fora da síntese "
                           f"{_de([c])} até alguém escrever o texto (botão Escrever do item): "
                           + "; ".join((_titulo(it) or re.sub(r"^https?://(www\.)?", "", it["url"]))[:60] for it in sem))
            cols = st.columns(len(se.EIXOS_EMAIL))
            for col, eixo in zip(cols, se.EIXOS_EMAIL):
                opcoes = [m for m in meus if m["secao"] == eixo]
                with col:
                    if not opcoes:
                        st.caption(f"{NOME_SECAO[eixo]}: nada nesta semana")
                        continue
                    ids = [m["_id"] for m in opcoes]
                    titulos = {m["_id"]: m["titulo"] for m in opcoes}
                    chave = f"ed_{c}_{eixo}"
                    wk = f"w{chave}_{_hash(ids)}"  # opções novas = widget novo (o escolhido segue pelo _id)

                    def _guardar(chave=chave, wk=wk):
                        SS[chave] = SS[wk]
                    salvo = SS.get(chave)
                    esc_id = st.selectbox(f"Email: {NOME_SECAO[eixo]}", ids, index=ids.index(salvo) if salvo in ids else 0,
                                          format_func=lambda k, t=titulos: t[k][:90], key=wk, on_change=_guardar)
                    destaques[c][eixo] = next(m for m in opcoes if m["_id"] == esc_id)

    assin = SS.setdefault("edu_assin", {})
    atual = {c: _assinatura(c, itens, props, destaques[c]) for c in CLIS}
    montados = [c for c in CLIS if c in assin]
    velhos = [c for c in montados if assin[c] != atual[c]]
    vazios = [c for c in CLIS if not _itens_do_cliente(itens, c) and not _props_do_cliente(props, c)]
    estado["prontos"] = bool(montados) and not velhos and len(montados) == len([c for c in CLIS if c not in vazios])
    if st.button("Montar de novo" if velhos else "Montar Word, PDF e email", type="primary",
                 disabled=len(vazios) == len(CLIS)):
        arquivos, emails = dict(SS.get("edu_arquivos") or {}), dict(SS.get("edu_emails") or {})
        feitos = [c for c in CLIS if c not in vazios]
        with st.spinner("Montando os arquivos..."):
            for c in feitos:
                modelo = (MODELOS / se.CLIENTES[c]["modelo"]).read_bytes()
                nome = se.nome_arquivo(c, INI, FIM)
                arquivos[nome] = se.gerar_docx(modelo, c, periodo, _itens_do_cliente(itens, c), _props_do_cliente(props, c))
                emails[c] = se.html_email(c, periodo, destaques[c])
                arquivos[nome.replace(".docx", " - email.html")] = emails[c].encode("utf8")
                arquivos.pop(nome.replace(".docx", ".pdf"), None)
        if ss.pdf_disponivel():
            with st.spinner("Convertendo para PDF..."):
                arquivos.update(ss.docx_para_pdf({se.nome_arquivo(c, INI, FIM): arquivos[se.nome_arquivo(c, INI, FIM)]
                                                  for c in feitos}, str(FONTES)))
        SS["edu_arquivos"], SS["edu_emails"] = arquivos, emails
        for c in feitos:
            assin[c] = atual[c]
        st.rerun()
    if vazios:
        st.caption(f"Sem item nesta semana, não monta: {', '.join(vazios)}.")

    arqs = SS.get("edu_arquivos") or {}
    if montados:
        if velhos:
            st.warning(f"Você mudou a síntese {_de(velhos)} depois de montar. Clique em Montar de novo antes de baixar.")
        with st.container(key="sx_entregas"):
            larg = [0.34, 0.40, 0.26]
            with st.container(key="lin_cab"):
                for col, t in zip(st.columns(larg, vertical_alignment="center"), ["Cliente", "Síntese", "Email (Wix)"]):
                    col.markdown(f'<div class="sx-th">{t}</div>', unsafe_allow_html=True)
            for k, c in enumerate(montados):
                nome = se.nome_arquivo(c, INI, FIM)
                with st.container(key=f"lin_edu_{k}"):
                    c0, c1, c2 = st.columns(larg, vertical_alignment="top")
                    n_it = len(_itens_do_cliente(itens, c))
                    sub = "mudou depois de montar" if c in velhos else _plural(n_it, "item", "itens")
                    c0.markdown(f'<p class="sx-cli">{esc(c)}<span{" style=\"color:#B4532A\"" if c in velhos else ""}>'
                                f'{sub}</span></p>', unsafe_allow_html=True)
                    with c1, st.container(horizontal=True, gap="small"):
                        if nome in arqs:
                            st.download_button("Word", arqs[nome], file_name=nome, mime=DOCX, key=f"dle_{k}_w",
                                               icon=":material/description:", on_click="ignore")
                        pdf = nome.replace(".docx", ".pdf")
                        if pdf in arqs:
                            st.download_button("PDF", arqs[pdf], file_name=pdf, mime="application/pdf",
                                               key=f"dle_{k}_p", icon=":material/picture_as_pdf:", on_click="ignore")
                    corpo = (SS.get("edu_emails") or {}).get(c)
                    if corpo:
                        with c2, st.popover("Ver email", icon=":material/mail:"):
                            _popover_email(corpo, f"edu_{k}")
        if not any(se.nome_arquivo(c, INI, FIM).replace(".docx", ".pdf") in arqs for c in montados):
            st.markdown('<p class="sx-nota">O PDF não está disponível neste servidor; baixe o Word e exporte pelo Word ou pelo Docs.</p>',
                        unsafe_allow_html=True)
        st.markdown('<p class="sx-nota">Email: abra "Ver email", clique em "Copiar email formatado" e cole no Wix; '
                    'depois anexe o PDF.</p>', unsafe_allow_html=True)
    _etapas()
