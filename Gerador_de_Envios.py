from __future__ import annotations

import base64
from datetime import datetime
from urllib.parse import quote
import os
import re
import json
import inspect

import streamlit as st
from google import genai
from google.genai import types
import gspread
from google.oauth2.service_account import Credentials

import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

import fitz  # PyMuPDF

from alerta_pesquisa_core import (
    REGRAS_POLITICOS,
    _instrucao_pesquisa_eleitoral,
    encurtar_link,
    normalizar_link,
    padronizar_politicos_no_texto,
)

# ─── Config ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gerador de Envios", layout="wide")

EIXO = {
    "tinta":    "#111111",
    "vinho":    "#962E4D",
    "gelo":     "#F4F3EF",
    "borda":    "#DADAD4",
    "subtexto": "#767672",
    "amarelo":  "#E8A600",
    "marinho":  "#192D4E",
}

LOGO_PATH        = "Marca_eixo_vetor_Logo horizontal magenta.png"
LOGO_BRANCA_PATH = "Marca_eixo_vetor_Logo horizontal branca.png"

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');
:root {{ --eixo-vinho: {EIXO["vinho"]}; --eixo-gelo: {EIXO["gelo"]}; --eixo-borda: {EIXO["borda"]}; }}
html, body, [data-testid="stAppViewContainer"] {{ background: {EIXO["gelo"]} !important; }}
[data-testid="stAppViewContainer"] > section > div {{ background: {EIXO["gelo"]}; }}
.block-container, [data-testid="stMainBlockContainer"] {{
    max-width: 1320px !important;
    padding: 0 2rem 3rem !important;
    background: {EIXO["gelo"]};
    overflow-x: hidden;
}}
* {{ box-sizing: border-box; }}
body, p, span, div, label, input, select, textarea {{ font-family: 'Montserrat', sans-serif !important; }}
[data-testid="stHeader"] {{ display: none; }}
[data-testid="stDecoration"] {{ display: none; }}
[data-testid="stSidebar"] {{ background: {EIXO["gelo"]} !important; border-right: 1px solid {EIXO["borda"]} !important; }}
[data-testid="stSidebar"] * {{ font-family: 'Montserrat', sans-serif !important; font-size: 13px !important; }}
/* Streamlit usa texto com fonte Material para ícones; não sobrescreva essa fonte. */
span.material-symbols-rounded, span.material-symbols-outlined, span.material-icons,
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {{
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    letter-spacing: normal !important; text-transform: none !important;
}}
footer {{ display: none !important; }}
#MainMenu {{ display: none !important; }}

/* Buttons */
[data-testid="stButton"] > button {{
    font-family: 'Montserrat', sans-serif !important;
    font-size: 11px !important; font-weight: 500 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important;
    border-radius: 0 !important;
    border: 1px solid {EIXO["vinho"]} !important;
    background: transparent !important;
    color: {EIXO["vinho"]} !important;
    padding: 5px 14px !important;
    transition: background 0.15s, color 0.15s !important;
}}
[data-testid="stButton"] > button:hover {{
    background: {EIXO["vinho"]} !important; color: #fff !important;
}}
[data-testid="stSidebar"] button {{
    text-align: center !important; display: flex !important;
    align-items: center !important; justify-content: center !important;
    padding: 10px 14px !important; line-height: 1 !important; min-height: 38px !important;
}}
[data-testid="stSidebar"] [data-testid="stButton"] > button {{
    border: 1px solid {EIXO["vinho"]} !important;
    color: {EIXO["vinho"]} !important;
    display: inline-flex !important; align-items: center !important; justify-content: center !important;
}}
[data-testid="stSidebar"] [data-testid="stButton"] > button:hover {{
    background: {EIXO["vinho"]} !important; color: #fff !important;
}}

/* Labels */
[data-testid="stRadio"] > label,
[data-testid="stSelectbox"] > label,
[data-testid="stMultiSelect"] > label,
[data-testid="stTextInput"] > label,
[data-testid="stNumberInput"] > label,
[data-testid="stTextArea"] > label {{
    font-family: 'Montserrat', sans-serif !important;
    font-size: 11px !important; font-weight: 700 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important;
    color: {EIXO["subtexto"]} !important; margin-bottom: 6px !important;
}}
[data-testid="stRadio"] > label p,
[data-testid="stSelectbox"] > label p,
[data-testid="stMultiSelect"] > label p,
[data-testid="stTextInput"] > label p,
[data-testid="stNumberInput"] > label p,
[data-testid="stTextArea"] > label p {{
    font-size: 11px !important; font-weight: 700 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important;
    color: {EIXO["subtexto"]} !important;
}}

/* Radios */
[data-testid="stRadio"] [role="radiogroup"] {{ gap: 14px !important; }}
[data-testid="stRadio"] [role="radiogroup"] label p {{
    font-family: 'Montserrat', sans-serif !important;
    font-size: 14px !important; color: {EIXO["tinta"]} !important;
}}

/* Tabs */
[data-testid="stTabs"] [role="tablist"] {{
    border-bottom: 1px solid {EIXO["borda"]} !important;
    gap: 0 !important; background: transparent;
}}
[data-testid="stTabs"] [role="tab"] {{
    font-family: 'Montserrat', sans-serif !important;
    font-size: 11px !important; font-weight: 500 !important;
    letter-spacing: 0.12em !important; text-transform: uppercase !important;
    color: {EIXO["subtexto"]} !important; padding: 10px 20px 9px !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important; border-radius: 0 !important;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
    color: {EIXO["vinho"]} !important; border-bottom-color: {EIXO["vinho"]} !important;
}}

/* Form */
div[data-testid="stForm"] {{
    border: 1px solid {EIXO["borda"]};
    border-radius: 0; padding: 20px 20px 12px 20px; background: #fff;
}}

/* Code block */
div[data-testid="stCodeBlock"] > pre {{
    max-height: 520px !important; overflow: auto !important; border-radius: 0 !important;
}}

/* Hero banner */
.ge-hero {{
    background: {EIXO["vinho"]};
    display: flex; align-items: center; justify-content: space-between;
    padding: 36px 48px; margin: 0 -2rem 32px -2rem;
}}
.ge-hero-title {{
    font-family: 'Montserrat', sans-serif;
    font-size: 48px; font-weight: 800; color: #fff;
    line-height: 1; letter-spacing: -0.01em;
}}
.ge-hero-logo {{ height: 90px; width: auto; object-fit: contain; }}

/* Section rule */
.ge-rule {{
    font-size: 12px; font-weight: 700; letter-spacing: 0.14em;
    text-transform: uppercase; color: {EIXO["vinho"]};
    border-top: 1.5px solid {EIXO["vinho"]};
    padding-top: 8px; margin: 20px 0 14px;
}}

/* Result card */
.ge-result-card {{
    background: #fff; border: 1px solid {EIXO["borda"]}; padding: 20px 24px; margin-top: 4px;
}}

