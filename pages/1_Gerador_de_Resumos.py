from datetime import datetime
from urllib.parse import quote
import os
import re
import json
import inspect

import streamlit as st
from google import genai
from google.genai import types
import fitz  # PyMuPDF

import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

st.set_page_config(page_title="Gerador de Resumos", layout="wide")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');
:root { --eixo-vinho: #962E4D; }
html, body, [data-testid="stAppViewContainer"] { background: #F4F3EF !important; }
[data-testid="stAppViewContainer"] > section > div { background: #F4F3EF; }
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1320px !important; padding: 0 2rem 3rem !important; background: #F4F3EF; }
* { box-sizing: border-box; }
body, p, span, div, label, input, select, textarea { font-family: 'Montserrat', sans-serif !important; }
[data-testid="stHeader"] { display: none; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stSidebar"] { background: #F4F3EF !important; border-right: 1px solid #DADAD4 !important; }
[data-testid="stSidebar"] * { font-family: 'Montserrat', sans-serif !important; font-size: 13px !important; }
/* Streamlit usa texto com fonte Material para ícones; não sobrescreva essa fonte. */
span.material-symbols-rounded, span.material-symbols-outlined, span.material-icons,
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    letter-spacing: normal !important; text-transform: none !important;
}
footer { display: none !important; }
#MainMenu { display: none !important; }
[data-testid="stButton"] > button {
    font-family: 'Montserrat', sans-serif !important; font-size: 11px !important;
    font-weight: 500 !important; letter-spacing: 0.1em !important;
    text-transform: uppercase !important; border-radius: 0 !important;
    border: 1px solid #962E4D !important; background: transparent !important;
    color: #962E4D !important; padding: 5px 14px !important;
    transition: background 0.15s, color 0.15s !important;
}
[data-testid="stButton"] > button:hover { background: #962E4D !important; color: #fff !important; }
[data-testid="stSidebar"] [data-testid="stButton"] > button { border: 1px solid #962E4D !important; color: #962E4D !important; }
[data-testid="stSidebar"] [data-testid="stButton"] > button:hover { background: #962E4D !important; color: #fff !important; }
[data-testid="stRadio"] > label, [data-testid="stSelectbox"] > label,
[data-testid="stMultiSelect"] > label, [data-testid="stTextInput"] > label,
[data-testid="stNumberInput"] > label, [data-testid="stTextArea"] > label {
    font-size: 11px !important; font-weight: 700 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important; color: #767672 !important;
}
[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid #DADAD4 !important; gap: 0 !important; }
[data-testid="stTabs"] [role="tab"] {
    font-size: 11px !important; font-weight: 500 !important; letter-spacing: 0.12em !important;
    text-transform: uppercase !important; color: #767672 !important;
    padding: 10px 20px 9px !important; border-bottom: 2px solid transparent !important;
    background: transparent !important; border-radius: 0 !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: #962E4D !important; border-bottom-color: #962E4D !important; }
div[data-testid="stCodeBlock"] > pre { max-height: 520px !important; overflow: auto !important; border-radius: 0 !important; }
.ge-hero { background: #962E4D; display: flex; align-items: center; padding: 36px 48px; margin: 0 -2rem 32px -2rem; }
.ge-hero-title { font-family: 'Montserrat', sans-serif; font-size: 48px; font-weight: 800; color: #fff; line-height: 1; letter-spacing: -0.01em; }
.ge-rule { font-size: 12px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #962E4D; border-top: 1.5px solid #962E4D; padding-top: 8px; margin: 20px 0 14px; }
</style>""", unsafe_allow_html=True)


# ── autenticação ──────────────────────────────────────────────────────────────

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


# ── configurações ─────────────────────────────────────────────────────────────

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-3.6-flash"   # 2.5-flash dá 404 para a chave do projeto novo

LOGO_PATH = "Marca_eixo_vetor_Logo horizontal magenta.png"

EIXO = {
    "preto":         "#000000",
    "cinza":         "#999999",
    "gelo":          "#F4F3EF",
    "vinho":         "#962E4D",
    "azul":          "#192D4E",
    "amarelo":       "#E8A600",
    "amarelo_claro": "#f0d46c",
    "vermelho":      "#B84349",
}


# ── clientes ──────────────────────────────────────────────────────────────────

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


# ── tipos de documento ────────────────────────────────────────────────────────

TIPOS_DOCUMENTO = {
    # Legislativo
    "Projeto de Lei (PL / PLC / PLP)": "pl",
    "Proposta de Emenda Constitucional (PEC)": "pec",
    "Medida Provisória (MPV)": "mpv",
    "Projeto de Decreto Legislativo (PDL)": "pdl",
    "Emenda Parlamentar": "emenda",
    "Parecer / Voto de Relator": "parecer",
    "Resultado de Votação em Plenário": "votacao",
    "Agenda / Pauta de Comissão ou Plenário": "pauta",
    # Executivo / Regulatório
    "Portaria ou Resolução": "portaria",
    "Nota Técnica (Ministério / Agência)": "nota_tecnica",
    "Ata de Reunião (Conitec, CNE, Conasp etc.)": "ata",
    "Dados Orçamentários (LOA / LDO / PPA)": "orcamento",
    # Mídia
    "Notícia / Reportagem": "noticia",
    "Editorial / Artigo de Opinião": "editorial",
    "Entrevista com Autoridade": "entrevista",
    "Pronunciamento / Discurso": "discurso",
    # Técnico / Científico
    "Estudo ou Relatório Técnico": "estudo",
    "Pesquisa / Survey": "pesquisa",
    "Documento Institucional (Relatório anual, posicionamento etc.)": "institucional",
}

LEITURA_PDF = [
    "Auto (texto se tiver; imagem se for scan)",
    "Texto (PyMuPDF)",
    "Imagem (Gemini visão)",
]


# ── estilos ───────────────────────────────────────────────────────────────────

# estilos já injetados no bloco único acima


# ── cliente Gemini ────────────────────────────────────────────────────────────

@st.cache_resource
def get_gemini_client():
    if not GEMINI_API_KEY.strip():
        raise RuntimeError(
            "Faltou a GEMINI_API_KEY. Configure nos Secrets do Streamlit Cloud "
            "ou crie .streamlit/secrets.toml local."
        )
    return genai.Client(api_key=GEMINI_API_KEY)


# ── prompts por tipo de documento ─────────────────────────────────────────────

def _prompt_por_tipo(tipo_key: str) -> str:
    """
    Retorna as instruções específicas de extração/resumo para cada tipo de documento.
    Essas instruções são injetadas no prompt principal.
    """

    prompts = {

        # ── LEGISLATIVO ───────────────────────────────────────────────────────

        "pl": """
TIPO: Projeto de Lei (PL / PLC / PLP)

Objetivo da leitura:
Extrair o conteúdo factual do projeto e, em seguida, avaliar se há impacto direto sobre a agenda do cliente.

Extraia e destaque obrigatoriamente, quando estiverem presentes no documento:
1. Número e ano do projeto, casa legislativa de origem (Câmara / Senado).
2. Autor(es) com partido e UF no formato "Nome (PARTIDO/UF)".
3. Ementa ou objeto do projeto em uma frase.
4. Estágio atual de tramitação e última movimentação relevante.
5. Prazo, urgência, votação agendada ou regime especial, se houver.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável no texto.

Critério de relevância para o cliente:
Considere relevante apenas se o projeto afetar de forma clara algum eixo temático, programa, arena institucional, regra, financiamento, implementação de política, grupo beneficiário prioritário ou posição pública descrita no perfil do cliente.
Não trate afinidade temática ampla como relevância suficiente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = identificação factual do projeto: número, objeto, autoria e situação.
2º parágrafo = tramitação, prazo/urgência e relevância analítica para o cliente, apenas com base no texto e no perfil fornecido.

Se não houver relação direta com a agenda do cliente, declare isso explicitamente no 2º parágrafo.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "pec": """
TIPO: Proposta de Emenda Constitucional (PEC)

Objetivo da leitura:
Identificar a alteração constitucional proposta, sua tramitação e seu impacto potencial sobre a agenda do cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Número e ano da PEC, casa de origem.
2. Autor(es) com partido e UF no formato "Nome (PARTIDO/UF)".
3. Dispositivo constitucional afetado e sentido da alteração.
4. Estágio de tramitação.
5. Quórum necessário ou exigências procedimentais, se mencionados.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável.

Critério de relevância para o cliente:
Só considere relevante se a mudança constitucional alterar de forma concreta o ambiente jurídico, institucional, programático ou orçamentário de temas monitorados pelo cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = identificação da PEC, objeto da alteração e autoria.
2º parágrafo = tramitação, exigências procedimentais e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso claramente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "mpv": """
TIPO: Medida Provisória (MPV)

Objetivo da leitura:
Identificar a mudança normativa imediata produzida pela MP, sua vigência e seus efeitos potenciais sobre a agenda do cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Número e data de edição da MP.
2. Objeto principal: o que institui, altera ou revoga.
3. Prazo de vigência e data de validade, se mencionados.
4. Situação no Congresso.
5. Alterações relevantes em relação à norma anterior, se mencionadas.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável.

Critério de relevância para o cliente:
Considere relevante apenas quando a MP alterar regra, financiamento, competência institucional, execução de política pública, acesso a direitos, regulação setorial ou implementação em eixo monitorado pelo cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = identificação da MP, objeto e vigência.
2º parágrafo = situação no Congresso, principais mudanças e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso explicitamente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "pdl": """
TIPO: Projeto de Decreto Legislativo (PDL)

Objetivo da leitura:
Identificar qual ato o PDL susta, ratifica ou aprova, em que estágio está e se isso afeta diretamente a agenda do cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Número e ano, casa de origem.
2. Autor(es) com partido e UF no formato "Nome (PARTIDO/UF)".
3. Objeto do PDL.
4. Ato do Executivo ou regulatório alvo do PDL, se houver.
5. Estágio de tramitação.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável.

Critério de relevância para o cliente:
Só considere relevante se o ato alvo do PDL interferir diretamente em pauta regulatória, institucional, programática ou de direitos conectada ao perfil do cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = identificação do PDL, objeto e ato alvo.
2º parágrafo = tramitação e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso claramente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "emenda": """
TIPO: Emenda Parlamentar

Objetivo da leitura:
Identificar como a emenda altera a matéria principal e se isso modifica de forma concreta um tema monitorado pelo cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Tipo de emenda, número e autor com partido/UF no formato "Nome (PARTIDO/UF)".
2. Matéria à qual se refere.
3. O que a emenda altera, acrescenta ou suprime.
4. Se muda o mérito ou apenas a redação, quando isso puder ser inferido com segurança.
5. Situação da emenda.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável.

Critério de relevância para o cliente:
Só considere relevante se a emenda alterar conteúdo, alcance, financiamento, beneficiários, governança ou implementação de tema monitorado pelo cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = identificação da emenda e conteúdo da mudança.
2º parágrafo = situação e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso explicitamente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "parecer": """
TIPO: Parecer / Voto de Relator

Objetivo da leitura:
Identificar a recomendação do relator, seus fundamentos e o que isso significa para a agenda do cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Relator com partido e UF no formato "Nome (PARTIDO/UF)".
2. Matéria analisada: número e objeto resumido.
3. Recomendação do relator.
4. Principais fundamentos do voto.
5. Próximo passo processual, se mencionado.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável.

Critério de relevância para o cliente:
Só considere relevante se a recomendação do relator puder alterar o destino legislativo, o conteúdo normativo ou a viabilidade política de pauta ligada ao cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = relator, matéria e recomendação.
2º parágrafo = fundamentos, próximo passo e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso claramente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "votacao": """
TIPO: Resultado de Votação em Plenário

Objetivo da leitura:
Registrar o resultado da deliberação e avaliar se o desfecho altera concretamente um tema monitorado pelo cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Casa legislativa, data e matéria votada.
2. Resultado da votação.
3. Placar, se disponível.
4. Destaques, emendas ou alterações conexas, se mencionados.
5. Próximo passo institucional, se houver.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável.

Critério de relevância para o cliente:
Só considere relevante se o resultado produzir efeito normativo, político, regulatório, orçamentário ou institucional claro sobre tema monitorado pelo cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = resultado factual da votação e matéria.
2º parágrafo = desdobramentos e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso explicitamente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "pauta": """
TIPO: Agenda / Pauta de Comissão ou Plenário

Objetivo da leitura:
Identificar as matérias pautadas e separar aquelas que têm relação direta com a agenda do cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Órgão, data e hora da sessão.
2. Matérias pautadas com número e objeto resumido.
3. Quais matérias têm relação direta com a agenda do cliente.
4. Relator das matérias relevantes, se indicado.
5. Urgência, retirada de pauta ou prioridade, se mencionadas.

Critério de relevância para o cliente:
Só considere relevante matéria com impacto direto identificável sobre tema, programa, regulação, orçamento, implementação ou posição institucional monitorada pelo cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = data, órgão e visão geral da pauta.
2º parágrafo = apenas as matérias diretamente relevantes para o cliente, com relator e urgência se houver.

Se nenhuma matéria tiver relação direta com a agenda do cliente, diga isso claramente no 2º parágrafo.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        # ── EXECUTIVO / REGULATÓRIO ───────────────────────────────────────────

        "portaria": """
TIPO: Portaria ou Resolução

Objetivo da leitura:
Identificar a norma, seu conteúdo regulatório e se ela altera concretamente um tema monitorado pelo cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Número, data e órgão emissor.
2. Objeto principal da norma.
3. Público-alvo, setor ou política afetada.
4. Vigência ou vacatio legis, se mencionada.
5. Obrigações, vedações ou mudanças concretas em relação à norma anterior, se mencionadas.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável.

Critério de relevância para o cliente:
Só considere relevante se a norma alterar governança, regulação, implementação, acesso, financiamento, exigências operacionais ou direitos em tema monitorado pelo cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = identificação da norma, objeto e público/setor afetado.
2º parágrafo = mudanças concretas, vigência e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso explicitamente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "nota_tecnica": """
TIPO: Nota Técnica (Ministério / Agência Reguladora)

Objetivo da leitura:
Identificar o objeto analisado, a conclusão da nota e se ela afeta diretamente uma agenda monitorada pelo cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Órgão emissor, número/referência e data.
2. Objeto analisado.
3. Conclusão ou recomendação principal.
4. Principais fundamentos técnicos.
5. Caráter vinculante ou consultivo, se mencionado.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável.

Critério de relevância para o cliente:
Só considere relevante se a nota influenciar decisão regulatória, incorporação de tecnologia, definição técnica, consulta pública, implementação normativa ou posicionamento institucional em tema monitorado pelo cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = identificação da nota, objeto e conclusão.
2º parágrafo = fundamentos, natureza do documento e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso claramente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "ata": """
TIPO: Ata de Reunião (Conitec, CNE, Conasp, CONANDA etc.)

Objetivo da leitura:
Registrar as decisões tomadas e indicar se alguma deliberação afeta diretamente tema monitorado pelo cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Órgão, número da reunião e data.
2. Principais deliberações.
3. Matérias aprovadas, rejeitadas ou adiadas.
4. Divergências relevantes, se mencionadas.
5. Pontos pendentes para próxima reunião, se houver.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável.

Critério de relevância para o cliente:
Só considere relevante se a deliberação afetar incorporação, regulamentação, implementação, financiamento, governança ou acesso a políticas relacionadas ao perfil do cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = identificação da reunião e principais deliberações.
2º parágrafo = pendências, divergências e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso claramente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "orcamento": """
TIPO: Dado Orçamentário (LOA / LDO / PPA / emenda orçamentária)

Objetivo da leitura:
Identificar os programas e valores associados à agenda do cliente e avaliar se há ampliação, corte, recomposição ou manutenção com impacto concreto.

Extraia e destaque obrigatoriamente, quando presentes:
1. Instrumento orçamentário e ano.
2. Programa(s), ação(ões) ou rubricas com relação direta à agenda do cliente.
3. Valores: dotação, crédito, liquidado, executado, se disponíveis.
4. Comparação com exercício anterior, se informada.
5. Órgão responsável, se mencionado.
6. Relação com a agenda do cliente apenas se houver impacto direto identificável.

Critério de relevância para o cliente:
Só considere relevante se houver vínculo claro entre a rubrica orçamentária e programa, política, serviço, público prioritário ou área de advocacy descrita no perfil do cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = instrumento, programas/rubricas e valores.
2º parágrafo = variação, órgão responsável e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso explicitamente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        # ── MÍDIA ─────────────────────────────────────────────────────────────

        "noticia": """
TIPO: Notícia / Reportagem

Objetivo da leitura:
Resumir o fato noticiado com precisão e avaliar se ele gera consequência concreta para a agenda do cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Veículo, data e autor.
2. Fato principal: o que aconteceu, com quem, quando e onde.
3. Contexto imediato que explica por que o fato ocorreu agora.
4. Personagens ou instituições centrais.
5. Próximos passos ou desdobramentos concretos, se mencionados.
6. Relação com a agenda do cliente apenas se houver consequência direta identificável.

Critério de relevância para o cliente:
Notícia só deve ser tratada como relevante se relatar decisão, proposta, conflito, anúncio, consulta, votação, mudança institucional, risco reputacional ou desdobramento operacional que afete diretamente tema monitorado pelo cliente.
Afinidade temática geral não basta.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = fato principal e contexto.
2º parágrafo = desdobramentos concretos e relevância para o cliente.

Se a notícia apenas contextualiza um tema amplo, sem efeito direto sobre a agenda do cliente, declare isso claramente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "editorial": """
TIPO: Editorial / Artigo de Opinião

Objetivo da leitura:
Identificar a tese defendida pelo texto e avaliar se ela converge, diverge ou é irrelevante para a agenda do cliente em termos de debate público e incidência.

Extraia e destaque obrigatoriamente, quando presentes:
1. Veículo, autor e data.
2. Tese central.
3. Principais argumentos mobilizados.
4. Alvo da crítica ou defesa, se identificável.
5. Propostas ou recomendações concretas, se houver.
6. Relação com a agenda do cliente apenas se houver conexão substantiva identificável.

Critério de relevância para o cliente:
Só considere relevante se o texto incidir diretamente sobre tema, norma, política, disputa regulatória ou enquadramento público importante para a atuação do cliente.
Não trate opinião genérica sobre área ampla como relevante por si só.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = autoria, veículo e tese central.
2º parágrafo = argumentos, propostas e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso claramente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "entrevista": """
TIPO: Entrevista com Autoridade

Objetivo da leitura:
Registrar as declarações centrais da autoridade e indicar se elas produzem sinalização política ou institucional relevante para o cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Entrevistado: nome, cargo e instituição, com partido/UF no formato "Nome (PARTIDO/UF)" se político.
2. Veículo e data.
3. Principais declarações e posicionamentos.
4. Anúncios, sinalizações ou compromissos concretos, se houver.
5. Polêmicas ou controvérsias mencionadas, se houver.
6. Relação com a agenda do cliente apenas se houver consequência direta identificável.

Critério de relevância para o cliente:
Só considere relevante se as declarações abrirem janela de decisão, indicarem mudança de posição, anteciparem medida concreta, afetarem reputação institucional ou alterarem o ambiente político de tema monitorado pelo cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = quem falou, onde e o que disse.
2º parágrafo = sinalizações concretas e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso explicitamente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "discurso": """
TIPO: Pronunciamento / Discurso

Objetivo da leitura:
Registrar o conteúdo do pronunciamento e identificar se ele altera, sinaliza ou pressiona tema monitorado pelo cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Autor com cargo e partido/UF no formato "Nome (PARTIDO/UF)", data e contexto do pronunciamento.
2. Tema central.
3. Principais argumentos ou posicionamentos.
4. Propostas, anúncios ou críticas concretas, se houver.
5. Tom geral, apenas se puder ser identificado claramente no texto.
6. Relação com a agenda do cliente apenas se houver consequência direta identificável.

Critério de relevância para o cliente:
Só considere relevante se o pronunciamento estiver associado a iniciativa legislativa, disputa institucional, pressão sobre política pública, articulação política ou enquadramento público relevante para tema monitorado pelo cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = autor, contexto e tema central.
2º parágrafo = posições concretas e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso claramente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        # ── TÉCNICO / CIENTÍFICO ──────────────────────────────────────────────

        "estudo": """
TIPO: Estudo ou Relatório Técnico

Objetivo da leitura:
Identificar o problema analisado, os principais achados e o uso potencial do estudo para a agenda do cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Instituição produtora, título e data.
2. Objeto do estudo.
3. Principais achados ou conclusões.
4. Metodologia resumida, se disponível.
5. Recomendações de política pública, se houver.
6. Relação com a agenda do cliente apenas se houver uso estratégico direto identificável.

Critério de relevância para o cliente:
Só considere relevante se os achados puderem sustentar diagnóstico, advocacy, incidência regulatória, formulação de proposta, monitoramento ou debate público em eixo descrito no perfil do cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = instituição, objeto e principais conclusões.
2º parágrafo = metodologia, recomendações e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso claramente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "pesquisa": """
TIPO: Pesquisa / Survey

Objetivo da leitura:
Registrar os resultados da pesquisa com precisão metodológica e avaliar se eles podem ser usados como evidência na agenda do cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Instituto responsável, encomendante, data de campo e amostra.
2. Objeto medido.
3. Principais resultados com percentuais exatos.
4. Margem de erro e nível de confiança, se disponíveis.
5. Registro ou referência metodológica, se houver.
6. Relação com a agenda do cliente apenas se houver uso direto identificável.

Critério de relevância para o cliente:
Só considere relevante se os resultados puderem ser mobilizados diretamente como evidência para tema, público, política ou disputa monitorada pelo cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = objeto e resultados centrais com percentuais.
2º parágrafo = ficha técnica e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso explicitamente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",

        "institucional": """
TIPO: Documento Institucional (Relatório anual, posicionamento, carta aberta, manifesto etc.)

Objetivo da leitura:
Identificar o objetivo político-institucional do documento e avaliar o que ele significa para o campo de atuação do cliente.

Extraia e destaque obrigatoriamente, quando presentes:
1. Organização emissora, tipo de documento e data.
2. Objetivo ou motivação do documento.
3. Principais posicionamentos, demandas ou propostas.
4. Destinatários, se identificáveis.
5. Pedidos, alertas ou recomendações concretas, se houver.
6. Relação com a agenda do cliente apenas se houver conexão substantiva identificável.

Critério de relevância para o cliente:
Só considere relevante se o documento atuar sobre debate, regulação, coalizão, advocacy, disputa pública ou formulação institucional em tema descrito no perfil do cliente.

Regras de estilo:
- Sem travessões.
- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'.
- O 2º parágrafo não deve repetir informações já apresentadas no 1º. Inicie diretamente com informação nova.

Estrutura obrigatória do resumo:
1º parágrafo = emissor, objetivo e posições centrais.
2º parágrafo = destinatários, pedidos concretos e relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso claramente.
Se algum item não estiver disponível, omita.
Não invente informações.
""",
    }

    return prompts.get(tipo_key, "")


# ── geração do resumo ─────────────────────────────────────────────────────────

# Regra de formatação de político é uma só para o app inteiro: envio, alerta e
# resumo. Aqui havia uma cópia que já tinha começado a divergir da original.
from alerta_pesquisa_core import REGRAS_POLITICOS, padronizar_politicos_no_texto

REGRAS_GERAIS = (
    "Regras gerais de escrita (obrigatório):\n"
    "- Escreva em PT-BR, em tom analítico, sóbrio e objetivo.\n"
    "- Sem opinião, especulação, bullets ou emojis.\n"
    "- Sem travessões, sem adjetivos exagerados e sem linguagem fatalista.\n"
    "- Preserve nomes, cargos, datas, percentuais, valores e números exatamente como aparecem no documento.\n"
    "- Não invente informações ausentes no texto.\n"
    "- Quando houver incerteza, ambiguidade ou evidência parcial, use formulações prudentes como "
    "'o documento indica', 'o texto sugere', 'não há informação suficiente para concluir'.\n"
    "- O resumo deve separar duas camadas: "
    "parágrafo 1 = extração factual do documento; "
    "parágrafo 2 = desdobramento processual e inferência analítica sobre relevância para o cliente.\n"
    "- A relevância para o cliente deve ser tratada como inferência analítica, nunca como fato literal do documento.\n"
    "- Só classifique algo como relevante para o cliente se houver impacto direto, regulatório, orçamentário, "
    "programático, institucional, operacional, reputacional ou político claramente identificável.\n"
    "- Não trate mera afinidade temática ampla como relevância suficiente.\n"
    "- Se o documento não tiver relação direta com a agenda do cliente, informe isso claramente e não force conexão.\n"
    "- Não atribua posicionamentos, histórico de atuação, preferências ou intenções ao cliente além do que está descrito "
    "no perfil fornecido.\n"
    "- A frase de relevância para o cliente deve ser específica: cite o eixo afetado e explique o mecanismo da relação.\n"
    "- Evite fórmulas vazias como 'tem relação com os temas do cliente' ou 'é importante para a agenda do cliente'.\n"
    "- O 2º parágrafo nunca deve repetir o conteúdo do 1º. Cada parágrafo deve acrescentar informação nova.\n"
    "- Não inicie frases com pronomes demonstrativos como 'Este', 'Esta', 'Esse', 'Essa'. Prefira sujeito explícito.\n"
    "- Evite redundâncias como 'retrocesso desfavorável', 'avanço favorável' ou 'impacto negativo prejudicial'.\n"
    "- Se não houver base suficiente para afirmar que o impacto é favorável, desfavorável, ambíguo ou neutro, "
    "explique a limitação em vez de forçar a classificação.\n"
)


def gerar_resumo(texto: str, cliente_key: str, tipo_label: str, tipo_key: str, contexto_extra: str = "") -> str:
    client = get_gemini_client()

    nome_cliente, desc_cliente = CLIENTE_DESCRICOES[cliente_key]
    instrucoes_tipo = _prompt_por_tipo(tipo_key)

    contexto_bloco = ""
    if contexto_extra.strip():
        contexto_bloco = f"\nCONTEXTO ADICIONAL FORNECIDO PELO ANALISTA:\n{contexto_extra.strip()}\n"

    prompt = f"""Você é um analista sênior de monitoramento legislativo e de políticas públicas da Eixo.
Sua tarefa é produzir um resumo estratégico e personalizado do documento abaixo, adaptado aos interesses do cliente indicado.

Leia o texto com prioridade para precisão factual.
Primeiro, identifique o conteúdo objetivo do documento.
Depois, avalie se existe relevância direta para a agenda do cliente com base apenas no perfil fornecido e no conteúdo do documento.

═══════════════════════════════
CLIENTE
═══════════════════════════════
Nome: {nome_cliente}
Perfil e temas de interesse:
{desc_cliente}

═══════════════════════════════
TIPO DE DOCUMENTO
═══════════════════════════════
{tipo_label}

═══════════════════════════════
INSTRUÇÕES ESPECÍFICAS PARA ESTE TIPO
═══════════════════════════════
{instrucoes_tipo}

═══════════════════════════════
REGRAS DE FORMATAÇÃO
═══════════════════════════════
{REGRAS_POLITICOS}
{REGRAS_GERAIS}

═══════════════════════════════
DOCUMENTO
═══════════════════════════════
{contexto_bloco}
{texto}

═══════════════════════════════
TAREFA
═══════════════════════════════
Produza um resumo em exatamente 2 parágrafos.

Função de cada parágrafo:
- 1º parágrafo: extração factual do documento.
- 2º parágrafo: tramitação, desdobramento, consequência prática ou leitura analítica de relevância para o cliente.

Se não houver relação direta com a agenda do cliente, diga isso explicitamente no 2º parágrafo.
Não use bullets.
Não use títulos.
Não invente informações.
Máximo: 180 palavras no total.
""".strip()

    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    # Partido por extenso e título de urna abreviado valem em tudo que a casa
    # publica, não só no Alerta de Pesquisa. O prompt pede; isto garante.
    return padronizar_politicos_no_texto((resp.text or "").strip())



# ── PDF helpers ───────────────────────────────────────────────────────────────

def extrair_texto_pdf(pdf_bytes: bytes, page_indices: list[int] | None = None) -> str:
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
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")

def extrair_pdf_imagem(pdf_bytes: bytes, page_indices: list[int]) -> str:
    client = get_gemini_client()
    imgs = [render_pdf_page_png(pdf_bytes, p) for p in page_indices]
    prompt = (
        "Extraia todo o texto visível nestas imagens de documento. "
        "Retorne apenas o texto corrido, sem formatação especial, preservando nomes, "
        "números, datas e citações exatamente como aparecem."
    )
    parts = [prompt] + [types.Part.from_bytes(data=img, mime_type="image/png") for img in imgs]
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=parts,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=8000)
        ),
    )
    return (resp.text or "").strip()

def processar_pdf(pdf_bytes: bytes, modo: str, page_indices: list[int]) -> str:
    if modo == "Texto (PyMuPDF)":
        txt = extrair_texto_pdf(pdf_bytes, page_indices[:10])
        return txt or "PDF sem texto extraível (possível scan)."
    elif modo == "Imagem (Gemini visão)":
        with st.spinner("Enviando imagens para o Gemini..."):
            return extrair_pdf_imagem(pdf_bytes, page_indices)
    else:  # Auto
        txt = extrair_texto_pdf(pdf_bytes, page_indices)
        if txt and len(txt.strip()) >= 800:
            return txt
        with st.spinner("PDF parece ser scan — usando visão do Gemini..."):
            return extrair_pdf_imagem(pdf_bytes, page_indices)


# ── session state ─────────────────────────────────────────────────────────────

for k, v in [
    ("resumo_gerado", ""),
    ("texto_fonte", ""),
    ("cliente_selecionado", ""),
    ("tipo_selecionado", ""),
]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    try:
        st.image(LOGO_PATH, use_container_width=True)
    except Exception:
        st.caption("Logo não encontrada.")
    st.markdown(
        '<div style="border-left:3px solid #962E4D;padding:10px 12px;'
        'margin:10px 0 0 0;background:transparent;">'
        '<p style="font-family:Montserrat,sans-serif;font-size:12.5px;'
        'color:#111;line-height:1.65;margin:0;">'
        'Cole o texto ou suba um PDF, selecione o cliente e o tipo de documento, '
        'e o app gera um <strong>resumo personalizado com IA</strong>.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("↻ Recarregar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.caption(f"Usuário: **{st.session_state.get('name', '')}** ({st.session_state.get('username', '')})")
    if _auth_cfg:
        authenticator.logout("Sair", "sidebar")


# ── página principal ──────────────────────────────────────────────────────────

st.markdown(
    '<div class="ge-hero"><div class="ge-hero-title">Gerador de Resumos</div></div>',
    unsafe_allow_html=True,
)

col_esq, col_dir = st.columns([1.25, 1])

with col_esq:
    st.markdown('<div class="ge-rule">Configuração</div>', unsafe_allow_html=True)

    # ── Seleção de cliente ────────────────────────────────────────────────────
    cliente_opcoes = {v[0]: k for k, v in CLIENTE_DESCRICOES.items()}
    cliente_label = st.selectbox(
        "Cliente",
        list(cliente_opcoes.keys()),
        key="cliente_select",
    )
    cliente_key = cliente_opcoes[cliente_label]

    # mostra descrição resumida do cliente
    with st.expander("Ver perfil do cliente", expanded=False):
        st.caption(CLIENTE_DESCRICOES[cliente_key][1])

    # ── Seleção de tipo de documento ──────────────────────────────────────────
    tipo_label = st.selectbox(
        "Tipo de documento",
        list(TIPOS_DOCUMENTO.keys()),
        key="tipo_select",
    )
    tipo_key = TIPOS_DOCUMENTO[tipo_label]

    st.markdown("---")

    # ── Upload de PDF ─────────────────────────────────────────────────────────
    with st.expander("Carregar texto a partir de PDF", expanded=False):
        pdf_file = st.file_uploader("Upload do PDF", type=["pdf"], key="pdf_uploader")

        if pdf_file is not None:
            pdf_bytes = pdf_file.getvalue()
            with fitz.open(stream=pdf_bytes, filetype="pdf") as d:
                total_pages = d.page_count

            modo_pdf = st.selectbox("Modo de leitura", LEITURA_PDF, index=0, key="modo_pdf")

            tab_intervalo, tab_avulsas = st.tabs(["Intervalo", "Páginas avulsas"])

            with tab_intervalo:
                ci1, ci2 = st.columns(2)
                with ci1:
                    pag_ini = int(st.number_input("Pág. inicial", min_value=1, max_value=total_pages, value=1, key="pag_ini"))
                with ci2:
                    pag_fim = int(st.number_input("Pág. final", min_value=1, max_value=total_pages, value=total_pages, key="pag_fim"))
                if pag_fim < pag_ini:
                    pag_fim = pag_ini
                page_indices_intervalo = list(range(pag_ini - 1, pag_fim))

            with tab_avulsas:
                st.caption(f"Páginas separadas por vírgula. Total: {total_pages}.")
                avulsas_raw = st.text_input("Páginas (ex: 1, 3, 5)", value="", key="pag_avulsas")
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

            page_indices = page_indices_avulsas if page_indices_avulsas else page_indices_intervalo

            if st.button("Extrair texto do PDF", use_container_width=True):
                try:
                    with st.spinner("Extraindo texto..."):
                        texto_extraido = processar_pdf(pdf_bytes, modo_pdf, page_indices)
                    st.session_state["texto_fonte"] = texto_extraido
                    st.success("Texto carregado. Revise abaixo e clique em Gerar.")
                except Exception as e:
                    st.error(f"Erro ao extrair PDF: {e}")

    # ── Formulário principal ──────────────────────────────────────────────────
    with st.form("form_resumo", clear_on_submit=False):
        texto = st.text_area(
            "Texto do documento (até 15 mil caracteres)",
            max_chars=15_000,
            height=260,
            placeholder="Cole aqui o texto do documento... (ou use o PDF acima)",
            value=st.session_state.get("texto_fonte", ""),
            key="texto_input",
        )

        contexto_extra = st.text_area(
            "Contexto adicional para o analista (opcional)",
            height=80,
            placeholder="Ex.: Este PL está travado há 3 meses e o cliente pediu atenção especial ao art. 5º...",
            key="contexto_input",
        )

        submitted = st.form_submit_button("Gerar resumo", use_container_width=True)

    if submitted:
        erros = []
        if not texto.strip():
            erros.append("Cole o texto do documento ou extraia de um PDF.")
        if erros:
            for e in erros:
                st.error(e)
        else:
            with st.spinner("Gerando resumo com IA..."):
                try:
                    resumo = gerar_resumo(
                        texto=texto,
                        cliente_key=cliente_key,
                        tipo_label=tipo_label,
                        tipo_key=tipo_key,
                        contexto_extra=contexto_extra,
                    )
                    st.session_state["resumo_gerado"] = resumo
                    st.session_state["cliente_selecionado"] = cliente_label
                    st.session_state["tipo_selecionado"] = tipo_label
                    st.success("Resumo gerado.")
                except Exception as e:
                    st.error(f"Erro ao gerar resumo: {e}")


# ── coluna direita: resultado ─────────────────────────────────────────────────

with col_dir:
    st.markdown('<div class="ge-rule">Resultado</div>', unsafe_allow_html=True)

    if not st.session_state["resumo_gerado"].strip():
        st.info("Preencha o formulário e clique em \"Gerar resumo\".")
    else:
        st.markdown(f"**{datetime.now().strftime('%d/%m/%Y')}**")
        st.markdown("---")

        st.code(st.session_state["resumo_gerado"], language="text")

        wa_text = (
            f"*Resumo | {st.session_state['cliente_selecionado']}*\n"
            f"{datetime.now().strftime('%d/%m/%Y')}\n\n"
            f"{st.session_state['resumo_gerado']}"
        )
        wa_url = f"https://wa.me/?text={quote(wa_text)}"
        st.markdown(
            f'<a href="{wa_url}" target="_blank">'
            f'<button style="'
            f'width:100%;'
            f'border-radius:12px;'
            f'border:1px solid rgba(255,255,255,0.14);'
            f'background:linear-gradient(90deg,#962E4D,rgba(150,46,77,0.75));'
            f'color:white;'
            f'font-weight:600;'
            f'padding:10px 14px;'
            f'cursor:pointer;'
            f'font-size:0.875rem;'
            f'">Enviar no WhatsApp</button></a>',
            unsafe_allow_html=True,
        )
