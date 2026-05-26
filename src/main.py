import sys
import signal
import os
from pathlib import Path

# Adiciona o diretório pai ao path para permitir imports relativos
src_path = str(Path(__file__).parent.parent)
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Função para ignorar sinais de interrupção
def ignore_signal(signum, frame):
    """Ignora sinais de interrupção para manter o servidor rodando."""
    try:
        from src.core.logging import get_error_logger
        error_logger = get_error_logger()
        error_logger.warning(f"Sinal {signum} ignorado - Servidor mantido ativo")
    except:
        pass
    print(f"[AVISO] Sinal de interrupção {signum} ignorado - Servidor continuará rodando")

# Configura handlers para ignorar sinais de interrupção
try:
    # Ignora SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, ignore_signal)
    # Ignora SIGTERM (terminação)
    signal.signal(signal.SIGTERM, ignore_signal)
    # No Windows, também ignora SIGBREAK (Ctrl+Break)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, ignore_signal)
except Exception as e:
    print(f"[AVISO] Não foi possível configurar handlers de sinal: {e}")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import uvicorn
import argparse
import os
import json
import socket
from datetime import datetime
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Import do TwoCaptcha para garantir que seja incluído no executável
try:
    from twocaptcha.solver import TwoCaptcha
    TWOCAPTCHA_AVAILABLE = True
except ImportError:
    TWOCAPTCHA_AVAILABLE = False

# Importações internas
from src.core.scheduler import init_scheduler
from src.core.logging import setup_logging
from src.config.paths import setup_paths
from src.database.sqlite import SQLiteDB
from src.api.routes import sql, python, log, scheduler, stream, browser, ocr, regex

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação."""
    try:
        # Inicialização
        setup_paths()
        setup_logging()
        
        # Importa o logger de erros após setup_logging
        from src.core.logging import get_error_logger
        error_logger = get_error_logger()
        
        try:
            init_scheduler()
            error_logger.info("Scheduler inicializado com sucesso")
        except Exception as e:
            error_logger.error(f"Erro ao inicializar scheduler: {str(e)}")
            raise
        
        # Inicializa o banco SQLite
        try:
            db = SQLiteDB()
            await db.initialize()
            error_logger.info("Banco SQLite inicializado com sucesso")
        except Exception as e:
            error_logger.error(f"Erro ao inicializar banco SQLite: {str(e)}")
            raise
        
        error_logger.info("Aplicação inicializada com sucesso")
        
    except Exception as e:
        # Se o logger ainda não foi configurado, usa print
        try:
            from src.core.logging import get_error_logger
            error_logger = get_error_logger()
            error_logger.error(f"Erro crítico durante inicialização da aplicação: {str(e)}")
        except:
            print(f"[ERRO CRÍTICO] Falha na inicialização: {str(e)}")
        raise
    
    yield
    
    # Limpeza ao encerrar
    try:
        from src.core.scheduler import stop_scheduler
        stop_scheduler()
        
        try:
            from src.core.logging import get_error_logger
            error_logger = get_error_logger()
            error_logger.info("Aplicação encerrada com sucesso")
        except:
            pass
    except Exception as e:
        try:
            from src.core.logging import get_error_logger
            error_logger = get_error_logger()
            error_logger.error(f"Erro durante encerramento da aplicação: {str(e)}")
        except:
            print(f"[ERRO] Falha no encerramento: {str(e)}")

def create_app() -> FastAPI:
    """Cria e configura a aplicação FastAPI."""
    app = FastAPI(
        title="RPA DB Server API",
        description="""# RPA DB Server API
        
## Descrição
API completa para automação de processos RPA (Robotic Process Automation) com suporte abrangente a:

### 🌐 Navegador Web
- Controle completo do Chrome/Chromium
- Execução de JavaScript
- Captura de screenshots e geração de PDFs
- Gerenciamento de abas e downloads
- Modos especiais (kiosk, fullscreen, incógnito)

### 🗄️ Banco de Dados
- Suporte a MariaDB e SQLite
- Execução de queries SQL com diferentes formatos de resposta
- Operações CRUD completas

### 🐍 Execução Python
- Execução síncrona e assíncrona de código Python
- Gerenciamento de contextos isolados
- Suporte a bibliotecas externas

### 📊 Sistema de Logs
- Gravação e consulta de logs
- Filtros avançados por data, status e texto
- Suporte a múltiplos bancos

### ⏰ Agendador de Tarefas
- Agendamento com triggers cron, interval e date
- Execução de código Python agendado
- Gerenciamento completo de tarefas

### 📺 Streaming de Tela
- Transmissão em tempo real da tela
- Controle de FPS e escala
- Interface web integrada

