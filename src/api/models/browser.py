from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class BrowserOpenRequest(BaseModel):
    """Modelo para abrir uma nova instância do navegador."""
    contexto: str = Field(
        description="Nome único do contexto para identificar a instância do navegador",
        example="navegacao_principal"
    )
    chromium_path: str = Field(
        description="Caminho completo para o executável do Chrome/Chromium",
        example="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    )
    profile_path: Optional[str] = Field(
        default=None,
        description="Caminho para o diretório do perfil do usuário. Se não especificado, será criado automaticamente",
        example="C:\\RPA\\sistema\\profile"
    )
    download_dir: Optional[str] = Field(
        default=None,
        description="Diretório onde os downloads serão salvos. Se não especificado, será criado automaticamente",
        example="C:\\Downloads\\navegacao_principal"
    )
    parametros_inicializacao: Optional[str] = Field(
        default=None,
        description="Parâmetros de inicialização separados por ponto e vírgula",
        example="--kiosk;--start-fullscreen;--disable-web-security"
    )
    chrome_args: Optional[List[str]] = Field(
        default=None,
        description="Lista de argumentos do Chrome para personalizar o comportamento",
        example=["--kiosk", "--disable-extensions", "--no-sandbox"]
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "contexto": "automacao_web",
                "chromium_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "profile_path": "C:\\RPA\\sistema\\profile",
                "download_dir": "C:\\Downloads\\automacao",
                "chrome_args": ["--kiosk", "--disable-extensions"]
            }
        }

class BrowserDownloadPathRequest(BaseModel):
    """Modelo para configurar o diretório de download."""
    contexto: str = Field(
        description="Nome do contexto do navegador",
        example="navegacao_principal"
    )
    download_dir: str = Field(
        description="Novo diretório para downloads",
        example="C:\\Downloads\\novo_diretorio"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "contexto": "automacao_web",
                "download_dir": "C:\\Downloads\\documentos_importantes"
            }
        }

class BrowserExecuteRequest(BaseModel):
    """Modelo para executar código no navegador."""
    contexto: str = Field(
        description="Nome do contexto do navegador",
        example="navegacao_principal"
    )
    code: str = Field(
        description="Código JavaScript ou Python para executar no navegador",
        example="document.querySelector('input[name=\"q\"]').value = 'Pesquisa automatizada';"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "contexto": "automacao_web",
                "code": "document.title = 'Página Modificada'; console.log('Título alterado');"
            }
        }

class BrowserScreenshotRequest(BaseModel):
    """Modelo para capturar screenshots."""
    contexto: str = Field(
        description="Nome do contexto do navegador",
        example="navegacao_principal"
    )
    path: str = Field(
        description="Diretório onde salvar o screenshot",
        example="C:\\Screenshots"
    )
    filename: str = Field(
        description="Nome do arquivo (sem extensão, será adicionado .png automaticamente)",
        example="captura_pagina_inicial"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "contexto": "automacao_web",
                "path": "C:\\Screenshots\\projeto",
                "filename": "evidencia_processo_001"
            }
        }

class BrowserPDFRequest(BaseModel):
    """Modelo para gerar PDFs."""
    contexto: str = Field(
        description="Nome do contexto do navegador",
        example="navegacao_principal"
    )
    path: str = Field(
        description="Diretório onde salvar o PDF",
        example="C:\\PDFs"
    )
    filename: str = Field(
        description="Nome do arquivo (sem extensão, será adicionado .pdf automaticamente)",
        example="relatorio_completo"
    )
    pdf_options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Opções de configuração do PDF (formato, orientação, margens, etc.)",
        example={
            "format": "A4",
            "landscape": False,
            "margin": {"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"}
        }
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "contexto": "automacao_web",
                "path": "C:\\Documentos\\Relatorios",
                "filename": "relatorio_mensal_janeiro",
                "pdf_options": {
                    "format": "A4",
                    "landscape": True,
                    "printBackground": True
                }
            }
        }

class BrowserOpenTabRequest(BaseModel):
    """Modelo para abrir uma nova aba no navegador."""
    contexto: str = Field(
        description="Nome do contexto do navegador onde abrir a nova aba",
        example="navegacao_principal"
    )
    url: str = Field(
        description="URL para carregar na nova aba",
        example="https://www.google.com"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "contexto": "automacao_web",
                "url": "https://github.com"
            }
        }

class BrowserSelectTabRequest(BaseModel):
    """Modelo para selecionar uma aba específica."""
    contexto: str = Field(
        description="Nome do contexto do navegador",
        example="navegacao_principal"
    )
    indice: Optional[int] = Field(
        default=None,
        description="Índice da aba (1, 2, 3...) para seleção por posição",
        example=2
    )
    target_id: Optional[str] = Field(
        default=None,
        description="Target ID específico da aba para seleção precisa",
        example="12345-67890-ABCDE"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "contexto": "automacao_web",
                "indice": 2
            }
        }

class BrowserCloseTabRequest(BaseModel):
    """Modelo para fechar uma aba específica."""
    contexto: str = Field(
        description="Nome do contexto do navegador",
        example="navegacao_principal"
    )
    indice: Optional[int] = Field(
        default=None,
        description="Índice da aba (1, 2, 3...) para fechamento por posição",
        example=3
    )
    target_id: Optional[str] = Field(
        default=None,
        description="Target ID específico da aba para fechamento preciso",
        example="12345-67890-ABCDE"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "contexto": "automacao_web",
                "target_id": "12345-67890-ABCDE"
            }
        }

class BrowserDialogHandlerRequest(BaseModel):
    """Modelo para configurar handlers de dialog JavaScript (alert, confirm, prompt)."""
    contexto: str = Field(
        description="Nome do contexto do navegador",
        example="navegacao_principal"
    )
    auto_accept: bool = Field(
        default=True,
        description="Se deve aceitar automaticamente todos os dialogs (clica OK/Sim)",
        example=True
    )
    default_prompt_text: Optional[str] = Field(
        default="",
        description="Texto padrão para inserir em prompts JavaScript",
        example="Resposta automática"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "contexto": "automacao_web",
                "auto_accept": True,
                "default_prompt_text": "Texto padrão"
            }
        }

class BrowserCloseRequest(BaseModel):
    """Modelo para fechar uma instância do navegador."""
    contexto: str = Field(
        description="Nome do contexto do navegador a ser fechado",
        example="navegacao_principal"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "contexto": "automacao_web"
            }
        }