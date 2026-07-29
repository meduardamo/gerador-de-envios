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
import unicodedata
import urllib.request
from urllib.parse import quote, urlparse

from graficos_pesquisa_core import periodo_campo_br

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

def _instrucao_pesquisa_eleitoral(com_selecao_de_cenario: bool = True) -> str:
    """Formato do envio de pesquisa eleitoral, o mesmo nas duas páginas.

    com_selecao_de_cenario=False no Alerta de Pesquisa: lá o cenário já vem
    escolhido e revisado por uma pessoa, então as regras de "pegue o cenário 1 e
    ignore o resto" atrapalhariam (a média dos cenários é um cenário só).
    """
    escolha_cenario = (
        "Foque somente em (1) cenário estimulado 1 e (2) ficha técnica.\n"
        if com_selecao_de_cenario else "")
    regra_cenario = (
        "- Priorize o cenário estimulado 1. Se houver mais de um, ignore os demais.\n"
        if com_selecao_de_cenario else "")
    abertura = ("comece pelos percentuais do cenário 1"
                if com_selecao_de_cenario else "comece pelos percentuais")
    return (
        "Escreva um texto curto para WhatsApp (PT-BR), factual e direto, sobre RESULTADO DE PESQUISA ELEITORAL.\n"
        "Sem opinião, sem especulação, sem bullets e sem emojis.\n"
        "Use 1 parágrafo (no máximo 90–110 palavras).\n"
        "Não comece com 'ALERTA'/'ENVIO' nem títulos.\n"
        f"{escolha_cenario}"
        f"\n{REGRAS_POLITICOS}\n"
        "Regras de conteúdo:\n"
        f"{regra_cenario}"
        "- Liste candidatos e percentuais. Se líder isolado, comece por ele.\n"
        "  Se empate técnico, diga 'empatados dentro da margem de erro'.\n"
        "  Exceção: se indecisos forem o maior percentual, abra com 'Indecisos lideram...'.\n"
        "- Brancos/nulos e indecisos no fim, em frase curta.\n"
        "- Inclua ficha técnica: registro TSE, margem de erro, confiança, amostra e datas de campo.\n"
        "- Preserve nomes, cargos, datas e números exatamente como no texto.\n"
        "- Se algum item não estiver no texto, omita — não invente.\n"
        f"\nFormato: {abertura}; feche com a ficha técnica em texto corrido.\n"
    )


CARGO_TEXTO = {"governador": "governador", "senador": "senador",
               "presidente": "presidente"}


# ── rótulo dos itens não válidos ─────────────────────────────────────────────
# Cada instituto escreve à sua maneira ("Não sabe/Não respondeu", "NS/NR",
# "Branco/Nulo", "Brancos e nulos"). Na peça publicada isso vira sempre o mesmo
# par, senão dois gráficos da mesma série saem com legenda diferente.
#
# Vale SÓ aqui, no Alerta: o Polling Manual continua gravando na matriz o rótulo
# como o instituto publicou.

ROTULO_NS_NR = "NS/NR"
ROTULO_BRANCOS_NULOS = "Brancos/Nulos"

_PADROES_NS_NR = (
    r"\bns\s*/?\s*nr\b", r"^ns$", r"^nr$",
    # "Indecisos" é o mesmo item que "Não sabe" com outro nome: os institutos
    # publicam um OU outro, nunca os dois (Quaest usa indecisos, AtlasIntel usa
    # não sei). Se algum publicar separado, a trava de rótulo repetido guarda o
    # segundo com o nome original.
    r"indecis",
    r"nao sabe", r"nao sei", r"nao sabem", r"nao souber",
    r"nao respond", r"nao opin", r"nao inform", r"nao declar", r"nao revel",
    r"nao quis", r"nao quer responder", r"sem opiniao",
    r"prefer\w* nao responder", r"prefiro nao responder",
)