/* UF chips */
.uf-chips-wrap {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }}
.uf-chip {{
    display: inline-block; padding: 3px 10px;
    border-radius: 0; border: 1px solid {EIXO["borda"]};
    font-size: 12px; font-weight: 500; cursor: pointer; user-select: none;
    background: #fff; color: {EIXO["subtexto"]}; transition: all 0.12s;
}}
.uf-chip.uf-sel {{
    background: {EIXO["vinho"]}; border-color: {EIXO["vinho"]}; color: #fff;
}}
</style>""", unsafe_allow_html=True)


# ─── Auth ────────────────────────────────────────────────────────────────────
def _load_auth_config():
    if "AUTH_CONFIG" in st.secrets:
        return yaml.load(st.secrets["AUTH_CONFIG"], Loader=SafeLoader)
    if os.path.exists("config.yaml"):
        with open("config.yaml", "r", encoding="utf-8") as f:
            return yaml.load(f, Loader=SafeLoader)
    return None


_auth_cfg = _load_auth_config()
if not _auth_cfg:
    st.error("Auth não configurado. Defina AUTH_CONFIG nos Secrets ou crie config.yaml local.")
    st.stop()

authenticator = stauth.Authenticate(
    _auth_cfg["credentials"],
    _auth_cfg["cookie"]["name"],
    _auth_cfg["cookie"]["key"],
    _auth_cfg["cookie"]["expiry_days"],
)

# O campo branco do login vem daqui, e tem que ser desenhado antes do gate:
# sem ninguém logado o gate chama st.stop() e nada depois dele roda.
from ui_login import CSS_LOGIN
st.markdown(CSS_LOGIN, unsafe_allow_html=True)

sig = inspect.signature(authenticator.login)
params = sig.parameters

try:
    if "location" in params:
        login_result = authenticator.login(location="main")
    else:
        login_result = authenticator.login("Login", "main")
except TypeError:
    login_result = authenticator.login("Login", "main")

if isinstance(login_result, (tuple, list)) and len(login_result) == 3:
    name, authentication_status, username = login_result
else:
    authentication_status = st.session_state.get("authentication_status", None)
    name = st.session_state.get("name", "")
    username = st.session_state.get("username", "")

if authentication_status is False:
    st.error("Usuário ou senha inválidos.")
    st.stop()

if authentication_status is None:
    st.info("Faça login para continuar.")
    st.stop()


# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    try:
        st.image(LOGO_PATH, use_container_width=True)
    except Exception:
        st.caption("Logo não encontrada.")
    st.markdown(
        f'<div style="border-left:3px solid {EIXO["vinho"]};padding:10px 12px;'
        f'margin:10px 0 0 0;background:transparent;">'
        f'<p style="font-family:Montserrat,sans-serif;font-size:12.5px;'
        f'color:{EIXO["tinta"]};line-height:1.65;margin:0;">'
        f'Cole o texto da notícia ou suba um PDF, escolha tipo e área, '
        f'e o app gera um <strong>envio/alerta padronizado com IA</strong>.'
        f'</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("↻ Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** ({st.session_state.get('username', '')})")
    if _auth_cfg:
        authenticator.logout("Sair", "sidebar")


# ─── Configurações ───────────────────────────────────────────────────────────
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-3.6-flash"   # 2.5-flash dá 404 para a chave do projeto novo
SHEET_ID       = st.secrets.get("SHEET_ID") or os.getenv("SHEET_ID", "")

AREAS = [
    "Eleições",
    "Política", "Economia", "Orçamento", "Tributação", "Energia", "Infraestrutura",
    "Meio Ambiente", "Agricultura", "Indústria e Comércio", "Trabalho e Renda",
    "Assistência Social", "Segurança Pública", "Educação", "Primeira Infância",
    "Saúde", "Direitos Humanos", "Mulheres", "Infância e Adolescência",
    "Tecnologia e Inovação", "Comunicações", "Justiça", "Judiciário",
    "Relações Internacionais", "Câmara dos Deputados", "Senado Federal",
    "Congresso Nacional", "Poder Executivo", "Agências Reguladoras",
    "ANS", "ANVISA",
]

UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]

FORMATOS = ["Padrão", "Pesquisa eleitoral"]
ABRANGENCIAS_OPCIONAIS = ["Não especificar", "Gov. Federal", "Subnacional"]

LEITURA_PDF = [
    "Auto (texto se tiver; imagem se for scan)",
    "Texto (PyMuPDF)",
    "Imagem (Gemini visão)",
]


# ─── Clientes ─────────────────────────────────────────────────────────────────
CLIENTE_DESCRICOES = {
    "IU": (
        "Instituto Unibanco (IU)",
        "O Instituto Unibanco (IU) é uma organização sem fins lucrativos que atua no fortalecimento da gestão educacional, desenvolvendo projetos como o Jovem de Futuro, oferecendo apoio técnico a secretarias estaduais de educação e produzindo conhecimento para aprimorar políticas públicas. Seu foco está tanto no cenário federal, acompanhando os debates sobre o financiamento da educação, programas nacionais de educação, regulação educacional e diretrizes definidas por órgãos como o Conselho Nacional de Educação, quanto subnacional, olhando para 6 estados prioritários (RS, MG, ES, CE, PI e GO). O IU apoia iniciativas de recomposição de aprendizagens, infraestrutura escolar, inclusão digital, educação ambiental, mudanças do clima e valorização de profissionais da educação.",
    ),
    "FMCSV": (
        "Fundação Maria Cecilia Souto Vidigal (FMCSV)",
        "A Fundação Maria Cecilia Souto Vidigal (FMCSV) é uma organização da sociedade civil dedicada ao fortalecimento da primeira infância no Brasil. Sua atuação concentra-se na integração entre produção de conhecimento, advocacy e apoio à formulação e implementação de políticas públicas, com o objetivo de assegurar o desenvolvimento integral de crianças de 0 a 6 anos. A Fundação acompanha o debate sobre educação domiciliar (homeschooling), posicionando-se de forma contrária a avanços nessa pauta. Além disso, participa ativamente da construção e implementação da Política Nacional Integrada da Primeira Infância. Desde 2007, a Fundação trabalha para garantir que todas as crianças brasileiras tenham uma infância saudável, com seus direitos plenamente assegurados. Com o lançamento da Agenda 2030 pela Organização das Nações Unidas (ONU), a instituição passou a alinhar suas estratégias à meta 4.2 dos Objetivos de Desenvolvimento Sustentável (ODS), que trata da garantia de acesso a cuidados e educação de qualidade na primeira infância. Entre suas iniciativas, destaca-se o programa 'Primeira Infância Primeiro', que disponibiliza dados, evidências e ferramentas para gestores públicos e candidatos, contribuindo para a qualificação do debate e das políticas voltadas à infância.",
    ),
    "IEPS": (
        "Instituto de Estudos para Políticas de Saúde (IEPS)",
        "O Instituto de Estudos para Políticas de Saúde (IEPS) é uma organização independente e sem fins lucrativos dedicada a aprimorar políticas de saúde no Brasil, combinando pesquisa aplicada, produção de evidências e advocacy em temas como atenção primária, saúde digital e financiamento do SUS. Com especialização em políticas públicas de saúde, o IEPS possui uma atuação centrada no fortalecimento do SUS enquanto sistema universal e equitativo. A organização se expande pela observação dos mais diversos temas, assim, é complexo delimitar seus núcleos de observação. No âmbito da análise da organização e governança federativa do SUS, com atenção especial ao modelo tripartite (União–Estados–Municípios), ao papel do Ministério da Saúde e às distorções introduzidas por emendas parlamentares no orçamento setorial. Existe um foco técnico na Estruturação da Atenção Primária à Saúde (APS), financiamento per capita e critérios redistributivos, regionalização como instrumento de coordenação federativa, e planejamento e alocação eficiente de recursos. Ademais, existe uma busca por equidade e enfrentamento de desigualdades, através do monitoramento de políticas criadas com ênfase em grupos historicamente vulnerabilizados, população negra, povos indígenas e originários, pessoas com deficiência, população LGBTQIA+, pessoas em situação de rua, e crianças, adolescentes, mulheres, homens e idosos. No campo da força de trabalho em saúde, a instituição aborda a relação entre disponibilidade de profissionais, organização federativa e financiamento do SUS. A análise envolve a escassez e a distribuição territorial de médicos, enfermeiros e demais categorias, considerando desigualdades regionais e capacidade instalada dos entes subnacionais. É necessário destaque para o Programa Agora Tem Especialistas, que vem sendo acompanhado desde sua instituição no ano passado. No âmbito da saúde mental, a atuação contempla a organização da Rede de Atenção Psicossocial e a consolidação do processo de desinstitucionalização. A fiscalização de comunidades terapêuticas é um tema de alta relevância. O uso terapêutico de cannabis e derivados é tratado no âmbito da regulação sanitária. Seguindo a nova ordem de prioridades de atuação do IEPS, especialmente em seu trabalho de incidência na Secretaria Executiva da Frente Parlamentar Mista para a Promoção da Saúde Mental, as BETs são destaque no monitoramento para 2026. A organização também realiza o acompanhamento das decisões da Anvisa e da ANS, com foco na regulação de produtos, serviços e operadoras de planos. No eixo de emergências sanitárias, a instituição acompanha políticas de vigilância epidemiológica, declaração de estados de emergência e coordenação federativa em situações de crise. Como as mudanças climáticas vêm sendo consideradas no planejamento das políticas de saúde, são observados debates relacionados a eventos extremos, deslocamentos populacionais e impactos sobre doenças transmissíveis e crônicas.",
    ),
    "IAS": (
        "Instituto Ayrton Senna (IAS)",
        "O Instituto Ayrton Senna (IAS) é um centro de inovação em educação que atua em pesquisa e desenvolvimento, disseminação em larga escala e influência em políticas públicas, com foco em aprendizagem acadêmica e competências socioemocionais na rede pública.",
    ),
    "ISG": (
        "Instituto Sonho Grande (ISG)",
        "O Instituto Sonho Grande (ISG) é uma organização sem fins lucrativos e apartidária voltada à expansão e qualificação do ensino médio integral em redes públicas. Atua em parceria com secretarias estaduais de educação, oferecendo apoio na revisão curricular, na formação de equipes escolares e na implementação de modelos de gestão orientados a resultados. Além disso, o Instituto mantém foco no fortalecimento da infraestrutura das escolas públicas de tempo integral e na promoção de políticas voltadas à alfabetização. Também acompanha o debate sobre educação domiciliar (homeschooling), posicionando-se de forma contrária à sua ampliação. Em colaboração com governos estaduais e organizações do terceiro setor, o ISG trabalha para ampliar o acesso ao Ensino Médio Integral em escolas públicas. Por meio de pesquisas e avaliações contínuas, analisa os impactos desse modelo educacional para a formação de jovens.",
    ),
    "Reúna": (
        "Instituto Reúna",
        "O Instituto Reúna desenvolve pesquisas e ferramentas para apoiar redes e escolas na implementação de políticas educacionais alinhadas à BNCC, com foco em currículo, materiais de apoio e formação de professores.",
    ),
    "REMS": (
        "Rede Esporte pela Mudança Social (REMS)",
        "A REMS – Rede Esporte pela Mudança Social articula organizações que usam o esporte como vetor de desenvolvimento humano, mobilizando atores e produzindo conhecimento para ampliar o impacto social dessa agenda no país. A rede atua desde 2007 no fortalecimento do campo do esporte para o desenvolvimento social, promovendo a troca de experiências, a sistematização de práticas e a realização de agendas coletivas, bem como acompanhando e incidindo em debates sobre políticas públicas, financiamento, marcos regulatórios e programas governamentais relacionados ao esporte educacional, comunitário e de participação. Sua atuação abrange o nível federal, com foco na qualificação da formulação e implementação de iniciativas, no fortalecimento técnico das organizações integrantes e no diálogo com gestores públicos e parlamentares, além da articulação da pauta esportiva com áreas como educação, assistência social, saúde e desenvolvimento territorial.",
    ),
    "Manual": (
        "Manual",
        "A Manual se posiciona como uma empresa de cuidado contínuo e personalizado, com foco em acesso facilitado, discrição e conveniência. Ela é uma plataforma digital voltada principalmente à saúde e bem-estar masculino, oferecendo atendimento online e tratamentos baseados em evidências (como saúde capilar, sono e saúde sexual), com prescrição médica e acompanhamento remoto. Tem um interesse em promover a inovação dentro da área de saúde, principalmente em relação a manipuláveis, como o princípio ativo GLP-1. Possui uma atuação aprofundada conectando clientes com médicos e tratamentos para emagrecimento (foco em GLP-1 e redutores de apetite), disfunção erétil (oferecendo serviços que incluem consultas médicas e medicamentos manipulados que impedem a ação da enzima PDE 5) e queda capilar (acompanhamento junto com o uso de Finasterida e Minoxidil). Por serem uma plataforma, também possuem interesse na expansão da telemedicina e inovações no campo tecnológico associado à saúde.",
    ),
    "Cactus": (
        "Instituto Cactus",
        "O Instituto Cactus é uma organização filantrópica e de direitos humanos, sem fins lucrativos e independente, que atua para ampliar e qualificar o ecossistema da saúde mental no Brasil, desenvolvendo projetos voltados à prevenção de agravos e à promoção do cuidado, com foco prioritário em mulheres e adolescentes. Sua atuação se organiza em duas frentes complementares: o fomento estratégico (grant-making), por meio do qual financia, co-cria e oferece suporte técnico a iniciativas que constroem e ampliam soluções e ferramentas em saúde mental, além de produzir evidências e incentivar inovações no campo da atenção psicossocial; e o advocacy, com foco na formulação, implementação e avaliação de políticas públicas, bem como na análise qualificada de projetos de lei. O Instituto também realiza incidência política para fortalecer a agenda da saúde mental no debate público e institucional, desenvolve ferramentas de apoio a gestores e governos e promove ações de educação, sensibilização e mobilização social, que objetivam reduzir o estigma e consolidar uma narrativa mais humanizada sobre o tema no país.",
    ),
    "Vital Strategies": (
        "Vital Strategies",
        "A Vital Strategies é uma organização global de saúde pública que trabalha com governos e sociedade civil na concepção e implementação de políticas baseadas em evidências em áreas como doenças crônicas, segurança viária, qualidade do ar, dados vitais e comunicação de risco. A organização trabalha com base em dados para a saúde e mortes evitáveis, então os temas são muito intersetoriais. Desde o ano passado tem focado na Reforma Tributária, em especial no Imposto Seletivo, buscando incidir sobre a alíquota em bebidas açucaradas, álcool e tabaco. O intuito é atingir um consumo zero sobre conteúdos que geram malefícios à saúde, como no caso de DCNTs, como hipertensão arterial. Para além desta campanha, também trata do cuidado no trânsito, observando acidentes que estão relacionados ao uso de drogas (lícitas ou não). Políticas sobre vedação total ou parcial de marketing, publicidade e rotulagem de cigarros, dispositivos eletrônicos para fumar, alimentos ultraprocessados e bebidas alcoólicas também são de interesse. Na área de desenvolvimento tecnológico, tem investido nos estudos que ligam Inteligência Artificial à jornada do paciente, buscando dois pontos principais: combate ao feminicídio e diagnóstico precoce de câncer. Com a incidência sobre a COP30 no ano passado, temas como saúde ambiental, qualidade do ar e intoxicação por chumbo também são acompanhados pela organização.",
    ),
    "Mevo": (
        "Mevo",
        "A Mevo é uma healthtech brasileira que integra soluções de saúde digital, da prescrição eletrônica à compra e entrega de medicamentos, conectando médicos, hospitais, farmácias e pacientes para tornar o cuidado mais simples, eficiente e rastreável. Seu foco está na construção de um ecossistema digital interoperável, atuando de forma contínua junto aos Poderes Legislativo e Executivo para contribuir com o fortalecimento de uma Rede Nacional de Dados em Saúde (RNDS) robusta e integrada. A empresa também mantém diálogo com agências reguladoras, com o objetivo de promover um ambiente normativo que viabilize uma rede de dados e de prescrição eletrônica interoperável e de alcance universal. Nesse contexto, acompanha e contribui para debates regulatórios relacionados à saúde digital, interoperabilidade de sistemas, proteção de dados e normativas que impactem o funcionamento de suas soluções tecnológicas.",
    ),
    "Coletivo Feminista": (
        "Coletivo Feminista",
        "O Nem Presa Nem Morta é um movimento feminista que atua pela descriminalização e legalização do aborto no Brasil, articulando pesquisa, incidência política e mobilização social. Seus princípios ético-políticos abrangem a comunicação como direito e fundamento da democracia, a defesa do Estado democrático de direito, a compreensão de que maternidade não é dever e deve respeitar a liberdade de escolha, a promoção de uma atenção universal, equânime e integral à saúde — com ênfase no papel do SUS, no acesso a métodos contraceptivos e abortivos seguros e no respeito à autodeterminação reprodutiva —, além da defesa da descriminalização e legalização do aborto. Desde o final do ano passado, o coletivo tem focado em dois projetos essenciais: o novo Código Civil e o PLD3/2025, que susta a resolução 258 do Conselho Nacional dos Direitos da Criança e do Adolescente (CONANDA). Em ambos os projetos a atuação da organização tem sido em evitar regressões inconstitucionais ligadas ao aborto, em especial quando se trata de crianças e adolescentes.",
    ),
    "IDEC": (
        "Instituto Brasileiro de Defesa do Consumidor (Idec)",
        "O Instituto Brasileiro de Defesa do Consumidor (Idec) é uma associação civil sem fins lucrativos, fundada em 1987, independente de empresas, partidos ou governos, que atua na defesa dos direitos dos consumidores e na promoção de relações de consumo éticas, seguras e sustentáveis. Sua atuação combina advocacy, pesquisa e litigância estratégica, com foco em temas como saúde, alimentação, energia, telecomunicações e direitos digitais, sendo os temas pautados muitas vezes transversais a todas as áreas. O Idec se destaca na formulação e incidência em políticas públicas relacionadas à promoção da alimentação adequada e saudável, ao controle de ultraprocessados e agrotóxicos, à rotulagem nutricional, à transição energética justa e à regulação de plataformas digitais. Também acompanha de perto a regulação dos planos de saúde, atuando junto à ANS, e a saúde digital do ponto de vista do direito do consumidor. Pauta temas como greenwashing e práticas abusivas de telemarketing. Paralelamente, produz estudos, materiais técnicos e eventos voltados à informação e mobilização da sociedade, mantendo diálogo com o Legislativo por meio de parcerias e incidência em projetos de lei, inclusive em debates como os relacionados ao ReData.",
    ),
    "Umane": (
        "Umane",
        "A Umane é uma organização da sociedade civil isenta, apartidária e sem fins lucrativos que atua para fomentar a saúde pública de forma sistêmica no Brasil, com foco em ampliar equidade, eficiência e qualidade do sistema de saúde. Sua missão é apoiar iniciativas transformadoras de prevenção de doenças e promoção da saúde que melhorem a qualidade de vida da população, operando por meio de fomento a projetos, articulação com uma rede de parceiros e um modelo de trabalho que combina monitoramento e avaliação, uso de dados e tecnologia (como telessaúde e uso de IA, com foco sempre na inovação dentro da área de saúde) e advocacy/comunicação para fortalecer políticas públicas. As frentes programáticas explicitadas pela Umane incluem o fortalecimento da Atenção Primária à Saúde (APS), a atenção integral às Doenças Crônicas Não Transmissíveis (DCNT), sendo o foco as doenças cardiovasculares, diabetes tipo 2, obesidade, subnutrição e dislipidemias; e a saúde da mulher, da criança e do adolescente, com ênfase na articulação entre os níveis de atenção à saúde para o pré-natal, no acompanhamento integral dos primeiros mil dias e no enfrentamento da má nutrição infantil e juvenil.",
    ),
    "ASBAI": (
        "Associação Brasileira de Alergia e Imunologia (ASBAI)",
        "A Associação Brasileira de Alergia e Imunologia (ASBAI) é uma entidade científica sem fins lucrativos que reúne médicos especialistas em alergia e imunologia clínica no Brasil. Atua na promoção do ensino, pesquisa e atualização profissional nessas áreas, elaborando diretrizes clínicas, posicionamentos técnicos e recomendações para o diagnóstico e tratamento de doenças alérgicas e imunológicas. Seu foco está tanto no cenário nacional, acompanhando debates regulatórios junto ao Ministério da Saúde (especialmente a Conitec) e à Anvisa, especialmente em temas como incorporação de tecnologias, imunobiológicos, vacinas, assistência farmacêutica e protocolos clínicos, quanto na articulação com sociedades médicas estaduais e internacionais. A ASBAI também promove congressos, cursos e campanhas de conscientização sobre condições como asma, rinite alérgica, dermatite atópica, alergias alimentares, imunodeficiências primárias e anafilaxia. Sua principal linha de atuação neste momento é sobre a incorporação da caneta de adrenalina autoinjetável no SUS e também a obrigatoriedade de notificação ao Ministério da Saúde de ocorrências de anafilaxia/choque anafilático.",
    ),
    "Infinis": (
        "Instituto Futuro é Infância Saudável (Infinis)",
        "O Instituto Futuro é Infância Saudável (Infinis) é a frente de filantropia estratégica e advocacy da Fundação José Luiz Setúbal (FJLS). A organização atua com base em evidências científicas para promover políticas públicas, fortalecer a sociedade civil e impulsionar soluções que assegurem saúde e bem-estar na infância. Sua atuação está estruturada em quatro eixos temáticos: segurança alimentar e enfrentamento da má nutrição; saúde mental; prevenção às violências; e fortalecimento da sociedade civil. Esses eixos estão alinhados aos Objetivos de Desenvolvimento Sustentável (ODS) da ONU, especialmente no que se refere à promoção da saúde, da equidade e da proteção de crianças e adolescentes. Com foco na incidência política, o Infinis busca contribuir para o aprimoramento e a efetiva implementação de políticas públicas, além de fomentar a transformação de comportamentos e o desenvolvimento de soluções locais sustentáveis. No campo do fortalecimento da sociedade civil, apoia a produção de pesquisas científicas e o desenvolvimento de organizações de infraestrutura que atuam no setor.",
    ),
}


# ─── Helpers gerais ───────────────────────────────────────────────────────────
def data_br(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y")

def data_hora_br(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")

def obter_contexto_classificacao(area: str, abrangencia_geral: str, escopo_eleicoes: str) -> dict:
    abrangencia = "" if abrangencia_geral == "Não especificar" else abrangencia_geral
    mostrar_ufs = False
    uf_obrigatoria = False

    if area == "Eleições":
        abrangencia = escopo_eleicoes
        mostrar_ufs = escopo_eleicoes == "Subnacional"
        uf_obrigatoria = mostrar_ufs
    elif abrangencia == "Subnacional":
        mostrar_ufs = True

    return {
        "area_header": area,
        "abrangencia": abrangencia,
        "mostrar_ufs": mostrar_ufs,
        "uf_obrigatoria": uf_obrigatoria,
    }

def montar_header(is_alerta: bool, area: str, abrangencia: str, ufs: list[str] | None) -> str:
    prefixo = "Alerta" if is_alerta else "Envio"
    if ufs:
        ufs_str = ", ".join(ufs)
        return f"{prefixo} | Eixo | {area} | Subnacional | {ufs_str}"
    if not (abrangencia or "").strip() or abrangencia == "Não especificar":
        return f"{prefixo} | Eixo | {area}"
    return f"{prefixo} | Eixo | {area} | {abrangencia}"

def limpar_prefixo_alerta_envio(resumo: str) -> str:
    s = (resumo or "").strip()
    s = re.sub(r"^(ALERTA|ENVIO)\s*(?:[-–—]|:)?\s*[^:\n]{0,60}:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(ALERTA|ENVIO)\s*(?:[-–—]|:)\s*", "", s, flags=re.IGNORECASE)
    return s.strip()


def gerar_resumo_seguro(resp) -> str:
    texto = limpar_prefixo_alerta_envio((getattr(resp, "text", "") or "").strip())
    if not texto:
        raise RuntimeError("O Gemini não retornou texto. Tente novamente ou reduza o conteúdo enviado.")
    return texto

def _logo_b64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""


# ─── Clientes de API ──────────────────────────────────────────────────────────
@st.cache_resource
def get_gemini_client():
    if not GEMINI_API_KEY.strip():
        raise RuntimeError(
            "Faltou a GEMINI_API_KEY. Configure nos Secrets do Streamlit Cloud "
            "(App settings → Secrets) ou crie .streamlit/secrets.toml local."
        )
    return genai.Client(api_key=GEMINI_API_KEY)

@st.cache_resource
def get_sheets_client():
    try:
        if not SHEET_ID.strip():
            return None
        if "GOOGLE_SHEETS_CREDS" in st.secrets:
            creds_dict = dict(st.secrets["GOOGLE_SHEETS_CREDS"])
        else:
            creds_json = os.getenv("GOOGLE_SHEETS_CREDS", "")
            if not creds_json:
                return None
            creds_dict = json.loads(creds_json)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except Exception as e:
        st.warning(f"Google Sheets não configurado: {e}")
        return None


# ─── Google Sheets ────────────────────────────────────────────────────────────
def salvar_no_sheets(tipo, area, uf, formato, cliente, titulo, resumo, analise_eixo, link, texto_completo):
    client = get_sheets_client()
    if not client:
        return False
    try:
        sheet = client.open_by_key(SHEET_ID).sheet1
        linha = [
            data_hora_br(datetime.now()), tipo, area, uf or "", formato, cliente or "Geral",
            titulo, resumo, analise_eixo or "", link or "", texto_completo,
        ]
        sheet.insert_row(linha, index=2)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no Sheets: {e}")
        return False


# ─── Prompts e geração de texto ───────────────────────────────────────────────


def gerar_resumo_gemini(
    texto: str,
    is_alerta: bool,
    area: str,
    formato: str,
    cliente_key: str | None = None,
) -> str:
    client = get_gemini_client()

    bloco_cliente = ""
    if cliente_key and cliente_key in CLIENTE_DESCRICOES:
        nome_cliente, desc_cliente = CLIENTE_DESCRICOES[cliente_key]
        bloco_cliente = f"""
