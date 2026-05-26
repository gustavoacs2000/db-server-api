from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class IniciarGravacaoRequest(BaseModel):
    """Modelo para iniciar uma nova gravação do stream."""
    fps: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Frames por segundo da gravação (1-60)",
        example=10
    )
    qualidade: int = Field(
        default=80,
        ge=1,
        le=100,
        description="Qualidade da gravação em porcentagem (1-100)",
        example=80
    )
    brilho: int = Field(
        default=0,
        ge=-100,
        le=100,
        description="Ajuste de brilho da gravação (-100 a +100)",
        example=0
    )
    contraste: float = Field(
        default=1.0,
        ge=0.5,
        le=3.0,
        description="Ajuste de contraste da gravação (0.5 a 3.0)",
        example=1.0
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "fps": 15,
                "qualidade": 90,
                "brilho": 10,
                "contraste": 1.2
            }
        }

class GravacaoResponse(BaseModel):
    """Modelo de resposta para operações de gravação."""
    sucesso: bool = Field(
        description="Status da operação",
        example=True
    )
    mensagem: str = Field(
        description="Mensagem descritiva da operação",
        example="Gravação iniciada com sucesso"
    )
    gravacao_id: Optional[str] = Field(
        default=None,
        description="ID único da gravação",
        example="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    )
    arquivo_saida: Optional[str] = Field(
        default=None,
        description="Caminho completo do arquivo de gravação",
        example="C:\\RPA\\dados\\scripts\\db\\dist\\records\\gravacao_stream_20240315_143022_a1b2c3d4.mp4"
    )
    tempo_decorrido: Optional[str] = Field(
        default=None,
        description="Tempo decorrido da gravação (formato HH:MM:SS)",
        example="00:05:23"
    )
    status: Optional[str] = Field(
        default=None,
        description="Status atual da gravação",
        example="gravando"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "sucesso": True,
                "mensagem": "Gravação iniciada com sucesso",
                "gravacao_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "arquivo_saida": "C:\\RPA\\dados\\scripts\\db\\dist\\records\\gravacao_stream_20240315_143022_a1b2c3d4.mp4"
            }
        }

class StatusGravacaoResponse(BaseModel):
    """Modelo de resposta para status de gravação."""
    ok: bool = Field(
        description="Status da operação",
        example=True
    )
    gravacao_id: str = Field(
        description="ID da gravação",
        example="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    )
    status: str = Field(
        description="Status atual da gravação (gravando, pausada, parada)",
        example="gravando"
    )
    tempo_decorrido: str = Field(
        description="Tempo total decorrido (formato HH:MM:SS)",
        example="00:05:23"
    )
    tempo_efetivo: str = Field(
        description="Tempo efetivo de gravação, excluindo pausas (formato HH:MM:SS)",
        example="00:04:15"
    )
    arquivo_saida: str = Field(
        description="Caminho do arquivo de saída",
        example="C:\\RPA\\dados\\scripts\\db\\dist\\records\\gravacao_stream_20240315_143022_a1b2c3d4.mp4"
    )
    fps: int = Field(
        description="Frames por segundo configurados",
        example=10
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "ok": True,
                "gravacao_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "status": "gravando",
                "tempo_decorrido": "00:05:23",
                "tempo_efetivo": "00:04:15",
                "arquivo_saida": "C:\\RPA\\dados\\scripts\\db\\dist\\records\\gravacao_stream_20240315_143022_a1b2c3d4.mp4",
                "fps": 10
            }
        }

class ListarGravacoesResponse(BaseModel):
    """Modelo de resposta para listar gravações ativas."""
    sucesso: bool = Field(
        description="Status da operação",
        example=True
    )
    gravacoes_ativas: List[Dict[str, Any]] = Field(
        description="Lista de gravações ativas",
        example=[
            {
                "gravacao_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "status": "gravando",
                "tempo_decorrido": "00:05:23",
                "arquivo_saida": "gravacao_stream_20240315_143022_a1b2c3d4.mp4"
            }
        ]
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "sucesso": True,
                "gravacoes_ativas": [
                    {
                        "gravacao_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "status": "gravando",
                        "tempo_decorrido": "00:05:23",
                        "arquivo_saida": "gravacao_stream_20240315_143022_a1b2c3d4.mp4"
                    },
                    {
                        "gravacao_id": "b2c3d4e5-f6g7-8901-bcde-f23456789012",
                        "status": "pausada",
                        "tempo_decorrido": "00:02:45",
                        "arquivo_saida": "gravacao_stream_20240315_144512_b2c3d4e5.mp4"
                    }
                ]
            }
        }

class ListarGravacoesSalvasResponse(BaseModel):
    """Modelo de resposta para listar gravações salvas."""
    sucesso: bool = Field(
        description="Status da operação",
        example=True
    )
    gravacoes_salvas: List[Dict[str, Any]] = Field(
        description="Lista de arquivos de gravação salvos",
        example=[
            {
                "nome_arquivo": "gravacao_stream_20240315_143022_a1b2c3d4.mp4",
                "tamanho_mb": 125.6,
                "data_criacao": "2024-03-15 14:30:22",
                "duracao_estimada": "00:05:23"
            }
        ]
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "sucesso": True,
                "gravacoes_salvas": [
                    {
                        "nome_arquivo": "gravacao_stream_20240315_143022_a1b2c3d4.mp4",
                        "tamanho_mb": 125.6,
                        "data_criacao": "2024-03-15 14:30:22",
                        "duracao_estimada": "00:05:23"
                    },
                    {
                        "nome_arquivo": "gravacao_stream_20240315_144512_b2c3d4e5.mp4",
                        "tamanho_mb": 89.3,
                        "data_criacao": "2024-03-15 14:45:12",
                        "duracao_estimada": "00:03:45"
                    }
                ]
            }
        }

class ConfigurarStreamRequest(BaseModel):
    """Modelo para configurar o stream."""
    habilitado: bool = Field(
        description="Habilitar ou desabilitar o stream",
        example=True
    )
    token: Optional[str] = Field(
        default=None,
        description="Token de autorização (opcional)",
        example="RpaDbServerApi12345678"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "habilitado": True,
                "token": "RpaDbServerApi12345678"
            }
        }

class ConfigurarStreamResponse(BaseModel):
    """Modelo de resposta para configuração do stream."""
    ok: bool = Field(
        description="Status da operação",
        example=True
    )
    mensagem: str = Field(
        description="Mensagem descritiva da operação",
        example="Stream habilitado com sucesso"
    )
    stream_ativo: bool = Field(
        description="Status atual do stream",
        example=True
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "ok": True,
                "mensagem": "Stream habilitado com sucesso",
                "stream_ativo": True
            }
        }