### 🔍 OCR (Reconhecimento Óptico)
- Processamento de PDFs e imagens
- Extração de texto com Tesseract
- Pré-processamento de imagens

### 🔤 Processamento Regex
- Aplicação de expressões regulares em arquivos
- Extração de dados estruturados
- Processamento em lote

## Autenticação
Todas as rotas (exceto `/stream` e `/tela`) requerem token de autorização no header:
```
Authorization: Bearer {token}
```

## Exemplos de Uso
Consulte a coleção Postman incluída no projeto para exemplos detalhados de todas as funcionalidades.
        """,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        contact={
            "name": "RPA DB Server API",
            "url": "https://github.com/seu-usuario/rpa-db-server",
            "email": "contato@exemplo.com"
        },
        license_info={
            "name": "MIT License",
            "url": "https://opensource.org/licenses/MIT"
        },
        # servers será definido automaticamente pelo FastAPI baseado na porta atual
        openapi_tags=[
            {
                "name": "🏠 Status",
                "description": "Verificação do status da API"
            },
            {
                "name": "💾 Banco de Dados",
                "description": "Operações SQL com MariaDB e SQLite"
            },
            {
                "name": "🐍 Python",
                "description": "Execução de código Python com contextos isolados"
            },
            {
                "name": "📋 Logs",
                "description": "Sistema de logs e auditoria"
            },
            {
                "name": "⏰ Agendador",
                "description": "Agendamento de tarefas com cron e intervalos"
            },
            {
                "name": "📹 Streaming",
                "description": "Captura e streaming de tela em tempo real"
            },
            {
                "name": "🌐 Navegador",
                "description": "Automação de navegador web com Chrome"
            },
            {
                "name": "🔍 OCR",
                "description": "Reconhecimento óptico de caracteres"
            },
            {
                "name": "🔤 Regex",
                "description": "Processamento de texto com expressões regulares"
            }
        ]
    )
    
    # Configuração CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Adiciona middlewares de autenticação e tratamento de exceções
    from src.core.middleware import BodyReaderMiddleware, validar_token, handle_exceptions, RequestLoggingMiddleware
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(BodyReaderMiddleware)
    app.middleware("http")(validar_token)
    app.middleware("http")(handle_exceptions)
    
    # Registro das rotas com tags organizadas
    app.include_router(
        sql.router,
        tags=["💾 Banco de Dados"]
    )
    app.include_router(
        python.router,
        tags=["🐍 Python"]
    )
    app.include_router(
        log.router,
        prefix="/log",
        tags=["📋 Logs"]
    )
    app.include_router(
        scheduler.router,
        prefix="/scheduler",
        tags=["⏰ Agendador"]
    )
    app.include_router(
        stream.router,
        tags=["📹 Streaming"]
    )
    app.include_router(
        browser.router,
        tags=["🌐 Navegador"]
    )
    app.include_router(
        ocr.router,
        tags=["🔍 OCR"]
    )
    app.include_router(
        regex.router,
        tags=["🔤 Regex"]
    )
    
    # Configuração de arquivos estáticos
    from src.config.settings import get_base_path
    static_path = os.path.join(get_base_path(), "public")
    if os.path.exists(static_path):
        app.mount("/static", StaticFiles(directory=static_path), name="static")
    
    @app.get("/", tags=["🏠 Status"], summary="Verifica status da API")
    async def root():
        """Endpoint para verificar se a API está funcionando."""
        return {"mensagem": "RPA DB Server - OK"}
    
    return app

app = create_app()

def get_free_port():
    """Retorna uma porta livre disponível."""
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def get_system_ips():
    """Retorna todos os IPs disponíveis no sistema."""
    ips = []
    
    # Método 1: Usando psutil se disponível
    if PSUTIL_AVAILABLE:
        try:
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET and addr.address != '127.0.0.1':
                        ips.append({
                            'ip': addr.address,
                            'interface': interface,
                            'method': 'psutil'
                        })
        except Exception:
            pass
    
    # Método 2: Usando socket para descobrir IP principal
    if not ips:
        try:
            # Conecta a um endereço externo para descobrir o IP local
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                if local_ip != '127.0.0.1':
                    ips.append({
                        'ip': local_ip,
                        'interface': 'primary',
                        'method': 'socket'
                    })
        except Exception:
            pass
    
    # Método 3: Usando hostname como fallback
    if not ips:
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            if local_ip != '127.0.0.1':
                ips.append({
                    'ip': local_ip,
                    'interface': 'hostname',
                    'method': 'hostname'
                })
        except Exception:
            pass
    
    # Sempre adiciona localhost
    ips.append({
        'ip': '127.0.0.1',
        'interface': 'loopback',
        'method': 'localhost'
    })
    
    return ips

def create_server_info_json(port: int):
    """Cria o arquivo JSON com informações do servidor."""
    from src.config.settings import get_base_path
    
    # Obtém todos os IPs do sistema
    system_ips = get_system_ips()
    
    info_path = os.path.join(get_base_path(), "db_server_api.json")
    info_data = {
        "pid": os.getpid(),
        "port": port,
        "start_time": datetime.now().strftime("%Y%m%d%H%M%S"),
        "ips": system_ips,
        "urls": [f"http://{ip_info['ip']}:{port}" for ip_info in system_ips]
    }
    
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(info_data, f, indent=2, ensure_ascii=False)
    
    print(f"Arquivo de informações criado: {info_path}")
    return info_path

def main():
    """Função principal para execução do servidor."""
    try:
        # Detecta se está sendo executado via outra ferramenta
        parent_process = None
        is_automated_execution = False
        
        try:
            if PSUTIL_AVAILABLE:
                current_process = psutil.Process()
                parent_process = current_process.parent()
                if parent_process:
                    parent_name = parent_process.name().lower()
                    # Detecta se foi executado por ferramentas automatizadas
                    automated_tools = ['cmd.exe', 'powershell.exe', 'pwsh.exe', 'python.exe', 'pythonw.exe', 'subprocess', 'popen']
                    is_automated_execution = any(tool in parent_name for tool in automated_tools)
                    
                    if is_automated_execution:
                        print(f"[INFO] Detectada execução via ferramenta automatizada: {parent_name}")
                        print(f"[INFO] Servidor configurado para máxima resistência a interrupções")
        except Exception as e:
            print(f"[AVISO] Não foi possível detectar processo pai: {e}")
        
        parser = argparse.ArgumentParser(description="RPA DB Server")
        parser.add_argument("--host", default="0.0.0.0", help="Host de bind do servidor")
        parser.add_argument("--port", type=int, default=0, help="Porta do servidor (0 = automática)")
        parser.add_argument("--reload", action="store_true", help="Ativar reload automático")
        args = parser.parse_args()
        
        # Determina a porta
        if args.port == 0:
            # Tenta ler a porta do config.ini
            try:
                from src.config.settings import load_config
                cfg = load_config()
                config_port = cfg.getint("server", "port", fallback=0)
                if config_port > 0:
                    port = config_port
                else:
                    port = get_free_port()
            except Exception as e:
                print(f"[AVISO] Erro ao ler configuração de porta: {str(e)}")
                port = get_free_port()
        else:
            port = args.port
        
        # Cria o arquivo JSON com informações do servidor
        try:
            create_server_info_json(port)
        except Exception as e:
            print(f"[AVISO] Erro ao criar arquivo de informações do servidor: {str(e)}")
        
        # Obtém e exibe todos os IPs disponíveis
        system_ips = get_system_ips()
        print(f"\n🟢 Servidor iniciado na porta {port}")
        print("📡 URLs disponíveis:")
        for ip_info in system_ips:
            url = f"http://{ip_info['ip']}:{port}"
            interface_info = f" ({ip_info['interface']})" if ip_info['interface'] != 'auto-detected' else ""
            print(f"   • {url}{interface_info}")
        print()
        
        # Executa o servidor com tratamento de erros e reinicialização automática
        while True:
            try:
                # Testa se a porta está disponível antes de iniciar o uvicorn
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    test_socket.bind((args.host, port))
                    test_socket.close()
                except OSError as bind_error:
                    # Erro de bind detectado antes do uvicorn
                    error_msg = f"Erro de bind/porta: {str(bind_error)}"
                    try:
                        # Força a inicialização do logging se ainda não foi feita
                        setup_paths()
                        setup_logging()
                        from src.core.logging import get_error_logger
                        error_logger = get_error_logger()
                        error_logger.error(f"ERRO DE INICIALIZAÇÃO - {error_msg}")
                        
                        # Se for erro de porta ocupada, não tenta reiniciar
                        if "10048" in str(bind_error) or "Address already in use" in str(bind_error) or "bind" in str(bind_error).lower():
                            error_logger.error("Porta já está em uso - Encerrando aplicação")
                            print(f"[ERRO CRÍTICO] {error_msg}")
                            print("[INFO] Porta já está em uso. Verifique se outro servidor está rodando.")
                            sys.exit(1)
                    except Exception as log_error:
                        print(f"[AVISO] Erro ao logar: {str(log_error)}")
                        pass
                    
                    print(f"[ERRO] {error_msg} - Tentando reiniciar em 5 segundos...")
                    import time
                    time.sleep(5)
                    continue
                
                # Se chegou aqui, a porta está disponível - inicia o uvicorn
                # Configurações para tornar o servidor mais resistente
                uvicorn_config = {
                    "app": app,
                    "host": args.host,
                    "port": port,
                    "reload": args.reload,
                    "log_config": None,
                    "access_log": False,
                    "server_header": False,
                    "date_header": False,
                    "use_colors": False,
                    "loop": "asyncio",
                    "lifespan": "on"
                }
                
                # Inicia o uvicorn com configurações robustas
                try:
                    uvicorn.run(**uvicorn_config)
                    # Se chegou aqui, o servidor foi encerrado normalmente
                    print("[INFO] Servidor uvicorn encerrado normalmente")
                    break
                except SystemExit as e:
                    # Captura SystemExit e reinicia o servidor
                    print(f"[AVISO] SystemExit capturado ({e}) - Reiniciando servidor em 3 segundos...")
                    try:
                        from src.core.logging import get_error_logger
                        error_logger = get_error_logger()
                        error_logger.warning(f"SystemExit capturado - Reiniciando servidor: {e}")
                    except:
                        pass
                    import time
                    time.sleep(3)
                    continue
                except Exception as uvicorn_error:
                    # Outros erros do uvicorn
                    print(f"[ERRO] Erro no uvicorn: {uvicorn_error} - Reiniciando em 3 segundos...")
                    try:
                        from src.core.logging import get_error_logger
                        error_logger = get_error_logger()
                        error_logger.error(f"Erro no uvicorn - Reiniciando: {uvicorn_error}")
                    except:
                        pass
                    import time
                    time.sleep(3)
                    continue
            except KeyboardInterrupt:
                print("\n[AVISO] Tentativa de interrupção no uvicorn detectada - Reiniciando servidor...")
                try:
                    from src.core.logging import get_error_logger
                    error_logger = get_error_logger()
                    error_logger.warning("Tentativa de interrupção no uvicorn ignorada - Reiniciando servidor")
                except:
                    pass
                continue  # Reinicia o loop
            except OSError as e:
                # Erro específico de bind/porta (como porta já ocupada)
                error_msg = f"Erro de bind/porta: {str(e)}"
                try:
                    # Força a inicialização básica do logging se ainda não foi feita
                    setup_paths()
                    setup_logging()
                    from src.core.logging import get_error_logger
                    error_logger = get_error_logger()
                    error_logger.error(f"ERRO DE INICIALIZAÇÃO - {error_msg}")
                    
                    # Se for erro de porta ocupada, não tenta reiniciar
                    if "10048" in str(e) or "Address already in use" in str(e) or "bind" in str(e).lower():
                        error_logger.error("Porta já está em uso - Encerrando aplicação")
                        print(f"[ERRO CRÍTICO] {error_msg}")
                        print("[INFO] Porta já está em uso. Verifique se outro servidor está rodando.")
                        sys.exit(1)
                except:
                    pass
                
                print(f"[ERRO] {error_msg} - Tentando reiniciar em 5 segundos...")
                import time
                time.sleep(5)
                continue
            except Exception as e:
                # Outros erros gerais
                try:
                    # Força a inicialização básica do logging se ainda não foi feita
                    setup_paths()
                    setup_logging()
                    from src.core.logging import get_error_logger
                    error_logger = get_error_logger()
                    error_logger.error(f"Erro crítico ao executar servidor uvicorn: {str(e)} - Tentando reiniciar...")
                except:
                    pass
                
                print(f"[ERRO] Falha no servidor: {str(e)} - Reiniciando em 5 segundos...")
                import time
                time.sleep(5)  # Aguarda 5 segundos antes de reiniciar
                continue  # Reinicia o loop
            
    except KeyboardInterrupt:
        print("\n[AVISO] Tentativa de interrupção detectada (Ctrl+C) - Servidor continuará rodando")
        print("[INFO] Para parar o servidor, use o gerenciador de tarefas ou comando 'taskkill'")
        try:
            from src.core.logging import get_error_logger
            error_logger = get_error_logger()
            error_logger.warning("Tentativa de interrupção via Ctrl+C ignorada - Servidor mantido ativo")
        except:
            pass
        
        # Reinicia o servidor automaticamente após tentativa de interrupção
        print("[INFO] Reiniciando servidor...")
        main()  # Chama recursivamente para manter o servidor ativo
    except Exception as e:
        # Tenta logar o erro no error.log
        try:
            setup_paths()
            setup_logging()
            from src.core.logging import get_error_logger
            error_logger = get_error_logger()
            error_logger.error(f"Erro crítico na função main: {str(e)}")
        except:
            pass
        
        print(f"[ERRO CRÍTICO] Falha na inicialização do servidor: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()