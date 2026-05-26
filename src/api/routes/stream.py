from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse, Response
import mss
import cv2
import numpy as np
from typing import Iterator
import threading
import time
from datetime import datetime
import os
import uuid
import pyautogui
from ...config.settings import stream_ativo
from ...config.paths import get_records_dir
from ..models.stream import (
    IniciarGravacaoRequest,
    GravacaoResponse,
    StatusGravacaoResponse,
    ListarGravacoesResponse,
    ListarGravacoesSalvasResponse,
    ConfigurarStreamResponse
)

router = APIRouter()

# Lock para sincronizar capturas de tela
mss_lock = threading.Lock()

# Thread local storage para instâncias MSS
mss_local = threading.local()

def get_mss_instance():
    """Obtém uma instância MSS thread-safe."""
    if not hasattr(mss_local, 'sct') or mss_local.sct is None:
        try:
            mss_local.sct = mss.mss()
        except (AttributeError, Exception) as e:
            # Se falhar devido a threading local ou outros problemas, tenta novamente
            time.sleep(0.1)
            try:
                mss_local.sct = mss.mss()
            except Exception as e2:
                # Se ainda falhar, força uma nova instância
                import logging
                logging.warning(f"Erro ao criar instância MSS: {e2}")
                mss_local.sct = mss.mss()
    return mss_local.sct

# Estado de uma gravação individual
class GravacaoState:
    def __init__(self, gravacao_id: str):
        self.id = gravacao_id
        self.gravando = False
        self.pausada = False
        self.writer = None
        self.arquivo_saida = None
        self.data_inicio = None
        self.data_fim = None
        self.fps = 10
        self.brilho = 0  # Ajuste de brilho (-100 a +100)
        self.contraste = 1.0  # Ajuste de contraste (0.5 a 3.0)
        self.thread_gravacao = None
        self.parar_thread = False
        self.tempo_pausado_total = 0  # Tempo total pausado em segundos
        self.data_pausa = None  # Quando foi pausado
        
    def pausar(self):
        """Marca o início de uma pausa."""
        if not self.pausada:
            self.pausada = True
            self.data_pausa = datetime.now()
    
    def retomar(self):
        """Marca o fim de uma pausa e acumula o tempo pausado."""
        if self.pausada and self.data_pausa:
            tempo_pausa = datetime.now() - self.data_pausa
            self.tempo_pausado_total += tempo_pausa.total_seconds()
            self.pausada = False
            self.data_pausa = None
    
    def get_tempo_decorrido_efetivo(self):
        """Retorna o tempo decorrido descontando as pausas."""
        if not self.data_inicio:
            return 0
        
        tempo_total = datetime.now() - self.data_inicio
        tempo_pausa_atual = 0
        
        # Se está pausado agora, calcula o tempo da pausa atual
        if self.pausada and self.data_pausa:
            tempo_pausa_atual = (datetime.now() - self.data_pausa).total_seconds()
        
        tempo_efetivo = tempo_total.total_seconds() - self.tempo_pausado_total - tempo_pausa_atual
        return max(0, int(tempo_efetivo))
        
    def reset(self):
        self.gravando = False
        self.pausada = False
        self.writer = None
        self.arquivo_saida = None
        self.data_inicio = None
        self.data_fim = None
        self.thread_gravacao = None
        self.parar_thread = False
        self.tempo_pausado_total = 0
        self.data_pausa = None

# Dicionário para múltiplas gravações simultâneas
gravacoes_ativas = {}

def ajustar_brilho_contraste(frame, brilho=0, contraste=1.0):
    """
    Ajusta brilho e contraste de um frame.
    
    Args:
        frame: Frame de vídeo (numpy array)
        brilho: Ajuste de brilho (-100 a +100)
        contraste: Ajuste de contraste (0.5 a 3.0)
    
    Returns:
        Frame ajustado
    """
    # Aplica ajuste de contraste e brilho
    # Fórmula: novo_pixel = contraste * pixel_original + brilho
    frame_ajustado = cv2.convertScaleAbs(frame, alpha=contraste, beta=brilho)
    return frame_ajustado

def gerar_frames(fps: int = 10, scale: float = 1.0) -> Iterator[bytes]:
    """Gera frames da tela para streaming com tratamento robusto de exceções."""
    try:
        while True:
            try:
                # Captura a tela com lock e instância MSS thread-safe
                with mss_lock:
                    sct = get_mss_instance()
                    monitor = sct.monitors[1]  # Monitor principal
                    screenshot = sct.grab(monitor)
                frame = np.array(screenshot)
                
                # Converte de BGRA para BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
                # Redimensiona se necessário
                if scale != 1.0:
                    width = int(frame.shape[1] * scale)
                    height = int(frame.shape[0] * scale)
                    frame = cv2.resize(frame, (width, height))
                
                # Adiciona cursor do mouse
                try:
                    # Obtém posição do cursor
                    x_real, y_real = pyautogui.position()
                    
                    # Obtém dimensões da tela e do frame
                    screen_width, screen_height = pyautogui.size()
                    frame_height, frame_width = frame.shape[:2]
                    
                    # Ajusta coordenadas se o frame foi redimensionado
                    x = int(x_real * (frame_width / screen_width))
                    y = int(y_real * (frame_height / screen_height))
                    
                    # Calcula raio do cursor baseado no tamanho do frame
                    base_size = frame_width
                    raio = int(base_size * 0.0035)
                    
                    # Desenha cursor (borda preta + ponteiro laranja)
                    cv2.circle(frame, (x, y), raio + 1, (0, 0, 0), -1)         # borda preta
                    cv2.circle(frame, (x, y), raio, (0, 140, 255), -1)         # ponteiro laranja
                except Exception:
                    # Se houver erro na captura do cursor, continua sem ele
                    pass
                
                # Salva frame em todas as gravações ativas com tratamento de erro
                try:
                    for gravacao in list(gravacoes_ativas.values()):
                        if gravacao.gravando and not gravacao.pausada and gravacao.writer:
                            gravacao.writer.write(frame)
                except Exception:
                    # Se houver erro na gravação, continua o streaming
                    pass
                
                # Codifica para JPEG
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not ret:
                    continue
                    
                frame_bytes = buffer.tobytes()
                frame_size = len(frame_bytes)
                
                # Formato MJPEG com Content-Length correto
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(frame_size).encode() + b'\r\n\r\n' + 
                       frame_bytes + b'\r\n')
                
                # Controle de FPS
                time.sleep(1.0/fps)
                
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                # Cliente desconectou - sai do loop graciosamente
                break
            except Exception as e:
                # Log do erro mas continua tentando
                print(f"[ERROR] Erro na geração de frame: {e}")
                time.sleep(0.1)  # Pequena pausa antes de tentar novamente
                continue
                
    except Exception as e:
        print(f"[ERROR] Erro crítico no streaming: {e}")
        return

def thread_gravacao(gravacao_id: str):
    """Thread dedicada para gravação de vídeo de uma gravação específica."""
    
    while (gravacao_id in gravacoes_ativas and 
           gravacoes_ativas[gravacao_id].gravando and 
           not gravacoes_ativas[gravacao_id].parar_thread):
        
        gravacao = gravacoes_ativas[gravacao_id]
        if not gravacao.pausada:
            # Captura a tela com lock e instância MSS thread-safe
            with mss_lock:
                sct = get_mss_instance()
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
            frame = np.array(screenshot)
            
            # Converte de BGRA para BGR
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            # Aplica ajustes de brilho e contraste
            frame = ajustar_brilho_contraste(frame, gravacao.brilho, gravacao.contraste)
            
            # Adiciona cursor do mouse
            try:
                # Obtém posição do cursor
                x_real, y_real = pyautogui.position()
                
                # Obtém dimensões da tela e do frame
                screen_width, screen_height = pyautogui.size()
                frame_height, frame_width = frame.shape[:2]
                
                # Ajusta coordenadas se o frame foi redimensionado
                x = int(x_real * (frame_width / screen_width))
                y = int(y_real * (frame_height / screen_height))
                
                # Calcula raio do cursor baseado no tamanho do frame
                base_size = frame_width
                raio = int(base_size * 0.0035)
                
                # Desenha cursor (borda preta + ponteiro laranja)
                cv2.circle(frame, (x, y), raio + 1, (0, 0, 0), -1)         # borda preta
                cv2.circle(frame, (x, y), raio, (0, 140, 255), -1)         # ponteiro laranja
            except Exception as e:
                # Se houver erro na captura do cursor, continua sem ele
                pass
            
            # Escreve o frame no vídeo
            if gravacao.writer:
                gravacao.writer.write(frame)
        
        # Controle de FPS
        time.sleep(1.0 / gravacao.fps)

