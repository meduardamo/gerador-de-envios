# app.py
from datetime import datetime
from urllib.parse import quote, urlparse
import os
import re
import json

import streamlit as st
from google import genai
import gspread
from google.oauth2.service_account import Credentials

# =========================
# CONFIG (NÃO COMMITE CHAVE)
# =========================
# No Streamlit Cloud: Settings -> Secrets:
# GEMINI_API_KEY = "..."
# GOOGLE_SHEETS_CREDS = {...} (JSON da service account)
#
# Local: crie .streamlit/secrets.toml (exemplo abaixo)
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

# ID da planilha (extraído da URL)
SHEET_ID = "14Gkj4uBYuY8sRNhjUMG8z58dkac02ZcMvmp56ER5A3o"

# Paleta Eixo
EIXO = {
    "preto": "#000000",
    "cinza": "#999999",
    "gelo": "#e1e1e1",
    "vinho": "#962E4D",
    "azul": "#192D4E",
    "amarelo": "#E8A600",
    "amarelo_claro": "#f0d46c",
    "vermelho": "#B84349",
}

# Coloque este arquivo na mesma pasta do app.py
LOGO_PATH = "Marca_eixo_vetor_Logo horizontal magenta.png"

AREAS = [
    "Política",
    "Economia",
    "Orçamento",
    "Tributação",
    "Energia",
    "Infraestrutura",
    "Meio Ambiente",
    "Agricultura",
    "Indústria e Comércio",
    "Trabalho e Renda",
    "Assistência Social",
    "Segurança Pública",
    "Educação",
    "Primeira Infância",
    "Saúde",
    "Direitos Humanos",
    "Mulheres",
    "Infância e Adolescência",
    "Tecnologia e Inovação",
    "Comunicações",
    "Justiça",
    "Judiciário",
    "Relações Internacionais",
    "Câmara dos Deputados",
    "Senado Federal",
    "Congresso Nacional",
    "Poder Executivo",
    "Agências Reguladoras",
    "ANS",
    "ANVISA",
    "Subnacional",
]

UFS = [
    "AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG",
    "PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"
]

st.set_page_config(page_title="Gerador de Envios", layout="wide")

st.markdown(
    f"""
<style>
:root {{
  --eixo-preto: {EIXO["preto"]};
  --eixo-cinza: {EIXO["cinza"]};
  --eixo-gelo: {EIXO["gelo"]};
  --eixo-vinho: {EIXO["vinho"]};
  --eixo-azul: {EIXO["azul"]};
  --eixo-amarelo: {EIXO["amarelo"]};
  --eixo-amarelo-claro: {EIXO["amarelo_claro"]};
  --eixo-vermelho: {EIXO["vermelho"]};
}}

h1, h2, h3 {{
  letter-spacing: -0.02em;
}}

div[data-testid="stForm"] {{
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 14px;
  padding: 14px 14px 8px 14px;
  background: rgba(255,255,255,0.02);
}}

.stButton > button {{
  border-radius: 12px !important;
  border: 1px solid rgba(255,255,255,0.14) !important;
  background: linear-gradient(90deg, var(--eixo-vinho), rgba(150,46,77,0.75)) !important;
  color: white !important;
  font-weight: 600 !important;
  padding: 10px 14px !important;
}}

.stButton > button:hover {{
  filter: brightness(1.05);
}}

small, .stCaption {{
  color: rgba(255,255,255,0.7) !important;
}}

hr {{
  border: 0;
  border-top: 1px solid rgba(255,255,255,0.08);
}}

div[data-testid="stCodeBlock"] > pre {{
  max-height: 520px !important;
  overflow: auto !important;
  border-radius: 14px !important;
}}
</style>
""",
    unsafe_allow_html=True
)