═══════════════════════════════
CONTEXTO DO CLIENTE
═══════════════════════════════
Nome: {nome_cliente}
Perfil e temas de interesse:
{desc_cliente}

Instrução de foco:
O texto deve ser escrito com atenção aos temas e eixos de interesse do cliente acima.
Ao selecionar e enquadrar as informações do documento, priorize o que tiver impacto
direto sobre a agenda descrita no perfil — sem mencionar o cliente no texto final,
sem frases explicativas sobre a relevância e sem alterar o tom factual e direto do envio.
"""

    if formato == "Pesquisa eleitoral":
        instrucao = _instrucao_pesquisa_eleitoral()
    elif is_alerta:
        instrucao = (
            "Escreva um texto curto para WhatsApp (PT-BR), factual e direto.\n"
            "Sem opinião, sem especulação, sem bullets e sem emojis.\n"
            "Comece pelo fato principal (quem fez o quê + consequência imediata).\n"
            "Use 1–2 parágrafos. Máximo: 90 palavras.\n"
            "Não comece com 'ALERTA'/'ENVIO' nem títulos.\n"
            "Preserve nomes, cargos, datas e números exatamente como no texto.\n"
            f"\n{REGRAS_POLITICOS}\n"
        )
    else:
        instrucao = (
            "Escreva um texto para WhatsApp (PT-BR), factual e claro.\n"
            "Sem opinião, sem especulação, sem bullets e sem emojis.\n"
            "Estrutura: 1º parágrafo = fato principal; 2º = detalhe essencial/impacto.\n"
            "Use 2–3 parágrafos. Máximo: 160 palavras.\n"
            "Não comece com 'ALERTA'/'ENVIO' nem títulos.\n"
            "Preserve nomes, cargos, datas e números exatamente como no texto.\n"
            f"\n{REGRAS_POLITICOS}\n"
        )

    prompt = f"""Você é um analista que produz envios padronizados para WhatsApp.