def _chave_rotulo(texto: str) -> str:
    """'Não sabe / Não respondeu' -> 'nao sabe nao respondeu'."""
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def padronizar_rotulo_nao_valido(nome: str) -> str:
    """Devolve o rótulo da casa. Texto que não for de nenhuma das duas famílias
    volta como veio ('Nenhum', 'Indecisos' e afins seguem intactos)."""
    chave = _chave_rotulo(nome)
    if not chave:
        return str(nome or "").strip()
    tem_bn = "branco" in chave or "nulo" in chave
    tem_ns = any(re.search(p, chave) for p in _PADROES_NS_NR)
    if tem_bn and tem_ns:
        # Instituto que publica tudo numa linha só ("Branco/Nulo/NS/NR"):
        # padroniza os dois nomes sem fingir que virou uma categoria só.
        return f"{ROTULO_BRANCOS_NULOS} e {ROTULO_NS_NR}"
    if tem_bn:
        return ROTULO_BRANCOS_NULOS
    if tem_ns:
        return ROTULO_NS_NR
    return str(nome or "").strip()


def padronizar_itens_alerta(itens: list[dict]) -> list[dict]:
    """Aplica o rótulo padrão nos itens não válidos do cenário.

    Só mexe em quem já está marcado como nao_valido: "Castelo Branco" é
    sobrenome de candidato, e renomear isso seria pior que a bagunça.

    Não junta linhas: se dois itens do mesmo cenário cairem no mesmo rótulo
    (branco e nulo publicados separados, ou "Indecisos" ao lado de "NS/NR"), os
    dois ficam com o nome original. Renomear os dois deixaria o gráfico com duas
    barras de mesmo nome, e somar inventaria um número que a fonte não publicou.
    """
    itens = list(itens or [])
    alvos = [padronizar_rotulo_nao_valido(item.get("candidato"))
             if item.get("tipo") == "nao_valido" else None for item in itens]
    repetidos = {alvo for alvo in alvos if alvo and alvos.count(alvo) > 1}

    saida = []
    for item, alvo in zip(itens, alvos):
        novo = dict(item)
        if alvo and alvo not in repetidos:
            novo["candidato"] = alvo
        saida.append(novo)
    return saida


