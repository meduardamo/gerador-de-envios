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
    "- UF sempre em caixa alta. Partido em caixa alta quando for sigla "
    "(PT, PL, PP, PSOL, MDB, PSDB).\n"
    "- Estes partidos se escrevem por extenso, em caixa mista: União, Missão, "
    "Republicanos, Democrata, Solidariedade, Rede, Avante, Podemos, Novo, "
    "Mobiliza, Agir, Cidadania.\n"
    "- Título dentro do nome de urna vai abreviado: Prof., Profa., Dr., Dra., "
    "Del., Dela., Cel., Pr., Pra. ('Professor Ivan' vira 'Prof. Ivan', "
    "'Pastor Marco' vira 'Pr. Marco'). Única exceção à "
    "regra de preservar o nome como está na fonte. Não abrevie quando a palavra "
    "for profissão fora do nome ('o delegado que conduz o caso') nem quando fizer "
    "parte de nome de cidade ('Coronel Fabriciano').\n"
    "- Profissão ou cargo que a fonte cola na frente do nome não entra: "
    "'Escritor Augusto Cury' vira 'Augusto Cury', 'Ex-senador Fulano' vira "
    "'Fulano'. Patente e profissão que fazem parte do nome de urna ficam "
    "('Capitão Wagner', 'Delegado Palumbo', 'Pastor Sena').\n"
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


# ── partido e título de urna na peça ─────────────────────────────────────────
# A peça publica o partido como ele se escreve, não como a matriz arquiva:
# "União", não "UNIAO"; "Cidadania", não "CID". Partido que só existe como sigla
# (PT, PL, PP, PSOL) continua em caixa alta.
#
# Vale SÓ aqui, no Alerta, pelo mesmo motivo do rótulo NS/NR: o Polling Manual
# grava em T1/T2 a sigla canônica, que é o que casa com a raspagem do
# PollingData.
#
# O mapa é por chave sem acento e sem caixa, com sigla e nome por extenso, porque
# o partido chega dos dois jeitos (extraído do PDF ou digitado na revisão).

_PARTIDO_NA_PECA = {
    "agir": "Agir",
    "avante": "Avante",
    "cid": "Cidadania", "cidadania": "Cidadania",
    "dem": "Democrata", "democrata": "Democrata", "democratas": "Democrata",
    "missao": "Missão",
    "mob": "Mobiliza", "mobiliza": "Mobiliza",
    "novo": "Novo", "partido novo": "Novo",
    "pode": "Podemos", "podemos": "Podemos",
    "rede": "Rede", "rede sustentabilidade": "Rede",
    "rep": "Republicanos", "republicanos": "Republicanos",
    "sd": "Solidariedade", "solidariedade": "Solidariedade",
    "uniao": "União", "uniao brasil": "União",
    # Os dois que a fonte costuma escrever por extenso ou com caixa própria e
    # que a peça publica como sigla.
    "pp": "PP", "progressista": "PP", "progressistas": "PP",
    "psol": "PSOL", "partido socialismo e liberdade": "PSOL",
}

# Título de urna: a peça abrevia ("Professor Ivan" -> "Prof. Ivan"), inclusive
# quando a fonte já abreviou sem ponto. Feminino tem forma própria.
_TITULO_URNA = {
    "professor": "Prof.", "prof": "Prof.",
    "professora": "Profa.", "profa": "Profa.",
    "doutor": "Dr.", "dr": "Dr.",
    "doutora": "Dra.", "dra": "Dra.",
    "delegado": "Del.", "del": "Del.",
    "delegada": "Dela.", "dela": "Dela.",
    "coronel": "Cel.", "cel": "Cel.", "coronela": "Cel.",
    "pastor": "Pr.", "pr": "Pr.",
    "pastora": "Pra.", "pra": "Pra.",
}


# Descritor que a fonte cola na frente do nome e que não é nome de urna:
# profissão usada como apresentação ("Escritor Augusto Cury" é "Augusto Cury"
# na urna) e cargo eletivo, que a Justiça Eleitoral não registra como nome de
# urna ("Senador Fulano" nunca é o nome registrado).
#
# Diferente de _TITULO_URNA: lá a palavra faz parte do nome e só encurta
# ("Professor Ivan" -> "Prof. Ivan"). Aqui ela sai inteira.
#
# A lista de profissão é curta e extensível de propósito: patente e profissão
# VALEM como nome de urna, e as matrizes T1/T2 estão cheias delas (Capitão
# Wagner, Coronel Rocha, Sargento Laudicério, Delegado Palumbo, Pastor Sena,
# Padre Fabrício, Missionário Evandro, Cabo Daciolo, Brigadeiro Atila Maia,
# Juíza Joenilda). Só entra palavra que a fonte usa como descrição, nunca como
# nome. Se aparecer candidato registrado com alguma delas, tire daqui.
_DESCRITOR_FORA_DO_NOME = {
    # cargo eletivo/mandato
    "presidente", "senador", "senadora", "deputado", "deputada",
    "governador", "governadora", "prefeito", "prefeita",
    "vereador", "vereadora", "ministro", "ministra",
    # profissão usada como apresentação
    "escritor", "escritora", "jornalista", "apresentador", "apresentadora",
    "empresario", "empresaria", "economista",
}