O cabeçalho, data e título serão adicionados fora — gere apenas o corpo do texto.

Área: {area}
Formato: {formato}
{bloco_cliente}
Instruções:
{instrucao}

TEXTO:
{texto}""".strip()

    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    # Partido por extenso e título de urna abreviado valem em todo texto que a
    # casa publica. O prompt pede; isto garante, porque modelo esquece regra de
    # formatação no meio de texto longo.
    return padronizar_politicos_no_texto(gerar_resumo_seguro(resp))


def compilar_envio(is_alerta, area, abrangencia, ufs, titulo, resumo, analise_eixo, link):
    header = montar_header(is_alerta=is_alerta, area=area, abrangencia=abrangencia, ufs=ufs)
    partes = [
        f"*{header}*",
        data_br(datetime.now()),
        "",
        f"*{titulo.strip()}*",
        "",
        resumo.strip(),
    ]
    if analise_eixo and analise_eixo.strip():
        partes += ["", "ANÁLISE EIXO", analise_eixo.strip()]
    link_norm = normalizar_link(link or "")
    if link_norm:
        partes += ["", f"Link: {link_norm}"]
    return "\n".join(partes)


def whatsapp_share_link(message: str) -> str:
    return f"https://wa.me/?text={quote(message)}"

@st.dialog("Enviar no WhatsApp")
def dialog_whatsapp(message: str):
    st.caption("Vai abrir o WhatsApp com o texto já preenchido. O envio final acontece por lá.")
    st.link_button("Abrir WhatsApp", whatsapp_share_link(message), use_container_width=True)


# ─── PDF: extração de texto ───────────────────────────────────────────────────
def extrair_texto_pdf_bytes(
    pdf_bytes: bytes,
    page_indices: list[int] | None = None,
    max_chars: int | None = None,
) -> str:
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
    out = " ".join(partes).strip()
    if max_chars and len(out) > max_chars:
        out = out[:max_chars] + "\n\n[TEXTO TRUNCADO]"
    return out

def render_pdf_page_png(pdf_bytes: bytes, page_index: int, zoom: float = 3.0) -> bytes:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_index = max(0, min(page_index, doc.page_count - 1))
        page = doc.load_page(page_index)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")


# ─── PDF: leitura por visão (Gemini) ─────────────────────────────────────────
def _ler_imagens_gemini(prompt: str, imagens_png: list[bytes]) -> str:
    client = get_gemini_client()
    parts = [prompt]
    for img in imagens_png:
        parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=parts,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=8000)
        ),
    )
    return gerar_resumo_seguro(resp)


def extrair_pdf_imagem_pesquisa_eleitoral(area: str, tipo: str, imagens_png: list[bytes]) -> str:
    prompt = """Você é um analista especializado em leitura de imagens de pesquisas eleitorais brasileiras.

