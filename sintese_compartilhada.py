"""Síntese da Semana compartilhada pela equipe (pedido da Mayara, 19/11/2026).

Quem sobe a Divisão ou gera os bullets grava a rodada da semana na planilha da Agenda; quem
abre a página depois vê a mesma rodada. Cada chave ligada ou desligada e cada texto editado
vira uma linha na aba de revisão (só acrescenta, a última de cada item vale), como a seleção
da Agenda da Semana.

Abas (criadas na primeira gravação):
- "Síntese rodada": Semana | Parte | Salvo por | Salvo em | JSON (o JSON grande segue nas colunas
  seguintes, em pedaços, porque a célula aceita 50 mil caracteres).
- "Síntese revisão": Semana | Versão | Chave | Valor | Salvo por | Salvo em.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from zoneinfo import ZoneInfo

ABA_RODADA = "Síntese rodada"
ABA_REVISAO = "Síntese revisão"
CAB_RODADA = ["Semana", "Parte", "Salvo por", "Salvo em", "JSON"]
CAB_REVISAO = ["Semana", "Versão", "Chave", "Valor", "Salvo por", "Salvo em"]
PEDACO = 45000
TZ = ZoneInfo("America/Sao_Paulo")


def agora() -> str:
    return dt.datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")


def chave_de(*partes: str) -> str:
    """Chave estável e só com letras e números (vira classe de CSS no Streamlit)."""
    return hashlib.md5("|".join(partes).encode("utf8")).hexdigest()[:10]


# datas viajam como {"__data__": "aaaa-mm-dd"}
def _padrao(o):
    if isinstance(o, dt.date):
        return {"__data__": o.isoformat()}
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(type(o).__name__)


def _gancho(d):
    return dt.date.fromisoformat(d["__data__"]) if set(d) == {"__data__"} else d


def para_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_padrao)


def de_json(txt: str):
    return json.loads(txt, object_hook=_gancho)


def _aba(sh, nome: str, cab: list[str], colunas: int):
    import gspread
    try:
        return sh.worksheet(nome)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=nome, rows=2, cols=colunas)
        ws.update(values=[cab], range_name="A1")
        return ws


def abas(sh):
    return _aba(sh, ABA_RODADA, CAB_RODADA, 40), _aba(sh, ABA_REVISAO, CAB_REVISAO, len(CAB_REVISAO))


def ler_rodada(ws, semana: dt.date) -> dict:
    """{parte: {"valor": objeto, "por": quem, "em": quando}} da semana."""
    s = semana.isoformat()
    out = {}
    for row in ws.get_all_values()[1:]:
        if len(row) >= 5 and row[0] == s:
            try:
                out[row[1]] = {"valor": de_json("".join(row[4:])), "por": row[2], "em": row[3]}
            except (json.JSONDecodeError, ValueError):
                continue
    return out


def salvar_partes(ws, semana: dt.date, partes: dict, quem: str, apagar: tuple[str, ...] = ()) -> None:
    """Grava (ou troca) as partes da semana; as de `apagar` saem."""
    s = semana.isoformat()
    vals = ws.get_all_values()
    linha_de = {row[1]: i + 1 for i, row in enumerate(vals) if i and len(row) >= 2 and row[0] == s}
    quando = agora()
    novas, atualiza = [], []
    for nome, obj in partes.items():
        txt = para_json(obj)
        pedacos = [txt[i:i + PEDACO] for i in range(0, len(txt), PEDACO)] or [""]
        row = [s, nome, quem, quando] + pedacos
        if nome in linha_de:
            atualiza.append((linha_de[nome], row))
        else:
            novas.append(row)
    largura = max([len(r) for _, r in atualiza] + [len(r) for r in novas] + [0])
    if largura > ws.col_count:
        ws.add_cols(largura - ws.col_count)
    if atualiza:
        ws.batch_update([{"range": f"A{n}", "values": [r + [""] * (largura - len(r))]} for n, r in atualiza],
                        value_input_option="RAW")
    if novas:
        ws.append_rows(novas, value_input_option="RAW")
    for n in sorted((linha_de[p] for p in apagar if p in linha_de and p not in partes), reverse=True):
        ws.delete_rows(n)


def apagar_semana(ws_rodada, semana: dt.date) -> None:
    s = semana.isoformat()
    vals = ws_rodada.get_all_values()
    for n in sorted((i + 1 for i, row in enumerate(vals) if i and row and row[0] == s), reverse=True):
        ws_rodada.delete_rows(n)


def registrar(ws, semana: dt.date, versao: str, chave: str, valor, quem: str) -> str:
    quando = agora()
    ws.append_row([semana.isoformat(), versao, chave, para_json(valor), quem, quando],
                  value_input_option="RAW")
    return quando


def ler_revisao(ws, semana: dt.date, versao: str) -> dict:
    """{chave: {"valor", "por", "em", "n"}}: a última linha de cada chave na versão da rodada."""
    s = semana.isoformat()
    out = {}
    for n, row in enumerate(ws.get_all_values()[1:]):
        if len(row) >= 6 and row[0] == s and row[1] == versao:
            try:
                out[row[2]] = {"valor": de_json(row[3]), "por": row[4], "em": row[5], "n": n}
            except (json.JSONDecodeError, ValueError):
                continue
    return out


def quem_curto(quem: str) -> str:
    """'EixoGov (Lívia)' -> 'Lívia'; sem nome entre parênteses fica o login."""
    m = re.search(r"\(([^)]+)\)\s*$", quem or "")
    return m.group(1) if m else (quem or "")


def hora_curta(quando: str) -> str:
    """'19/11/2026 10:32:05' -> '19/11 10:32'."""
    m = re.match(r"(\d{2}/\d{2})/\d{4} (\d{2}:\d{2})", quando or "")
    return f"{m.group(1)} {m.group(2)}" if m else (quando or "")
