"""
Texto do alerta de pesquisa eleitoral, a partir do payload estruturado que o
Polling Manual extrai (ver polling_extracao_core).

O prompt vive aqui, e não no Gerador_de_Envios.py, porque as duas páginas
escrevem o mesmo tipo de texto: o Gerador parte de notícia colada, a página de
Alerta de Pesquisa parte do payload já revisado. Regra de redação corrigida aqui
vale para as duas.

Diferença que importa: aqui o modelo NÃO lê o material bruto. Ele recebe os
números que você já conferiu na tela, em bloco fechado, e só redige. É o que
tira do caminho a alucinação de percentual e de registro TSE.
"""

import re
import urllib.request
from urllib.parse import quote, urlparse

REGRAS_POLITICOS = (
    "Formatação de políticos (obrigatório):\n"
    "- Formato: 'Nome (PARTIDO/UF)'. Use barra, nunca hífen entre PARTIDO e UF.\n"
    "- Use PARTIDO e UF em caixa alta.\n"
    "- Se partido/UF não estiverem no texto, não invente.\n"
    "- Se o texto trouxer '(PARTIDO-UF)', padronize para '(PARTIDO/UF)'.\n"
    "- PRIMEIRA menção de um político: use 'Nome (PARTIDO/UF)'.\n"
    "- MENÇÕES SEGUINTES do mesmo político no texto: use apenas o nome, sem repetir partido/UF.\n"
    "- Nunca repita o partido do mesmo político mais de uma vez no texto final.\n"
)

def _instrucao_pesquisa_eleitoral() -> str:
    return (
        "Escreva um texto curto para WhatsApp (PT-BR), factual e direto, sobre RESULTADO DE PESQUISA ELEITORAL.\n"
        "Sem opinião, sem especulação, sem bullets e sem emojis.\n"
        "Use 1 parágrafo (no máximo 90–110 palavras).\n"
        "Não comece com 'ALERTA'/'ENVIO' nem títulos.\n"
        "Foque somente em (1) cenário estimulado 1 e (2) ficha técnica.\n"
        f"\n{REGRAS_POLITICOS}\n"
        "Regras de conteúdo:\n"
        "1) Priorize o cenário estimulado 1. Se houver mais de um, ignore os demais.\n"
        "2) Liste candidatos e percentuais. Se líder isolado, comece por ele.\n"
        "   Se empate técnico, diga 'empatados dentro da margem de erro'.\n"
        "   Exceção: se indecisos forem o maior percentual, abra com 'Indecisos lideram...'.\n"
        "3) Brancos/nulos e indecisos no fim, em frase curta.\n"
        "4) Inclua ficha técnica: registro TSE, margem de erro, confiança, amostra e datas de campo.\n"
        "5) Preserve nomes, cargos, datas e números exatamente como no texto.\n"
        "6) Se algum item não estiver no texto, omita — não invente.\n"
        "\nFormato: comece pelos percentuais do cenário 1; feche com a ficha técnica em texto corrido.\n"
    )


CARGO_TEXTO = {"governador": "governador", "senador": "senador",
               "presidente": "presidente"}


