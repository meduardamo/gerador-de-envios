"""
Leitura de tabela por Gemini para o Gerador de Gráficos: entra PDF, imagem ou
texto solto e sai a tabela já no formato do editor.

O modelo só TRANSCREVE. Ele não calcula, não completa célula vazia, não escolhe
tipo de gráfico e não desenha: o desenho e as contas são do código
(gerador_graficos_core). O que ele devolve cai no editor da página, onde quem
monta a peça confere contra a fonte.

Guarda contra número inventado: quando a fonte tem texto (texto colado ou PDF
com camada de texto), cada número devolvido é procurado nela. O que não for
achado volta listado, e a página mostra. Com imagem pura não há contra o que
conferir por código, e a página diz isso.

Sem Streamlit, como os outros cores.
"""

import re

import fitz
from google.genai import types

from polling_extracao_core import (
    GEMINI_MODEL,
    extrair_json_de_texto_bruto,
    extrair_texto_pdf_bytes,
    gerar_conteudo_gemini,
    render_pdf_page_png,
)

UNIDADES_ACEITAS = ("R$ milhões", "R$ bilhões", "R$", "%", "Número")
MAX_PAGINAS = 5

PROMPT = """Você transcreve UMA tabela de um documento brasileiro (orçamento, execução, série histórica, ranking) para JSON.

Regras:
- Transcreva só o que está escrito. Não calcule, não some, não estime, não preencha célula vazia.
- Copie cada número exatamente como aparece na fonte, com vírgula decimal, ponto de milhar e asterisco se houver. Tire só o símbolo de moeda e a abreviação de escala ("R$ 308,8 mi" vira "308,8").
- Célula vazia ou com traço vira "".
- A primeira coluna é a categoria de cada linha (ano, órgão, UF, programa).
- Coluna de percentual mantém o sinal: "72,6%".
- "titulo": só se a fonte traz um título para a tabela; senão "".
- "nota": nota de rodapé ou fonte escrita junto da tabela, copiada literalmente; senão "".
- "unidade": uma de "R$ milhões", "R$ bilhões", "R$", "%", "Número", conforme a fonte indica para os valores; na dúvida "".
- Se houver mais de uma tabela, transcreva a que o pedido abaixo indicar; sem pedido, a primeira.
- Se não houver tabela, devolva "colunas": [] e "linhas": [].

Responda só com o JSON:
{"titulo": "", "colunas": ["Ano", "..."], "linhas": [["2023", "..."]], "unidade": "", "nota": ""}
"""


def paginas_do_texto(texto: str, total: int) -> list[int]:
    """'3', '2-4' ou '1, 3' -> índices de página (base zero), sem repetir e
    dentro do documento. Vazio ou ilegível cai na primeira página."""
    indices: list[int] = []
    for pedaco in re.split(r"[,;\s]+", str(texto or "").strip()):
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", pedaco)
        if not m:
            continue
        ini, fim = int(m.group(1)), int(m.group(2) or m.group(1))
        for pagina in range(min(ini, fim), max(ini, fim) + 1):
            if 1 <= pagina <= total and pagina - 1 not in indices:
                indices.append(pagina - 1)
    return (indices or [0])[:MAX_PAGINAS]


def normalizar_tabela(payload: dict) -> dict:
    """Resposta do modelo -> {titulo, colunas, linhas, unidade, nota}, com tudo
    em texto e todas as linhas na largura do cabeçalho."""
    payload = payload if isinstance(payload, dict) else {}
    colunas = [str(c or "").strip() for c in payload.get("colunas") or []]
    linhas = []
    for linha in payload.get("linhas") or []:
        if not isinstance(linha, (list, tuple)):
            continue
        celulas = ["" if c is None else str(c).strip() for c in linha]
        celulas = (celulas + [""] * len(colunas))[:len(colunas)]
        if any(celulas):
            linhas.append(celulas)
    unidade = str(payload.get("unidade") or "").strip()
    return {
        "titulo": str(payload.get("titulo") or "").strip(),
        "colunas": colunas,
        "linhas": linhas,
        "unidade": unidade if unidade in UNIDADES_ACEITAS else "",
        "nota": str(payload.get("nota") or "").strip(),
    }


def numeros_fora_da_fonte(tabela: dict, texto_fonte: str) -> list[str]:
    """Células com número que não aparece no texto da fonte.

    Compara só os dígitos e os separadores, sem espaço: a fonte pode escrever
    'R$ 308,8 mi' e a célula trazer '308,8'. Não prova que o número está na
    célula certa, só que ele existe na fonte.
    """
    fonte = re.sub(r"\s+", "", str(texto_fonte or ""))
    if not fonte:
        return []
    fora = []
    for linha in tabela.get("linhas") or []:
        for celula in linha:
            numero = re.sub(r"[^0-9.,]", "", celula).strip(".,")
            if numero and numero not in fonte:
                fora.append(celula)
    return fora


def extrair_tabela(*, texto: str = "", imagens: list[tuple[bytes, str]] | None = None,
                   pedido: str = "") -> dict:
    """Chama o Gemini e devolve a tabela normalizada.

    imagens: [(bytes, mime_type)]. texto e imagens podem ir juntos: num PDF a
    imagem dá a estrutura da tabela e o texto dá os dígitos exatos.
    """
    partes = [PROMPT]
    if pedido.strip():
        partes.append(f"Pedido de quem está montando a peça: {pedido.strip()}")
    if texto.strip():
        partes.append(f"Texto da fonte:\n{texto.strip()}")
    for dados, mime in imagens or []:
        partes.append(types.Part.from_bytes(data=dados, mime_type=mime))
    if len(partes) == 1 + bool(pedido.strip()):
        raise ValueError("Envie um arquivo ou cole o texto da fonte.")

    resp = gerar_conteudo_gemini(GEMINI_MODEL, partes)
    tabela = normalizar_tabela(extrair_json_de_texto_bruto(getattr(resp, "text", "") or ""))
    if len(tabela["colunas"]) < 2 or not tabela["linhas"]:
        raise RuntimeError("Não achei tabela nessa fonte. Confira a página do PDF "
                           "ou diga no pedido qual tabela ler.")
    return tabela


def extrair_de_pdf(pdf_bytes: bytes, paginas: str = "", pedido: str = "") -> tuple[dict, str]:
    """(tabela, texto das páginas). paginas é o que a pessoa digitou ('3',
    '2-4'). O texto volta para a guarda de números; vem vazio quando o PDF é
    digitalizado."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        total = doc.page_count
    indices = paginas_do_texto(paginas, total)
    texto = extrair_texto_pdf_bytes(pdf_bytes, page_indices=indices) or ""
    imagens = [(render_pdf_page_png(pdf_bytes, i, zoom=2.5), "image/png") for i in indices]
    return extrair_tabela(texto=texto, imagens=imagens, pedido=pedido), texto
