"""Coleta a pauta da semana e grava em agenda/semanas/<segunda>.json.

Roda pelo workflow "Agenda da Semana" toda segunda. Sem argumento, pega a semana
corrente (ou a seguinte, se rodar no fim de semana); com AAAA-MM-DD, a semana
que começa na segunda daquela data.

A rodada de segunda (ou anterior) fixa a foto da pauta em `idsSegunda`; as rodadas
seguintes da mesma semana (terça) mantêm a foto, e a página marca como novo o que
não estava nela.
"""
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import agenda_semana_core as ag

agora = dt.datetime.now(ZoneInfo("America/Recife"))
if len(sys.argv) > 1 and sys.argv[1].strip():
    base = dt.date.fromisoformat(sys.argv[1].strip())
else:
    base = agora.date()
    if base.weekday() >= 5:
        base += dt.timedelta(days=7 - base.weekday())
seg = base - dt.timedelta(days=base.weekday())

semana = ag.coletar_semana(seg, seg + dt.timedelta(days=4))
semana["coletadoEm"] = agora.strftime("%d/%m %H:%M")
for erro in semana["erros"]:
    print(f"::warning::{erro}")

saida = Path("agenda/semanas") / f"{seg.isoformat()}.json"
anterior = json.loads(saida.read_text(encoding="utf-8")) if saida.exists() else None
semana.update(ag.foto_segunda(semana, anterior, agora.date() <= seg))
saida.parent.mkdir(parents=True, exist_ok=True)
saida.write_text(json.dumps(semana, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{saida}: {len(semana['itens'])} itens ({semana['periodo']})")
if semana["erros"] and not semana["itens"]:
    sys.exit(1)