TAREFA: Leia TODAS as imagens enviadas com atenção máxima e extraia as informações abaixo.

PASSO 1 — ENCONTRE O CENÁRIO PRINCIPAL
Procure por qualquer uma dessas variações de rótulo (todas significam a mesma coisa):
  • "CENÁRIO 01" / "CENÁRIO 1" / "CENÁRIO 0I"
  • "cenário estimulado 1" / "cenário estimulado 01"
  • "1º cenário" / "primeiro cenário"

SE NENHUM RÓTULO FOR ENCONTRADO — não retorne erro. Em vez disso:
  → Use o primeiro gráfico de barras ou tabela com nomes de candidatos e percentuais que aparecer.
  → Se houver mais de um gráfico/tabela, use sempre o PRIMEIRO da sequência de páginas.
  → Nunca desista por falta de rótulo: se houver dados eleitorais visíveis, extraia-os.

PASSO 2 — EXTRAIA OS DADOS DO CENÁRIO
Para CADA candidato/opção listada no gráfico ou tabela escolhido:
  • Nome completo exatamente como aparece
  • Partido entre parênteses, se visível
  • Percentual exatamente como aparece (ex: 41%, 38%)
Inclua também: Nulo/Branco e NS/NR se aparecerem.

PASSO 3 — ENCONTRE A FICHA TÉCNICA
Pode estar em qualquer página — procure por:
  • Número de entrevistados / tamanho da amostra
  • Período de campo / datas das entrevistas
  • Margem de erro
  • Nível de confiança
  • Número de registro no TSE
  • Instituto/empresa responsável
