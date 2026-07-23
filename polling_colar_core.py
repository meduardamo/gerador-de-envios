"""
Transforma o texto COPIADO da secao "Dados das Pesquisas" do PollingData
(flex.pollingdata.com.br) em linhas no schema das matrizes T1/T2.

Nao raspa nada e nao usa token: le o texto que a pessoa ja tem na tela e colou.
UF, cargo e turno vem da URL da pagina, informada junto.

Uso:
  python -m outros.polling_colar --url <url> --texto arquivo.txt          # revisar
  python -m outros.polling_colar --url <url> --texto arquivo.txt --gravar  # gravar

  <url> = https://flex.pollingdata.com.br/pdvoto/2026/governador/pi/t1
          (aceita tambem a de www.pollingdata.com.br/2026/...)

Secrets/env pra gravar:
  GOOGLE_CREDENTIALS_JSON
  SPREADSHEET_ID_POLLINGDATA      (T1)
  SPREADSHEET_ID_POLLINGDATA_T2   (T2)
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))

COLUNAS_PESQUISAS = ["scenario_id", "poll_id", "ano", "uf", "cargo", "turno", "instituto",
                     "registro_tse", "data_campo", "modo", "amostra", "margem_erro",
                     "confianca", "scenario_label", "disputa", "fonte_url",
                     "fonte_url_original", "horario_raspagem", "origem"]
COLUNAS_RESULTADOS = ["scenario_id", "poll_id", "ano", "uf", "cargo", "turno", "data_campo",
                      "instituto", "registro_tse", "scenario_label", "candidato", "partido",
                      "candidato_partido", "tipo", "percentual", "disputa", "fonte_url",
                      "horario_raspagem", "origem"]

# Marca a procedência: veio de texto colado do PollingData, não do PDF/Gemini
# (Polling Manual). Dedup dentro do colar é por scenario_id no salvar_tudo; o
# cruzamento com entrada manual do mesmo registro é sinalizado na página.
ORIGEM_COLAR = "polling_colar"

REG = re.compile(r"^[A-Z]{2}-\d{4,6}/\d{4}$")
NAO_VALIDO = {"outros", "não válido", "nao valido", "nulo", "branco", "ns/nr",
              "não sabe", "nao sabe", "indeciso", "nenhum"}


def _cargo_uf_turno(url):
    m = re.search(r"/(\d{4})/(presidente|governador|senador)/([a-z]{2})/(t\d)", url.lower())
    if not m:
        raise SystemExit(f"não achei cargo/uf/turno na URL: {url}\n"
                         "esperado algo como .../2026/governador/pi/t1")
    return int(m.group(1)), m.group(2), m.group(3).upper(), m.group(4)


def _disputa_da_url(url):
    """Slug do confronto de 2º turno na URL (t2_lula-zema -> 't2_lula-zema').
    Só vale no t2; no t1 fica vazio, senão serrilha a média móvel."""
    m = re.search(r"/(?:presidente|governador|senador)/[a-z]{2}/(t\d)_([a-z0-9-]+)",
                  url.lower())
    if not m:
        return ""
    turno, slug = m.group(1), m.group(2)
    return f"{turno}_{slug}" if turno == "t2" else ""


def _e_percentual(linha):
    return bool(re.fullmatch(r"[\d.,%\s]+", linha)) and re.search(r"\d", linha)


def _nums(linha):
    return [x.replace(",", ".") for x in re.findall(r"\d+(?:[.,]\d+)?", linha)]


def _tipo(nome):
    return "nao_valido" if re.sub(r"\s+", " ", nome.strip().lower()) in NAO_VALIDO else "candidato"


def _data_iso(d):
    """DD/MM/YYYY (formato do flex) -> YYYY-MM-DD (convenção da matriz)."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (d or "").strip())
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else (d or "").strip()


def _e_rotulo_cenario(linha):
    """Rótulo de cenário (ex.: 'Intenção de voto (estimulada) para Senado ...'),
    para separá-lo das colunas de candidato."""
    return bool(re.search(
        r"inten[çc]|voto|turno|op[çc][ãa]o|cen[áa]rio|estimulad|espont[âa]n|1[ªº]|2[ªº]",
        linha, re.I))


