from fastapi import APIRouter, HTTPException, Request, Body, Query
from ..models.browser import (
    BrowserOpenRequest,
    BrowserDownloadPathRequest,
    BrowserScreenshotRequest,
    BrowserPDFRequest,
    BrowserCloseRequest,
    BrowserOpenTabRequest,
    BrowserSelectTabRequest,
    BrowserCloseTabRequest,
    BrowserDialogHandlerRequest
)
from typing import Dict, Any, Optional
from ...services.global_context import global_context_manager
import subprocess
import os
import time
import json
import base64
import socket
import re
from websocket import create_connection
import requests
import asyncio

router = APIRouter(prefix="/browser", tags=["Navegador"])

# DEPRECATED: Mantidos para compatibilidade, mas agora usa o contexto global
contextos: Dict[str, Dict[str, Any]] = {}
browser_contextos: Dict[str, Dict[str, Any]] = {}

# Função para limpar Preferences preservando o perfil do usuário
def limpar_preferences_preservando_perfil(profile_path):
    """Limpa configurações do Preferences que causam mensagem de restauração, preservando o perfil."""
    preferences_path = os.path.join(profile_path, "Preferences")
    
    try:
        # Tentar ler arquivo existente ou criar um novo
        prefs = {}
        backup_path = preferences_path + ".backup"
        
        if os.path.exists(preferences_path):
            # Fazer backup do arquivo original
            import shutil
            shutil.copy2(preferences_path, backup_path)
            
            try:
                with open(preferences_path, 'r', encoding='utf-8') as f:
                    prefs = json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Se o arquivo estiver corrompido, começar com um dicionário vazio
                prefs = {}
        
        # Garantir estrutura básica do Preferences
        if 'profile' not in prefs:
            prefs['profile'] = {}
        if 'session' not in prefs:
            prefs['session'] = {}
        if 'user_experience_metrics' not in prefs:
            prefs['user_experience_metrics'] = {}
        if 'stability' not in prefs['user_experience_metrics']:
            prefs['user_experience_metrics']['stability'] = {}
        
        # Configurações críticas para eliminar mensagem de restauração
        prefs['profile']['exit_type'] = 'Normal'
        prefs['profile']['exited_cleanly'] = True
        prefs['profile']['was_shutdown_cleanly'] = True
        
        # Configurar para não restaurar abas (1 = Nova aba, 4 = Continuar de onde parou)
        prefs['session']['restore_on_startup'] = 1
        prefs['session']['startup_urls'] = []
        
        # Limpar flags de crash e configurar estabilidade
        prefs['user_experience_metrics']['stability']['crashed_on_launch'] = False
        prefs['user_experience_metrics']['stability']['exited_cleanly'] = True
        prefs['user_experience_metrics']['stability']['launch_count'] = 1
        prefs['user_experience_metrics']['stability']['crash_count'] = 0
        prefs['user_experience_metrics']['stability']['incomplete_session_end_count'] = 0
        prefs['user_experience_metrics']['stability']['page_load_count'] = 1
        prefs['user_experience_metrics']['stability']['renderer_crash_count'] = 0
        prefs['user_experience_metrics']['stability']['extension_renderer_crash_count'] = 0
        
        # Remover dados de sessão que causam restauração
        if 'sessions' in prefs:
            prefs['sessions'] = {}
        if 'session_restore' in prefs:
            del prefs['session_restore']
        
        # Configurações adicionais para evitar mensagens
        if 'browser' not in prefs:
            prefs['browser'] = {}
        prefs['browser']['show_home_button'] = True
        prefs['browser']['check_default_browser'] = False
        prefs['browser']['has_seen_welcome_page'] = True
        
        # Configurações de shutdown para evitar detecção de crash
        if 'shutdown' not in prefs:
            prefs['shutdown'] = {}
        prefs['shutdown']['type'] = 1  # Normal shutdown
        prefs['shutdown']['num_processes'] = 0
        prefs['shutdown']['num_processes_slow'] = 0
        
        # Configurações de tabs para evitar restauração
        if 'tabs' not in prefs:
            prefs['tabs'] = {}
        prefs['tabs']['use_vertical_tabs'] = False
        
        # Limpar histórico de crashes
        if 'unclean_shutdown_detected' in prefs:
            del prefs['unclean_shutdown_detected']
        if 'was_shutdown_cleanly' in prefs:
            prefs['was_shutdown_cleanly'] = True
        
        # Salvar arquivo com configurações limpas
        with open(preferences_path, 'w', encoding='utf-8') as f:
            json.dump(prefs, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        # Em caso de erro crítico, tentar restaurar do backup
        backup_path = preferences_path + ".backup"
        if os.path.exists(backup_path):
            try:
                import shutil
                shutil.copy2(backup_path, preferences_path)
            except:
                pass
        # Se não conseguir restaurar, criar arquivo mínimo
        else:
            try:
                minimal_prefs = {
                    "profile": {
                        "exit_type": "Normal",
                        "exited_cleanly": True
                    },
                    "session": {
                        "restore_on_startup": 1
                    },
                    "user_experience_metrics": {
                        "stability": {
                            "crashed_on_launch": False,
                            "exited_cleanly": True
                        }
                    }
                }
                with open(preferences_path, 'w', encoding='utf-8') as f:
                    json.dump(minimal_prefs, f, indent=2)
            except:
                pass  # Se falhar completamente, deixar o Chrome criar o arquivo

@router.post(
    "/abrir",
    summary="Abre uma nova instância do navegador",
    description="Inicia uma nova instância do navegador Chromium com perfil e diretório de download personalizados. Permite parâmetros opcionais de inicialização separados por ponto e vírgula (ex: '--kiosk;--start-fullscreen').",
    response_description="Retorna informações sobre a instância do navegador iniciada",
    status_code=200,
    responses={
        200: {
            "description": "Navegador iniciado com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Navegador iniciado para contexto 'exemplo'",
                        "porta": 9222,
                        "download_dir": "C:/Downloads/exemplo"
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        500: {"description": "Erro ao iniciar o navegador"}
    }
)
async def abrir_browser(request: BrowserOpenRequest):
    if not request.contexto:
        raise HTTPException(status_code=400, detail="Parâmetro 'contexto' é obrigatório")
    if not request.chromium_path or not os.path.exists(request.chromium_path):
        raise HTTPException(status_code=400, detail="Parâmetro 'chromium_path' inválido ou ausente")

    # Define caminho do perfil
    profile_path = request.profile_path or os.path.join(os.path.expanduser("~"), ".chromium_profiles", request.contexto)
    os.makedirs(profile_path, exist_ok=True)
    
    # Limpar arquivo Preferences para evitar mensagem de restauração preservando o perfil
    limpar_preferences_preservando_perfil(profile_path)

    # Define caminho do download
    download_dir = request.download_dir or os.path.join(os.path.expanduser("~"), "Downloads", request.contexto)
    os.makedirs(download_dir, exist_ok=True)

    # Reutilizar processo se já existir para o contexto
    if request.contexto in browser_contextos:
        ctx = browser_contextos[request.contexto]
        proc = ctx.get("proc")
        if proc and proc.poll() is None:
            return {"ok": True, "mensagem": "Navegador já iniciado para este contexto"}

    # Porta dinâmica
    def porta_livre():
        with socket.socket() as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    porta = porta_livre()

    # Lista base de argumentos do Chromium
    # Argumentos básicos obrigatórios
    chrome_args = [
        request.chromium_path,
        f'--user-data-dir={profile_path}',
        f'--remote-debugging-port={porta}',
        f'--remote-allow-origins=*',
        f'--download-default-directory={download_dir}',
        '--kiosk-printing',
        # Argumentos para prevenir mensagens de restauração
        '--disable-session-crashed-bubble',
        '--disable-infobars',
        '--disable-restore-session-state',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-default-apps',
        '--disable-popup-blocking'
    ]
    
    # Adiciona argumentos customizados do Chrome se fornecidos
    if request.chrome_args:
        chrome_args.extend(request.chrome_args)
    
    # Adiciona parâmetros opcionais de inicialização se fornecidos
    if request.parametros_inicializacao:
        parametros_extras = [param.strip() for param in request.parametros_inicializacao.split(';') if param.strip()]
        chrome_args.extend(parametros_extras)
    
    # Adiciona URL inicial
    chrome_args.append('about:blank')

    # Configurações específicas do Windows para evitar processos cmd.exe intermediários
    import platform
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        proc = subprocess.Popen(
            chrome_args, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            startupinfo=startupinfo
        )
    else:
        proc = subprocess.Popen(chrome_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(30):
        try:
            tabs = requests.get(f"http://127.0.0.1:{porta}/json", timeout=1).json()
            break
        except:
            time.sleep(0.5)
    else:
        proc.kill()
        raise HTTPException(status_code=500, detail="DevTools não respondeu em até 15 segundos")

    page_target = next(t for t in tabs if t.get("type") == "page")
    initial_targetId = page_target["id"]
    ws_page = create_connection(page_target["webSocketDebuggerUrl"], header=["Origin: http://127.0.0.1"])

    ver = requests.get(f"http://127.0.0.1:{porta}/json/version", timeout=1).json()
    ws_browser = create_connection(ver["webSocketDebuggerUrl"], header=["Origin: http://127.0.0.1"])

    exec_id = 0
    browser_id = 0

    def cdp_browser(method, params=None):
        nonlocal browser_id
        browser_id += 1
        msg = {"id": browser_id, "method": method, "params": params or {}}
        ws_browser.send(json.dumps(msg))
        while True:
            resp = json.loads(ws_browser.recv())
            if resp.get("id") == browser_id:
                return resp

    def exec_js(expression, targetId=None):
        nonlocal exec_id
        exec_id += 1
        msg = {
            "id": exec_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True
            }
        }
        ws_page.send(json.dumps(msg))
        while True:
            resp = json.loads(ws_page.recv())
            if resp.get("id") == exec_id:
                return resp.get("result", {}).get("result", {}).get("value")

    exec_js("void 0")

    browser_contextos[request.contexto] = {
        "porta": porta,
        "proc": proc,
        "ws_page": ws_page,
        "ws_browser": ws_browser,
        "exec_js": exec_js,
        "cdp_browser": cdp_browser,
        "profile_path": profile_path,
        "targetId": initial_targetId
    }

    # Criar objeto page simulado usando exec_js
    class MockPage:
        def __init__(self, exec_js_func):
            self.exec_js = exec_js_func
        
        def goto(self, url):
            return self.exec_js(f'window.location.href = "{url}"')
        
        def title(self):
            return self.exec_js('document.title')
        
        def url(self):
            return self.exec_js('window.location.href')
        
        def click(self, selector):
            return self.exec_js(f'document.querySelector("{selector}").click()')
        
        def fill(self, selector, text):
            return self.exec_js(f'document.querySelector("{selector}").value = "{text}"')
        
        def evaluate(self, script):
            return self.exec_js(script)
    
    page = MockPage(exec_js)
    
    contextos[request.contexto] = {
        "_exec_id": exec_id,
        "_page_ws": ws_page,
        "_browser_ws": ws_browser,
        "exec_js": exec_js,
        "cdp_browser": cdp_browser,
        "initial_targetId": initial_targetId,
        "page": page,
        "time": time
    }

    return {
        "ok": True,
        "mensagem": f"Navegador iniciado para contexto '{request.contexto}'",
        "porta": porta,
        "download_dir": download_dir
    }

@router.post(
    "/set_download_path",
    summary="Configura o diretório de download",
    description="Define o diretório onde os arquivos serão baixados para uma instância específica do navegador.",
    response_description="Retorna o status da configuração do diretório de download",
    status_code=200,
    responses={
        200: {
            "description": "Diretório configurado com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "resposta_cdp": {"id": 1, "result": {}}
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        404: {"description": "Contexto não encontrado"},
        500: {"description": "Erro ao configurar diretório"}
    }
)
async def set_download_path(request: BrowserDownloadPathRequest):
    if not request.contexto or not request.download_dir:
        raise HTTPException(status_code=400, detail="Parâmetros 'contexto' e 'download_dir' são obrigatórios")

    ctx = browser_contextos.get(request.contexto)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Contexto '{request.contexto}' não encontrado")

    try:
        os.makedirs(request.download_dir, exist_ok=True)

        cdp = ctx.get("cdp_browser")
        if not cdp:
            raise HTTPException(status_code=500, detail="Função CDP não disponível no contexto")

        resp = cdp("Browser.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": request.download_dir
        })
        return {"ok": True, "resposta_cdp": resp}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post(
    "/executar",
    summary="Executa código no navegador (SEMPRE text/plain)",
    description="""Executa código Python assíncrono no contexto do navegador.
    
    **⚠️ IMPORTANTE: Esta rota SEMPRE trata o body como text/plain, independente do Content-Type enviado.**
    
    **Formato aceito:**
    - **APENAS Text/plain**: código python direto no body da requisição
    - **Content-Type ignorado**: mesmo enviando application/json, será tratado como texto
    - **Contexto obrigatório**: deve ser fornecido via query parameter `?contexto=nome` ou JSON no body
    
    **Exemplos de uso:**
    ```bash
    # Usando text/plain com contexto na query:
    curl -X POST http://localhost:PORT/browser/executar?contexto=teste \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: text/plain" \
      -d 'page.goto("https://google.com")'
    
    # Mesmo com application/json, será tratado como texto:
    curl -X POST http://localhost:PORT/browser/executar?contexto=teste \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d 'page.goto("https://google.com")'
    ```
    """,
    response_description="Retorna o resultado da execução do código",
    status_code=200,
    responses={
        200: {
            "description": "Código executado com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "resultado": "Resultado da execução",
                        "formato_detectado": "json_auto",
                        "content_type_original": "não especificado"
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        404: {"description": "Contexto não encontrado"},
        500: {"description": "Erro na execução do código"}
    }
)
async def executar_browser_query(request: Request):
    """Executa código Python no navegador com detecção automática de formato."""
    try:
        # Obtém contexto do query parameter
        contexto_query = request.query_params.get("contexto")
        
        # Obtém content-type (pode ser None ou vazio)
        content_type = request.headers.get("content-type", "").lower()
        
        # Lê o body da requisição
        body = await request.body()
        body_text = body.decode("utf-8")
        
        contexto = None
        code = None
        formato_detectado = None
        
        # SEMPRE força text/plain - ignora content-type JSON
        # Só tenta JSON se o conteúdo claramente parece ser JSON E não há contexto via query
        body_stripped = body_text.strip()
        if not contexto_query and body_stripped.startswith('{') and body_stripped.endswith('}'):
            try:
                # Tenta como JSON apenas se não há contexto via query E parece ser JSON
                data = json.loads(body_text)
                contexto = data.get("contexto")
                code = data.get("code")
                formato_detectado = "json_fallback"
            except json.JSONDecodeError:
                # Se não for JSON válido, trata como texto
                contexto = contexto_query
                code = body_text
                formato_detectado = "texto_forcado"
        else:
            # SEMPRE prioriza text/plain, mesmo com content-type JSON
            contexto = contexto_query
            code = body_text
            formato_detectado = "texto_forcado"
        
        # Validações
        if not contexto:
            raise HTTPException(status_code=400, detail="Parâmetro 'contexto' é obrigatório (via JSON ou query parameter)")
        
        if not code or not code.strip():
            raise HTTPException(status_code=400, detail="Código não pode estar vazio")
        
        if contexto not in contextos:
            raise HTTPException(status_code=404, detail=f"Contexto '{contexto}' não encontrado ou não iniciado")
        
        # Executa o código usando o contexto global compartilhado
        # Mantém compatibilidade com contextos de browser específicos
        if contexto not in contextos:
            raise HTTPException(status_code=404, detail=f"Contexto '{contexto}' não encontrado ou não iniciado")
        
        # Combina contexto do browser com contexto global
        browser_ctx = contextos[contexto]
        
        # Executa no contexto global, mas com acesso ao contexto do browser
        combined_globals = globals().copy()
        combined_globals.update(browser_ctx)
        
        result = global_context_manager.execute_in_context(contexto, code, combined_globals)
        
        if not result["ok"]:
            raise HTTPException(status_code=500, detail=result["error"])
            
        resultado = result["result"]
        
        return {
            "ok": True,
            "resultado": resultado,
            "formato_detectado": formato_detectado,
            "content_type_original": content_type or "não especificado"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/console",
    summary="Executa JavaScript no console (SEMPRE text/plain)",
    description="""Executa código JavaScript no console do navegador.
    
    **⚠️ IMPORTANTE: Esta rota SEMPRE trata o body como text/plain, independente do Content-Type enviado.**
    
    **Formato aceito:**
    - **APENAS Text/plain**: código javascript direto no body da requisição
    - **Content-Type ignorado**: mesmo enviando application/json, será tratado como texto
    - **Contexto obrigatório**: deve ser fornecido via query parameter `?contexto=nome` ou JSON no body
    
    **Exemplos de uso:**
    ```bash
    # Usando text/plain com contexto na query:
    curl -X POST http://localhost:PORT/browser/console?contexto=teste \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: text/plain" \
      -d 'window.location.href'
    
    # Mesmo com application/json, será tratado como texto:
    curl -X POST http://localhost:PORT/browser/console?contexto=teste \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d 'window.location.href'
    ```
    """,
    response_description="Retorna o resultado da execução do JavaScript",
    status_code=200,
    responses={
        200: {
            "description": "JavaScript executado com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "resultado": "Resultado da execução",
                        "formato_detectado": "json_auto",
                        "content_type_original": "não especificado"
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        404: {"description": "Contexto não encontrado"},
        500: {"description": "Erro na execução do JavaScript"}
    }
)
async def browser_console(request: Request):
    """Executa JavaScript no console com detecção automática de formato."""
    try:
        # Obtém contexto do query parameter
        contexto_query = request.query_params.get("contexto")
        
        # Obtém content-type (pode ser None ou vazio)
        content_type = request.headers.get("content-type", "").lower()
        
        # Lê o body da requisição
        body = await request.body()
        body_text = body.decode("utf-8")
        
        contexto = None
        code = None
        formato_detectado = None
        
        # SEMPRE força text/plain - ignora content-type JSON
        # Só tenta JSON se o conteúdo claramente parece ser JSON E não há contexto via query
        body_stripped = body_text.strip()
        if not contexto_query and body_stripped.startswith('{') and body_stripped.endswith('}'):
            try:
                # Tenta como JSON apenas se não há contexto via query E parece ser JSON
                data = json.loads(body_text)
                contexto = data.get("contexto")
                code = data.get("code")
                formato_detectado = "json_fallback"
            except json.JSONDecodeError:
                # Se não for JSON válido, trata como texto
                contexto = contexto_query
                code = body_text
                formato_detectado = "texto_forcado"
        else:
            # SEMPRE prioriza text/plain, mesmo com content-type JSON
            contexto = contexto_query
            code = body_text
            formato_detectado = "texto_forcado"
        
        # Validações
        if not contexto:
            raise HTTPException(status_code=400, detail="Parâmetro 'contexto' é obrigatório (via JSON ou query parameter)")
        
        if not code or not code.strip():
            raise HTTPException(status_code=400, detail="Código JavaScript não pode estar vazio")
        
        if contexto not in contextos:
            raise HTTPException(status_code=404, detail=f"Contexto '{contexto}' não encontrado ou não iniciado")
        
        # Executa o JavaScript
        ctx = contextos[contexto]
        exec_js = ctx["exec_js"]
        
        resultado = exec_js(code)
        if resultado is None:
            resultado = "null"
            
        return {
            "ok": True,
            "resultado": resultado,
            "formato_detectado": formato_detectado,
            "content_type_original": content_type or "não especificado"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/screenshot",
    summary="Captura screenshots",
    description="Captura uma screenshot da página atual do navegador e salva em um arquivo.",
    response_description="Retorna o status da captura da screenshot",
    status_code=200,
    responses={
        200: {
            "description": "Screenshot capturada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Screenshot salva em C:/screenshots/exemplo.png"
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        404: {"description": "Contexto não encontrado"},
        500: {"description": "Erro ao capturar screenshot"}
    }
)
async def browser_screenshot(request: BrowserScreenshotRequest):
    if not request.contexto:
        raise HTTPException(status_code=400, detail="Parâmetro 'contexto' obrigatório")
    if request.contexto not in browser_contextos:
        raise HTTPException(status_code=404, detail=f"Contexto '{request.contexto}' não encontrado")

    if not request.path or not request.filename:
        raise HTTPException(status_code=400, detail="Parâmetros 'path' e 'filename' obrigatórios")

    ctx = browser_contextos[request.contexto]
    ws_page = ctx["ws_page"]
    exec_id = ctx.get("exec_id", 0) + 1
    ctx["exec_id"] = exec_id

    msg = {
        "id": exec_id,
        "method": "Page.captureScreenshot",
        "params": {"format": "png", "fromSurface": True}
    }
    ws_page.send(json.dumps(msg))

    while True:
        resp = json.loads(ws_page.recv())
        if resp.get("id") == exec_id:
            break

    b64 = resp.get("result", {}).get("data")
    if not b64:
        raise HTTPException(status_code=500, detail="Falha ao gerar screenshot")

    try:
        os.makedirs(request.path, exist_ok=True)
        full_path = os.path.join(request.path, request.filename)
        with open(full_path, "wb") as f:
            f.write(base64.b64decode(b64))
        return {"ok": True, "mensagem": f"Screenshot salva em {full_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/pdf",
    summary="Gera PDFs de páginas web",
    description="Captura a página atual do navegador como PDF com opções personalizáveis.",
    response_description="Retorna o status da geração do PDF",
    status_code=200,
    responses={
        200: {
            "description": "PDF gerado com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "PDF salvo em C:/pdfs/exemplo.pdf"
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        404: {"description": "Contexto não encontrado"},
        500: {"description": "Erro ao gerar PDF"}
    }
)
async def browser_pdf(request: BrowserPDFRequest):
    if not request.contexto:
        raise HTTPException(status_code=400, detail="Parâmetro 'contexto' obrigatório")
    if request.contexto not in browser_contextos:
        raise HTTPException(status_code=404, detail=f"Contexto '{request.contexto}' não encontrado")

    if not request.path or not request.filename:
        raise HTTPException(status_code=400, detail="Parâmetros 'path' e 'filename' obrigatórios")

    ctx = browser_contextos[request.contexto]
    ws_page = ctx["ws_page"]
    exec_id = ctx.get("exec_id", 0) + 1
    ctx["exec_id"] = exec_id

    # Opções padrão do PDF otimizadas para qualidade
    pdf_options = {
        "landscape": False,
        "displayHeaderFooter": False,  # Remove cabeçalho/rodapé padrão do Chrome
        "printBackground": True,
        "scale": 1.0,  # Escala 1:1 para máxima qualidade
        "preferCSSPageSize": True,  # Usa tamanho CSS ao invés de escalar
        "paperWidth": 8.5,
        "paperHeight": 11,
        "marginTop": 0.4,  # Margens padrão em polegadas
        "marginBottom": 0.4,
        "marginLeft": 0.4,
        "marginRight": 0.4,
        "pageRanges": "",
        "ignoreInvalidPageRanges": True,
        "headerTemplate": "",
        "footerTemplate": ""
    }

    # Atualiza com as opções fornecidas
    if request.pdf_options:
        pdf_options.update(request.pdf_options)

    msg = {
        "id": exec_id,
        "method": "Page.printToPDF",
        "params": pdf_options
    }
    ws_page.send(json.dumps(msg))

    while True:
        resp = json.loads(ws_page.recv())
        if resp.get("id") == exec_id:
            break

    b64 = resp.get("result", {}).get("data")
    if not b64:
        raise HTTPException(status_code=500, detail="Falha ao gerar PDF")

    try:
        os.makedirs(request.path, exist_ok=True)
        full_path = os.path.join(request.path, request.filename)
        with open(full_path, "wb") as f:
            f.write(base64.b64decode(b64))
        return {"ok": True, "mensagem": f"PDF salvo em {full_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/fechar",
    summary="Fecha uma instância do navegador (JSON ou Query Parameters)",
    description="""Encerra uma instância específica do navegador e limpa seus contextos.
    
    **⚠️ FLEXIBILIDADE: Esta rota aceita parâmetros tanto via JSON no body quanto via query parameters na URL.**
    
    **Formatos aceitos:**
    - **JSON no body**: `{"contexto": "nome_contexto"}`
    - **Query parameters**: `/browser/fechar?contexto=nome_contexto`
    - **Ambos**: Query parameters têm prioridade sobre JSON
    
    **Exemplos de uso:**
    ```bash
    # Via JSON no body:
    curl -X POST http://localhost:PORT/browser/fechar \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"contexto": "meu_contexto"}'
    
    # Via query parameters:
    curl -X POST http://localhost:PORT/browser/fechar?contexto=meu_contexto \
      -H "Authorization: Bearer TOKEN"
    ```
    """,
    response_description="Retorna o status do fechamento do navegador",
    status_code=200,
    responses={
        200: {
            "description": "Navegador fechado com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Navegador fechado para contexto 'exemplo'"
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        404: {"description": "Contexto não encontrado"}
    }
)
async def fechar_browser(request: Request, contexto: Optional[str] = Query(None)):
    # Prioridade: Query parameters > JSON body
    final_contexto = contexto
    
    # Se não veio via query parameter, tenta pegar do JSON
    if not final_contexto:
        try:
            body = await request.body()
            if body:
                body_str = body.decode('utf-8')
                try:
                    json_data = json.loads(body_str)
                    final_contexto = json_data.get('contexto')
                except json.JSONDecodeError:
                    # Se não for JSON válido, tenta como texto simples
                    final_contexto = body_str.strip()
        except Exception:
            pass
    
    if not final_contexto:
        raise HTTPException(status_code=400, detail="Parâmetro 'contexto' é obrigatório")

    if final_contexto not in browser_contextos:
        raise HTTPException(status_code=404, detail=f"Contexto '{final_contexto}' não encontrado")

    ctx = browser_contextos[final_contexto]
    ws_browser = ctx.get("ws_browser")
    proc = ctx.get("proc")
    
    try:
        # Primeiro, tenta fechar o navegador de forma elegante via CDP
        if ws_browser:
            exec_id = ctx.get("exec_id", 0) + 1
            ctx["exec_id"] = exec_id
            
            # Listar todas as abas/targets
            msg_list = {
                "id": exec_id,
                "method": "Target.getTargets",
                "params": {}
            }
            ws_browser.send(json.dumps(msg_list))
            
            # Aguardar resposta
            try:
                resp = json.loads(ws_browser.recv())
                if "result" in resp:
                    targets = resp["result"]["targetInfos"]
                    
                    # Simular fechamento humano em cada aba
                    for target in targets:
                        if target.get("type") == "page":
                            try:
                                # Conectar à aba específica para executar JavaScript
                                porta = ctx.get("porta")
                                ws_url_page = f"ws://localhost:{porta}/devtools/page/{target['targetId']}"
                                ws_page_temp = create_connection(ws_url_page)
                                
                                # Executar JavaScript para simular fechamento humano
                                exec_id += 1
                                ctx["exec_id"] = exec_id
                                
                                # JavaScript mais robusto para simular fechamento humano natural
                                js_graceful_close = """
                                // Simular interação humana antes do fechamento
                                document.dispatchEvent(new Event('visibilitychange'));
                                
                                // Marcar como fechamento normal em múltiplos pontos
                                window.addEventListener('beforeunload', function(e) {
                                    // Não retornar nada para evitar prompt
                                    delete e['returnValue'];
                                });
                                
                                window.addEventListener('unload', function() {
                                    // Marcar fechamento limpo
                                    if (window.chrome && window.chrome.runtime) {
                                        try {
                                            chrome.runtime.sendMessage({type: 'clean_exit'});
                                        } catch(e) {}
                                    }
                                });
                                
                                // Simular atividade normal antes do fechamento
                                if (window.chrome && window.chrome.runtime) {
                                    try {
                                        window.chrome.runtime.onSuspend.addListener(function() {
                                            console.log('Fechamento gracioso detectado');
                                        });
                                        
                                        // Disparar evento de suspensão
                                        if (chrome.runtime.onSuspend) {
                                            chrome.runtime.onSuspend.dispatch();
                                        }
                                    } catch(e) {}
                                }
                                
                                // Limpar dados de sessão
                                try {
                                    sessionStorage.clear();
                                    // Marcar como fechamento limpo no localStorage
                                    localStorage.setItem('clean_exit', 'true');
                                    localStorage.setItem('exit_timestamp', Date.now().toString());
                                } catch(e) {}
                                
                                // Simular foco perdido (como se usuário tivesse clicado fora)
                                window.dispatchEvent(new Event('blur'));
                                document.dispatchEvent(new Event('blur'));
                                
                                'Fechamento gracioso completo executado';
                                """
                                
                                msg_js = {
                                    "id": exec_id,
                                    "method": "Runtime.evaluate",
                                    "params": {
                                        "expression": js_graceful_close,
                                        "awaitPromise": True,
                                        "returnByValue": True
                                    }
                                }
                                ws_page_temp.send(json.dumps(msg_js))
                                
                                # Aguardar resposta do JavaScript
                                try:
                                    ws_page_temp.recv()
                                except:
                                    pass
                                
                                ws_page_temp.close()
                                
                                # Aguardar mais tempo para o JavaScript ser processado
                                import time
                                time.sleep(0.5)
                                
                            except Exception:
                                pass  # Se falhar, continua normalmente
                            
                            # Fechar a aba via CDP
                            exec_id += 1
                            ctx["exec_id"] = exec_id
                            
                            msg_close = {
                                "id": exec_id,
                                "method": "Target.closeTarget",
                                "params": {"targetId": target["targetId"]}
                            }
                            ws_browser.send(json.dumps(msg_close))
                            
                            # Aguardar confirmação (com timeout)
                            try:
                                ws_browser.recv()
                            except:
                                pass  # Ignora erros de timeout
                    
                    # Aguardar mais tempo para todas as abas fecharem completamente
                    import time
                    time.sleep(1.5)
                    
                    # Fechar o navegador via CDP
                    exec_id += 1
                    ctx["exec_id"] = exec_id
                    
                    msg_close_browser = {
                        "id": exec_id,
                        "method": "Browser.close",
                        "params": {}
                    }
                    ws_browser.send(json.dumps(msg_close_browser))
                    
                    # Aguardar confirmação (com timeout)
                    try:
                        ws_browser.recv()
                    except:
                        pass  # Ignora erros de timeout
                        
            except Exception:
                pass  # Se falhar, continua com o método de força
                
    except Exception:
        pass  # Se falhar, usa o método de força
    
    # Aguardar tempo suficiente para o navegador fechar completamente
    import time
    time.sleep(2.0)
    
    # Limpar arquivo Preferences após fechamento para garantir estado normal preservando perfil
    profile_path = ctx.get("profile_path")
    if profile_path:
        try:
            limpar_preferences_preservando_perfil(profile_path)
        except:
            pass  # Ignora erros na limpeza
    
    # Se o processo ainda estiver rodando, força o fechamento
    if proc and proc.poll() is None:
        try:
            proc.terminate()  # Tenta terminar graciosamente primeiro
            time.sleep(0.5)
            if proc.poll() is None:
                proc.kill()  # Se não funcionar, força o fechamento
        except:
            pass

    # Fecha as conexões WebSocket
    ws_page = ctx.get("ws_page")
    if ws_page:
        try:
            ws_page.close()
        except:
            pass

    if ws_browser:
        try:
            ws_browser.close()
        except:
            pass

    # Remove os contextos
    del browser_contextos[final_contexto]
    if final_contexto in contextos:
        del contextos[final_contexto]

    return {"ok": True, "mensagem": f"Navegador fechado para contexto '{final_contexto}'"}

@router.post(
    "/abriraba",
    summary="Abre uma nova aba no navegador",
    description="""Cria uma nova aba no navegador com a URL especificada.
    
    **Parâmetros obrigatórios:**
    - `contexto`: Nome do contexto do navegador ativo
    - `url`: URL completa para carregar na nova aba
    
    **Exemplo de uso:**
    ```json
    {
        "contexto": "navegacao_principal",
        "url": "https://www.google.com"
    }
    ```
    
    **A nova aba será automaticamente ativada após a criação.**
    """,
    response_description="Retorna informações sobre a nova aba criada",
    status_code=200,
    responses={
        200: {
            "description": "Nova aba criada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Nova aba criada com sucesso",
                        "target_id": "12345-67890-ABCDE",
                        "url": "https://www.google.com"
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos ou JSON malformado"},
        404: {"description": "Contexto não encontrado"},
        500: {"description": "Erro ao criar nova aba"}
    }
)
async def abrir_nova_aba(request: BrowserOpenTabRequest):
    """Abre uma nova aba com a URL especificada.
    
    Args:
        request: Dados da requisição contendo contexto e URL
        
    Returns:
        dict: Informações sobre a nova aba criada
        
    Raises:
        HTTPException: Se o contexto não for encontrado ou houver erro na criação
    """
    contexto = request.contexto
    url = request.url
    
    if contexto not in browser_contextos:
        raise HTTPException(status_code=404, detail=f"Contexto '{contexto}' não encontrado")

    ctx = browser_contextos[contexto]
    ws_browser = ctx["ws_browser"]
    exec_id = ctx.get("exec_id", 0) + 1
    ctx["exec_id"] = exec_id

    try:
        # Criar nova aba
        msg_create = {
            "id": exec_id,
            "method": "Target.createTarget",
            "params": {"url": url}
        }
        ws_browser.send(json.dumps(msg_create))

        while True:
            resp = json.loads(ws_browser.recv())
            if resp.get("id") == exec_id:
                break

        if "result" in resp:
            target_id = resp["result"]["targetId"]
            
            # Manter ordem das abas criadas
            if "tab_order" not in ctx:
                ctx["tab_order"] = []
            ctx["tab_order"].append(target_id)
            
            return {
                "ok": True,
                "mensagem": "Nova aba criada com sucesso",
                "target_id": target_id,
                "url": url
            }
        else:
            raise HTTPException(status_code=500, detail=f"Erro ao criar aba: {resp.get('error', 'Erro desconhecido')}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar nova aba: {str(e)}")

@router.post(
    "/selecionar",
    summary="Seleciona uma aba do navegador",
    description="""Seleciona e ativa uma aba específica por índice ou target_id.
    
    **Parâmetros obrigatórios:**
    - `contexto`: Nome do contexto do navegador ativo
    
    **Parâmetros opcionais (um dos dois é obrigatório):**
    - `indice`: Número da aba (1, 2, 3...) baseado na ordem visual
    - `target_id`: ID específico da aba no Chrome DevTools
    
    **Exemplo de uso:**
    ```json
    {
        "contexto": "navegacao_principal",
        "indice": 2
    }
    ```
    
    **Ou usando target_id:**
    ```json
    {
        "contexto": "navegacao_principal",
        "target_id": "12345-67890-ABCDEF"
    }
    ```
    """,
    response_description="Retorna informações sobre a aba selecionada",
    status_code=200,
    responses={
        200: {
            "description": "Aba selecionada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Aba selecionada com sucesso",
                        "target_id": "12345",
                        "indice": 2
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        404: {"description": "Contexto não encontrado"},
        500: {"description": "Erro ao selecionar aba"}
    }
)
async def selecionar_aba(request: BrowserSelectTabRequest):
    """Seleciona uma aba por índice ou target_id."""
    try:
        contexto = request.contexto
        indice = request.indice
        target_id = request.target_id
        
        # Validações
        if not contexto:
            raise HTTPException(status_code=400, detail="Parâmetro 'contexto' é obrigatório")
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar requisição: {str(e)}")
    
    if contexto not in browser_contextos:
        raise HTTPException(status_code=404, detail=f"Contexto '{contexto}' não encontrado")

    ctx = browser_contextos[contexto]
    ws_browser = ctx["ws_browser"]
    exec_id = ctx.get("exec_id", 0) + 1
    ctx["exec_id"] = exec_id

    try:
        # Se foi fornecido um índice, primeiro precisamos listar as abas para obter o target_id
        if indice is not None and target_id is None:
            # Listar targets para obter o target_id pelo índice
            msg_list = {
                "id": exec_id,
                "method": "Target.getTargets",
                "params": {}
            }
            ws_browser.send(json.dumps(msg_list))

            while True:
                resp = json.loads(ws_browser.recv())
                if resp.get("id") == exec_id:
                    break

            if "result" in resp:
                targets = resp["result"]["targetInfos"]
                page_targets = [t for t in targets if t.get("type") == "page"]
                
                # Usar a ordem armazenada no contexto para manter a ordem visual
                if "tab_order" in ctx and ctx["tab_order"]:
                    # Criar lista ordenada baseada na ordem armazenada
                    ordered_targets = []
                    target_dict = {t["targetId"]: t for t in page_targets}
                    
                    # Primeiro, adicionar as abas na ordem armazenada
                    for stored_id in ctx["tab_order"]:
                        if stored_id in target_dict:
                            ordered_targets.append(target_dict[stored_id])
                    
                    # Depois, adicionar qualquer aba que não esteja na ordem armazenada (aba inicial)
                    for target in page_targets:
                        if target["targetId"] not in ctx["tab_order"]:
                            ordered_targets.insert(0, target)  # Aba inicial sempre primeiro
                    
                    page_targets = ordered_targets
                else:
                    # Se não há ordem armazenada, ordenar por targetId (fallback)
                    page_targets.sort(key=lambda x: x.get("targetId", ""))
                
                if indice < 1 or indice > len(page_targets):
                    raise HTTPException(status_code=400, detail=f"Índice {indice} inválido. Abas disponíveis: 1-{len(page_targets)}")
                
                target_id = page_targets[indice - 1]["targetId"]
            else:
                raise HTTPException(status_code=500, detail="Erro ao listar abas")

        if not target_id:
            raise HTTPException(status_code=400, detail="É necessário fornecer 'indice' ou 'target_id'")

        # Ativar a aba
        exec_id += 1
        ctx["exec_id"] = exec_id
        
        msg_activate = {
            "id": exec_id,
            "method": "Target.activateTarget",
            "params": {"targetId": target_id}
        }
        ws_browser.send(json.dumps(msg_activate))

        while True:
            resp = json.loads(ws_browser.recv())
            if resp.get("id") == exec_id:
                break

        if "result" in resp:
            # Agora precisamos conectar à nova aba para atualizar o exec_js
            porta = ctx["porta"]
            ws_url_new_page = f"ws://localhost:{porta}/devtools/page/{target_id}"
            
            try:
                # Criar nova conexão WebSocket para a aba selecionada
                ws_page_new = create_connection(ws_url_new_page)
                
                # Criar nova função exec_js para a aba selecionada
                def exec_js_new(expression):
                    exec_id = ctx.get("exec_id", 0) + 1
                    ctx["exec_id"] = exec_id
                    msg = {
                        "id": exec_id,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": expression,
                            "awaitPromise": True,
                            "returnByValue": True
                        }
                    }
                    ws_page_new.send(json.dumps(msg))
                    while True:
                        resp = json.loads(ws_page_new.recv())
                        if resp.get("id") == exec_id:
                            return resp.get("result", {}).get("result", {}).get("value")
                
                # Atualizar o contexto com a nova conexão e função
                ctx["ws_page"] = ws_page_new
                ctx["exec_js"] = exec_js_new
                ctx["targetId"] = target_id
                
                # Atualizar também o contexto principal se existir
                if contexto in contextos:
                    contextos[contexto]["exec_js"] = exec_js_new
                    contextos[contexto]["_page_ws"] = ws_page_new
                    
                    # Atualizar o MockPage para usar a nova função exec_js
                    class MockPage:
                        def __init__(self, exec_js_func):
                            self.exec_js = exec_js_func
                        
                        def goto(self, url):
                            return self.exec_js(f'window.location.href = "{url}"')
                        
                        def title(self):
                            return self.exec_js('document.title')
                        
                        def url(self):
                            return self.exec_js('window.location.href')
                        
                        def click(self, selector):
                            return self.exec_js(f'document.querySelector("{selector}").click()')
                        
                        def fill(self, selector, text):
                            return self.exec_js(f'document.querySelector("{selector}").value = "{text}"')
                        
                        def evaluate(self, script):
                            return self.exec_js(script)
                    
                    contextos[contexto]["page"] = MockPage(exec_js_new)
                
                return {
                    "ok": True, 
                    "mensagem": "Aba selecionada com sucesso e contexto atualizado",
                    "target_id": target_id,
                    "indice": indice
                }
                
            except Exception as e:
                # Se falhar ao conectar à nova aba, ainda retorna sucesso da ativação
                return {
                    "ok": True, 
                    "mensagem": f"Aba ativada, mas erro ao atualizar contexto: {str(e)}",
                    "target_id": target_id,
                    "indice": indice
                }
        else:
            raise HTTPException(status_code=500, detail=f"Erro ao ativar aba: {resp.get('error', 'Erro desconhecido')}")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao selecionar aba: {str(e)}")

@router.post(
    "/fecharaba",
    summary="Fecha uma aba específica do navegador",
    description="""Fecha uma aba específica por índice ou target_id.
    
    **Parâmetros obrigatórios:**
    - `contexto`: Nome do contexto do navegador ativo
    
    **Parâmetros opcionais (um dos dois é obrigatório):**
    - `indice`: Número da aba (1, 2, 3...) baseado na ordem visual
    - `target_id`: ID específico da aba no Chrome DevTools
    
    **Exemplo de uso:**
    ```json
    {
        "contexto": "navegacao_principal",
        "indice": 2
    }
    ```
    
    **Ou usando target_id:**
    ```json
    {
        "contexto": "navegacao_principal",
        "target_id": "12345-67890-ABCDEF"
    }
    ```
    """,
    response_description="Retorna informações sobre a aba fechada",
    status_code=200,
    responses={
        200: {
            "description": "Aba fechada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Aba fechada com sucesso",
                        "target_id": "12345"
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        404: {"description": "Contexto não encontrado"},
        500: {"description": "Erro ao fechar aba"}
    }
)
async def fechar_aba(request: BrowserCloseTabRequest):
    """Fecha uma aba específica por índice ou target_id."""
    try:
        contexto = request.contexto
        indice = request.indice
        target_id = request.target_id
        
        # Validações
        if not contexto:
            raise HTTPException(status_code=400, detail="Parâmetro 'contexto' é obrigatório")
        
        if contexto not in browser_contextos:
            raise HTTPException(status_code=404, detail=f"Contexto '{contexto}' não encontrado")
        
        ctx = browser_contextos[contexto]
        ws_browser = ctx["ws_browser"]
        exec_id = ctx.get("exec_id", 0)
        formato_detectado = "Pydantic model"
        
        # Se foi fornecido um índice, primeiro precisamos listar as abas para obter o target_id
        if indice is not None and target_id is None:
            # Listar targets para obter o target_id pelo índice
            exec_id += 1
            ctx["exec_id"] = exec_id
            
            msg_list = {
                "id": exec_id,
                "method": "Target.getTargets",
                "params": {}
            }
            ws_browser.send(json.dumps(msg_list))
            
            while True:
                resp = json.loads(ws_browser.recv())
                if resp.get("id") == exec_id:
                    break
            
            if "result" in resp:
                targets = resp["result"]["targetInfos"]
                page_targets = [t for t in targets if t.get("type") == "page"]
                
                # Ordenar abas conforme a ordem armazenada
                if "tab_order" in ctx and ctx["tab_order"]:
                    ordered_targets = []
                    target_dict = {t["targetId"]: t for t in page_targets}
                    
                    # Primeiro, adicionar as abas na ordem armazenada
                    for stored_id in ctx["tab_order"]:
                        if stored_id in target_dict:
                            ordered_targets.append(target_dict[stored_id])
                    
                    # Depois, adicionar qualquer aba que não esteja na ordem armazenada (aba inicial)
                    for target in page_targets:
                        if target["targetId"] not in ctx["tab_order"]:
                            ordered_targets.insert(0, target)  # Aba inicial sempre primeiro
                    
                    page_targets = ordered_targets
                else:
                    # Se não há ordem armazenada, ordenar por targetId (fallback)
                    page_targets.sort(key=lambda x: x.get("targetId", ""))
                
                if indice < 1 or indice > len(page_targets):
                    raise HTTPException(status_code=400, detail=f"Índice {indice} inválido. Abas disponíveis: 1-{len(page_targets)}")
                
                target_id = page_targets[indice - 1]["targetId"]
            else:
                raise HTTPException(status_code=500, detail="Erro ao listar abas")
        
        if not target_id:
            raise HTTPException(status_code=400, detail="É necessário fornecer 'indice' ou 'target_id'")
        
        # Fechar a aba
        exec_id += 1
        ctx["exec_id"] = exec_id
        
        msg_close = {
            "id": exec_id,
            "method": "Target.closeTarget",
            "params": {"targetId": target_id}
        }
        ws_browser.send(json.dumps(msg_close))
        
        while True:
            resp = json.loads(ws_browser.recv())
            if resp.get("id") == exec_id:
                break
        
        if "result" in resp and resp["result"].get("success"):
            # Remover da ordem de abas se existir
            if "tab_order" in ctx and target_id in ctx["tab_order"]:
                ctx["tab_order"].remove(target_id)
            
            return {
                "ok": True,
                "mensagem": "Aba fechada com sucesso",
                "target_id": target_id,
                "indice": indice,
                "formato_detectado": formato_detectado
            }
        else:
            raise HTTPException(status_code=500, detail=f"Erro ao fechar aba: {resp.get('error', 'Erro desconhecido')}")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao fechar aba: {str(e)}")

@router.get(
    "/listarabas",
    summary="Lista todas as abas abertas do navegador",
    description="Retorna uma lista de todas as abas abertas no contexto especificado.",
    response_description="Retorna informações sobre todas as abas abertas",
    status_code=200,
    responses={
        200: {
            "description": "Lista de abas obtida com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Lista de abas obtida com sucesso",
                        "total_abas": 3,
                        "abas": [
                            {
                                "indice": 1,
                                "target_id": "12345",
                                "title": "Google",
                                "url": "https://www.google.com",
                                "ativa": True
                            }
                        ]
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        404: {"description": "Contexto não encontrado"},
        500: {"description": "Erro ao listar abas"}
    }
)
async def listar_abas(contexto: str):
    """Lista todas as abas abertas no contexto especificado."""
    try:
        if not contexto:
            raise HTTPException(status_code=400, detail="Parâmetro 'contexto' é obrigatório")
        
        if contexto not in browser_contextos:
            raise HTTPException(status_code=404, detail=f"Contexto '{contexto}' não encontrado")
        
        ctx = browser_contextos[contexto]
        ws_browser = ctx["ws_browser"]
        exec_id = ctx.get("exec_id", 0)
        
        # Listar targets
        exec_id += 1
        ctx["exec_id"] = exec_id
        
        msg_list = {
            "id": exec_id,
            "method": "Target.getTargets",
            "params": {}
        }
        ws_browser.send(json.dumps(msg_list))
        
        while True:
            resp = json.loads(ws_browser.recv())
            if resp.get("id") == exec_id:
                break
        
        if "result" in resp:
            targets = resp["result"]["targetInfos"]
            page_targets = [t for t in targets if t.get("type") == "page"]
            
            # Ordenar abas conforme a ordem armazenada
            if "tab_order" in ctx and ctx["tab_order"]:
                ordered_targets = []
                target_dict = {t["targetId"]: t for t in page_targets}
                
                # Primeiro, adicionar as abas na ordem armazenada
                for stored_id in ctx["tab_order"]:
                    if stored_id in target_dict:
                        ordered_targets.append(target_dict[stored_id])
                
                # Depois, adicionar qualquer aba que não esteja na ordem armazenada (aba inicial)
                for target in page_targets:
                    if target["targetId"] not in ctx["tab_order"]:
                        ordered_targets.insert(0, target)  # Aba inicial sempre primeiro
                
                page_targets = ordered_targets
            else:
                # Se não há ordem armazenada, ordenar por targetId (fallback)
                page_targets.sort(key=lambda x: x.get("targetId", ""))
            
            # Obter aba ativa atual
            target_id_ativo = ctx.get("targetId")
            
            # Formatar lista de abas
            abas = []
            for i, target in enumerate(page_targets, 1):
                aba_info = {
                    "indice": i,
                    "target_id": target["targetId"],
                    "title": target.get("title", "Sem título"),
                    "url": target.get("url", "about:blank"),
                    "ativa": target["targetId"] == target_id_ativo
                }
                abas.append(aba_info)
            
            return {
                "ok": True,
                "mensagem": "Lista de abas obtida com sucesso",
                "total_abas": len(abas),
                "abas": abas
            }
        else:
            raise HTTPException(status_code=500, detail="Erro ao listar abas")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar abas: {str(e)}")

@router.post(
    "/configurar_dialogs",
    summary="Configura tratamento automático de dialogs JavaScript",
    description="""Configura como o navegador deve tratar dialogs JavaScript (alert, confirm, prompt).
    
    **Funcionalidades:**
    - **Auto-aceitar**: Aceita automaticamente todos os dialogs (clica OK/Sim)
    - **Texto padrão**: Define texto padrão para prompts JavaScript
    - **Compatível**: Funciona com Chrome DevTools Protocol
    
    **Tipos de dialog suportados:**
    - `alert()`: Mensagens de alerta simples
    - `confirm()`: Confirmações com OK/Cancelar
    - `prompt()`: Entrada de texto do usuário
    - `beforeunload`: Confirmações de saída da página
    
    **Exemplo de uso:**
    ```json
    {
        "contexto": "navegacao_principal",
        "auto_accept": true,
        "default_prompt_text": "Resposta automática"
    }
    ```
    
    **Após configurar, todos os dialogs serão tratados automaticamente sem intervenção do usuário.**
    """,
    response_description="Retorna o status da configuração dos handlers de dialog",
    status_code=200,
    responses={
        200: {
            "description": "Handlers de dialog configurados com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "mensagem": "Handlers de dialog configurados com sucesso",
                        "auto_accept": True,
                        "default_prompt_text": "Resposta automática"
                    }
                }
            }
        },
        400: {"description": "Parâmetros inválidos"},
        404: {"description": "Contexto não encontrado"},
        500: {"description": "Erro ao configurar handlers"}
    }
)
async def configurar_dialogs(request: BrowserDialogHandlerRequest):
    if not request.contexto:
        raise HTTPException(status_code=400, detail="Parâmetro 'contexto' é obrigatório")
    
    # Verificar se o contexto existe
    if request.contexto not in browser_contextos:
        raise HTTPException(status_code=404, detail=f"Contexto '{request.contexto}' não encontrado")
    
    ctx = browser_contextos[request.contexto]
    
    try:
        # Conectar ao WebSocket do Chrome DevTools
        ws_url = f"ws://localhost:{ctx['porta']}/devtools/page/{ctx['targetId']}"
        ws_browser = create_connection(ws_url)
        
        # Habilitar eventos de Runtime para capturar dialogs
        enable_runtime_cmd = {
            "id": 1,
            "method": "Runtime.enable"
        }
        ws_browser.send(json.dumps(enable_runtime_cmd))
        
        # Aguardar resposta
        while True:
            resp = json.loads(ws_browser.recv())
            if resp.get("id") == 1:
                break
        
        # Configurar handler para dialogs JavaScript
        dialog_handler_script = f"""
        // Sobrescrever funções de dialog nativas
        window.originalAlert = window.alert;
        window.originalConfirm = window.confirm;
        window.originalPrompt = window.prompt;
        
        window.alert = function(message) {{
            console.log('Alert interceptado:', message);
            {'return true;' if request.auto_accept else 'return window.originalAlert(message);'}
        }};
        
        window.confirm = function(message) {{
            console.log('Confirm interceptado:', message);
            {'return true;' if request.auto_accept else 'return window.originalConfirm(message);'}
        }};
        
        window.prompt = function(message, defaultText) {{
            console.log('Prompt interceptado:', message);
            {'return "' + (request.default_prompt_text or '') + '";' if request.auto_accept else 'return window.originalPrompt(message, defaultText);'}
        }};
        
        // Handler para beforeunload
        window.addEventListener('beforeunload', function(e) {{
            {'delete e["returnValue"]; return undefined;' if request.auto_accept else ''}
        }});
        
        console.log('Handlers de dialog configurados - Auto-accept: {request.auto_accept}');
        """
        
        # Executar script de configuração
        exec_cmd = {
            "id": 2,
            "method": "Runtime.evaluate",
            "params": {
                "expression": dialog_handler_script,
                "returnByValue": True
            }
        }
        ws_browser.send(json.dumps(exec_cmd))
        
        # Aguardar resposta
        while True:
            resp = json.loads(ws_browser.recv())
            if resp.get("id") == 2:
                break
        
        ws_browser.close()
        
        # Armazenar configuração no contexto
        ctx["dialog_config"] = {
            "auto_accept": request.auto_accept,
            "default_prompt_text": request.default_prompt_text
        }
        
        return {
            "ok": True,
            "mensagem": "Handlers de dialog configurados com sucesso",
            "auto_accept": request.auto_accept,
            "default_prompt_text": request.default_prompt_text
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao configurar handlers de dialog: {str(e)}")