Se a ficha técnica não estiver nas páginas enviadas, omita — não invente.

PASSO 4 — ESCREVA O TEXTO FINAL
Escreva UM parágrafo em português (PT-BR), máximo 110 palavras, para ser enviado por WhatsApp.

REGRAS OBRIGATÓRIAS:
- Sem bullets, sem emojis, sem títulos, sem "ALERTA"/"ENVIO" no início
- Comece diretamente pelos resultados (candidato + percentual)
- Formato de político: "Nome (PARTIDO/UF)" — use barra, nunca hífen entre partido e UF
- Se PARTIDO ou UF não estiverem visíveis na imagem, não invente
- Se houver ficha técnica, termine com ela em texto corrido
- Preserve números e percentuais exatamente como aparecem nas imagens

REGRA DE OURO: sempre produza o texto com o que for legível.
Só informe impossibilidade se as imagens estiverem completamente em branco ou ilegíveis."""
    return _ler_imagens_gemini(prompt, imagens_png)


def extrair_pdf_imagem_padrao(area: str, tipo: str, imagens_png: list[bytes]) -> str:
    prompt = f"""Você é um analista que extrai o conteúdo textual de imagens de documentos e notícias brasileiras.

TAREFA: Leia TODAS as imagens enviadas e extraia o texto principal do documento.

PASSO 1 — LEIA O CONTEÚDO
Leia todo o texto visível nas imagens com atenção máxima.
Preserve nomes, cargos, datas, números e citações exatamente como aparecem.

PASSO 2 — EXTRAIA O TEXTO PRINCIPAL
Ignore elementos de layout como cabeçalhos de site, menus, rodapés e propagandas.
Foque no corpo da notícia ou documento.

PASSO 3 — RETORNE O TEXTO EXTRAÍDO
Retorne o texto extraído em português corrido, sem bullets, sem formatação especial.
Preserve a ordem e estrutura original do conteúdo.
Não resuma nem interprete — apenas transcreva o conteúdo relevante.

Área do conteúdo: {area}
Tipo de saída esperada: {tipo}

