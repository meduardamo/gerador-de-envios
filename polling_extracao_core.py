"""
Extração de pesquisa eleitoral (texto ou PDF) para o payload estruturado que o
Polling Manual e o Alerta de Pesquisa consomem.

Saiu de pages/2_Polling.py para virar código único: as armadilhas já validadas
contra PDF real (senador nunca tem t2, cargo/turno por cenário, coluna
"Porcentual" vs "Porcentagem válida", confiança só quando declarada na fonte)
valem para as duas páginas. Corrigir o prompt aqui conserta as duas.

Sem Streamlit de propósito: dá pra testar o parser sem subir o app. A chave da
API entra por definir_api_key() (a página injeta st.secrets) ou pela env
GEMINI_API_KEY.

Payload devolvido por extrair_dados_polling_gemini():
    cargo, turno, uf, instituto, registro_tse, data_campo, data_campo_inicio,
    amostra, margem_erro, confianca, modo, observacoes, pendencias,
    cenarios: [{scenario_label, cargo, turno, uf,
                itens: [{candidato, partido, percentual, tipo}]}]
"""

import json
import os
import re
import unicodedata
from datetime import datetime
from functools import lru_cache

import fitz
from google import genai
from google.genai import types

from polling_manual_core import (
    normalizar_instituto,
    normalizar_partido,
)

GEMINI_MODEL = "gemini-2.5-flash"

UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]
POLLING_MANUAL_CARGOS = ["governador", "senador", "presidente"]
POLLING_MANUAL_TURNOS = ["t1", "t2"]
POLLING_MANUAL_TIPOS_RESULTADO = ["candidato", "nao_valido"]

_API_KEY = ""


def definir_api_key(chave: str) -> None:
    """A página injeta a chave (st.secrets) uma vez, no import. Fora do
    Streamlit, get_gemini_client() cai na variável de ambiente."""
    global _API_KEY
    _API_KEY = (chave or "").strip()


@lru_cache(maxsize=2)
def _client_gemini(chave: str):
    return genai.Client(api_key=chave)


def get_gemini_client():
    chave = _API_KEY or os.getenv("GEMINI_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("Configure a GEMINI_API_KEY nos Secrets ou nas variáveis de ambiente.")
    return _client_gemini(chave)


def gerar_conteudo_gemini(model: str, contents, *, tentativas: int = 3, backoff_inicial: float = 1.5):
    """Chama o Gemini com retry/backoff. Lança RuntimeError se todas as
    tentativas falharem ou se o conteúdo retornado vier vazio."""
    import time

    client = get_gemini_client()
    ultimo_erro: Exception | None = None

    for tentativa in range(1, tentativas + 1):
        try:
            try:
                config = types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=8000)
                )
                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except Exception:
                # Algumas versões do SDK não aceitam ThinkingConfig; tenta sem.
                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                )

            if getattr(resp, "text", None):
                return resp

            ultimo_erro = RuntimeError("Gemini retornou resposta vazia.")
        except Exception as exc:
            ultimo_erro = exc

        if tentativa < tentativas:
            time.sleep(backoff_inicial * (2 ** (tentativa - 1)))

    raise RuntimeError(
        f"Falha ao chamar o Gemini após {tentativas} tentativas: {ultimo_erro}"
    )


def normalizar_texto_simples(valor) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()