# Palavra que completa o cargo e só cai depois que o cargo caiu ("Deputado
# Federal Fulano"). Sozinha não quer dizer nada: "Federal" pode ser apelido.
_QUALIFICADOR_DE_CARGO = {"federal", "estadual", "distrital", "geral"}

# 'Ex-senador', 'Vice-governador', 'Ex-vice-prefeito' são o mesmo cargo com
# prefixo, e saem pelo mesmo motivo.
_RE_PREFIXO_CARGO = re.compile(r"^(?:(?:ex|vice)\s+)+")


def remover_descritor_fora_do_nome(nome) -> str:
    """'Escritor Augusto Cury' -> 'Augusto Cury'; 'Ex-senador Fulano' -> 'Fulano'.

    Só a(s) primeira(s) palavra(s), e só quando sobra nome depois: descritor
    sozinho é o rótulo inteiro de alguém, e no meio do nome a palavra pode ser
    sobrenome ('Ângelo Coronel', 'Marcelo Brigadeiro').
    """
    texto = re.sub(r"\s+", " ", str(nome or "")).strip()
    caiu = False
    while " " in texto:
        primeira, resto = texto.split(" ", 1)
        chave = _RE_PREFIXO_CARGO.sub("", _chave_rotulo(primeira))
        if chave in _DESCRITOR_FORA_DO_NOME or (caiu and chave in _QUALIFICADOR_DE_CARGO):
            texto, caiu = resto.strip(), True
            continue
        break
    return texto


def rotulo_partido_alerta(valor) -> str:
    """Partido como a peça publica. Fora do mapa, volta como veio: sigla que a
    extração já normalizou não tem por que ser mexida aqui."""
    bruto = re.sub(r"\s+", " ", str(valor or "")).strip()
    if not bruto:
        return ""
    return _PARTIDO_NA_PECA.get(_chave_rotulo(bruto), bruto)


def abreviar_titulo_urna(nome) -> str:
    """'Professor Ivan' -> 'Prof. Ivan'; 'DELEGADA PAULA' -> 'Dela. Paula'.

    Só a primeira palavra, e só quando tem nome depois dela: "Delegado" sozinho
    é o nome de urna inteiro de alguém, não um título a abreviar. Fora dessa
    posição a palavra pode ser sobrenome ("Zé Professor"), então não se mexe.
    """
    texto = re.sub(r"\s+", " ", str(nome or "")).strip()
    if " " not in texto:
        return texto
    primeira, resto = texto.split(" ", 1)
    abreviado = _TITULO_URNA.get(_chave_rotulo(primeira))
    return f"{abreviado} {resto}" if abreviado else texto


def nome_de_urna_alerta(nome) -> str:
    """Nome do candidato como a peça publica: sem o descritor que a fonte
    colou na frente e com título de urna abreviado."""
    return abreviar_titulo_urna(remover_descritor_fora_do_nome(nome))


# ── as mesmas duas regras aplicadas a texto corrido ──────────────────────────
# O gráfico recebe item por item, mas o envio e o resumo saem como texto do
# Gemini. O prompt já pede a forma certa; isto aqui é a garantia, porque modelo
# esquece regra de formatação no meio de um texto longo.

UFS = {"AC", "AL", "AP", "AM", "BA", "BR", "CE", "DF", "ES", "GO", "MA", "MT",
       "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR",
       "SC", "SP", "SE", "TO"}

# '(UNIAO/PR)', '(União Brasil - PR)', '(PSol/RJ)'. Hífen e travessão entram
# porque a fonte escreve dos dois jeitos e a saída padroniza na barra.
_RE_PARTIDO_UF = re.compile(
    r"\(\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.\s]{1,38}?)\s*[/\-–—]\s*([A-Za-z]{2})\s*\)")