def parsear(texto):
    """Devolve lista de pesquisas: cada uma com metadados + lista de (candidato_partido, %)."""
    # Achata tabs em quebras de linha: o copy da tabela mistura os dois.
    linhas = [l.strip() for l in re.split(r"[\t\n]", texto) if l.strip()]
    pesquisas = []
    i = 0
    while i < len(linhas):
        # Início de pesquisa: nº de cenários (dígito), instituto, registro.
        if re.fullmatch(r"\d+", linhas[i]) and i + 2 < len(linhas) and REG.match(linhas[i + 2]):
            inst, reg, j = linhas[i + 1], linhas[i + 2], i + 3
            datas = re.search(r"(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})", linhas[j]) if j < len(linhas) else None
            if datas:
                j += 1
            modo = linhas[j] if j < len(linhas) else ""
            j += 1
            if j < len(linhas) and linhas[j].startswith("("):
                modo += " " + linhas[j]
                j += 1
            amostra = re.sub(r"\D", "", linhas[j]) if j < len(linhas) else ""
            j += 1
            margem, confianca = "", ""
            if j < len(linhas):
                m = re.match(r"±?([\d,]+)%\s*(?:\((\d+)%?\))?", linhas[j])
                if m:
                    margem = m.group(1).replace(",", ".")
                    confianca = m.group(2) or ""
                    j += 1
            while j < len(linhas) and linhas[j].startswith(("CNPJ", "CPF")):
                j += 1

            # Cabeçalho de colunas: "Cenário<tab>cand1", depois (partido), cand2, ...
            colunas = []
            if j < len(linhas) and linhas[j].lower().startswith("cenário"):
                resto = re.sub(r"^cenário\s*", "", linhas[j], flags=re.I).strip()
                if resto:
                    colunas.append(resto)
                j += 1
                while j < len(linhas):
                    l = linhas[j]
                    if l.startswith("(") and colunas:      # partido do candidato anterior
                        colunas[-1] = colunas[-1] + " " + l
                        j += 1
                    elif _e_percentual(l):                  # chegou nos números: fim do cabeçalho
                        break
                    elif _e_rotulo_cenario(l):              # rótulo do 1º cenário: acabaram as colunas
                        break
                    else:
                        # "Outros    Não Válido" às vezes vem numa linha só (espaços, não tab):
                        # quebra em colunas separadas.
                        partes = re.split(r"\s{2,}", l)
                        colunas.extend(partes if len(partes) > 1 else [l])
                        j += 1

            # Um ou mais cenários: (rótulo) seguido da(s) linha(s) de percentuais.
            # A matriz rotula o cenário por número (1, 2, 3...), não pelo texto do
            # portal, então numeramos na ordem em que aparecem nesta pesquisa.
            n_cen = 0
            while j < len(linhas):
                while j < len(linhas) and not _e_percentual(linhas[j]):
                    if re.fullmatch(r"\d+", linhas[j]) and j + 2 < len(linhas) and REG.match(linhas[j + 2]):
                        break  # é a próxima pesquisa
                    j += 1  # pula o rótulo descritivo do portal
                if j >= len(linhas) or not _e_percentual(linhas[j]):
                    break
                # Junta linhas de percentuais consecutivas: o copy separa as
                # células por TAB, e o split atomiza cada % numa linha própria.
                pcts = []
                while j < len(linhas) and _e_percentual(linhas[j]):
                    pcts += _nums(linhas[j])
                    j += 1
                n_cen += 1
                pesquisas.append({
                    "registro_tse": reg, "instituto": inst,
                    "data_campo": _data_iso(datas.group(2)) if datas else "", "modo": modo,
                    "amostra": amostra, "margem": margem, "confianca": confianca,
                    "scenario_label": str(n_cen),
                    "colunas": colunas, "percentuais": pcts,
                })
                # Se a próxima linha reinicia uma pesquisa, sai do loop de cenários.
                if j < len(linhas) and re.fullmatch(r"\d+", linhas[j]) and j + 2 < len(linhas) and REG.match(linhas[j + 2]):
                    break
            i = j
        else:
            i += 1
    return pesquisas


