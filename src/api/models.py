from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class SQLRequest(BaseModel):
    """Modelo para requisições SQL."""
    sql: str = Field(
        description="Query SQL a ser executada no banco de dados",
        example="SELECT * FROM usuarios WHERE ativo = 1"
    )
    params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Parâmetros para a query SQL (para queries preparadas)",
        example={"user_id": 123, "status": "ativo"}
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "sql": "SELECT nome, email FROM usuarios WHERE departamento = :dept",
                "params": {"dept": "TI"}
            }
        }

class LogEntry(BaseModel):
    """Modelo para entradas de log."""
    status: str = Field(
        description="Status da operação (sucesso, erro, aviso, info)",
        example="sucesso"
    )
    log_texto: str = Field(
        description="Texto descritivo do log",
        example="Operação de backup concluída com sucesso"
    )
    data_criacao: Optional[datetime] = Field(
        default=None,
        description="Data e hora de criação do log (será preenchida automaticamente se não informada)",
        example="2024-01-15T10:30:00"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "info",
                "log_texto": "Processo de sincronização iniciado",
                "data_criacao": "2024-01-15T14:25:30"
            }
        }

class PythonExecutionRequest(BaseModel):
    """Modelo para requisições de execução de código Python."""
    code: str = Field(
        description="Código Python a ser executado",
        example="import datetime\nprint(f'Data atual: {datetime.datetime.now()}')"
    )
    contexto: Optional[str] = Field(
        default=None,
        description="Contexto de execução para identificar a sessão",
        example="processamento_dados"
    )
    formato_resposta: Optional[str] = Field(
        default=None,
        description="Formato da resposta (json, text, html)",
        example="json"
    )
    subprocess: bool = Field(
        default=False,
        description="Se True, executa em subprocess separado",
        example=False
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "import pandas as pd\ndf = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})\nprint(df.to_json())",
                "contexto": "analise_vendas",
                "formato_resposta": "json",
                "subprocess": False
            }
        }

class ScheduleRequest(BaseModel):
    """Modelo para requisições de agendamento."""
    code: str = Field(
        description="Código Python a ser executado no agendamento",
        example="print('Tarefa agendada executada!')"
    )
    trigger_type: str = Field(
        description="Tipo de trigger: 'date' (data específica), 'interval' (intervalo), ou 'cron' (expressão cron)",
        example="interval"
    )
    trigger_args: Dict[str, Any] = Field(
        description="Argumentos do trigger conforme o tipo escolhido",
        example={"seconds": 30}
    )
    contexto: Optional[str] = Field(
        default=None,
        description="Contexto para identificar o agendamento",
        example="backup_diario"
    )
    job_id: Optional[str] = Field(
        default=None,
        description="ID único do job (será gerado automaticamente se não informado)",
        example="job_backup_001"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "import shutil\nshutil.copy2('/origem/arquivo.txt', '/destino/arquivo.txt')",
                "trigger_type": "cron",
                "trigger_args": {"hour": 2, "minute": 0},
                "contexto": "backup_noturno",
                "job_id": "backup_daily_02h"
            }
        }

class OCRRequest(BaseModel):
    """Modelo para requisições de OCR."""
    pasta_origem: str = Field(
        description="Caminho da pasta contendo os arquivos para OCR",
        example="C:\\Documentos\\Scans"
    )
    pasta_destino: str = Field(
        description="Caminho da pasta onde salvar os resultados do OCR",
        example="C:\\Documentos\\OCR_Resultados"
    )
    pre_processar: bool = Field(
        default=False,
        description="Se True, aplica pré-processamento nas imagens para melhorar OCR",
        example=True
    )
    extrair_imagens: bool = Field(
        default=False,
        description="Se True, extrai imagens de PDFs antes do OCR",
        example=True
    )
    rasterizar: bool = Field(
        default=False,
        description="Se True, rasteriza PDFs antes do OCR",
        example=False
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "pasta_origem": "C:\\Documentos\\Faturas_Scan",
                "pasta_destino": "C:\\Documentos\\Faturas_OCR",
                "pre_processar": True,
                "extrair_imagens": True,
                "rasterizar": False
            }
        }

class BrowserOpenRequest(BaseModel):
    """Modelo para abrir navegador."""
    perfil: Optional[str] = Field(
        default=None,
        description="Caminho do perfil do navegador",
        example="C:\\RPA\\sistema\\profile"
    )
    diretorio_download: Optional[str] = Field(
        default=None,
        description="Diretório padrão para downloads",
        example="C:\\Downloads"
    )
    headless: bool = Field(
        default=False,
        description="Se True, executa o navegador em modo headless (sem interface gráfica)",
        example=False
    )
    width: int = Field(
        default=1920,
        description="Largura da janela do navegador em pixels",
        example=1920
    )
    height: int = Field(
        default=1080,
        description="Altura da janela do navegador em pixels",
        example=1080
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "perfil": "C:\\RPA\\sistema\\profile",
                "diretorio_download": "C:\\Downloads\\automacao",
                "headless": False,
                "width": 1366,
                "height": 768
            }
        }

class BrowserExecuteRequest(BaseModel):
    """Modelo para executar código no navegador."""
    code: str = Field(
        description="Código JavaScript a ser executado no navegador",
        example="document.querySelector('h1').textContent = 'Título Modificado';"
    )
    contexto: Optional[str] = Field(
        default=None,
        description="Contexto do navegador onde executar o código",
        example="automacao_principal"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "window.scrollTo(0, document.body.scrollHeight);",
                "contexto": "navegacao_web"
            }
        }

class BrowserScreenshotRequest(BaseModel):
    """Modelo para capturar screenshot."""
    caminho_arquivo: Optional[str] = Field(
        default=None,
        description="Caminho completo onde salvar o screenshot",
        example="C:\\Screenshots\\captura.png"
    )
    full_page: bool = Field(
        default=True,
        description="Se True, captura a página inteira; se False, apenas a área visível",
        example=True
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "caminho_arquivo": "C:\\Evidencias\\screenshot_001.png",
                "full_page": False
            }
        }

class BrowserPDFRequest(BaseModel):
    """Modelo para gerar PDF."""
    caminho_arquivo: Optional[str] = Field(
        default=None,
        description="Caminho completo onde salvar o PDF",
        example="C:\\PDFs\\relatorio.pdf"
    )
    format: str = Field(
        default="A4",
        description="Formato do papel (A4, A3, Letter, etc.)",
        example="A4"
    )
    landscape: bool = Field(
        default=False,
        description="Se True, gera PDF em orientação paisagem; se False, retrato",
        example=False
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "caminho_arquivo": "C:\\Relatorios\\relatorio_mensal.pdf",
                "format": "A4",
                "landscape": True
            }
        }

class BrowserDownloadRequest(BaseModel):
    """Modelo para configurar download."""
    caminho: str = Field(
        description="Caminho do diretório onde salvar os downloads",
        example="C:\\Downloads\\projeto"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "caminho": "C:\\Downloads\\documentos_importantes"
            }
        }