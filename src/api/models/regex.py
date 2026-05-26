from pydantic import BaseModel, Field
from typing import Optional

class RegexActivatorRequest(BaseModel):
    """Modelo para requisições de carregamento de ativadores regex."""
    
    code: str = Field(
        ...,
        description="Código Python que define regex_ativadores (lista) e função extrair",
        example="regex_ativadores = [r'\\d+', r'[A-Z]{2,}']; def extrair(text): return re.findall(r'\\d+', text)"
    )
    
    contexto: Optional[str] = Field(
        default="default_regex",
        description="Nome do contexto para armazenar os ativadores regex",
        example="contexto_numeros"
    )