def montar(pesquisas, ano, uf, cargo, turno, fonte_url, disputa=""):
    """Constrói linhas no MESMO schema do Polling Manual, usando os helpers do
    core (poll_id, classificação, metodologia, normalização de nome/partido/%).

    Assim a página pode chamar salvar_tudo() e o dado sai idêntico ao do Polling
    Manual: mesmo scenario_id (a chave de dedup), mesma classificação de
    instituto, mesma metodologia. Sem isso, uma pesquisa colada e a mesma pesquisa
    cadastrada à mão virariam duas entradas, e o dedup por scenario_id não pegaria.
    """
    from polling_manual_core import (
        classificar_instituto, gerar_poll_id, gerar_scenario_id,
        normalizar_instituto, normalizar_nome_candidato, normalizar_partido, obter_metodologia,
    )
    agora = datetime.now(BRT).strftime("%Y-%m-%d %H:%M:%S")
    linhas_p, linhas_r, avisos, vistos = [], [], [], set()
    for p in pesquisas:
        cols, pcts = p["colunas"], p["percentuais"]
        if len(cols) != len(pcts):
            avisos.append(f"{p['registro_tse']} / {p['scenario_label']}: "
                          f"{len(cols)} coluna(s) mas {len(pcts)} percentual(is) — confira")
        instituto = normalizar_instituto(p["instituto"].split("<>")[0].strip())
        registro = p["registro_tse"]
        data_campo = p["data_campo"]
        # Mesma identidade do Polling Manual: registro entra no poll_id; sem
        # block_hash na chave pública (só compat).
        poll_id = gerar_poll_id(uf, instituto, registro, data_campo, cargo, turno, "",
                                disputa=disputa, exigir_registro=False)
        scenario_id = gerar_scenario_id(poll_id, p["scenario_label"])
        if scenario_id in vistos:
            avisos.append(f"{registro} / {p['scenario_label']}: cenário duplicado no texto colado")
            continue
        vistos.add(scenario_id)

        linhas_p.append({
            "scenario_id": scenario_id, "poll_id": poll_id, "ano": ano, "uf": uf,
            "cargo": cargo, "turno": turno, "disputa": disputa,
            "instituto": instituto, "classificacao_instituto": classificar_instituto(instituto),
            "registro_tse": registro, "data_campo": data_campo, "modo": p["modo"],
            "amostra": p["amostra"], "margem_erro": p["margem"], "confianca": p["confianca"],
            "scenario_label": p["scenario_label"], "fonte_url": fonte_url,
            "fonte_url_original": fonte_url, "horario_raspagem": agora,
            "metodologia": obter_metodologia(instituto), "origem": ORIGEM_COLAR,
        })
        for col, pct in zip(cols, pcts):
            bruto = col.strip()
            mp = re.search(r"\(([^)]+)\)\s*$", bruto)
            partido = normalizar_partido(mp.group(1)) if mp else ""
            nome = normalizar_nome_candidato(re.sub(r"\s*\([^)]*\)\s*$", "", bruto).strip())
            tipo = _tipo(nome)
            candidato_partido = nome if tipo == "nao_valido" else (f"{nome} ({partido})" if partido else nome)
            try:
                percentual = round(float(str(pct).replace(",", ".")), 1)
            except (ValueError, TypeError):
                percentual = None
            linhas_r.append({
                "scenario_id": scenario_id, "poll_id": poll_id, "ano": ano, "uf": uf,
                "cargo": cargo, "turno": turno, "disputa": disputa, "data_campo": data_campo,
                "instituto": instituto, "classificacao_instituto": classificar_instituto(instituto),
                "registro_tse": registro, "scenario_label": p["scenario_label"],
                "candidato": nome, "partido": partido, "candidato_partido": candidato_partido,
                "tipo": tipo, "percentual": percentual, "fonte_url": fonte_url,
                "horario_raspagem": agora, "origem": ORIGEM_COLAR,
            })
    return linhas_p, linhas_r, avisos


def _revisar(linhas_p, linhas_r, avisos):
    print(f"\n{'='*70}\nREVISÃO — {len(linhas_p)} pesquisa(s), {len(linhas_r)} resultado(s)\n{'='*70}")
    por_pesq = {}
    for r in linhas_r:
        por_pesq.setdefault(r["poll_id"], []).append(r)
    for p in linhas_p:
        print(f"\n{p['registro_tse']} · {p['instituto']} · campo {p['data_campo']} · "
              f"n={p['amostra']} · erro {p['margem_erro']}% ({p['confianca']}%) · {p['scenario_label']}")
        for r in por_pesq.get(p["poll_id"], []):
            marca = "" if r["tipo"] == "candidato" else "  [não válido]"
            print(f"    {r['candidato_partido']:<36} {r['percentual']}%{marca}")
    if avisos:
        print("\n⚠️  CONFERIR:")
        for a in avisos:
            print("   ", a)


# A gravação nas matrizes e a UI ficam na página Streamlit (7_Polling_Colar.py),
# que reusa o cliente de Sheets e o destino T1/T2 do Polling Manual. Aqui só o
# parser puro, testável sem Streamlit.
