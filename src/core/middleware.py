from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from ..config.settings import get_api_token
from .logging import get_request_logger, get_error_logger, should_log_route
import logging
import time
import json
import traceback

class BodyReaderMiddleware(BaseHTTPMiddleware):
    """Middleware para permitir múltiplas leituras do corpo da requisição."""
    async def dispatch(self, request: Request, call_next):
        # Não sobrescrever _receive para rotas de streaming
        if request.url.path not in ("/tela", "/stream") and not request.url.path.startswith("/stream_video/"):
            if not hasattr(request.state, "body"):
                try:
                    body = await request.body()
                    request.state.body = body
                    
                    body_sent = False
                    disconnected = False
                    
                    async def receive():
                        nonlocal body_sent, disconnected
                        try:
                            if not body_sent:
                                body_sent = True
                                return {"type": "http.request", "body": body, "more_body": False}
                            elif not disconnected:
                                disconnected = True
                                return {"type": "http.disconnect"}
                            else:
                                # Em vez de lançar RuntimeError, retorna disconnect silenciosamente
                                return {"type": "http.disconnect"}
                        except Exception as e:
                            # Log do erro mas não quebra a aplicação
                            print(f"[WARNING] Erro no middleware BodyReader: {e}")
                            return {"type": "http.disconnect"}
                    
                    request._receive = receive
                except Exception as e:
                    # Se falhar ao ler o corpo, continua sem modificar o request
                    print(f"[WARNING] Erro ao ler corpo da requisição: {e}")
                    pass

        response = await call_next(request)
        return response

async def validar_token(request: Request, call_next):
    """Middleware para validação do token de API."""
    # Rotas públicas não requerem autenticação
    public_paths = ["/", "/tela", "/favicon.ico", "/stream", "/stream_fullscreen", "/docs", "/redoc", "/openapi.json"]
    # Adiciona todos os endpoints de stream e gravação como públicos (sem prefixo)
    stream_paths = [
        "/iniciar_gravacao", "/listar_gravacoes", "/listar_gravacoes_salvas", "/stream/config"
    ]
    
    # Verifica se é uma rota de stream com parâmetros (ex: /pausar_gravacao/{id}, /status_gravacao/{id})
    if (request.url.path.startswith("/pausar_gravacao/") or 
        request.url.path.startswith("/retomar_gravacao/") or 
        request.url.path.startswith("/parar_gravacao/") or 
        request.url.path.startswith("/status_gravacao/") or
        request.url.path.startswith("/download_gravacao/") or
        request.url.path.startswith("/stream_video/") or
        request.url.path.startswith("/static/")):
        return await call_next(request)
    
    if request.url.path in public_paths + stream_paths:
        return await call_next(request)

    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != get_api_token():
        return JSONResponse(
            status_code=401,
            content={"ok": False, "erro": "Token inválido"}
        )
    
    return await call_next(request)

async def handle_exceptions(request: Request, call_next):
    """Middleware para tratamento global de exceções."""
    try:
        return await call_next(request)
    except Exception as exc:
        error_logger = get_error_logger()
        
        # Log detalhado do erro
        error_details = {
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "headers": dict(request.headers),
            "error_type": type(exc).__name__,
            "error_message": str(exc)
        }
        
        # Mascara o token se presente
        if "authorization" in error_details["headers"]:
            error_details["headers"]["authorization"] = "Bearer ***TOKEN_MASCARADO***"
        
        # Tenta capturar o corpo da requisição se disponível
        try:
            if hasattr(request.state, "body") and request.state.body:
                body_preview = request.state.body[:500].decode('utf-8', errors='ignore')
                if len(request.state.body) > 500:
                    body_preview += "...[TRUNCADO]"
                error_details["body_preview"] = body_preview
        except:
            error_details["body_preview"] = "[ERRO_AO_LER_CORPO]"
        
        # Log do erro com stack trace completo
        error_logger.error(f"Erro não tratado na requisição: {json.dumps(error_details, ensure_ascii=False)}")
        error_logger.exception(f"Stack trace completo do erro {type(exc).__name__}: {str(exc)}")
        
        return JSONResponse(
            status_code=500,
            content={"ok": False, "erro": "Erro interno do servidor"}
        )

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware para logging de requisições HTTP sem expor tokens."""
    
    def _mask_token(self, headers: dict) -> dict:
        """Mascara o token de autorização nos headers."""
        masked_headers = dict(headers)
        if "authorization" in masked_headers:
            auth_value = masked_headers["authorization"]
            if auth_value.startswith("Bearer "):
                masked_headers["authorization"] = "Bearer ***TOKEN_MASCARADO***"
        return masked_headers
    
    def _get_body_preview(self, body: bytes, max_length: int = 200) -> str:
        """Retorna uma prévia do corpo da requisição."""
        if not body:
            return "[CORPO_VAZIO]"
        
        # Tenta diferentes encodings
        encodings = ['utf-8', 'latin-1', 'cp1252']
        for encoding in encodings:
            try:
                body_str = body.decode(encoding)
                if len(body_str) > max_length:
                    return body_str[:max_length] + "...[TRUNCADO]"
                return body_str
            except UnicodeDecodeError:
                continue
        
        # Se não conseguir decodificar, mostra os primeiros bytes em hex
        return f"[BINARIO: {body[:50].hex()}]"
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Captura informações da requisição
        method = request.method
        url = str(request.url)
        route_path = request.url.path
        headers = dict(request.headers)
        masked_headers = self._mask_token(headers)
        
        # Verifica se deve logar esta rota
        should_log = should_log_route(route_path)
        
        # Captura o corpo da requisição se disponível
        body_preview = ""
        if should_log:
            try:
                if hasattr(request.state, "body"):
                    body_preview = self._get_body_preview(request.state.body)
                else:
                    body_preview = "[CORPO_NAO_DISPONIVEL]"
            except:
                body_preview = "[ERRO_AO_LER_CORPO]"
        
        # Processa a requisição
        response = await call_next(request)
        
        # Calcula tempo de processamento
        process_time = time.time() - start_time
        
        # Log da requisição apenas se deve ser logada
        if should_log:
            log_data = {
                "method": method,
                "url": url,
                "status_code": response.status_code,
                "process_time_ms": round(process_time * 1000, 2),
                "headers": masked_headers,
                "body_preview": body_preview
            }
            
            # Usa o logger específico para requisições
            request_logger = get_request_logger()
            
            # Log como erro se status >= 400, senão como info
            if response.status_code >= 400:
                error_logger = get_error_logger()
                error_logger.error(f"HTTP Request Error: {json.dumps(log_data, ensure_ascii=False)}")
            else:
                request_logger.info(f"HTTP Request: {json.dumps(log_data, ensure_ascii=False)}")
        
        return response