@router.get(
    "/stream",
    summary="Stream de vídeo em tempo real",
    description="""Fornece streaming de vídeo da tela em tempo real no formato MJPEG.
    
    **Funcionalidades:**
    - Captura da tela em tempo real
    - Streaming MJPEG otimizado
    - Configuração de FPS e escala
    - Suporte a HEAD requests
    - Isolamento de erros robusto
    - Compatível com navegadores e players
    
    **Parâmetros:**
    - **fps**: Frames por segundo (1-60, padrão: 10)
    - **scale**: Escala do vídeo (0.1-2.0, padrão: 1.0)
    
    **Exemplo de uso:**
    ```bash
    curl -X GET "http://localhost:PORT/stream?fps=15&scale=0.8" \
      -H "Authorization: Bearer TOKEN"
    ```
    
    **Uso em HTML:**
    ```html
    <img src="/stream?fps=10&scale=1.0" alt="Stream da tela">
    ```
    """,
    responses={
        200: {
            "description": "Stream MJPEG iniciado com sucesso",
            "content": {
                "multipart/x-mixed-replace": {
                    "example": "--frame\r\nContent-Type: image/jpeg\r\n\r\n[JPEG DATA]\r\n"
                }
            }
        },
        400: {"description": "Streaming desativado ou parâmetros inválidos"}
    },
    tags=["Stream - Tempo Real"]
)
@router.head("/stream")
async def video_stream(request: Request, fps: int = 10, scale: float = 1.0):
    """Fornece streaming de vídeo da tela em tempo real no formato MJPEG."""
    try:
        if not stream_ativo():
            return {"erro": "Streaming desativado"}
        
        # Para requisições HEAD, retorna apenas headers
        if request.method == "HEAD":
            return Response(
                headers={
                    'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
        
        # Wrapper para isolamento do streaming
        def isolated_stream_generator():
            try:
                yield from gerar_frames(fps, scale)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                # Cliente desconectou - termina graciosamente
                print("[INFO] Cliente desconectou do streaming")
                return
            except Exception as e:
                print(f"[ERROR] Erro isolado no streaming: {e}")
                # Retorna um frame de erro em vez de quebrar a API
                error_frame = b'--frame\r\nContent-Type: text/plain\r\n\r\nErro no streaming\r\n'
                yield error_frame
                return
        
        return StreamingResponse(
            isolated_stream_generator(),
            media_type='multipart/x-mixed-replace; boundary=frame'
        )
        
    except Exception as e:
        print(f"[ERROR] Erro crítico no endpoint de streaming: {e}")
        # Retorna erro HTTP em vez de quebrar a aplicação
        raise HTTPException(status_code=500, detail="Erro interno no streaming")

@router.get(
    "/tela",
    summary="Interface web do stream",
    description="""Fornece uma interface web completa para visualização e controle do streaming.
    
    **Funcionalidades:**
    - Interface Bootstrap responsiva
    - Visualização do stream em tempo real
    - Controles de gravação integrados
    - Gerenciamento de gravações ativas
    - Lista de gravações salvas
    - Configurações de qualidade e FPS
    - Modo fullscreen
    - Atualização automática de status
    
    **Recursos da interface:**
    - Stream de vídeo MJPEG em tempo real
    - Botões para iniciar/pausar/parar gravações
    - Configuração de parâmetros (FPS, qualidade, brilho, contraste)
    - Lista dinâmica de gravações ativas
    - Reprodução de gravações salvas
    - Design moderno e intuitivo
    
    **Exemplo de uso:**
    ```bash
    curl -X GET "http://localhost:PORT/tela" \
      -H "Authorization: Bearer TOKEN"
    ```
    
    **Acesso direto:**
    Abra no navegador: `http://localhost:PORT/tela`
    """,
    responses={
        200: {
            "description": "Interface web carregada com sucesso",
            "content": {
                "text/html": {
                    "example": "<html>Interface completa do sistema de streaming...</html>"
                }
            }
        },
        503: {"description": "Streaming desativado"}
    },
    tags=["Stream - Interface"]
)
async def pagina_stream():
    """Fornece uma interface web completa para visualização e controle do streaming."""
    if not stream_ativo():
        return HTMLResponse(content="<h1>Streaming desativado</h1>")
    
    html_content = """
    <html>
        <head>
            <title>Stream da Tela - Sistema de Gravação</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <!-- Bootstrap CSS -->
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <!-- Bootstrap Icons -->
            <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
            <style>
                :root {
                    --bg-primary: #0a0a0a;
                    --bg-secondary: #1a1a1a;
                    --border-color: #333;
                    --text-primary: #ffffff;
                    --text-secondary: #cccccc;
                    --accent-color: #007bff;
                    --success-color: #28a745;
                    --danger-color: #dc3545;
                    --warning-color: #ffc107;
                }
                
                body { 
                    background: var(--bg-primary);
                    color: var(--text-primary);
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    font-size: 0.875rem;
                    overflow: auto;
                    cursor: auto;
                }
                
                .main-container {
                    height: 100vh;
                    background: var(--bg-primary);
                }
                
                .sidebar {
                    background: var(--bg-secondary);
                    border-right: 1px solid var(--border-color);
                    height: 100vh;
                    overflow-y: auto;
                }
                
                .content-area {
                    background: var(--bg-primary);
                    height: 100vh;
                    display: flex;
                    flex-direction: column;
                }
                
                .controls-section {
                    background: var(--bg-secondary);
                    border-bottom: 1px solid var(--border-color);
                    padding: 1rem;
                }
                
                .stream-section {
                    flex: 1;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 1rem;
                    background: var(--bg-primary);
                }
                
                .stream-video {
                    max-width: 100%;
                    max-height: 100%;
                    border-radius: 8px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.8);
                    border: 1px solid var(--border-color);
                }
                
                .section-title {
                    color: var(--text-primary);
                    font-size: 0.9rem;
                    font-weight: 600;
                    margin-bottom: 0.75rem;
                    padding-bottom: 0.5rem;
                    border-bottom: 1px solid var(--border-color);
                }
                
                .btn-custom {
                    font-size: 0.8rem;
                    padding: 0.375rem 0.75rem;
                    border-radius: 6px;
                    border: none;
                    transition: all 0.2s ease;
                }
                
                .btn-record {
                    background: var(--danger-color);
                    color: white;
                }
                
                .btn-record:hover {
                    background: #c82333;
                    transform: translateY(-1px);
                }
                
                .btn-primary-custom {
                    background: var(--accent-color);
                    color: white;
                }
                
                .btn-primary-custom:hover {
                    background: #0056b3;
                    transform: translateY(-1px);
                }
                
                .form-control-sm-custom {
                    background: var(--bg-primary);
                    border: 1px solid var(--border-color);
                    color: var(--text-primary);
                    font-size: 0.8rem;
                    padding: 0.25rem 0.5rem;
                }
                
                .form-control-sm-custom:focus {
                    background: var(--bg-primary);
                    border-color: var(--accent-color);
                    color: var(--text-primary);
                    box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
                }
                
                .form-label-sm {
                    font-size: 0.75rem;
                    color: var(--text-secondary);
                    margin-bottom: 0.25rem;
                }
                
                /* Estilos customizados para gravações */
                .empty-state {
                    text-align: center;
                    color: var(--text-secondary);
                    font-size: 0.9rem;
                    padding: 2rem 1rem;
                    font-style: italic;
                }
                
                /* Responsividade */
                @media (max-width: 768px) {
                    .sidebar {
                        position: fixed;
                        top: 0;
                        left: -100%;
                        width: 280px;
                        z-index: 1050;
                        transition: left 0.3s ease;
                    }
                    
                    .sidebar.show {
                        left: 0;
                    }
                    
                    .content-area {
                        margin-left: 0;
                    }
                    
                    .mobile-toggle {
                        display: block !important;
                    }
                }
                
                @media (min-width: 769px) {
                    .mobile-toggle {
                        display: none !important;
                    }
                }
                
                .mobile-toggle {
                    position: fixed;
                    top: 1rem;
                    left: 1rem;
                    z-index: 1060;
                    background: var(--bg-secondary);
                    border: 1px solid var(--border-color);
                    color: var(--text-primary);
                    border-radius: 6px;
                    padding: 0.5rem;
                }
                
                .resize-handle {
                    position: absolute;
                    top: 0;
                    right: 0;
                    width: 4px;
                    height: 100%;
                    background: #333;
                    cursor: ew-resize;
                    transition: background 0.2s;
                    z-index: 1000;
                }
                .resize-handle:hover {
                    background: #4CAF50;
                }
                .resizing {
                    user-select: none;
                    pointer-events: none;
                }
                
                .sidebar {
                    user-select: none;
                }
                
                .controls-section {
                    user-select: none;
                }
                .fullscreen-btn {
                    background: #333;
                    border: 1px solid #555;
                    color: white;
                    padding: 6px 10px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 11px;
                    transition: all 0.2s;
                    width: auto;
                    margin: 0;
                }
                .fullscreen-btn:hover {
                    background: #4CAF50;
                    border-color: #4CAF50;
                }
                .controls-header {
                    background: #2a2a2a;
                    padding: 12px;
                    border-bottom: 1px solid #333;
                    border-radius: 8px 8px 0 0;
                }
                .controls-row {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    margin-bottom: 8px;
                }
                .controls-row:last-child {
                    margin-bottom: 0;
                }
                .control-group {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                }
                .control-group label {
                    font-size: 10px;
                    color: #ccc;
                    white-space: nowrap;
                    margin: 0;
                    text-transform: none;
                    letter-spacing: normal;
                }
                .control-group input {
                    width: 50px;
                    padding: 4px 6px;
                    background: #333;
                    border: 1px solid #555;
                    border-radius: 4px;
                    color: #fff;
                    font-size: 11px;
                    margin: 0;
                }
                .control-group button {
                    width: auto;
                    padding: 6px 10px;
                    margin: 0;
                    font-size: 11px;
                }
                .panel-title {
                    color: #4CAF50;
                    margin: 0 0 15px 0;
                    font-size: 14px;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    border-bottom: 1px solid #333;
                    padding-bottom: 8px;
                }
                .controls-section {
                    background: #252525;
                    padding: 12px;
                    border-radius: 6px;
                    margin-bottom: 10px;
                    border: 1px solid #333;
                }
                .section-title {
                    color: #81C784;
                    margin: 0 0 10px 0;
                    font-size: 12px;
                    font-weight: 500;
                }
                .form-group {
                    margin-bottom: 12px;
                }
                label {
                    display: block;
                    margin-bottom: 4px;
                    color: #ccc;
                    font-weight: 400;
                    font-size: 11px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                input {
                    width: 100%;
                    padding: 8px;
                    border: 1px solid #444;
                    border-radius: 3px;
                    background: #0a0a0a;
                    color: white;
                    font-size: 12px;
                    transition: border-color 0.2s;
                }
                input:focus {
                    outline: none;
                    border-color: #4CAF50;
                }
                button {
                    width: 100%;
                    padding: 8px;
                    border: 1px solid #444;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: all 0.2s;
                    margin-bottom: 6px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                .btn-primary { background: #4CAF50; color: white; border-color: #4CAF50; }
                .btn-primary:hover { background: #45a049; border-color: #45a049; }
                .btn-record { background: #f44336; color: white; border-color: #f44336; }
                .btn-record:hover { background: #da190b; border-color: #da190b; }
                .btn-pause { background: #ff9800; color: white; border-color: #ff9800; }
                .btn-pause:hover { background: #e68900; border-color: #e68900; }
                .btn-resume { background: #2196F3; color: white; border-color: #2196F3; }
                .btn-resume:hover { background: #1976D2; border-color: #1976D2; }
                .btn-stop { background: #666; color: white; border-color: #666; }
                .btn-stop:hover { background: #555; border-color: #555; }
                .btn-test { background: #ff9800; color: white; border-color: #ff9800; }
                .btn-test:hover { background: #e68900; border-color: #e68900; }
                .btn-small {
                    width: auto;
                    padding: 4px 8px;
                    margin: 1px;
                    font-size: 10px;
                }
                .gravacoes-section {
                    flex: 1;
                    overflow: hidden;
                }

                .gravacao-item {
                    background: #1a1a1a;
                    margin: 6px 0;
                    padding: 10px;
                    border-radius: 6px;
                    border-left: 3px solid #4CAF50;
                    transition: all 0.3s;
                }
                .gravacao-item:hover {
                    background: #252525;
                    transform: translateX(3px);
                }
                .gravacao-pausada { border-left-color: #ff9800; }
                .gravacao-salva { border-left-color: #2196F3; }
                .gravacao-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 6px;
                }
                .gravacao-nome {
                    font-weight: 500;
                    color: #4CAF50;
                    font-size: 11px;
                }
                .gravacao-status {
                    padding: 2px 6px;
                    border-radius: 10px;
                    font-size: 9px;
                    font-weight: 600;
                    text-transform: uppercase;
                }
                .status-gravando { background: #f44336; }
                .status-pausada { background: #ff9800; }
                .status-salva { background: #2196F3; }
                
                /* Cores do ícone do relógio */
                .relogio-gravando { color: #4CAF50 !important; }
                .relogio-pausado { color: #ff9800 !important; }
                .gravacao-info {
                    font-size: 10px;
                    color: #aaa;
                    margin-bottom: 8px;
                }
                .tempo-info {
                    display: flex;
                    align-items: center;
                    margin-bottom: 2px;
                    font-size: 9px;
                }
                .tempo-efetivo {
                    color: #4CAF50;
                    font-weight: bold;
                }
                .tempo-total {
                    color: #2196F3;
                }
                .tempo-pausado {
                    color: #ff9800;
                }
                .fps-info {
                    color: #9C27B0;
                    margin-top: 4px;
                }
                .gravacao-controls {
                    display: flex;
                    gap: 4px;
                    flex-wrap: wrap;
                }
                .empty-state {
                    text-align: center;
                    padding: 40px 20px;
                    color: #666;
                }
                .empty-state i {
                    font-size: 48px;
                    margin-bottom: 15px;
                    display: block;
                }
                .stream-controls {
                    display: flex;
                    gap: 10px;
                    margin-top: 15px;
                    flex-wrap: wrap;
                }
                .stream-controls input {
                    width: auto;
                    min-width: 80px;
                }
                .stream-controls button {
                    width: auto;
                    padding: 8px 16px;
                }
                @media (max-width: 1200px) {
                    .main-container {
                        flex-direction: column;
                        height: auto;
                    }
                    .left-panel {
                        max-width: none;
                        min-width: auto;
                    }
                    .stream-video {
                        max-height: 50vh;
                    }
                }
            </style>
        </head>
        <body>
            <!-- Container para notificações Bootstrap -->
            <div id="alert-container" style="position: fixed; top: 20px; right: 20px; z-index: 9999; max-width: 400px;"></div>
            
            <!-- Botão toggle para mobile -->
            <button class="mobile-toggle d-md-none" type="button" onclick="toggleSidebar()">
                <i class="bi bi-list"></i>
            </button>
            
            <div class="container-fluid main-container">
                <div class="row h-100">
                    <!-- Sidebar Esquerda -->
                    <div class="col-md-3 col-lg-3 sidebar p-0" id="sidebar" style="position: relative;">
                        <!-- Divisor de redimensionamento -->
                        <div class="resize-handle" id="resize-handle"></div>
                        <div class="p-3">
                            <!-- Seção Gravações Ativas -->
                            <div class="mb-4">
                                <h6 class="section-title">
                                    <i class="bi bi-record-circle text-danger me-2"></i>
                                    Gravações Ativas
                                </h6>
                                <div id="gravacoes-ativas-container"></div>
                            </div>
                            
                            <!-- Seção Gravações Salvas -->
                            <div>
                                <h6 class="section-title">
                                    <i class="bi bi-save text-success me-2"></i>
                                    Gravações Salvas
                                </h6>
                                <div id="gravacoes-salvas-container"></div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Área Principal -->
                    <div class="col-md-9 col-lg-9 content-area p-0">
                        <!-- Seção de Controles -->
                        <div class="controls-section">
                            <!-- Primeira linha de controles -->
                            <div class="row g-2 mb-3">
                                <div class="col-6 col-md-2">
                                    <label class="form-label-sm">FPS Gravação:</label>
                                    <input type="number" class="form-control form-control-sm-custom" id="record-fps" value="10" min="1" max="30">
                                </div>
                                <div class="col-6 col-md-2">
                                    <label class="form-label-sm">Qualidade:</label>
                                    <input type="number" class="form-control form-control-sm-custom" id="record-quality" value="80" min="1" max="100">
                                </div>
                                <div class="col-6 col-md-2">
                                    <label class="form-label-sm">Brilho:</label>
                                    <input type="number" class="form-control form-control-sm-custom" id="record-brightness" value="0" min="-100" max="100" title="Ajuste de brilho (-100 a +100)">
                                </div>
                                <div class="col-6 col-md-2">
                                    <label class="form-label-sm">Contraste:</label>
                                    <input type="number" class="form-control form-control-sm-custom" id="record-contrast" value="1.0" min="0.5" max="3.0" step="0.1" title="Ajuste de contraste (0.5 a 3.0)">
                                </div>
                                <div class="col-12 col-md-4 d-flex align-items-end">
                                    <button class="btn btn-custom btn-record me-2" onclick="iniciarGravacao()">
                                        <i class="bi bi-record-circle me-1"></i>Iniciar
                                    </button>
                                </div>
                            </div>
                            
                            <!-- Segunda linha de controles -->
                            <div class="row g-2">
                                <div class="col-6 col-md-2">
                                    <label class="form-label-sm">FPS Stream:</label>
                                    <input type="number" class="form-control form-control-sm-custom" id="fps" value="10" min="1" max="30">
                                </div>
                                <div class="col-6 col-md-2">
                                    <label class="form-label-sm">Escala:</label>
                                    <input type="number" class="form-control form-control-sm-custom" id="scale" value="1.0" min="0.1" max="2.0" step="0.1">
                                </div>
                                <div class="col-12 col-md-8 d-flex align-items-end gap-2">
                                    <button class="btn btn-custom btn-primary-custom" onclick="updateStream()">
                                        <i class="bi bi-arrow-clockwise me-1"></i>Atualizar
                                    </button>
                                    <button class="btn btn-custom btn-primary-custom" onclick="atualizarTudo()">
                                        <i class="bi bi-arrow-repeat me-1"></i>Recarregar
                                    </button>
                                    <button class="btn btn-custom btn-primary-custom" onclick="toggleFullscreen()">
                                        <i class="bi bi-fullscreen me-1"></i>Tela Cheia
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Seção do Stream -->
                        <div class="stream-section" id="stream-container">
                            <img id="stream" class="stream-video" src="/stream?fps=10&scale=1.0" alt="Stream da tela">
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Bootstrap JS -->
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
            
            <script>
                // Sistema de notificações Bootstrap
                function mostrarNotificacao(tipo, titulo, mensagem, duracao = 5000) {
                    const alertContainer = document.getElementById('alert-container');
                    const alertId = 'alert-' + Date.now();
                    
                    const alertHtml = `
                        <div id="${alertId}" class="alert alert-${tipo} alert-dismissible fade show" role="alert">
                            <strong>${titulo}</strong> ${mensagem}
                            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                        </div>
                    `;
                    
                    alertContainer.insertAdjacentHTML('beforeend', alertHtml);
                    
                    // Auto-remover após a duração especificada
                    if (duracao > 0) {
                        setTimeout(() => {
                            const alertElement = document.getElementById(alertId);
                            if (alertElement) {
                                alertElement.remove();
                            }
                        }, duracao);
                    }
                }
                
                // Função para toggle do sidebar em mobile
                function toggleSidebar() {
                    const sidebar = document.getElementById('sidebar');
                    sidebar.classList.toggle('show');
                }
                
                // Fechar sidebar ao clicar fora (mobile)
                document.addEventListener('click', function(event) {
                    const sidebar = document.getElementById('sidebar');
                    const toggleBtn = document.querySelector('.mobile-toggle');
                    
                    if (window.innerWidth <= 768 && 
                        !sidebar.contains(event.target) && 
                        !toggleBtn.contains(event.target) && 
                        sidebar.classList.contains('show')) {
                        sidebar.classList.remove('show');
                    }
                });
                
                // Função para atualizar tudo
                function atualizarTudo() {
                    atualizarGravacoes();
                    carregarGravacoesSalvas();
                }
                
                // Função para carregar gravações salvas
                async function carregarGravacoesSalvas() {
                    console.log('🔄 Iniciando carregamento de gravações salvas...');
                    try {
                        const response = await fetch('/listar_gravacoes_salvas');
                        
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                        }
                        
                        const data = await response.json();
                        console.log('📊 Dados recebidos:', data);
                        
                        const container = document.getElementById('gravacoes-salvas-container');
                        if (!container) {
                            console.error('❌ Container gravacoes-salvas-container não encontrado!');
                            return;
                        }
                        
                        if (!data.gravacoes_salvas || data.gravacoes_salvas.length === 0) {
                            container.innerHTML = `
                                <div class="empty-state">
                                    <i class="bi bi-save" style="font-size: 2rem;"></i>
                                    <p>Nenhuma gravação salva</p>
                                </div>
                            `;
                            return;
                        }
                        
                        // Ordenar gravações por data (mais nova primeiro)
                        const gravacoesSorted = data.gravacoes_salvas.sort((a, b) => {
                            return new Date(b.data_criacao || 0) - new Date(a.data_criacao || 0);
                        });
                        
                        let html = '';
                        gravacoesSorted.forEach((gravacao) => {
                            const nomeArquivo = gravacao.nome_arquivo || 'Nome não disponível';
                            const tamanhoMB = gravacao.tamanho_mb || '0';
                            const dataFormatada = gravacao.data_criacao_formatada || 'Data não disponível';
                            const duracaoFormatada = gravacao.duracao_formatada || '00:00:00';
                            
                            html += `
                                <div class="gravacao-item">
                                    <div class="d-flex justify-content-between align-items-start mb-2">
                                        <div class="gravacao-nome flex-grow-1 me-2">${nomeArquivo}</div>
                                        <span class="gravacao-status status-salva">SALVA</span>
                                    </div>
                                    <div class="gravacao-info mb-2">
                                        <i class="bi bi-hdd me-1"></i>${tamanhoMB} MB
                                        <i class="bi bi-clock ms-2 me-1"></i>${duracaoFormatada}
                                        <i class="bi bi-calendar3 ms-2 me-1"></i>${dataFormatada}
                                    </div>
                                    <div class="d-flex gap-1 flex-wrap">
                                        <button class="btn btn-sm btn-sm-custom btn-primary-custom" onclick="baixarVideo('${nomeArquivo}')">
                                            <i class="bi bi-download"></i>
                                        </button>
                                    </div>
                                </div>
                            `;
                        });
                        
                        container.innerHTML = html;
                        console.log('✅ Gravações salvas carregadas com sucesso!');
                        
                    } catch (error) {
                        console.error('❌ Erro ao carregar gravações salvas:', error);
                        const container = document.getElementById('gravacoes-salvas-container');
                        if (container) {
                            container.innerHTML = `
                                <div class="empty-state">
                                    <i class="bi bi-exclamation-triangle text-warning" style="font-size: 2rem;"></i>
                                    <p>Erro ao carregar gravações salvas</p>
                                    <small class="text-muted">${error.message}</small>
                                </div>
                            `;
                        }
                    }
                }
                

                
                // Função para baixar vídeo
                function baixarVideo(nomeArquivo) {
                    console.log('Baixando vídeo:', nomeArquivo);
                    const url = `/download_gravacao/${encodeURIComponent(nomeArquivo)}`;
                    console.log('URL de download:', url);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = nomeArquivo;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                }
                
                // Função para renomear vídeo

                function updateStream() {
                    const fps = document.getElementById('fps').value;
                    const scale = document.getElementById('scale').value;
                    document.getElementById('stream').src = `/stream?fps=${fps}&scale=${scale}`;
                }
                
                async function iniciarGravacao() {
                    const fps = document.getElementById('record-fps').value;
                    const qualidade = document.getElementById('record-quality').value;
                    const brilho = document.getElementById('record-brightness').value;
                    const contraste = document.getElementById('record-contrast').value;
                    
                    try {
                        const response = await fetch('/iniciar_gravacao', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ 
                                fps: parseInt(fps), 
                                qualidade: parseInt(qualidade),
                                brilho: parseInt(brilho),
                                contraste: parseFloat(contraste)
                            })
                        });
                        
                        const result = await response.json();
                        if (result.sucesso) {
                            mostrarNotificacao('success', 'Gravação Iniciada!', `ID: ${result.gravacao_id}`);
                            // Atualizar automaticamente a lista de gravações ativas
                            atualizarGravacoes();
                        } else {
                            mostrarNotificacao('danger', 'Erro!', result.erro);
                        }
                    } catch (error) {
                        mostrarNotificacao('danger', 'Erro!', `Falha ao iniciar gravação: ${error.message}`);
                    }
                }
                
                async function pausarGravacao(gravacaoId) {
                    try {
                        const response = await fetch(`/pausar_gravacao/${gravacaoId}`, { method: 'POST' });
                        const result = await response.json();
                        
                        if (result.sucesso) {
                            mostrarNotificacao('warning', 'Gravação Pausada!', 'A gravação foi pausada com sucesso.');
                            atualizarGravacoes();
                        } else {
                            mostrarNotificacao('danger', 'Erro!', result.erro);
                        }
                    } catch (error) {
                        console.error('Erro ao pausar:', error);
                        mostrarNotificacao('danger', 'Erro!', `Falha ao pausar gravação: ${error.message}`);
                    }
                }
                
                async function retomarGravacao(gravacaoId) {
                    try {
                        const response = await fetch(`/retomar_gravacao/${gravacaoId}`, { method: 'POST' });
                        const result = await response.json();
                        
                        if (result.sucesso) {
                            mostrarNotificacao('info', 'Gravação Retomada!', 'A gravação foi retomada com sucesso.');
                            atualizarGravacoes();
                        } else {
                            mostrarNotificacao('danger', 'Erro!', result.erro);
                        }
                    } catch (error) {
                        console.error('Erro ao retomar:', error);
                        mostrarNotificacao('danger', 'Erro!', `Falha ao retomar gravação: ${error.message}`);
                    }
                }
                
                function pararGravacao(gravacaoId) {
                    console.log('=== FUNÇÃO PARAR GRAVAÇÃO CHAMADA ===');
                    console.log('ID da gravação:', gravacaoId);
                    
                    // Confirmar se quer continuar
                    if (!confirm('Tem certeza que deseja parar esta gravação?')) {
                        console.log('Operação cancelada pelo usuário');
                        return false;
                    }
                    
                    console.log('Fazendo requisição para:', `/parar_gravacao/${gravacaoId}`);
                    
                    // Usar fetch simples
                    fetch(`/parar_gravacao/${gravacaoId}`, { 
                        method: 'POST' 
                    })
                    .then(response => {
                        console.log('Status da resposta:', response.status);
                        return response.json();
                    })
                    .then(result => {
                        console.log('Resultado da API:', result);
                        if (result.sucesso) {
                            mostrarNotificacao('success', 'Gravação Finalizada!', 'A gravação foi parada e salva com sucesso.');
                            atualizarGravacoes();
                        } else {
                            mostrarNotificacao('danger', 'Erro!', result.erro);
                        }
                    })
                    .catch(error => {
                        console.error('Erro na requisição:', error);
                        mostrarNotificacao('danger', 'Erro!', `Falha ao parar gravação: ${error.message}`);
                    });
                    
                    return false;
                }
                
                // Função de teste adicional
                function testarBotao() {
                    mostrarNotificacao('info', 'Teste!', 'Teste de clique funcionando!');
                    console.log('Teste de clique executado');
                }
                
                async function atualizarGravacoes() {
                    try {
                        const response = await fetch('/listar_gravacoes');
                        const result = await response.json();
                        
                        const container = document.getElementById('gravacoes-ativas-container');
                        
                        // Verificar se há erro na resposta
                        if (result.erro) {
                            console.error('Erro da API:', result.erro);
                            container.innerHTML = `
                                <div class="empty-state">
                                    <i class="bi bi-exclamation-triangle text-warning" style="font-size: 2rem;"></i>
                                    <p>Erro ao carregar gravações</p>
                                    <small class="text-muted">${result.erro}</small>
                                </div>
                            `;
                            return;
                        }
                        
                        // Verificar se não há gravações ativas
                        if (!result.gravacoes_ativas || result.gravacoes_ativas.length === 0) {
                            container.innerHTML = `
                                <div class="empty-state">
                                    <i class="bi bi-camera-video" style="font-size: 2rem;"></i>
                                    <p>Nenhuma gravação ativa</p>
                                </div>
                            `;
                            return;
                        }
                        
                        // Ordenar gravações por data (mais nova primeiro)
                        const gravacoesSorted = result.gravacoes_ativas.sort((a, b) => {
                            return new Date(b.data_inicio || 0) - new Date(a.data_inicio || 0);
                        });
                        
                        let html = '';
                        gravacoesSorted.forEach(gravacao => {
                            const statusText = gravacao.pausada ? 'PAUSADA' : 'GRAVANDO';
                            const pauseResumeBtn = gravacao.pausada 
                                ? `<button class="btn btn-sm btn-sm-custom btn-primary-custom" data-action="retomar" data-id="${gravacao.gravacao_id}">
                                     <i class="bi bi-play-fill"></i>
                                   </button>`
                                : `<button class="btn btn-sm btn-sm-custom btn-primary-custom" data-action="pausar" data-id="${gravacao.gravacao_id}">
                                     <i class="bi bi-pause-fill"></i>
                                   </button>`;
                            
                            // Corrigir nome do arquivo (remover undefined)
                            const nomeArquivo = gravacao.arquivo && gravacao.arquivo !== 'undefined' ? 
                                gravacao.arquivo : 
                                `gravacao_${new Date().toISOString().slice(0,19).replace(/[T:]/g, '_')}.mp4`;
                            
                            html += `
                                <div class="gravacao-item">
                                    <div class="d-flex justify-content-between align-items-start mb-2">
                                        <div class="gravacao-nome flex-grow-1 me-2">${nomeArquivo}</div>
                                        <span class="gravacao-status ${gravacao.pausada ? 'status-pausada' : 'status-gravando'}">
                                            ${statusText}
                                        </span>
                                    </div>
                                    <div class="gravacao-info mb-2">
                                        <div class="tempo-info">
                                            <i class="bi bi-stopwatch me-1 ${gravacao.pausada ? 'relogio-pausado' : 'relogio-gravando'}"></i>
                                            <span class="tempo-efetivo">Efetivo: ${gravacao.tempo_decorrido_formatado || '00:00:00'}</span>
                                        </div>
                                        <div class="tempo-info">
                                            <i class="bi bi-clock me-1"></i>
                                            <span class="tempo-total">Total: ${gravacao.tempo_total_formatado || '00:00:00'}</span>
                                        </div>
                                        ${gravacao.tempo_pausado_total > 0 ? `
                                        <div class="tempo-info">
                                            <i class="bi bi-pause-circle me-1"></i>
                                            <span class="tempo-pausado">Pausado: ${gravacao.tempo_pausado_formatado || '00:00:00'}</span>
                                        </div>
                                        ` : ''}
                                        <div class="fps-info">
                                            <i class="bi bi-camera-video me-1"></i>${gravacao.fps} FPS
                                        </div>
                                    </div>
                                    <div class="d-flex gap-1 flex-wrap">
                                        ${pauseResumeBtn}
                                        <button class="btn btn-sm btn-sm-custom btn-danger" data-action="parar" data-id="${gravacao.gravacao_id}">
                                            <i class="bi bi-stop-fill"></i>
                                        </button>
                                        <button class="btn btn-sm btn-sm-custom" style="background-color: orange; color: white;" onclick="testarBotao(); return false;">
                                            <i class="bi bi-bug"></i>
                                        </button>
                                    </div>
                                </div>
                            `;
                        });
                        
                        container.innerHTML = html;
                        
                        // Adicionar event listeners para os botões
                        container.querySelectorAll('button[data-action]').forEach(button => {
                            button.addEventListener('click', function(e) {
                                e.preventDefault();
                                const action = this.getAttribute('data-action');
                                const id = this.getAttribute('data-id');
                                
                                if (action === 'pausar') {
                                    pausarGravacao(id);
                                } else if (action === 'retomar') {
                                    retomarGravacao(id);
                                } else if (action === 'parar') {
                                    pararGravacao(id);
                                }
                                
                                return false;
                            });
                        });
                        
                    } catch (error) {
                        console.error('Erro ao carregar gravações:', error);
                        document.getElementById('gravacoes-ativas-container').innerHTML = `
                            <div class="empty-state">
                                <i class="bi bi-exclamation-triangle text-warning" style="font-size: 2rem;"></i>
                                <p>Erro ao carregar gravações ativas</p>
                            </div>
                        `;
                    }
                }
                
                // Manter compatibilidade com função antiga
                const atualizarListaGravacoes = atualizarGravacoes;
                
                // Funcionalidade de redimensionamento da sidebar
                function initResizers() {
                    const resizeHandle = document.getElementById('resize-handle');
                    const sidebar = document.getElementById('sidebar');
                    const contentArea = document.querySelector('.content-area');
                    
                    if (!resizeHandle || !sidebar || !contentArea) {
                        console.log('Elementos de redimensionamento não encontrados');
                        return;
                    }
                    
                    let isResizing = false;
                    let startX = 0;
                    let startWidth = 0;
                    
                    resizeHandle.addEventListener('mousedown', (e) => {
                        isResizing = true;
                        startX = e.clientX;
                        startWidth = sidebar.offsetWidth;
                        
                        document.body.classList.add('resizing');
                        document.addEventListener('mousemove', handleResize);
                        document.addEventListener('mouseup', stopResize);
                        e.preventDefault();
                    });
                    
                    function handleResize(e) {
                        if (!isResizing) return;
                        
                        const deltaX = e.clientX - startX;
                        const newWidth = startWidth + deltaX;
                        const containerWidth = document.querySelector('.main-container').offsetWidth;
                        const minWidth = 200; // Largura mínima em pixels
                        const maxWidth = containerWidth * 0.6; // Máximo 60% da tela
                        
                        if (newWidth >= minWidth && newWidth <= maxWidth) {
                            const widthPercent = (newWidth / containerWidth) * 100;
                            sidebar.style.width = widthPercent + '%';
                            sidebar.style.flex = 'none';
                            
                            // Ajustar área de conteúdo
                            const remainingWidth = 100 - widthPercent;
                            contentArea.style.width = remainingWidth + '%';
                            contentArea.style.flex = 'none';
                        }
                    }
                    
                    function stopResize() {
                        isResizing = false;
                        document.body.classList.remove('resizing');
                        document.removeEventListener('mousemove', handleResize);
                        document.removeEventListener('mouseup', stopResize);
                    }
                    
                    console.log('Sistema de redimensionamento da sidebar inicializado');
                }
                
                // Funcionalidade de fullscreen - abre nova janela
                let fullscreenWindow = null;
                
                function toggleFullscreen() {
                    if (fullscreenWindow && !fullscreenWindow.closed) {
                        // Se a janela já está aberta, fecha ela
                        fullscreenWindow.close();
                        fullscreenWindow = null;
                        console.log('Fechando janela de fullscreen');
                        return;
                    }
                    
                    // Abre nova janela com o stream
                    const streamUrl = window.location.origin + '/stream_fullscreen';
                    fullscreenWindow = window.open(
                        streamUrl,
                        'fullscreen_stream',
                        'width=' + screen.width + ',height=' + screen.height + ',fullscreen=yes,resizable=yes,scrollbars=no,menubar=no,toolbar=no,location=no,status=no'
                    );
                    
                    if (fullscreenWindow) {
                        console.log('Abrindo janela de fullscreen');
                        
                        // Monitora se a janela foi fechada
                        const checkClosed = setInterval(() => {
                            if (fullscreenWindow.closed) {
                                fullscreenWindow = null;
                                clearInterval(checkClosed);
                                console.log('Janela de fullscreen foi fechada');
                            }
                        }, 1000);
                        
                        // Tenta colocar em fullscreen após carregar
                        fullscreenWindow.addEventListener('load', () => {
                            try {
                                fullscreenWindow.document.documentElement.requestFullscreen();
                            } catch (err) {
                                console.log('Não foi possível entrar em fullscreen automaticamente:', err);
                            }
                        });
                    } else {
                        mostrarNotificacao('warning', 'Fullscreen Bloqueado!', 'Não foi possível abrir a janela de fullscreen. Verifique se pop-ups estão bloqueados.');
                    }
                }
                
                // Função para atualizar tudo
                function atualizarTudo() {
                    updateStream();
                    atualizarGravacoes();
                    carregarGravacoesSalvas();
                }
                
                // Inicializar interface quando a página carregar
                document.addEventListener('DOMContentLoaded', function() {
                    // Inicializar redimensionadores
                    initResizers();
                    
                    // Carregar ambas as listas
                    atualizarGravacoes();
                    carregarGravacoesSalvas();
                });
                
                // Atualizar gravações ativas a cada 3 segundos
                setInterval(atualizarGravacoes, 3000);
                
                // Atualizar gravações salvas a cada 10 segundos
                setInterval(carregarGravacoesSalvas, 10000);
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.post(
    "/stream/config",
    response_model=ConfigurarStreamResponse,
    summary="Configurar streaming",
    description="""Habilita ou desabilita o streaming de vídeo em tempo de execução.
    
    **Funcionalidades:**
    - Ativa/desativa o streaming globalmente
    - Persiste configuração no arquivo config.ini
    - Autenticação obrigatória via token
    - Validação de parâmetros
    - Feedback imediato do status
    
    **Parâmetros:**
    - **habilitado**: true para habilitar, false para desabilitar
    - **token**: Token de autenticação da API
    
    **Exemplo de uso:**
    ```bash
    curl -X POST "http://localhost:PORT/stream/config?habilitado=true&token=TOKEN" \
      -H "Authorization: Bearer TOKEN"
    ```
    
    **Habilitando streaming:**
    ```bash
    curl -X POST "http://localhost:PORT/stream/config" \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"habilitado": true, "token": "TOKEN"}'
    ```
    """,
    responses={
        200: {
            "description": "Configuração atualizada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "sucesso": True,
                        "mensagem": "Streaming habilitado com sucesso",
                        "stream_habilitado": True
                    }
                }
            }
        },
        401: {"description": "Token de autenticação inválido"},
        500: {"description": "Erro interno do servidor"}
    },
    tags=["Stream - Configuração"]
)
async def configurar_stream(request: Request, habilitado: bool, token: str = None):
    """Habilita ou desabilita o streaming de vídeo em tempo de execução."""
    from ...config.settings import get_api_token, load_config
    import configparser
    import os
    
    # Verificar autenticação
    api_token = get_api_token()
    if not token or token != api_token:
        raise HTTPException(status_code=401, detail="Token de autenticação inválido")
    
    try:
        # Carregar configuração atual
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
            "config.ini"
        )
        
        cfg = configparser.ConfigParser()
        cfg.read(config_path, encoding="utf-8")
        
        # Atualizar configuração
        if "stream" not in cfg:
            cfg.add_section("stream")
        
        cfg.set("stream", "habilitado", str(habilitado).lower())
        
        # Salvar configuração
        with open(config_path, "w", encoding="utf-8") as f:
            cfg.write(f)
        
        status = "habilitado" if habilitado else "desabilitado"
        return {
            "sucesso": True,
            "mensagem": f"Streaming {status} com sucesso",
            "stream_habilitado": habilitado
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao configurar streaming: {str(e)}")

@router.post(
    "/iniciar_gravacao",
    response_model=GravacaoResponse,
    summary="Inicia uma nova gravação do stream",
    description="""Inicia uma nova gravação do stream de tela em formato MP4 com configurações personalizáveis.
    
    **Parâmetros configuráveis:**
    - **FPS**: Frames por segundo (1-60, padrão: 10)
    - **Qualidade**: Qualidade da gravação em % (1-100, padrão: 80)
    - **Brilho**: Ajuste de brilho (-100 a +100, padrão: 0)
    - **Contraste**: Ajuste de contraste (0.5 a 3.0, padrão: 1.0)
    
    **Funcionalidades:**
    - Gera ID único para cada gravação
    - Cria automaticamente a pasta 'records' se não existir
    - Salva arquivo com timestamp no nome
    - Suporte a múltiplas gravações simultâneas
    - Codec XVID para melhor performance
    
    **Exemplo de uso:**
    ```bash
    curl -X POST "http://localhost:PORT/iniciar_gravacao" \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "fps": 15,
        "qualidade": 90,
        "brilho": 10,
        "contraste": 1.2
      }'
    ```
    """,
    responses={
        200: {
            "description": "Gravação iniciada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Gravação iniciada com sucesso",
                        "gravacao_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "arquivo_saida": "C:\\RPA\\dados\\scripts\\db\\dist\\records\\gravacao_stream_20240315_143022_a1b2c3d4.mp4"
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        500: {"description": "Erro ao iniciar gravação"}
    },
    tags=["Stream - Gravação"]
)
async def iniciar_gravacao(request: IniciarGravacaoRequest):
    """Inicia uma nova gravação do stream em MP4 com configurações personalizáveis."""
    try:
        # Gera ID único para a gravação
        gravacao_id = str(uuid.uuid4())
        
        # Cria nova instância de gravação
        gravacao = GravacaoState(gravacao_id)
        
        # Configurações da gravação
        gravacao.fps = request.fps
        gravacao.brilho = request.brilho
        gravacao.contraste = request.contraste
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Define o caminho da pasta records
        records_dir = get_records_dir()
        
        # Nome do arquivo com caminho completo
        nome_arquivo = f"gravacao_stream_{timestamp}_{gravacao_id[:8]}.mp4"
        gravacao.arquivo_saida = os.path.join(records_dir, nome_arquivo)
        
        # Captura dimensões da tela com instância MSS thread-safe
        with mss_lock:
            sct = get_mss_instance()
            monitor = sct.monitors[1]
            width = monitor["width"]
            height = monitor["height"]
        
        # Configura o codec e writer (XVID para melhor performance e menor uso de CPU)
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        gravacao.writer = cv2.VideoWriter(
            gravacao.arquivo_saida, 
            fourcc, 
            gravacao.fps, 
            (width, height)
        )
        
        if not gravacao.writer.isOpened():
            return {
            "sucesso": False,
            "erro": "Não foi possível inicializar o gravador de vídeo"
        }
        
        # Inicia o estado de gravação
        gravacao.gravando = True
        gravacao.pausada = False
        gravacao.data_inicio = datetime.now()
        gravacao.parar_thread = False
        
        # Adiciona ao dicionário de gravações ativas
        gravacoes_ativas[gravacao_id] = gravacao
        
        # Inicia thread de gravação
        gravacao.thread_gravacao = threading.Thread(target=thread_gravacao, args=(gravacao_id,))
        gravacao.thread_gravacao.start()
        
        return {
            "sucesso": True,
            "mensagem": "Gravação iniciada com sucesso",
            "gravacao_id": gravacao_id,
            "arquivo_saida": gravacao.arquivo_saida
        }
        
    except Exception as e:
        print(f"[ERROR] Erro ao iniciar gravação: {e}")
        return {
            "sucesso": False,
            "erro": f"Erro ao iniciar gravação: {str(e)}"
        }

@router.post(
    "/pausar_gravacao/{gravacao_id}",
    response_model=GravacaoResponse,
    summary="Pausa uma gravação ativa",
    description="""Pausa uma gravação que está em andamento, mantendo o arquivo e permitindo retomar posteriormente.
    
    **Funcionalidades:**
    - Pausa a gravação sem perder o progresso
    - Mantém o arquivo de saída
    - Permite retomar a gravação posteriormente
    - Atualiza o status para 'pausada'
    
    **Exemplo de uso:**
    ```bash
    curl -X POST "http://localhost:PORT/pausar_gravacao/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
      -H "Authorization: Bearer TOKEN"
    ```
    """,
    responses={
        200: {
            "description": "Gravação pausada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Gravação pausada com sucesso",
                        "gravacao_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "status": "pausada"
                    }
                }
            }
        },
        404: {"description": "Gravação não encontrada"},
        400: {"description": "Gravação não está ativa"}
    },
    tags=["Stream - Gravação"]
)
async def pausar_gravacao(gravacao_id: str):
    """Pausa uma gravação ativa, mantendo o arquivo e permitindo retomar posteriormente."""
    try:
        if gravacao_id not in gravacoes_ativas:
            return {"erro": "Gravação não encontrada"}
        
        gravacao = gravacoes_ativas[gravacao_id]
        
        if not gravacao.gravando:
            return {"erro": "Gravação não está ativa"}
        
        if gravacao.pausada:
            return {"erro": "Gravação já está pausada"}
        
        gravacao.pausar()  # Usar o novo método
        
        return {
            "sucesso": True,
            "mensagem": "Gravação pausada",
            "gravacao_id": gravacao_id,
            "arquivo": gravacao.arquivo_saida
        }
        
    except Exception as e:
        return {"erro": f"Erro ao pausar gravação: {str(e)}"}

@router.post(
    "/retomar_gravacao/{gravacao_id}",
    response_model=GravacaoResponse,
    summary="Retoma uma gravação pausada",
    description="""Retoma uma gravação que foi pausada anteriormente, continuando a partir do ponto onde parou.
    
    **Funcionalidades:**
    - Retoma gravação pausada
    - Continua no mesmo arquivo de saída
    - Atualiza o status para 'gravando'
    - Mantém configurações originais (FPS, qualidade, etc.)
    
    **Exemplo de uso:**
    ```bash
    curl -X POST "http://localhost:PORT/retomar_gravacao/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
      -H "Authorization: Bearer TOKEN"
    ```
    """,
    responses={
        200: {
            "description": "Gravação retomada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Gravação retomada com sucesso",
                        "gravacao_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "status": "gravando"
                    }
                }
            }
        },
        404: {"description": "Gravação não encontrada"},
        400: {"description": "Gravação não está pausada"}
    },
    tags=["Stream - Gravação"]
)
async def retomar_gravacao(gravacao_id: str):
    """Retoma uma gravação pausada, continuando a partir do ponto onde parou."""
    try:
        if gravacao_id not in gravacoes_ativas:
            return {"erro": "Gravação não encontrada"}
        
        gravacao = gravacoes_ativas[gravacao_id]
        
        if not gravacao.gravando:
            return {"erro": "Gravação não está ativa"}
        
        if not gravacao.pausada:
            return {"erro": "Gravação não está pausada"}
        
        gravacao.retomar()  # Usar o novo método
        
        return {
            "sucesso": True,
            "mensagem": "Gravação retomada",
            "gravacao_id": gravacao_id,
            "arquivo": gravacao.arquivo_saida
        }
        
    except Exception as e:
        return {"erro": f"Erro ao retomar gravação: {str(e)}"}

@router.post(
    "/parar_gravacao/{gravacao_id}",
    response_model=GravacaoResponse,
    summary="Para uma gravação e finaliza o arquivo",
    description="""Para uma gravação ativa ou pausada e finaliza o arquivo MP4, salvando-o na pasta records.
    
    **Funcionalidades:**
    - Para a gravação definitivamente
    - Finaliza e salva o arquivo MP4
    - Remove a gravação da lista de ativas
    - Libera recursos do sistema
    - Retorna informações do arquivo final
    
    **Exemplo de uso:**
    ```bash
    curl -X POST "http://localhost:PORT/parar_gravacao/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
      -H "Authorization: Bearer TOKEN"
    ```
    """,
    responses={
        200: {
            "description": "Gravação finalizada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Gravação finalizada e salva com sucesso",
                        "gravacao_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "arquivo_saida": "C:\\RPA\\dados\\scripts\\db\\dist\\records\\gravacao_stream_20240315_143022_a1b2c3d4.mp4",
                        "tempo_decorrido": "00:05:23"
                    }
                }
            }
        },
        404: {"description": "Gravação não encontrada"}
    },
    tags=["Stream - Gravação"]
)
async def parar_gravacao(gravacao_id: str):
    """Para uma gravação ativa ou pausada e finaliza o arquivo MP4."""
    try:
        if gravacao_id not in gravacoes_ativas:
            return {"erro": "Gravação não encontrada"}
        
        gravacao = gravacoes_ativas[gravacao_id]
        
        if not gravacao.gravando:
            return {"erro": "Gravação não está ativa"}
        
        # Para a gravação
        gravacao.gravando = False
        gravacao.parar_thread = True
        gravacao.data_fim = datetime.now()
        
        # Aguarda a thread terminar
        if gravacao.thread_gravacao and gravacao.thread_gravacao.is_alive():
            gravacao.thread_gravacao.join(timeout=5)
        
        # Finaliza o writer
        if gravacao.writer:
            gravacao.writer.release()
        
        # Calcula duração
        duracao = gravacao.data_fim - gravacao.data_inicio
        duracao_segundos = int(duracao.total_seconds())
        
        # Informações do arquivo
        arquivo_info = {
            "sucesso": True,
            "mensagem": "Gravação finalizada e salva com sucesso",
            "gravacao_id": gravacao_id,
            "arquivo": gravacao.arquivo_saida,
            "data_inicio": gravacao.data_inicio.isoformat(),
            "data_fim": gravacao.data_fim.isoformat(),
            "duracao_segundos": duracao_segundos,
            "duracao_formatada": str(duracao).split('.')[0],  # Remove microssegundos
            "tamanho_arquivo": os.path.getsize(gravacao.arquivo_saida) if os.path.exists(gravacao.arquivo_saida) else 0
        }
        
        # Remove a gravação do dicionário
        del gravacoes_ativas[gravacao_id]
        
        return arquivo_info
        
    except Exception as e:
        # Em caso de erro, tenta limpar recursos
        if gravacao_id in gravacoes_ativas:
            gravacao = gravacoes_ativas[gravacao_id]
            if gravacao.writer:
                gravacao.writer.release()
            del gravacoes_ativas[gravacao_id]
        return {"erro": f"Erro ao parar gravação: {str(e)}"}

@router.get(
    "/status_gravacao/{gravacao_id}",
    response_model=StatusGravacaoResponse,
    summary="Consulta o status de uma gravação",
    description="""Retorna informações detalhadas sobre o status atual de uma gravação específica.
    
    **Informações retornadas:**
    - Status atual (gravando, pausada, parada)
    - Tempo total decorrido
    - Tempo efetivo de gravação (excluindo pausas)
    - Caminho do arquivo de saída
    - Configurações da gravação (FPS, etc.)
    
    **Exemplo de uso:**
    ```bash
    curl -X GET "http://localhost:PORT/status_gravacao/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
      -H "Authorization: Bearer TOKEN"
    ```
    """,
    responses={
        200: {
            "description": "Status da gravação retornado com sucesso",
            "content": {
                "application/json": {
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
            }
        },
        404: {"description": "Gravação não encontrada"}
    },
    tags=["Stream - Gravação"]
)
async def status_gravacao(gravacao_id: str):
    """Retorna informações detalhadas sobre o status atual de uma gravação específica."""
    try:
        if gravacao_id not in gravacoes_ativas:
            return {
                "erro": "Gravação não encontrada",
                "gravacao_id": gravacao_id
            }
        
        gravacao = gravacoes_ativas[gravacao_id]
        
        # Calcula tempo decorrido efetivo (descontando pausas)
        tempo_segundos = gravacao.get_tempo_decorrido_efetivo()
        
        # Calcula tempo total desde o início (incluindo pausas)
        tempo_total_segundos = 0
        if gravacao.data_inicio:
            tempo_total_segundos = int((datetime.now() - gravacao.data_inicio).total_seconds())
        
        # Formata os tempos
        def formatar_tempo(segundos):
            horas = segundos // 3600
            minutos = (segundos % 3600) // 60
            segs = segundos % 60
            return f"{horas:02d}:{minutos:02d}:{segs:02d}"
        
        status = "pausada" if gravacao.pausada else "gravando"
        
        return {
            "gravacao_id": gravacao_id,
            "gravando": gravacao.gravando,
            "status": status,
            "pausada": gravacao.pausada,
            "arquivo": gravacao.arquivo_saida,
            "data_inicio": gravacao.data_inicio.isoformat() if gravacao.data_inicio else None,
            "tempo_decorrido_segundos": tempo_segundos,
            "tempo_decorrido_formatado": formatar_tempo(tempo_segundos),
            "tempo_total_segundos": tempo_total_segundos,
            "tempo_total_formatado": formatar_tempo(tempo_total_segundos),
            "tempo_pausado_total": int(gravacao.tempo_pausado_total),
            "tempo_pausado_formatado": formatar_tempo(int(gravacao.tempo_pausado_total)),
            "data_pausa": gravacao.data_pausa.isoformat() if gravacao.data_pausa else None,
            "fps": gravacao.fps
        }
        
    except Exception as e:
        return {"erro": f"Erro ao obter status: {str(e)}"}

@router.get(
    "/listar_gravacoes",
    response_model=ListarGravacoesResponse,
    summary="Lista todas as gravações ativas",
    description="""Retorna uma lista de todas as gravações que estão atualmente ativas (gravando ou pausadas).
    
    **Informações retornadas para cada gravação:**
    - ID da gravação
    - Status atual (gravando, pausada)
    - Tempo decorrido
    - Nome do arquivo de saída
    - Configurações da gravação
    
    **Exemplo de uso:**
    ```bash
    curl -X GET "http://localhost:PORT/listar_gravacoes" \
      -H "Authorization: Bearer TOKEN"
    ```
    """,
    responses={
        200: {
            "description": "Lista de gravações ativas retornada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "gravacoes_ativas": [
                            {
                                "gravacao_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                                "status": "gravando",
                                "tempo_decorrido": "00:05:23",
                                "arquivo_saida": "gravacao_stream_20240315_143022_a1b2c3d4.mp4"
                            }
                        ]
                    }
                }
            }
        }
    },
    tags=["Stream - Gravação"]
)
async def listar_gravacoes():
    """Retorna uma lista de todas as gravações que estão atualmente ativas."""
    try:
        if not gravacoes_ativas:
            return {
            "sucesso": True,
            "gravacoes_ativas": []
        }
        
        gravacoes_info = []
        for gravacao_id, gravacao in gravacoes_ativas.items():
            tempo_segundos = gravacao.get_tempo_decorrido_efetivo()  # Usar o novo método
            status = "pausada" if gravacao.pausada else "gravando"
            
            # Calcula tempo total desde o início (incluindo pausas)
            tempo_total_segundos = 0
            if gravacao.data_inicio:
                tempo_total_segundos = int((datetime.now() - gravacao.data_inicio).total_seconds())
            
            # Formata os tempos
            def formatar_tempo(segundos):
                horas = segundos // 3600
                minutos = (segundos % 3600) // 60
                segs = segundos % 60
                return f"{horas:02d}:{minutos:02d}:{segs:02d}"
            
            gravacoes_info.append({
                "gravacao_id": gravacao_id,
                "status": status,
                "arquivo": os.path.basename(gravacao.arquivo_saida),
                "arquivo_completo": gravacao.arquivo_saida,
                "data_inicio": gravacao.data_inicio.isoformat(),
                "tempo_decorrido_segundos": tempo_segundos,
                "tempo_decorrido_formatado": formatar_tempo(tempo_segundos),
                "tempo_total_segundos": tempo_total_segundos,
                "tempo_total_formatado": formatar_tempo(tempo_total_segundos),
                "tempo_pausado_total": int(gravacao.tempo_pausado_total),
                "tempo_pausado_formatado": formatar_tempo(int(gravacao.tempo_pausado_total)),
                "fps": gravacao.fps,
                "pausada": gravacao.pausada
            })
        
        return {
            "sucesso": True,
            "gravacoes_ativas": gravacoes_info
        }
        
    except Exception as e:
        return {"erro": f"Erro ao listar gravações: {str(e)}"}

@router.get(
    "/listar_gravacoes_salvas",
    response_model=ListarGravacoesSalvasResponse,
    summary="Lista todas as gravações salvas",
    description="""Retorna uma lista de todos os arquivos MP4 salvos na pasta 'records' com informações detalhadas.
    
    **Informações retornadas para cada gravação:**
    - Nome do arquivo
    - Tamanho em MB
    - Data de criação
    - Data de modificação
    - Caminho completo
    - Duração estimada (se disponível)
    
    **Exemplo de uso:**
    ```bash
    curl -X GET "http://localhost:PORT/listar_gravacoes_salvas" \
      -H "Authorization: Bearer TOKEN"
    ```
    """,
    responses={
        200: {
            "description": "Lista de gravações salvas retornada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "total_gravacoes": 2,
                        "gravacoes": [
                            {
                                "nome_arquivo": "gravacao_stream_20240315_143022_a1b2c3d4.mp4",
                                "tamanho_mb": 45.67,
                                "data_criacao": "2024-03-15T14:30:22",
                                "data_modificacao": "2024-03-15T14:35:45",
                                "caminho_completo": "C:/RPA/records/gravacao_stream_20240315_143022_a1b2c3d4.mp4"
                            }
                        ]
                    }
                }
            }
        }
    },
    tags=["Stream - Gravação"]
)
async def listar_gravacoes_salvas():
    """Retorna uma lista de todos os arquivos MP4 salvos na pasta 'records'."""
    try:
        # Define o caminho da pasta records
        records_dir = get_records_dir()
        
        if not os.path.exists(records_dir):
            return {
                "sucesso": True,
                "gravacoes_salvas": []
            }
        
        # Lista todos os arquivos MP4 na pasta
        arquivos_mp4 = [f for f in os.listdir(records_dir) if f.endswith('.mp4')]
        
        if not arquivos_mp4:
            return {
                "sucesso": True,
                "gravacoes_salvas": []
            }
        
        gravacoes_salvas = []
        for arquivo in sorted(arquivos_mp4, reverse=True):  # Mais recentes primeiro
            caminho_completo = os.path.join(records_dir, arquivo)
            
            # Obtém informações do arquivo
            stat_info = os.stat(caminho_completo)
            tamanho_mb = round(stat_info.st_size / (1024 * 1024), 2)
            data_criacao = datetime.fromtimestamp(stat_info.st_ctime)
            data_modificacao = datetime.fromtimestamp(stat_info.st_mtime)
            
            # Obtém duração do vídeo usando OpenCV
            duracao_segundos = 0
            duracao_formatada = "00:00:00"
            try:
                cap = cv2.VideoCapture(caminho_completo)
                if cap.isOpened():
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    if fps > 0:
                        duracao_segundos = int(frame_count / fps)
                        horas = duracao_segundos // 3600
                        minutos = (duracao_segundos % 3600) // 60
                        segundos = duracao_segundos % 60
                        duracao_formatada = f"{horas:02d}:{minutos:02d}:{segundos:02d}"
                cap.release()
            except Exception as e:
                print(f"Erro ao obter duração do vídeo {arquivo}: {e}")
            
            gravacoes_salvas.append({
                "nome_arquivo": arquivo,
                "caminho_completo": caminho_completo,
                "tamanho_mb": tamanho_mb,
                "duracao_segundos": duracao_segundos,
                "duracao_formatada": duracao_formatada,
                "data_criacao": data_criacao.isoformat(),
                "data_modificacao": data_modificacao.isoformat(),
                "data_criacao_formatada": data_criacao.strftime("%d/%m/%Y %H:%M:%S"),
                "data_modificacao_formatada": data_modificacao.strftime("%d/%m/%Y %H:%M:%S")
            })
        
        return {
            "sucesso": True,
            "gravacoes_salvas": gravacoes_salvas
        }
        
    except Exception as e:
        print(f"[ERROR] Erro ao listar gravações salvas: {e}")
        return {
            "sucesso": False,
            "gravacoes_salvas": []
        }

@router.get(
    "/stream_video/{nome_arquivo}",
    summary="Reproduz vídeo gravado",
    description="""Faz streaming de um arquivo de vídeo MP4 gravado com suporte a Range requests para reprodução eficiente.
    
    **Funcionalidades:**
    - Suporte a Range requests para seek/navegação no vídeo
    - Streaming otimizado para reprodução em tempo real
    - Tratamento robusto de exceções
    - Compatível com players HTML5
    - Headers apropriados para cache e performance
    
    **Parâmetros:**
    - **nome_arquivo**: Nome do arquivo MP4 na pasta 'records'
    
    **Exemplo de uso:**
    ```bash
    curl -X GET "http://localhost:PORT/stream_video/gravacao_stream_20240315_143022_a1b2c3d4.mp4" \
      -H "Authorization: Bearer TOKEN" \
      -H "Range: bytes=0-1023"
    ```
    
    **Uso em HTML:**
    ```html
    <video controls>
      <source src="/stream_video/gravacao_stream_20240315_143022_a1b2c3d4.mp4" type="video/mp4">
    </video>
    ```
    """,
    responses={
        200: {"description": "Stream de vídeo iniciado com sucesso"},
        206: {"description": "Conteúdo parcial (Range request)"},
        404: {"description": "Arquivo de vídeo não encontrado"},
        416: {"description": "Range não satisfatório"}
    },
    tags=["Stream - Reprodução"]
)
@router.head("/stream_video/{nome_arquivo}")
async def stream_video(request: Request, nome_arquivo: str):
    """Faz streaming de um arquivo de vídeo MP4 gravado com suporte a Range requests."""
    try:
        print(f"[DEBUG] Solicitação de streaming para: {nome_arquivo}")
        
        # Define o caminho da pasta records
        records_dir = get_records_dir()
        caminho_arquivo = os.path.join(records_dir, nome_arquivo)
        
        print(f"[DEBUG] Caminho do arquivo: {caminho_arquivo}")
        print(f"[DEBUG] Arquivo existe: {os.path.exists(caminho_arquivo)}")
        
        # Verifica se o arquivo existe
        if not os.path.exists(caminho_arquivo):
            print(f"[DEBUG] Arquivo não encontrado: {caminho_arquivo}")
            raise HTTPException(status_code=404, detail="Arquivo não encontrado")
        
        # Verifica se é um arquivo MP4
        if not nome_arquivo.endswith('.mp4'):
            print(f"[DEBUG] Arquivo não é MP4: {nome_arquivo}")
            raise HTTPException(status_code=400, detail="Apenas arquivos MP4 são permitidos")
        
        # Obtém o tamanho do arquivo
        try:
            file_size = os.path.getsize(caminho_arquivo)
        except OSError as e:
            print(f"[ERROR] Erro ao obter tamanho do arquivo: {e}")
            raise HTTPException(status_code=500, detail="Erro ao acessar arquivo")
        
        # Para requisições HEAD, retorna apenas headers
        if request.method == "HEAD":
            return Response(
                headers={
                    'Accept-Ranges': 'bytes',
                    'Content-Length': str(file_size),
                    'Content-Type': 'video/mp4',
                    'Cache-Control': 'public, max-age=3600'
                }
            )
        
        # Verifica se há Range header para streaming parcial
        range_header = request.headers.get('Range')
        if range_header:
            try:
                # Parse do Range header (formato: bytes=start-end)
                range_match = range_header.replace('bytes=', '').split('-')
                start = int(range_match[0]) if range_match[0] else 0
                end = int(range_match[1]) if range_match[1] else file_size - 1
                
                # Valida os ranges
                if start >= file_size or start > end:
                    raise HTTPException(status_code=416, detail="Range Not Satisfiable")
                
                # Garante que o end não ultrapasse o final do arquivo
                if end >= file_size:
                    end = file_size - 1
                
                content_length = end - start + 1
                
                print(f"[INFO] Range request: {start}-{end}/{file_size}, Content-Length: {content_length}")
                
                # Lê apenas a parte solicitada do arquivo
                def read_range():
                    try:
                        with open(caminho_arquivo, 'rb') as f:
                            f.seek(start)
                            chunk_size = 8192
                            remaining = content_length
                            total_sent = 0
                            
                            while remaining > 0:
                                chunk = f.read(min(chunk_size, remaining))
                                if not chunk:
                                    # Se não conseguiu ler mais dados, para o loop
                                    print(f"[WARNING] Fim do arquivo atingido. Enviados {total_sent}/{content_length} bytes")
                                    break
                                
                                chunk_len = len(chunk)
                                remaining -= chunk_len
                                total_sent += chunk_len
                                yield chunk
                            
                            # Verifica se enviou todos os bytes prometidos
                            if total_sent != content_length:
                                print(f"[WARNING] Content-Length mismatch: prometido {content_length}, enviado {total_sent}")
                                
                    except Exception as e:
                        print(f"[ERROR] Erro na leitura do arquivo: {e}")
                        return
                
                return StreamingResponse(
                    read_range(),
                    status_code=206,
                    headers={
                        'Content-Range': f'bytes {start}-{end}/{file_size}',
                        'Accept-Ranges': 'bytes',
                        'Content-Length': str(content_length),
                        'Content-Type': 'video/mp4',
                        'Cache-Control': 'public, max-age=3600'
                    }
                )
            except ValueError:
                # Range header inválido, ignora e serve o arquivo completo
                pass
            except Exception as e:
                print(f"[ERROR] Erro no processamento de Range: {e}")
                # Continua para servir o arquivo completo
                pass
        
        # Usa FileResponse para arquivo completo
        print(f"[DEBUG] Usando FileResponse para arquivo completo")
        return FileResponse(
            path=caminho_arquivo,
            media_type='video/mp4',
            headers={
                'Accept-Ranges': 'bytes',
                'Cache-Control': 'public, max-age=3600'
            }
        )
        
    except HTTPException:
        raise
    except FileNotFoundError as e:
        print(f"[ERROR] Arquivo não encontrado: {e}")
        raise HTTPException(status_code=404, detail="Arquivo de vídeo não encontrado")
    except PermissionError as e:
        print(f"[ERROR] Erro de permissão: {e}")
        raise HTTPException(status_code=403, detail="Sem permissão para acessar o arquivo")
    except Exception as e:
        print(f"[ERROR] Erro crítico no streaming de vídeo: {e}")
        print(f"[ERROR] Tipo do erro: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")

@router.get(
    "/download_gravacao/{nome_arquivo}",
    summary="Download de gravação",
    description="""Faz download de uma gravação salva em formato MP4.
    
    **Funcionalidades:**
    - Download direto de arquivos MP4
    - Validação de existência do arquivo
    - Verificação de formato (apenas MP4)
    - Headers otimizados para download
    - Suporte a Accept-Ranges
    - Nome de arquivo preservado
    
    **Parâmetros:**
    - **nome_arquivo**: Nome do arquivo MP4 na pasta 'records'
    
    **Exemplo de uso:**
    ```bash
    curl -X GET "http://localhost:PORT/download_gravacao/gravacao_stream_20240315_143022_a1b2c3d4.mp4" \
      -H "Authorization: Bearer TOKEN" \
      -o "minha_gravacao.mp4"
    ```
    
    **Download com wget:**
    ```bash
    wget "http://localhost:PORT/download_gravacao/gravacao_stream_20240315_143022_a1b2c3d4.mp4" \
      --header="Authorization: Bearer TOKEN"
    ```
    
    **Acesso direto no navegador:**
    `http://localhost:PORT/download_gravacao/nome_do_arquivo.mp4`
    """,
    responses={
        200: {
            "description": "Download iniciado com sucesso",
            "content": {
                "video/mp4": {
                    "example": "[BINARY MP4 DATA]"
                }
            },
            "headers": {
                "Accept-Ranges": {"description": "Suporte a range requests"},
                "Content-Disposition": {"description": "Attachment para forçar download"},
                "Cache-Control": {"description": "Controle de cache"}
            }
        },
        400: {"description": "Formato de arquivo inválido (apenas MP4 permitido)"},
        404: {"description": "Arquivo não encontrado"}
    },
    tags=["Stream - Download"]
)
async def download_gravacao(nome_arquivo: str):
    """Faz download de uma gravação salva em formato MP4."""
    try:
        # Define o caminho da pasta records
        records_dir = get_records_dir()
        caminho_arquivo = os.path.join(records_dir, nome_arquivo)
        
        # Verifica se o arquivo existe
        if not os.path.exists(caminho_arquivo):
            raise HTTPException(status_code=404, detail="Arquivo não encontrado")
        
        # Verifica se é um arquivo MP4
        if not nome_arquivo.endswith('.mp4'):
            raise HTTPException(status_code=400, detail="Apenas arquivos MP4 são permitidos")
        
        return FileResponse(
            path=caminho_arquivo,
            filename=nome_arquivo,
            media_type='video/mp4',
            headers={
                'Accept-Ranges': 'bytes',
                'Content-Disposition': 'attachment',
                'Cache-Control': 'no-cache'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao fazer download: {str(e)}")



@router.get(
    "/stream_fullscreen",
    summary="Página de visualização em tela cheia",
    description="""Retorna uma página HTML otimizada para visualização do stream em tela cheia.
    
    **Funcionalidades:**
    - Interface limpa sem elementos de navegação
    - Otimizada para tela cheia
    - Stream de vídeo em tempo real
    - Controles de reprodução integrados
    - Responsiva para diferentes resoluções
    
    **Exemplo de uso:**
    ```bash
    curl -X GET "http://localhost:PORT/stream_fullscreen" \
      -H "Authorization: Bearer TOKEN"
    ```
    
    **Acesso direto:**
    Abra no navegador: `http://localhost:PORT/stream_fullscreen`
    """,
    responses={
        200: {
            "description": "Página HTML de visualização em tela cheia",
            "content": {
                "text/html": {
                    "example": "<!DOCTYPE html><html>...</html>"
                }
            }
        }
    },
    tags=["Stream - Interface"]
)
async def stream_fullscreen():
    """Retorna uma página HTML otimizada para visualização do stream em tela cheia."""
    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Stream - Tela Cheia</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                background-color: #000;
                overflow: hidden;
                font-family: Arial, sans-serif;
            }
            
            #stream-container {
                width: 100vw;
                height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                position: relative;
            }
            
            #stream {
                max-width: 100%;
                max-height: 100%;
                width: auto;
                height: auto;
                object-fit: contain;
            }
            
            .controls {
                position: absolute;
                top: 20px;
                right: 20px;
                z-index: 1000;
                opacity: 0.8;
                transition: opacity 0.3s;
            }
            
            .controls:hover {
                opacity: 1;
            }
            
            .btn {
                background-color: rgba(255, 255, 255, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.3);
                color: white;
                padding: 10px 15px;
                margin: 5px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
                transition: background-color 0.3s;
            }
            
            .btn:hover {
                background-color: rgba(255, 255, 255, 0.3);
            }
            
            .status {
                position: absolute;
                bottom: 20px;
                left: 20px;
                color: white;
                background-color: rgba(0, 0, 0, 0.5);
                padding: 10px;
                border-radius: 5px;
                font-size: 12px;
                opacity: 0.8;
            }
        </style>
    </head>
    <body>
        <div id="stream-container">
            <img id="stream" src="/stream" alt="Stream da Tela">
            
            <div class="controls">
                <button class="btn" onclick="toggleFullscreen()">Sair Tela Cheia</button>
                <button class="btn" onclick="window.close()">Fechar</button>
            </div>
            
            <div class="status" id="status">
                Stream ativo
            </div>
        </div>
        
        <script>
            // Função para alternar fullscreen
            function toggleFullscreen() {
                if (document.fullscreenElement) {
                    document.exitFullscreen();
                } else {
                    document.documentElement.requestFullscreen();
                }
            }
            
            // Atualizar status do stream
            function updateStatus() {
                const statusDiv = document.getElementById('status');
                const streamImg = document.getElementById('stream');
                
                if (streamImg.complete && streamImg.naturalWidth > 0) {
                    statusDiv.textContent = `Stream ativo - ${streamImg.naturalWidth}x${streamImg.naturalHeight}`;
                } else {
                    statusDiv.textContent = 'Carregando stream...';
                }
            }
            
            // Atualizar status periodicamente
            setInterval(updateStatus, 2000);
            
            // Tentar entrar em fullscreen automaticamente
            window.addEventListener('load', () => {
                setTimeout(() => {
                    try {
                        document.documentElement.requestFullscreen();
                    } catch (err) {
                        console.log('Não foi possível entrar em fullscreen automaticamente:', err);
                    }
                }, 500);
            });
            
            // Teclas de atalho
            document.addEventListener('keydown', (e) => {
                switch(e.key) {
                    case 'Escape':
                        if (document.fullscreenElement) {
                            document.exitFullscreen();
                        } else {
                            window.close();
                        }
                        break;
                    case 'F11':
                        e.preventDefault();
                        toggleFullscreen();
                        break;
                    case 'q':
                    case 'Q':
                        window.close();
                        break;
                }
            });
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)