def _pct_br(valor) -> str:
    """34.0 -> '34%'; 4.5 -> '4,5%'."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return ""
    if abs(n - round(n)) < 0.05:
        return f"{int(round(n))}%"
    return f"{n:.1f}".replace(".", ",") + "%"


MODOS_COMBINACAO = ("media", "soma")


def combinar_cenarios(cenarios: list[dict], modo: str = "media") -> list[dict]:
    """Junta vários cenários num só, casando pelo nome.

    Existe por causa do Senado com DUAS vagas, em que a mesma pesquisa aparece
    publicada de jeitos diferentes: parte dos institutos já entrega o resultado
    consolidado numa pergunta só (AtlasIntel), parte publica dois ou três
    cenários estimulados separados (Quaest). Não dá pra decidir por código qual
    é qual, então quem lê a matéria escolhe o que combinar.

    modo "media" (padrão): média DOS DISPONÍVEIS, ou seja, cada nome é dividido
    só pelos cenários em que ele aparece. Quem está em um cenário só mantém o
    valor que tem, em vez de ser diluído por uma ausência que não é zero.
    modo "soma": soma direta, para quando os cenários forem o 1º e o 2º voto da
    mesma pergunta e a leitura da disputa for o total (~200%).

    Nome é casado sem acento e sem caixa; partido e tipo vêm da primeira
    aparição, e o percentual sai com uma casa decimal.
    """
    modo = modo if modo in MODOS_COMBINACAO else "media"
    combinado: dict[str, dict] = {}
    for cenario in cenarios or []:
        for item in (cenario or {}).get("itens") or []:
            nome = str(item.get("candidato") or "").strip()
            chave = _chave_rotulo(nome)
            if not chave:
                continue
            atual = combinado.setdefault(chave, {
                "candidato": nome,
                "partido": "",
                "percentual": None,
                "tipo": item.get("tipo") or "candidato",
                "_total": 0.0,
                "_vezes": 0,
            })
            if not atual["partido"]:
                atual["partido"] = str(item.get("partido") or "").strip()
            if item.get("percentual") is not None:
                atual["_total"] += float(item["percentual"])
                atual["_vezes"] += 1

    saida = []
    for item in combinado.values():
        vezes = item.pop("_vezes")
        total = item.pop("_total")
        if vezes:
            item["percentual"] = round(total / vezes if modo == "media" else total, 1)
        saida.append(item)
    return saida


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
    periodo = periodo_campo_br(p.get("data_campo_inicio"), p.get("data_campo"))
    if periodo:
        linhas.append(f"Período de campo: {periodo}")
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
    combinacao = c.get("combinacao") or {}
    rotulos_comb = ", ".join(combinacao.get("cenarios") or [])
    if combinacao.get("modo") == "media":
        linhas.append(
            f"\nATENÇÃO: os percentuais abaixo são a MÉDIA dos cenários "
            f"estimulados da mesma pesquisa ({rotulos_comb}), calculada nome a "
            "nome sobre os cenários em que cada um aparece. Diga isso no texto, "
            "uma vez, com naturalidade (ex.: 'na média dos cenários "
            "estimulados'). Não descreva como se fosse um cenário publicado "
            "pelo instituto e não recalcule nada."
        )
    elif combinacao.get("modo") == "soma":
        # Sem isso o modelo trata soma de ~200% como erro e "corrige" o número.
        linhas.append(
            "\nATENÇÃO: os percentuais abaixo somam as respostas de mais de uma "
            f"pergunta da mesma pesquisa ({rotulos_comb}). São duas vagas em "
            "disputa e cada entrevistado cita dois nomes, então o total passa "
            "de 100% — isso está correto, não é erro. Diga no texto que o "
            "percentual considera os dois votos do entrevistado. Nunca reduza, "
            "divida ou 'ajuste' os números."
        )
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


LIMITE_CONTEXTO = 20000


def gerar_texto_alerta_pesquisa(payload: dict, cenario: dict, *, gerar_conteudo,
                                modelo: str, texto_fonte: str = "") -> str:
    """Redige o alerta a partir dos dados já conferidos.

    texto_fonte é a matéria/relatório que originou a extração. Entra como
    CONTEXTO, não como fonte de número: sem ele o modelo só tem uma tabela e
    devolve uma lista de percentuais, em vez do texto que a casa publica (o que
    está em disputa, quantas vagas, quem lidera, quem empata). Os números
    continuam vindo só do bloco conferido.

    gerar_conteudo/modelo entram por parâmetro para este módulo não importar o
    cliente do Gemini nem o Streamlit: quem chama passa o
    polling_extracao_core.gerar_conteudo_gemini.
    """
    dados = bloco_dados_pesquisa(payload, cenario)
    contexto = (texto_fonte or "").strip()[:LIMITE_CONTEXTO]
    prompt = (
        f"{_instrucao_pesquisa_eleitoral(com_selecao_de_cenario=False)}\n"
        "Regras que valem sobre as anteriores:\n"
        "- Os DADOS CONFERIDOS abaixo são UM cenário só, já escolhido e revisado\n"
        "  por uma pessoa. São a única fonte de número, nome, partido e ficha\n"
        "  técnica. Não acrescente nada que não esteja neles.\n"
        "- Abra pela leitura da disputa, nunca pela ficha técnica: quem lidera e\n"
        "  com quanto, quem vem em seguida, quem está empatado. Dois nomes\n"
        "  separados por menos que o dobro da margem de erro estão empatados\n"
        "  dentro da margem de erro, e é assim que isso deve ser dito.\n"
        "- Feche com brancos, nulos e NS/NR em frase curta e a ficha técnica em\n"
        "  texto corrido. Item que não estiver nos dados, omita.\n"
    )
    if contexto:
        prompt += (
            "- O MATERIAL DE ORIGEM serve para o enquadramento da disputa (o que\n"
            "  está em jogo, quantas vagas, o que a pergunta mede, quem\n"
            "  encomendou) e para o texto não sair como lista de percentuais.\n"
            "  NUNCA tire número dele: percentual que estiver lá e não estiver nos\n"
            "  DADOS CONFERIDOS é de outro cenário e deve ser ignorado. Não cite\n"
            "  outro cenário nem compare com ele.\n"
        )
    prompt += f"\nDADOS CONFERIDOS:\n{dados}\n"
    if contexto:
        prompt += ("\nMATERIAL DE ORIGEM (contexto, não é fonte de número):\n"
                   f"{contexto}\n")
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