def data_br(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y")


def data_hora_br(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")


def montar_header(is_alerta: bool, area: str, uf: str | None) -> str:
    prefixo = "Alerta" if is_alerta else "Envio"
    if area == "Subnacional" and uf:
        return f"{prefixo} | Eixo | Subnacional | {uf}"
    return f"{prefixo} | Eixo | {area}"


def limpar_prefixo_alerta_envio(resumo: str) -> str:
    s = (resumo or "").strip()

    s = re.sub(
        r"^(ALERTA|ENVIO)\s*(?:[-–—]|:)?\s*[^:\n]{0,60}:\s*",
        "",
        s,
        flags=re.IGNORECASE
    )

    s = re.sub(
        r"^(ALERTA|ENVIO)\s*(?:[-–—]|:)\s*",
        "",
        s,
        flags=re.IGNORECASE
    )

    return s.strip()


def normalizar_link(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None

    if not re.match(r"^https?://", s, flags=re.IGNORECASE):
        s = "https://" + s

    p = urlparse(s)
    if p.scheme not in ("http", "https"):
        return None
    if not p.netloc:
        return None

    return s


@st.cache_resource
def get_gemini_client():
    if not GEMINI_API_KEY.strip():
        raise RuntimeError(
            "Faltou a GEMINI_API_KEY. Configure nos Secrets do Streamlit Cloud "
            "(App settings -> Secrets) ou crie .streamlit/secrets.toml local."
        )
    return genai.Client(api_key=GEMINI_API_KEY)


@st.cache_resource
def get_sheets_client():
    """Conecta ao Google Sheets usando credenciais da service account"""
    try:
        # Tenta pegar as credenciais do secrets
        if "GOOGLE_SHEETS_CREDS" in st.secrets:
            creds_dict = dict(st.secrets["GOOGLE_SHEETS_CREDS"])
        else:
            # Fallback para variável de ambiente (JSON string)
            creds_json = os.getenv("GOOGLE_SHEETS_CREDS", "")
            if not creds_json:
                return None
            creds_dict = json.loads(creds_json)
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.warning(f"⚠️ Google Sheets não configurado: {e}")
        return None


def salvar_no_sheets(
    tipo: str,
    area: str,
    uf: str | None,
    titulo: str,
    resumo: str,
    analise_eixo: str | None,
    link: str | None,
    texto_completo: str
):
    """Salva o envio na planilha do Google Sheets"""
    client = get_sheets_client()
    if not client:
        return False
    
    try:
        sheet = client.open_by_key(SHEET_ID).sheet1
        
        # Prepara a linha para inserir
        agora = datetime.now()
        linha = [
            data_hora_br(agora),  # Data/Hora
            tipo,                  # Tipo (Envio/Alerta)
            area,                  # Área
            uf or "",              # UF
            titulo,                # Título
            resumo,                # Resumo
            analise_eixo or "",    # Análise Eixo
            link or "",            # Link
            texto_completo         # Texto Completo
        ]
        
        # Adiciona a linha na planilha
        sheet.append_row(linha)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no Sheets: {e}")
        return False


def gerar_resumo_gemini(texto: str, is_alerta: bool, area: str) -> str:
    client = get_gemini_client()

    if is_alerta:
        instrucao = (
            "Escreva um texto curto para WhatsApp (PT-BR), factual e direto.\n"
            "Sem opinião, sem especulação, sem bullets e sem emojis.\n"
            "Comece pelo fato principal (quem fez o quê + consequência imediata).\n"
            "Use 1–2 parágrafos. Máximo: 90 palavras.\n"
            "Não comece com 'ALERTA'/'ENVIO' nem títulos.\n"
            "Preserve nomes, cargos, datas e números exatamente como no texto.\n"
        )
    else:
        instrucao = (
            "Escreva um texto para WhatsApp (PT-BR), factual e claro.\n"
            "Sem opinião, sem especulação, sem bullets e sem emojis.\n"
            "Estrutura: 1º parágrafo = fato principal; 2º = detalhe essencial/impacto.\n"
            "Use 2–3 parágrafos. Máximo: 160 palavras.\n"
            "Não comece com 'ALERTA'/'ENVIO' nem títulos.\n"
            "Preserve nomes, cargos, datas e números exatamente como no texto.\n"
        )

    prompt = f"""
Você é um analista que produz envios padronizados para WhatsApp.

Contexto:
- O cabeçalho (Alerta/Envio | Eixo | Área) + a data + o título já serão adicionados fora do modelo.
- Sua tarefa aqui é gerar apenas o corpo do texto (resumo), em parágrafos.

Área: {area}
Instruções: {instrucao}

TEXTO:
{texto}
""".strip()

    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    resumo = (resp.text or "").strip()
    resumo = limpar_prefixo_alerta_envio(resumo)
    return resumo


def compilar_envio(
    is_alerta: bool,
    area: str,
    uf: str | None,
    titulo: str,
    resumo: str,
    analise_eixo: str | None,
    link: str | None,
) -> str:
    header = montar_header(is_alerta=is_alerta, area=area, uf=uf)
    dt = data_br(datetime.now())

    header_fmt = f"*{header}*"
    titulo_fmt = f"*{titulo.strip()}*"

    partes = []
    partes.append(header_fmt)
    partes.append(dt)
    partes.append("")
    partes.append(titulo_fmt)
    partes.append("")
    partes.append(resumo.strip())

    if analise_eixo and analise_eixo.strip():
        partes.append("")
        partes.append("ANÁLISE EIXO")
        partes.append(analise_eixo.strip())

    link_norm = normalizar_link(link or "")
    if link_norm:
        partes.append("")
        partes.append(f"Link: {link_norm}")

    return "\n".join(partes)


def whatsapp_share_link(message: str) -> str:
    return f"https://wa.me/?text={quote(message)}"


@st.dialog("Enviar no WhatsApp")
def dialog_whatsapp(message: str):
    st.caption("Vai abrir o WhatsApp com o texto já preenchido. O envio final acontece por lá.")
    st.link_button("Abrir WhatsApp", whatsapp_share_link(message), use_container_width=True)


with st.sidebar:
    try:
        st.image(LOGO_PATH, use_container_width=True)
    except Exception:
        st.caption("Logo não encontrada. Coloque o arquivo na mesma pasta do app.py:")
        st.code(LOGO_PATH, language="text")

    st.markdown("---")
    st.caption(
        "Cole o texto da notícia, escolha tipo e área, e o app gera um envio/alerta padronizado com IA. O resultado já sai no formato para copiar e colar no WhatsApp."
    )
    
    # Status do Google Sheets
    st.markdown("---")
    sheets_client = get_sheets_client()
    if sheets_client:
        st.success("Google Sheets conectado")
    else:
        st.warning("⚠️ Google Sheets não configurado")
        with st.expander("Como configurar?"):
            st.markdown("""
            1. Crie uma Service Account no Google Cloud
            2. Baixe o JSON das credenciais
            3. No Streamlit Cloud: Settings → Secrets
            4. Adicione: `GOOGLE_SHEETS_CREDS = {seu_json_aqui}`
            5. Compartilhe a planilha com o email da service account
            """)

if "resultado_final" not in st.session_state:
    st.session_state["resultado_final"] = ""
if "dados_envio" not in st.session_state:
    st.session_state["dados_envio"] = {}

st.title("Gerador de Envios")

col_esq, col_dir = st.columns([1.25, 1])

with col_esq:
    st.subheader("Preenchimento do envio")
    st.markdown("### Classificação")

    is_alerta = st.radio(
        "Tipo",
        ["Envio", "Alerta"],
        index=0,
        horizontal=True,
        key="tipo_radio",
    ) == "Alerta"

    area = st.selectbox(
        "Área",
        AREAS,
        index=0,
        key="area_select",
    )

    uf = None
    if area.strip() == "Subnacional":
        uf = st.selectbox(
            "UF (obrigatório se Subnacional)",
            UFS,
            index=0,
            key="uf_select",
        )

    st.markdown("---")

    with st.form("form_envio", clear_on_submit=False):
        texto = st.text_area(
            "Texto da notícia (até 10 mil caracteres)",
            max_chars=10_000,
            height=240,
            placeholder="Cole aqui o texto da notícia..."
        )

        st.markdown("### Campos")

        titulo = st.text_input(
            "Título (obrigatório)",
            value="",
            placeholder="Ex.: Haddad descarta candidatura em 2026..."
        )

        analise_eixo = st.text_area(
            "Análise Eixo (opcional)",
            height=120,
            placeholder="Se quiser, escreva aqui uma análise curta e objetiva."
        )

        link = st.text_input(
            "Link (opcional)",
            value="",
            placeholder="Ex.: https://... (ou cole só o domínio que eu completo)"
        )

        submitted = st.form_submit_button("Gerar envio/alerta")

    if submitted:
        erros = []
        if not texto.strip():
            erros.append("Cole o texto da notícia.")
        if not titulo.strip():
            erros.append("Preencha o título (obrigatório).")
        if area.strip() == "Subnacional" and not uf:
            erros.append("Selecione a UF (obrigatório para Subnacional).")

        link_norm = normalizar_link(link)
        if link.strip() and not link_norm:
            erros.append("O link parece inválido. Cole uma URL completa (http/https) ou um domínio válido.")

        if erros:
            for e in erros:
                st.error(e)
        else:
            with st.spinner("Gerando resumo com IA e compilando o envio..."):
                try:
                    resumo = gerar_resumo_gemini(texto=texto, is_alerta=is_alerta, area=area)
                    resultado = compilar_envio(
                        is_alerta=is_alerta,
                        area=area,
                        uf=uf,
                        titulo=titulo,
                        resumo=resumo,
                        analise_eixo=analise_eixo,
                        link=link_norm
                    )
                    
                    st.session_state["resultado_final"] = resultado
                    st.session_state["dados_envio"] = {
                        "tipo": "Alerta" if is_alerta else "Envio",
                        "area": area,
                        "uf": uf,
                        "titulo": titulo,
                        "resumo": resumo,
                        "analise_eixo": analise_eixo,
                        "link": link_norm,
                        "texto": texto
                    }
                    
                    st.success("Envio gerado.")
                except Exception as e:
                    st.error(f"Erro ao gerar com Gemini: {e}")

with col_dir:
    st.subheader("Resultado")

    if not st.session_state["resultado_final"].strip():
        st.info("Preencha o formulário e clique em \"Gerar envio/alerta\".")
    else:
        st.markdown("**Copiar:**")
        st.code(st.session_state["resultado_final"], language="text")

        c1, c2, c3 = st.columns([1, 1, 1])

        with c1:
            if st.button("Enviar no WhatsApp", use_container_width=True):
                dialog_whatsapp(st.session_state["resultado_final"])

        with c2:
            st.download_button(
                "Baixar como .txt",
                data=st.session_state["resultado_final"].encode("utf-8"),
                file_name="envio_padronizado.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        with c3:
            if st.button("💾 Salvar no Sheets", use_container_width=True):
                if get_sheets_client():
                    with st.spinner("Salvando..."):
                        dados = st.session_state["dados_envio"]
                        sucesso = salvar_no_sheets(
                            tipo=dados["tipo"],
                            area=dados["area"],
                            uf=dados["uf"],
                            titulo=dados["titulo"],
                            resumo=dados["resumo"],
                            analise_eixo=dados["analise_eixo"],
                            link=dados["link"],
                            texto_completo=dados["texto"]
                        )
                        if sucesso:
                            st.success("✅ Salvo no Google Sheets!")
                        else:
                            st.error("❌ Erro ao salvar")
                else:
                    st.error("Google Sheets não configurado. Veja a sidebar.")