# Título de urna no meio da frase. Sem re.IGNORECASE de propósito: "o delegado
# que assina o inquérito" é profissão, não nome, e só a forma capitalizada
# seguida de nome próprio é candidato.
#
# 'Pra.' e 'Pr.' só entram com o ponto: sem ele, 'Pra Marina' (o 'para' falado)
# viraria título. As outras formas abreviadas seguem com ponto opcional.
_RE_TITULO_TEXTO = re.compile(
    r"(?<![\wÀ-ÿ])(Professora|Professor|Doutora|Doutor|Delegada|Delegado|"
    r"Coronela|Coronel|Pastora|Pastor|Profa|Prof|Dra|Dr|Dela|Del|Cel|"
    r"Pra\.|Pr\.)\.?\s+(?=[A-ZÀ-Þ])")

# Cidade que começa com título não é candidato. Lista curta e extensível: só
# entram os topônimos que aparecem em texto político com alguma frequência.
_TOPONIMOS_COM_TITULO = {
    "coronel fabriciano", "coronel vivida", "coronel sapucaia",
    "coronel freitas", "coronel bicaco", "coronel ezequiel", "coronel murta",
    "coronel jose dias", "coronel joao pessoa", "coronel xavier chaves",
    "doutor ricardo", "doutor camargo", "doutor ulysses", "doutor severiano",
    "doutor pedrinho", "doutor mauricio cardoso",
}


# Descritor de profissão em texto corrido. Sem re.IGNORECASE, pelo mesmo motivo
# do título: "o escritor que se candidatou" é profissão dentro da frase, e tirar
# a palavra ali quebraria o português. Só a forma capitalizada seguida de nome
# próprio é apresentação de candidato.
#
# Cargo NÃO entra aqui de propósito, embora saia do rótulo do item: este passo
# vale também para o envio e o resumo de notícia, e lá "Ministro Alexandre de
# Moraes" ou "Senador Renan Calheiros" é informação da matéria, não descritor
# sobrando no nome. No rótulo do gráfico o partido e a UF já dizem quem é.
_RE_DESCRITOR_TEXTO = re.compile(
    r"(?<![\wÀ-ÿ])(Escritora|Escritor|Jornalista|Apresentadora|Apresentador|"
    r"Empresária|Empresário|Economista)\s+(?=[A-ZÀ-Þ])")


def remover_descritores_no_texto(texto: str) -> str:
    """'Escritor Augusto Cury lidera' -> 'Augusto Cury lidera'."""
    return _RE_DESCRITOR_TEXTO.sub("", str(texto or ""))


def padronizar_partidos_no_texto(texto: str) -> str:
    """'(UNIAO/PR)' -> '(União/PR)'; '(Progressistas-BA)' -> '(PP/BA)'.

    Só mexe no que estiver no formato '(algo/UF)' com UF de verdade: fora daí
    não dá pra saber se o parêntese é partido.
    """
    def troca(m):
        uf = m.group(2).upper()
        if uf not in UFS:
            return m.group(0)
        return f"({rotulo_partido_alerta(m.group(1))}/{uf})"

    return _RE_PARTIDO_UF.sub(troca, str(texto or ""))


def padronizar_titulos_no_texto(texto: str) -> str:
    """'Professor Ivan' -> 'Prof. Ivan', dentro do texto corrido."""
    def troca(m):
        depois = m.string[m.end():]
        proxima = re.split(r"[\s,;:.]", depois, maxsplit=1)[0]
        chave = _chave_rotulo(f"{m.group(1)} {proxima}")
        if chave in _TOPONIMOS_COM_TITULO:
            return m.group(0)
        return f"{_TITULO_URNA[_chave_rotulo(m.group(1))]} "

    return _RE_TITULO_TEXTO.sub(troca, str(texto or ""))


def padronizar_politicos_no_texto(texto: str) -> str:
    """Partido por extenso e título abreviado no texto pronto do Gemini. Vale
    para envio, alerta e resumo: é a mesma casa publicando."""
    return padronizar_titulos_no_texto(
        padronizar_partidos_no_texto(remover_descritores_no_texto(texto)))


def padronizar_itens_alerta(itens: list[dict]) -> list[dict]:
    """Deixa os itens do cenário na forma que a peça publica: rótulo padrão nos
    não válidos, título de urna abreviado e partido em nome próprio.

    O rótulo só mexe em quem já está marcado como nao_valido: "Castelo Branco" é
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
        elif item.get("tipo") != "nao_valido":
            novo["candidato"] = nome_de_urna_alerta(item.get("candidato"))
        novo["partido"] = rotulo_partido_alerta(item.get("partido"))
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
    return padronizar_politicos_no_texto(
        limpar_prefixo_alerta(getattr(resp, "text", "") or ""))


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