IMPORTANTE: Retorne apenas o texto extraído, limpo e em prosa.
Se as imagens estiverem ilegíveis, informe brevemente."""
    return _ler_imagens_gemini(prompt, imagens_png)


def processar_pdf(
    pdf_bytes: bytes,
    modo: str,
    page_indices: list[int],
    area: str,
    tipo_pdf: str,
    formato: str,
) -> str:
    eh_pesquisa = (formato == "Pesquisa eleitoral")
    n_paginas = len(page_indices)

    def _renderizar_imagens():
        imgs, preview = [], None
        with st.spinner(f"Renderizando {n_paginas} página(s) em alta resolução..."):
            for p in page_indices:
                img = render_pdf_page_png(pdf_bytes, p, zoom=3.0)
                imgs.append(img)
                if preview is None:
                    preview = img
        st.session_state["pdf_preview_png"] = preview
        return imgs

    def _extrair_por_imagem(imgs):
        with st.spinner("Enviando imagens para o Gemini..."):
            if eh_pesquisa:
                return extrair_pdf_imagem_pesquisa_eleitoral(area, tipo_pdf, imgs)
            else:
                return extrair_pdf_imagem_padrao(area, tipo_pdf, imgs)

    if modo == "Texto (PyMuPDF)":
        txt = extrair_texto_pdf_bytes(pdf_bytes, page_indices=page_indices)
        st.session_state["pdf_preview_png"] = None
        return txt or "PDF sem texto extraível (possível scan)."

    elif modo == "Imagem (Gemini visão)":
        return _extrair_por_imagem(_renderizar_imagens())

    else:  # Auto
        txt = extrair_texto_pdf_bytes(pdf_bytes, page_indices=page_indices)
        if txt and len(txt.strip()) >= 800:
            st.session_state["pdf_preview_png"] = None
            return txt
        return _extrair_por_imagem(_renderizar_imagens())


# ─── Session state ────────────────────────────────────────────────────────────
for k, v in [
    ("resultado_final", ""),
    ("dados_envio", {}),
    ("texto_gerador", ""),
    ("pdf_preview_png", None),
    ("ufs_selecionadas", []),
    ("reset_titulo", False),
]:
    if k not in st.session_state:
        st.session_state[k] = v


# ─── Hero banner ──────────────────────────────────────────────────────────────
_b64 = _logo_b64(LOGO_BRANCA_PATH)
_logo_html = (
    f'<img class="ge-hero-logo" src="data:image/png;base64,{_b64}" alt="Eixo">'
    if _b64 else ""
)
st.markdown(f"""
<div class="ge-hero">
  <div class="ge-hero-title">Gerador de Envios</div>
  {_logo_html}
