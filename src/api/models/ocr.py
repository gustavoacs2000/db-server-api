from pydantic import BaseModel

class OCRRequest(BaseModel):
    """Modelo para requisições de OCR."""
    pasta_origem: str
    pasta_destino: str
    pre_processar: bool = False
    extrair_imagens: bool = False
    rasterizar: bool = False