def normalizar_percentual_simples(valor) -> float | None:
    s = normalizar_texto_simples(valor).replace("%", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def normalizar_percentual_resultado(valor) -> float | None:
    """Percentual de candidato/opção arredondado para 1 casa (pro mais perto),
    igual ao resto das matrizes. Instituto que reporta 2 casas (ex.: 41,49)
    vira 41.5, não 41.4 — o editor com step 0.1 truncava a segunda casa."""
    n = normalizar_percentual_simples(valor)
    return round(n, 1) if n is not None else None


def normalizar_inteiro_simples(valor) -> int | None:
    s = normalizar_texto_simples(valor)
    if not s:
        return None
    s = re.sub(r"[^\d]", "", s)
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def limitar_inteiro(valor, minimo: int, maximo: int, padrao: int) -> int:
    n = normalizar_inteiro_simples(valor)
    if n is None:
        return padrao
    return max(minimo, min(maximo, n))


def limitar_float(valor, minimo: float, maximo: float, padrao: float) -> float:
    n = normalizar_percentual_simples(valor)
    if n is None:
        return padrao
    return max(minimo, min(maximo, float(n)))


def extrair_json_de_texto_bruto(texto: str) -> dict:
    bruto = (texto or "").strip()
    if not bruto:
        raise RuntimeError("O Gemini não retornou JSON.")

    bruto = re.sub(r"^```json\s*", "", bruto, flags=re.IGNORECASE)
    bruto = re.sub(r"^```\s*", "", bruto)
    bruto = re.sub(r"\s*```$", "", bruto)
    decoder = json.JSONDecoder()

    for match in re.finditer(r"\{", bruto):
        ini = match.start()
        try:
            obj, _ = decoder.raw_decode(bruto[ini:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    raise RuntimeError("Não foi possível localizar um objeto JSON válido na resposta do Gemini.")


def extrair_texto_pdf_bytes(pdf_bytes: bytes, page_indices: list[int] | None = None) -> str:
    partes = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        pages = page_indices if page_indices is not None else list(range(doc.page_count))
        for idx in pages:
            if idx < 0 or idx >= doc.page_count:
                continue
            raw = doc.load_page(idx).get_text("text") or ""
            raw = raw.replace("-\n", "").replace("\n", " ")
            raw = re.sub(r"\s{2,}", " ", raw).strip()
            if raw:
                partes.append(raw)
    return " ".join(partes).strip()


def render_pdf_page_png(pdf_bytes: bytes, page_index: int, zoom: float = 3.0) -> bytes:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_index = max(0, min(page_index, doc.page_count - 1))
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")


def extrair_pdf_imagem_padrao(imagens_png: list[bytes]) -> str:
    prompt = """Você está lendo imagens de uma pesquisa eleitoral brasileira.
Extraia o texto principal de todas as páginas.
Preserve nomes, datas, números, percentuais e registro TSE exatamente como aparecem.
Ignore menus, rodapés e elementos decorativos.
Retorne apenas o texto extraído em prosa limpa, sem markdown."""

    parts = [prompt]
    for img in imagens_png:
        parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))

    resp = gerar_conteudo_gemini(GEMINI_MODEL, parts)
    return normalizar_texto_simples(getattr(resp, "text", "") or "")


def classificar_tipo_resultado_manual(nome: str, tipo_informado: str = "") -> str:
    tipo = normalizar_texto_simples(tipo_informado).lower()
    if tipo in POLLING_MANUAL_TIPOS_RESULTADO:
        return tipo

    nome_norm = normalizar_texto_simples(nome).lower()
    marcadores = [
        "branco", "nulo", "nulos", "ns/nr", "nsnr",
        "não sabe", "nao sabe", "indeciso", "indecisos", "nenhum",
    ]
    if any(tag in nome_norm for tag in marcadores):
        return "nao_valido"

    return "candidato"


def normalizar_payload_polling(payload: dict) -> dict:
    payload = payload or {}
    cenarios = payload.get("cenarios") or []
    cargo = normalizar_texto_simples(payload.get("cargo")).lower() or "governador"
    turno = normalizar_texto_simples(payload.get("turno")).lower() or "t1"
    uf = normalizar_texto_simples(payload.get("uf")).upper() or "BR"
    instituto = normalizar_instituto(normalizar_texto_simples(payload.get("instituto")))

    cenarios_norm = []
    for idx, cenario in enumerate(cenarios, start=1):
        label = normalizar_texto_simples(cenario.get("scenario_label") or cenario.get("cenario") or idx)
        itens_raw = cenario.get("itens") or cenario.get("resultados") or []
        itens_norm = []

        for item in itens_raw:
            candidato = normalizar_texto_simples(
                item.get("candidato") or item.get("nome") or item.get("opcao") or item.get("candidato_partido")
            )
            partido = normalizar_partido(item.get("partido"))
            percentual = normalizar_percentual_resultado(item.get("percentual"))
            tipo = classificar_tipo_resultado_manual(candidato, item.get("tipo", ""))

            if not candidato and percentual is None:
                continue

            itens_norm.append({
                "candidato": candidato,
                "partido": partido,
                "percentual": percentual,
                "tipo": tipo,
            })

        # Cenário pode trazer turno próprio (material com T1 e T2 juntos);
        # cai pro turno do payload quando o cenário não especificar o dele.
        turno_cenario = normalizar_texto_simples(cenario.get("turno")).lower()
        if turno_cenario not in POLLING_MANUAL_TURNOS:
            turno_cenario = turno

        # Mesma lógica pro cargo: relatório estadual costuma trazer presidente
        # + governador + senador no mesmo material — cai pro cargo do payload
        # quando o cenário não especificar o dele.
        cargo_cenario = normalizar_texto_simples(cenario.get("cargo")).lower()
        if cargo_cenario not in POLLING_MANUAL_CARGOS:
            cargo_cenario = cargo

        # SENADOR NUNCA TEM SEGUNDO TURNO (regra também no prompt, mas o modelo
        # às vezes desobedece - visto ao vivo com "2º voto" de senador virando
        # t2). O prompt já pede pra nem criar cenário nesse caso, mas se o
        # modelo criar mesmo assim, força t1 aqui em vez de deixar um "Segundo
        # turno" fantasma entrar na revisão/planilha: 1º/2º voto de senador de
        # 2 vagas é sempre t1, nunca é o confronto de 2º turno de verdade.
        # Usa o cargo DESTE cenário, não o do payload - um material com vários
        # cargos juntos pode ter, no mesmo lote, um cenário de senador e outro
        # de governador/presidente que É t2 de verdade.
        if cargo_cenario == "senador" and turno_cenario == "t2":
            turno_cenario = "t1"

        # Para T2, a identidade persistida vem dos dois candidatos. Rótulos
        # determinísticos evitam conteúdo alucinado ou herdado na revisão.
        if turno_cenario == "t2":
            label = f"Segundo turno — cenário {idx}"

        # UF do cenário: presidente às vezes é pesquisado só num estado; cai
        # pra UF geral do payload quando o cenário não trouxer a sua.
        uf_cenario = normalizar_texto_simples(cenario.get("uf")).upper()
        if uf_cenario not in (["BR"] + UFS):
            uf_cenario = uf

        cenarios_norm.append({
            "scenario_label": label or str(idx),
            "cargo": cargo_cenario,
            "turno": turno_cenario,
            "uf": uf_cenario,
            "itens": itens_norm,
        })

    return {
        "cargo": cargo,
        "turno": turno,
        "uf": uf,
        "instituto": instituto,
        "registro_tse": normalizar_texto_simples(payload.get("registro_tse")),
        "data_campo": normalizar_texto_simples(payload.get("data_campo")),
        # Primeiro dia da coleta. Só o Alerta usa (o rodapé do gráfico publica o
        # período por extenso); a matriz continua guardando só a data final.
        "data_campo_inicio": normalizar_texto_simples(payload.get("data_campo_inicio")),
        "amostra": normalizar_inteiro_simples(payload.get("amostra")),
        "margem_erro": normalizar_percentual_simples(payload.get("margem_erro")),
        "confianca": normalizar_inteiro_simples(payload.get("confianca")),
        "modo": normalizar_texto_simples(payload.get("modo")),
        # A metodologia é cadastrada por instituto no arquivo central.
        "metodologia": "",
        "fonte_url_original": normalizar_texto_simples(payload.get("fonte_url_original")),
        "observacoes": normalizar_texto_simples(payload.get("observacoes")),
        "pendencias": payload.get("pendencias") or [],
        "cenarios": cenarios_norm or [{"scenario_label": "1", "cargo": cargo, "turno": turno, "uf": uf, "itens": []}],
    }


MESES_PT_NUMERO = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _mes_pt_numero(nome: str) -> int | None:
    """'Março'/'marco' -> 3. None quando não for nome de mês."""
    chave = unicodedata.normalize("NFKD", str(nome or "").lower())
    chave = "".join(ch for ch in chave if not unicodedata.combining(ch))
    return MESES_PT_NUMERO.get(chave)


def corrigir_metadados_explicitos_da_fonte(payload: dict, texto_fonte: str) -> dict:
    """Prefere metadados declarados textualmente à inferência do modelo.

    Esta checagem não faz outra chamada ao Gemini: apenas corrige confiança e
    data final de coleta quando elas estão inequívocas no material de origem.
    """
    payload = dict(payload or {})
    texto = normalizar_texto_simples(texto_fonte)

    # Aceita "nível/grau/índice/intervalo de confiança", "confiança de 95%" e a
    # ordem invertida "95% de confiança". Institutos usam grafias variadas.
    confianca = re.search(
        r"(?:n[íi]vel|grau|[íi]ndice|intervalo)?\s*(?:de\s+)?confian[çc]a\s*(?:de|:)?\s*(\d{1,3}(?:[,.]\d+)?)\s*%",
        texto,
        flags=re.IGNORECASE,
    )
    if not confianca:
        confianca = re.search(
            r"(\d{1,3}(?:[,.]\d+)?)\s*%\s*(?:de\s+)?(?:n[íi]vel|grau|[íi]ndice|intervalo)?\s*(?:de\s+)?confian[çc]a",
            texto,
            flags=re.IGNORECASE,
        )
    if confianca:
        try:
            valor = float(confianca.group(1).replace(",", "."))
            if 0 <= valor <= 100:
                payload["confianca"] = int(valor) if valor.is_integer() else valor
        except ValueError:
            pass
    else:
        # Não deixe uma inferência do modelo virar "95" se a fonte colada não
        # informou confiança. A interface agora mantém esse campo em branco.
        payload["confianca"] = None

    # Aya Bancah é parceiro de divulgação; a realização desta série é do
    # PoderData. Isso também impede a reutilização de um instituto anterior.
    if re.search(r"\bpoderdata\s*/\s*aya(?:\s+bancah)?\b", texto, flags=re.IGNORECASE):
        payload["instituto"] = "PoderData"

    # Grupos: 1 dia inicial, 2 mês inicial (só quando escrito), 3 dia final,
    # 4 mês final. O dia inicial vira data_campo_inicio, que é o que o rodapé do
    # Alerta publica por extenso ("15 a 17 de julho").
    intervalo = re.search(
        r"(?:entre\s+(?:os\s+)?dias?\s+)?(\d{1,2})(?:º|o)?"
        r"(?:\s+de\s+([a-záàâãéêíóôõúç]+))?\s*(?:a|até|e|-)\s*"
        r"(\d{1,2})(?:º|o)?\s+de\s+"
        r"(janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)",
        texto,
        flags=re.IGNORECASE,
    )
    if intervalo:
        anos = re.findall(r"(?<!\d)(20\d{2})(?!\d)", " ".join([
            texto,
            normalizar_texto_simples(payload.get("registro_tse")),
            normalizar_texto_simples(payload.get("data_campo")),
        ]))
        if anos:
            mes_fim = _mes_pt_numero(intervalo.group(4))
            mes_ini = _mes_pt_numero(intervalo.group(2)) or mes_fim
            try:
                fim = datetime(int(anos[0]), mes_fim, int(intervalo.group(3)))
                payload["data_campo"] = fim.strftime("%Y-%m-%d")
                # Campo que atravessa o réveillon ("28 de dezembro a 2 de
                # janeiro") começa no ano anterior ao da data final.
                ano_ini = fim.year - 1 if mes_ini > mes_fim else fim.year
                inicio = datetime(ano_ini, mes_ini, int(intervalo.group(1)))
                if inicio < fim:
                    payload["data_campo_inicio"] = inicio.strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                pass

    return payload


def extrair_dados_polling_gemini(
    texto_fonte: str,
    url_original: str = "",
    *,
    escopo: dict | None = None,
) -> dict:
    """Extrai dados estruturados via Gemini.

    Args:
        texto_fonte: texto cru da pesquisa (notícia, PDF OCR, release).
        url_original: URL da fonte para preencher fonte_url_original.
        escopo: dict opcional com filtros de foco:
            cargo, uf, turno, instituto (strings; "" = sem filtro)
            instrucoes (string livre adicional)
    """
    escopo = escopo or {}
    cargo_alvo = normalizar_texto_simples(escopo.get("cargo")).lower()
    uf_alvo = normalizar_texto_simples(escopo.get("uf")).upper()
    turno_alvo = normalizar_texto_simples(escopo.get("turno")).lower()
    instituto_alvo = normalizar_texto_simples(escopo.get("instituto"))
    instrucoes_livres = normalizar_texto_simples(escopo.get("instrucoes"))

    # Monta seção de restrições só se algo foi definido. turno NÃO é restrição
    # de exclusão (ver bloco separado abaixo) — cargo/uf/instituto continuam
    # obrigatórios quando informados.
    restricoes = []
    if cargo_alvo:
        restricoes.append(f"- cargo = {cargo_alvo}")
    if uf_alvo:
        restricoes.append(f"- uf = {uf_alvo}")
    if instituto_alvo:
        restricoes.append(f"- instituto = {instituto_alvo}")

    bloco_escopo = ""
    if restricoes or turno_alvo or instrucoes_livres:
        partes = []
        if restricoes:
            partes.append("FOCO DA EXTRAÇÃO (restrições obrigatórias):")
            partes.extend(restricoes)
            partes.append(
                "Extraia APENAS o bloco que casa com essas restrições. "
                "Ignore qualquer outro estado, cargo ou instituto que apareça no material."
            )
            partes.append(
                "Se o material NÃO contém um bloco que case com essas restrições, "
                "retorne cenarios=[] e adicione em pendencias um aviso claro do que faltou "
                "(ex.: \"Não encontrei pesquisa de presidente na BA no material fornecido\")."
            )
        if turno_alvo:
            partes.append(
                f"TURNO-ALVO = {turno_alvo} é uma PRIORIDADE, não um filtro de exclusão: "
                "extraia normalmente os cenários desse turno, mas se o material também trouxer, "
                "para o MESMO cargo/uf/instituto, um cenário do OUTRO turno claramente identificado "
                "(ver regra de classificação de turno abaixo), extraia esse também em vez de "
                "descartar — cada cenário tem seu próprio campo 'turno', então os dois convivem na "
                "mesma resposta. Não deixe de extrair o turno-alvo pedido só porque achou também o "
                "outro."
            )
        if instrucoes_livres:
            partes.append(f"INSTRUÇÕES ADICIONAIS DO USUÁRIO: {instrucoes_livres}")
        bloco_escopo = "\n".join(partes) + "\n\n"

    prompt = f"""
Você recebe o texto completo de uma notícia, release ou PDF de uma pesquisa eleitoral brasileira.
Extraia os dados estruturados para inserção em planilha.

{bloco_escopo}REGRAS:
- Responda somente com JSON válido.
- Não invente dados ausentes. Use string vazia ou null.
- data_campo deve ser a data FINAL da coleta, em YYYY-MM-DD. Quando a fonte
  informar um intervalo (ex.: "1º a 5 de julho"), use o último dia (dia 5),
  nunca o primeiro. Se a fonte não informar a data final de coleta, use a data
  de divulgação como fallback e registre em observacoes: "data de divulgação
  usada como data_campo; período de coleta não informado".
- data_campo_inicio é o PRIMEIRO dia da coleta, em YYYY-MM-DD, quando a fonte
  informar um intervalo (ex.: "15 a 17 de julho" → "2026-07-15"). Mesmas regras
  de ano do data_campo. Se a fonte der só uma data, ou se o data_campo veio da
  data de divulgação, use "" — não repita a data final nem chute o começo.
- O ANO de data_campo vem SEMPRE do período de coleta (ou da data de
  divulgação, no fallback), NUNCA do número de uma norma citada. Ex.:
  "Resolução-TSE n.º 23.600/2019" — o 2019 é o ano da resolução, não da
  pesquisa, e deve ser IGNORADO como data. Uma pesquisa registrada sob
  protocolo terminado em /2026 tem data_campo em 2026.
- registro_tse é o número de registro da pesquisa na Justiça Eleitoral
  (formato UF-XXXXX/AAAA, ex.: "AL-01460/2026"). Extraia SOMENTE se ele
  aparecer explicitamente escrito na fonte. NUNCA invente, deduza, "complete"
  ou chute um número de registro que não esteja no material. Se a fonte não
  informar o registro, use "" (string vazia) — não preencha com um valor
  plausível.
- confianca é o percentual do nível/grau/índice/intervalo de confiança. Aceite
  qualquer dessas expressões: "nível de confiança", "grau de confiança",
  "índice de confiança", "intervalo de confiança de 95%". Costuma vir junto da
  margem de erro (na mesma frase ou na mesma lista de metodologia)
  (ex.: "margem estimada de erro de 2,6 pontos percentuais para um grau de
  confiança de 95,0%") — se achou a margem, procure a confiança ao lado.
  Descarte casa decimal e símbolo (95,0% = 95). Nunca presuma 100 ou 95 quando
  a fonte não informar esse dado; nesse caso use null.
- cargo deve ser governador, senador ou presidente.
- turno deve ser t1 ou t2.
- uf deve estar em caixa alta. Para presidente use BR.
- instituto é quem realizou a pesquisa, não o veículo que a publicou nem
  parceiro só de divulgação. Na série "PoderData/Aya", use "PoderData": Aya
  Bancah é parceiro de divulgação.
- percentual deve ser numérico, sem %.
- tipo deve ser candidato ou nao_valido.
- Use nao_valido para branco/nulo, indecisos, ns/nr e equivalentes.
- modo é o MÉTODO DE COLETA da pesquisa (ex.: "Presencial", "Telefônica (CATI)",
  "Telefônica (IVR)", "Online", "Misto"). Use string vazia se não houver indicação.
- SÓ EXTRAIA PERGUNTA ESTIMULADA (com lista de nomes apresentada ao entrevistado).
  NUNCA extraia uma tabela/gráfico rotulado "espontânea" ou "espontâneas"
  (resposta aberta, sem lista de nomes) — isso NUNCA vira cenário, mesmo que
  seja a única opção disponível para aquele cargo. É comum o documento NUNCA
  usar a palavra "estimulada" em lugar nenhum: nesse caso, a tabela estimulada
  é identificada por ELIMINAÇÃO — é a que NÃO tem "espontânea" no título/rótulo.
  Se toda tabela do cargo estiver rotulada como espontânea (nenhuma estimulada
  disponível), não crie cenário para esse cargo e registre em pendencias.
- Se o mesmo cargo tiver mais de uma tabela estimulada (não-espontânea) —
  ex.: uma com todos os candidatos e outra com lista reduzida ("considerando
  apenas estes N candidatos..."), ou perguntas de 1º e 2º voto quando o cargo
  elege mais de um nome (ex.: dois senadores) — NÃO escolha só uma nem some os
  números: crie um cenário separado para cada tabela, com scenario_label que
  descreva a diferença (ex.: "Estimulada", "Estimulada - 5 candidatos",
  "1º voto", "2º voto").
- CLASSIFICAÇÃO DE TURNO: use t2 quando a própria pergunta, título ou
  cabeçalho da tabela/gráfico disser explicitamente "segundo turno", "2º
  turno", "2° turno" ou equivalente inequívoco. Além disso, EXCLUSIVAMENTE
  para presidente e governador (únicos cargos com 2º turno de verdade no
  sistema eleitoral brasileiro), uma tabela estimulada com EXATAMENTE dois
  nomes de candidato (mais NH/BR/NULO e NS/NR, sem nenhum outro candidato) é
  t2 mesmo sem menção explícita — é a forma mais comum de reportar simulação
  de 2º turno. NÃO aplique essa contagem para senador (nunca tem 2º turno, ver
  regra própria abaixo) nem para uma tabela de rejeição/aprovação/comparação
  entre dois nomes que não seja pergunta de intenção de voto.
- CADA CENÁRIO TEM SEU PRÓPRIO CAMPO "turno" (t1 ou t2), classificado pela
  regra literal acima. Não existe um turno único pra resposta inteira: se o
  material trouxer, pro mesmo cargo/uf/instituto, tanto o campo completo de
  1º turno quanto uma simulação de 2º turno EXPLICITAMENTE identificada,
  extraia OS DOIS como cenários separados na mesma resposta, cada um com seu
  turno correto — não descarte um pra "focar" só no outro, mesmo que
  TURNO-ALVO tenha sido informado (ver regra de FOCO DA EXTRAÇÃO acima). Não
  use inferência eleitoral pra completar confrontos que o material não trouxer.
- CADA CENÁRIO TAMBÉM TEM SEU PRÓPRIO CAMPO "cargo": relatório estadual
  frequentemente traz presidente + governador + senador no MESMO material
  (às vezes até no mesmo PDF, um bloco de páginas por cargo). Não existe um
  cargo único pra resposta inteira: se o material trouxer estimulada de mais
  de um cargo, extraia os cenários de TODOS eles na mesma resposta, cada um
  com o "cargo" correto — não escolha só um cargo "principal" pra focar,
  mesmo que CARGO-ALVO não tenha sido informado (auto-detectar = pegar
  todos). Só restrinja a um cargo quando CARGO-ALVO tiver sido informado
  explicitamente (ver FOCO DA EXTRAÇÃO acima).
- Para t2, cada confronto direto deve ser um cenário separado.
- SENADOR NUNCA TEM SEGUNDO TURNO: eleição de senador no Brasil não tem 2º
  turno (decide por maioria simples no 1º turno). Mesmo que o relatório traga
  uma pergunta chamada "simulação de 2º turno para Senador" ou um confronto
  direto de dois nomes para esse cargo, IGNORE essa pergunta por completo, não
  crie cenário nenhum para ela. Vale só para senador; presidente e governador
  continuam normalmente.
- SENADOR COM 1º/2º VOTO SEPARADOS: se o relatório trouxer tabelas separadas
  para senador de 2 vagas ("1º voto", "2º voto" e/ou "média do 1º e 2º voto"),
  crie um cenário separado para cada uma que existir, preservando o dado bruto
  exatamente como publicado (cada tabela soma ~100% sozinha). NÃO calcule
  média, NÃO some, NÃO junte as tabelas.
- Se o relatório indicar que o entrevistado podia citar/votar em mais de um
  nome no mesmo cenário (comum pra senador de 2 vagas relatado numa tabela só,
  não separada em "1º/2º voto") e os percentuais somarem perto de 200% em vez
  de 100%, NÃO tente corrigir nem dividir os números — extraia como está e
  registre em observacoes que os percentuais somam ~200% (voto múltiplo por
  entrevistado nesse cenário).
- IGNORE páginas de SÍNTESE/RESUMO/DESTAQUE (capa de capítulo, "principais
  leituras", "síntese", cards de highlight com 1 ou 2 números grandes tipo
  "36% × 36%"): elas repetem números de cenários que já aparecem completos em
  outra página, e extraí-las cria cenários fragmentados/duplicados. Só extraia
  da tabela ou gráfico COMPLETO, com a lista de candidatos.
- LISTA SEM CONTEXTO NÃO É CENÁRIO: se aparecer uma lista de nomes+percentuais
  sem pergunta ou título identificável, não invente um cenário pra ela — pode
  ser o final de uma tabela de rejeição ou de outra pergunta. Só extraia
  quando conseguir identificar qual pergunta a tabela responde.
- Quando uma tabela trouxer as colunas "Porcentual" e "Porcentagem válida",
  escolha UMA base só. Como o JSON consolida branco/nulo/NS/NR em "nao_valido",
  use a coluna "Porcentual" para candidatos E inválidos. Não misture
  "Porcentagem válida" dos candidatos com "Porcentual" dos inválidos. Só use
  "Porcentagem válida" se não houver nenhum item "nao_valido" no cenário.

FORMATO:
{{
  "cargo": "",
  "turno": "",
  "uf": "",
  "instituto": "",
  "registro_tse": "",
  "data_campo": "",
  "data_campo_inicio": "",
  "amostra": null,
  "margem_erro": null,
  "confianca": null,
  "modo": "",
  "fonte_url_original": "{url_original}",
  "observacoes": "",
  "pendencias": [],
  "cenarios": [
    {{
      "scenario_label": "",
      "cargo": "",
      "turno": "",
      "itens": [
        {{
          "candidato": "",
          "partido": "",
          "percentual": null,
          "tipo": "candidato"
        }}
      ]
    }}
  ]
}}
"turno" no nível raiz = turno predominante do material (fallback pra cenário
que não preencher o próprio); "turno" dentro de cada cenário é obrigatório
sempre que houver mais de um turno no material (ver regra acima) — nesse caso
preencha os dois, raiz E cada cenário. Mesma lógica pro "cargo": o do nível
raiz é o predominante/fallback, e "cargo" dentro de cada cenário é
obrigatório sempre que o material trouxer mais de um cargo (ver regra
acima) — preencha os dois, raiz E cada cenário, nesse caso.

TEXTO FONTE:
{texto_fonte}
""".strip()

    resp = gerar_conteudo_gemini(GEMINI_MODEL, prompt)
    payload = extrair_json_de_texto_bruto(getattr(resp, "text", "") or "")
    payload = corrigir_metadados_explicitos_da_fonte(payload, texto_fonte)
    return normalizar_payload_polling(payload)
