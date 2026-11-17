"""Modelo e configuração do Gemini, num lugar só para o app inteiro.

Trocar de modelo é mudar MODELO aqui. Todas as páginas importam daqui.

Nível de raciocínio (thinking_level do Gemini 3.x; quanto mais alto, mais tokens e mais demora):
- TEXTO_CURTO ("low"): texto de WhatsApp de até ~100 palavras a partir de um texto dado.
- PADRAO ("medium", o padrão do modelo): extração de dados (pesquisa, tabela, PDF por imagem),
  seleção e redação das sínteses, resumo analítico por cliente.

temperature/top_p/top_k não entram: o Gemini 3.6+ ignora e vai passar a recusar.
"""
from google.genai import types

MODELO = "gemini-3.6-flash"

TEXTO_CURTO = "low"
PADRAO = "medium"


def config(nivel: str = PADRAO, json: bool = False) -> types.GenerateContentConfig:
    """Configuração da chamada. json=True pede a resposta já em JSON (sem texto em volta)."""
    return types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=nivel),
        response_mime_type="application/json" if json else None,
    )