def _pct_br(valor) -> str:
    """34.0 -> '34%'; 4.5 -> '4,5%'."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return ""
    if abs(n - round(n)) < 0.05:
        return f"{int(round(n))}%"
    return f"{n:.1f}".replace(".", ",") + "%"


def _data_br(iso: str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(iso or "").strip())
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(iso or "").strip()


def bloco_dados_pesquisa(payload: dict, cenario: dict) -> str:
    """Monta o bloco de fatos que vai no lugar do 'texto fonte'.

    Só entra o que existe no payload: campo vazio é omitido, nunca preenchido
    com suposição. O modelo recebe isso como a única verdade disponível.
    """
    p, c = payload or {}, cenario or {}
    cargo = (c.get("cargo") or p.get("cargo") or "").lower()
    uf = (c.get("uf") or p.get("uf") or "").upper()
    turno = (c.get("turno") or p.get("turno") or "t1").lower()

    linhas = []
    if cargo in CARGO_TEXTO:
        linhas.append(f"Cargo: {CARGO_TEXTO[cargo]}")
    if uf:
        linhas.append(f"UF: {uf}")
    linhas.append("Turno: 2º turno" if turno == "t2" else "Turno: 1º turno")
    if str(p.get("instituto") or "").strip():
        linhas.append(f"Instituto: {str(p['instituto']).strip()}")
    if str(p.get("registro_tse") or "").strip():
        linhas.append(f"Registro TSE: {str(p['registro_tse']).strip()}")
    if p.get("data_campo"):
        linhas.append(f"Data final de campo: {_data_br(p['data_campo'])}")
    if p.get("amostra"):
        linhas.append(f"Amostra: {p['amostra']} entrevistas")
    if p.get("margem_erro") is not None:
        linhas.append(f"Margem de erro: {_pct_br(p['margem_erro']).replace('%', '')} pontos percentuais")
    if p.get("confianca") is not None:
        linhas.append(f"Nível de confiança: {_pct_br(p['confianca'])}")
    if str(p.get("modo") or "").strip():
        linhas.append(f"Modo de coleta: {str(p['modo']).strip()}")

    candidatos, invalidos = [], []
    for item in c.get("itens") or []:
        if item.get("percentual") is None:
            continue
        nome = str(item.get("candidato") or "").strip()
        partido = str(item.get("partido") or "").strip()
        pct = _pct_br(item["percentual"])
        if item.get("tipo") == "nao_valido":
            invalidos.append(f"- {nome}: {pct}")
        else:
            # (PARTIDO/UF) com barra, o formato da casa; sem partido, só o nome.
            rotulo = f"{nome} ({partido}/{uf})" if partido and uf else (
                f"{nome} ({partido})" if partido else nome)
            candidatos.append((float(item["percentual"]), f"- {rotulo}: {pct}"))

    candidatos.sort(key=lambda x: x[0], reverse=True)
    if candidatos:
        linhas.append("\nResultado do cenário (do maior para o menor):")
        linhas += [linha for _, linha in candidatos]
    if invalidos:
        linhas.append("\nBrancos, nulos e indecisos:")
        linhas += invalidos

    return "\n".join(linhas)


def limpar_prefixo_alerta(resumo: str) -> str:
    """Tira 'ALERTA:' / 'ENVIO -' que o modelo às vezes cola na frente, já que o
    cabeçalho é montado por compilar_alerta_pesquisa()."""
    s = (resumo or "").strip()
    s = re.sub(r"^(ALERTA|ENVIO)\s*(?:[-–—]|:)?\s*[^:\n]{0,60}:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(ALERTA|ENVIO)\s*(?:[-–—]|:)\s*", "", s, flags=re.IGNORECASE)
    return s.strip()


def gerar_texto_alerta_pesquisa(payload: dict, cenario: dict, *, gerar_conteudo,
                                modelo: str) -> str:
    """Redige o alerta a partir dos dados já conferidos.

    gerar_conteudo/modelo entram por parâmetro para este módulo não importar o
    cliente do Gemini nem o Streamlit: quem chama passa o
    polling_extracao_core.gerar_conteudo_gemini.
    """
    dados = bloco_dados_pesquisa(payload, cenario)
    prompt = (
        f"{_instrucao_pesquisa_eleitoral()}\n"
        "Os DADOS abaixo já foram conferidos por uma pessoa e são a única fonte.\n"
        "Não acrescente número, nome, data ou registro que não esteja neles.\n"
        "Se um item da ficha técnica não aparecer nos dados, apenas omita.\n"
        f"\nDADOS DA PESQUISA:\n{dados}\n"
    )
    resp = gerar_conteudo(modelo, prompt)
    return limpar_prefixo_alerta(getattr(resp, "text", "") or "")


def compilar_alerta_pesquisa(texto: str, titulo: str, uf: str = "",
                             link: str = "", data_envio: str = "") -> str:
    """Fecha o formato de WhatsApp da casa: cabeçalho, data, título, corpo, link."""
    cabecalho = "Alerta | Eixo | Eleições"
    if (uf or "").strip().upper() not in ("", "BR"):
        cabecalho += f" | Subnacional | {uf.strip().upper()}"
    partes = [f"*{cabecalho}*"]
    if data_envio:
        partes.append(data_envio)
    partes += ["", f"*{(titulo or '').strip()}*", "", (texto or "").strip()]
    if (link or "").strip():
        partes += ["", f"Link: {link.strip()}"]
    return "\n".join(partes)


# ── link ─────────────────────────────────────────────────────────────────────

def normalizar_link(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    if not re.match(r"^https?://", s, flags=re.IGNORECASE):
        s = "https://" + s
    p = urlparse(s)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    return s

def encurtar_link(url: str) -> str:
    if not url:
        return url
    try:
        api_url = f"http://tinyurl.com/api-create.php?url={quote(url)}"
        with urllib.request.urlopen(api_url, timeout=5) as resp:
            return resp.read().decode()
    except Exception:
        return url
