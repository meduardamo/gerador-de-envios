"""Páginas que saem do menu lateral sem deixar de existir.

O endereço continua abrindo a página (o email de pesquisas do eixo-eleicoes
aponta para /Polling), só o link do menu some. Vai junto do CSS_LOGIN porque o
menu aparece antes do gate de login.
"""
from estilo_paginas import CSS_PAGINAS

PAGINAS_OCULTAS = ["Polling"]

CSS_MENU = "<style>" + "".join(
    f'[data-testid="stSidebarNav"] li:has(a[href$="/{p}"]) {{ display: none !important; }}'
    for p in PAGINAS_OCULTAS
) + "</style>" + CSS_PAGINAS