</div>
""", unsafe_allow_html=True)


# ─── Layout principal ─────────────────────────────────────────────────────────
col_esq, col_dir = st.columns([1.25, 1])

with col_esq:
    st.markdown('<div class="ge-rule">Preenchimento</div>', unsafe_allow_html=True)

    # ── Classificação ────────────────────────────────────────────────────────
    st.markdown(
        f'<p style="font-family:Montserrat,sans-serif;font-size:11px;font-weight:700;'
        f'letter-spacing:0.1em;text-transform:uppercase;color:{EIXO["subtexto"]};margin-bottom:6px;">Classificação</p>',
        unsafe_allow_html=True,
    )

    is_alerta = st.radio(
        "Tipo", ["Envio", "Alerta"], index=0, horizontal=True, key="tipo_radio"
    ) == "Alerta"

    c1, c2, c3 = st.columns(3)
    with c1:
        area = st.selectbox("Área", AREAS, index=0, key="area_select")
    with c2:
        formato = st.selectbox("Formato", FORMATOS, index=0, key="formato_select")
    with c3:
        if area == "Eleições":
            st.markdown(
                f'<p style="font-family:Montserrat,sans-serif;font-size:11px;font-weight:700;'
                f'letter-spacing:0.1em;text-transform:uppercase;color:{EIXO["subtexto"]};margin-bottom:2px;">Abrangência</p>',
                unsafe_allow_html=True,
            )
            st.caption("Para eleições, o recorte é definido logo abaixo.")
            abrangencia_geral = "Não especificar"
        else:
            abrangencia_geral = st.selectbox(
                "Abrangência",
                ABRANGENCIAS_OPCIONAIS,
                index=0,
                key="abrangencia_select",
            )

    escopo_eleicoes = ""

    if area == "Eleições":
        escopo_eleicoes = st.radio(
            "Recorte das eleições",
            ["Gov. Federal", "Subnacional"],
            index=0,
            horizontal=True,
            key="eleicoes_escopo_radio",
        )
    contexto = obter_contexto_classificacao(
        area=area,
        abrangencia_geral=abrangencia_geral,
        escopo_eleicoes=escopo_eleicoes,
    )
    abrangencia = contexto["abrangencia"]
    area_header = contexto["area_header"]

    # ── Chips de UF ──────────────────────────────────────────────────────────
    ufs_selecionadas: list[str] = []
    mostrar_ufs = contexto["mostrar_ufs"]

    if mostrar_ufs:
        st.caption("Selecione a(s) UF(s):")
        ac1, _ = st.columns([1, 8])
        with ac1:
            if st.button("Limpar", key="ufs_clear", use_container_width=True):
                for estado in UFS:
                    st.session_state[f"uf_chip_{estado}"] = False
                st.rerun()

        cols_uf = st.columns(9)
        for i, estado in enumerate(UFS):
            with cols_uf[i % 9]:
                if st.checkbox(estado, key=f"uf_chip_{estado}", label_visibility="visible"):
                    ufs_selecionadas.append(estado)

        if ufs_selecionadas:
            st.caption(f"Selecionadas: {', '.join(ufs_selecionadas)}")

    # ── Toggle de cliente ────────────────────────────────────────────────────
    usar_cliente = st.toggle("Personalizar para cliente", value=False, key="usar_cliente")

    cliente_key = None
    if usar_cliente:
        cliente_opcoes = {v[0]: k for k, v in CLIENTE_DESCRICOES.items()}
        cliente_label = st.selectbox(
            "Cliente",
            list(cliente_opcoes.keys()),
            key="cliente_select",
        )
        cliente_key = cliente_opcoes[cliente_label]
        with st.expander("Ver perfil do cliente", expanded=False):
            st.caption(CLIENTE_DESCRICOES[cliente_key][1])

    st.markdown("---")

    # ── Upload de PDF ─────────────────────────────────────────────────────────
    with st.expander("Carregar texto a partir de PDF", expanded=False):
        pdf_file = st.file_uploader(
            "Upload do PDF", type=["pdf"], accept_multiple_files=False, key="pdf_uploader"
        )

        if pdf_file is not None:
            pdf_bytes = pdf_file.getvalue()
            with fitz.open(stream=pdf_bytes, filetype="pdf") as d:
                total_pages = d.page_count

            modo_pdf = st.selectbox("Modo de leitura", LEITURA_PDF, index=0, key="modo_pdf")

            tab_intervalo, tab_avulsas = st.tabs(["Intervalo", "Páginas avulsas"])

            with tab_intervalo:
                ci1, ci2 = st.columns(2)
                with ci1:
                    pagina_ini = int(st.number_input("Pág. inicial", min_value=1, max_value=total_pages, value=1, key="pag_ini"))
                with ci2:
                    pagina_fim = int(st.number_input("Pág. final", min_value=1, max_value=total_pages, value=total_pages, key="pag_fim"))
                if pagina_fim < pagina_ini:
                    pagina_fim = pagina_ini
                page_indices_intervalo = list(range(pagina_ini - 1, pagina_fim))

            with tab_avulsas:
                st.caption(f"Digite os números separados por vírgula. Total de páginas: {total_pages}.")
                avulsas_raw = st.text_input("Páginas (ex: 4, 7, 11)", value="", key="pag_avulsas")
                page_indices_avulsas = []
                if avulsas_raw.strip():
                    for tok in avulsas_raw.split(","):
                        tok = tok.strip()
                        if tok.isdigit():
                            n = int(tok)
                            if 1 <= n <= total_pages:
                                idx = n - 1
                                if idx not in page_indices_avulsas:
                                    page_indices_avulsas.append(idx)
                    page_indices_avulsas.sort()
                    if page_indices_avulsas:
                        st.caption(f"{len(page_indices_avulsas)} página(s) selecionada(s): {[p+1 for p in page_indices_avulsas]}")
                    else:
                        st.warning("Nenhuma página válida informada.")

            page_indices = page_indices_avulsas if page_indices_avulsas else page_indices_intervalo
            n_paginas = len(page_indices)

            if modo_pdf != "Texto (PyMuPDF)" and n_paginas > 5:
                st.warning(
                    f"Atenção: {n_paginas} páginas selecionadas para leitura por imagem. "
                    "Para pesquisas eleitorais, recomenda-se 2–3 páginas."
                )

            if st.button("Extrair texto do PDF", use_container_width=True):
                try:
                    texto_extraido = processar_pdf(
                        pdf_bytes=pdf_bytes,
                        modo=modo_pdf,
                        page_indices=page_indices,
                        area=area_header,
                        tipo_pdf="Alerta" if is_alerta else "Envio",
                        formato=formato,
                    )
                    st.session_state["texto_gerador"] = texto_extraido
                    st.success("Texto carregado no campo abaixo. Preencha o título e clique em Gerar.")
                    if st.session_state.get("pdf_preview_png"):
                        st.image(
                            st.session_state["pdf_preview_png"],
                            caption="Prévia da primeira página renderizada",
                            use_container_width=True,
                        )
                except Exception as e:
                    st.error(f"Erro ao extrair do PDF: {e}")

    # ── Formulário principal ──────────────────────────────────────────────────
    with st.form("form_envio", clear_on_submit=False):
        texto = st.text_area(
            "Texto da notícia (até 10 mil caracteres)",
            max_chars=10_000,
            height=240,
            placeholder="Cole aqui o texto da notícia... (ou use o PDF acima para preencher automaticamente)",
            value=st.session_state.get("texto_gerador", ""),
        )

        st.markdown(
            f'<p style="font-family:Montserrat,sans-serif;font-size:11px;font-weight:700;'
            f'letter-spacing:0.1em;text-transform:uppercase;color:{EIXO["subtexto"]};margin:14px 0 6px;">Campos</p>',
            unsafe_allow_html=True,
        )

        if st.session_state.get("reset_titulo"):
            st.session_state["titulo_gerador"] = ""
            st.session_state["reset_titulo"] = False

        titulo = st.text_input(
            "Título (obrigatório)",
            value=st.session_state.get("titulo_gerador", ""),
            placeholder="Ex.: Percent divulga pesquisa para governo em MT...",
            key="titulo_gerador",
        )

        analise_eixo = st.text_area(
            "Análise Eixo (opcional)",
            height=100,
            placeholder="Se quiser, escreva aqui uma análise curta e objetiva.",
        )

        link = st.text_input("Link (opcional)", value="", placeholder="Ex.: https://...")

        submitted = st.form_submit_button("Gerar envio/alerta", use_container_width=True)

    if submitted:
        erros = []
        if not texto.strip():
            erros.append("Cole o texto da notícia (ou extraia de um PDF acima).")
        if not titulo.strip():
            erros.append("Preencha o título (obrigatório).")
        if contexto["uf_obrigatoria"] and not ufs_selecionadas:
            erros.append("Selecione ao menos uma UF para eleições subnacionais.")
        link_norm = normalizar_link(link)
        if link_norm:
            link_norm = encurtar_link(link_norm)
        if link.strip() and not link_norm:
            erros.append("O link parece inválido. Cole uma URL completa (http/https).")

        if erros:
            for e in erros:
                st.error(e)
        else:
            with st.spinner("Gerando resumo com IA e compilando o envio..."):
                try:
                    resumo = gerar_resumo_gemini(
                        texto=texto,
                        is_alerta=is_alerta,
                        area=area_header,
                        formato=formato,
                        cliente_key=cliente_key,
                    )
                    resultado = compilar_envio(
                        is_alerta=is_alerta,
                        area=area_header,
                        abrangencia=abrangencia,
                        ufs=ufs_selecionadas if mostrar_ufs else None,
                        titulo=titulo,
                        resumo=resumo,
                        analise_eixo=analise_eixo,
                        link=link_norm,
                    )
                    st.session_state["resultado_final"] = resultado
                    st.session_state["dados_envio"] = {
                        "tipo": "Alerta" if is_alerta else "Envio",
                        "area": area_header,
                        "uf": ", ".join(ufs_selecionadas) if ufs_selecionadas else "",
                        "formato": formato,
                        "cliente": CLIENTE_DESCRICOES[cliente_key][0] if cliente_key else "Geral",
                        "titulo": titulo,
                        "resumo": resumo,
                        "analise_eixo": analise_eixo,
                        "link": link_norm,
                        "texto": texto,
                    }
                    st.session_state["reset_titulo"] = True
                    st.success("Envio gerado.")
                except Exception as e:
                    st.error(f"Erro ao gerar com Gemini: {e}")


# ─── Coluna direita: resultado ────────────────────────────────────────────────
with col_dir:
    st.markdown('<div class="ge-rule">Resultado</div>', unsafe_allow_html=True)

    if not st.session_state["resultado_final"].strip():
        st.markdown(
            f'<div class="ge-result-card">'
            f'<p style="font-family:Montserrat,sans-serif;font-size:13px;color:{EIXO["subtexto"]};margin:0;">'
            f'Preencha o formulário e clique em <strong style="color:{EIXO["tinta"]};">Gerar envio/alerta</strong>.'
            f'</p></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<p style="font-family:Montserrat,sans-serif;font-size:11px;font-weight:700;'
            f'letter-spacing:0.08em;text-transform:uppercase;color:{EIXO["subtexto"]};margin-bottom:6px;">Copiar:</p>',
            unsafe_allow_html=True,
        )
        st.code(st.session_state["resultado_final"], language="text")

        c1, c2 = st.columns(2)

        with c1:
            if st.button("Enviar no WhatsApp", use_container_width=True):
                dialog_whatsapp(st.session_state["resultado_final"])

        with c2:
            if st.button("Salvar no Sheets", use_container_width=True):
                if get_sheets_client():
                    with st.spinner("Salvando..."):
                        dados = st.session_state["dados_envio"]
                        sucesso = salvar_no_sheets(
                            tipo=dados["tipo"], area=dados["area"], uf=dados["uf"],
                            formato=dados["formato"], cliente=dados.get("cliente"),
                            titulo=dados["titulo"], resumo=dados["resumo"],
                            analise_eixo=dados["analise_eixo"],
                            link=dados["link"], texto_completo=dados["texto"],
                        )
                        if sucesso:
                            st.success("Salvo no Google Sheets!")
                        else:
                            st.error("Erro ao salvar")
                else:
                    st.error("Google Sheets não configurado. Veja a sidebar.")
