"""Pauta salva da Agenda da Semana (agenda/semanas/<segunda>.json) lida e gravada no GitHub.

A página lê do repositório pela API, e não da cópia do app, para que a pauta buscada por
uma pessoa em "Buscar pauta de novo" apareça na hora para a equipe toda. O workflow
continua gravando por git push no mesmo arquivo; a gravação daqui usa o sha do arquivo,
então duas gravações ao mesmo tempo não se apagam (a segunda relê e grava de novo).
"""
from __future__ import annotations

import base64
import json

import requests

REPO = "meduardamo/gerador-de-envios"
PASTA = "agenda/semanas"
API = f"https://api.github.com/repos/{REPO}"


class Conflito(Exception):
    """O arquivo mudou no GitHub entre a leitura e a gravação."""


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def listar(token: str) -> dict[str, str]:
    """{segunda ISO: sha do blob} das semanas salvas no main."""
    r = requests.get(f"{API}/contents/{PASTA}", headers=_h(token), params={"ref": "main"}, timeout=20)
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return {f["name"][:-5]: f["sha"] for f in r.json() if f["name"].endswith(".json")}


def ler(token: str, sha: str) -> dict:
    """Conteúdo de um arquivo pelo sha do blob (a API de blobs aceita arquivo acima de 1 MB)."""
    r = requests.get(f"{API}/git/blobs/{sha}", headers=_h(token), timeout=30)
    r.raise_for_status()
    return json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))


def gravar(token: str, sid: str, semana: dict, sha: str | None, mensagem: str) -> str:
    """Grava agenda/semanas/<sid>.json no main. `sha` é o do arquivo lido (None se é novo).

    Levanta Conflito se outra gravação chegou antes. Devolve o sha novo do blob."""
    corpo = {"message": mensagem, "branch": "main",
             "content": base64.b64encode(
                 json.dumps(semana, ensure_ascii=False, indent=1).encode("utf-8")).decode("ascii")}
    if sha:
        corpo["sha"] = sha
    r = requests.put(f"{API}/contents/{PASTA}/{sid}.json", headers=_h(token), json=corpo, timeout=60)
    if r.status_code in (409, 422) and ("sha" in r.text or r.status_code == 409):
        raise Conflito(r.text[:200])
    r.raise_for_status()
    return r.json()["content"]["sha"]
