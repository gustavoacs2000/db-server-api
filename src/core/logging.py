import os
import sys
import logging
import configparser
from logging.handlers import TimedRotatingFileHandler
from ..config.settings import get_base_path

# Loggers específicos para diferentes tipos de log
request_logger = None
error_logger = None

def get_log_path() -> str:
    """Retorna o caminho do arquivo de log principal."""
    base = get_base_path()
    log_dir = os.path.join(base, "logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "server.log")

def get_requests_log_path() -> str:
    """Retorna o caminho do arquivo de log de requisições."""
    base = get_base_path()
    log_dir = os.path.join(base, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Lê configuração do config.ini
    config = configparser.ConfigParser()
    config_path = os.path.join(get_base_path(), "config.ini")
    requests_file = "requests.log"  # Valor padrão
    
    if os.path.exists(config_path):
        config.read(config_path)
        if config.has_option('logging', 'log_requests_file'):
            requests_file = config.get('logging', 'log_requests_file')
    
    return os.path.join(log_dir, requests_file)

def get_errors_log_path() -> str:
    """Retorna o caminho do arquivo de log de erros."""
    base = get_base_path()
    log_dir = os.path.join(base, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Lê configuração do config.ini
    config = configparser.ConfigParser()
    config_path = os.path.join(get_base_path(), "config.ini")
    errors_file = "errors.log"  # Valor padrão
    
    if os.path.exists(config_path):
        config.read(config_path)
        if config.has_option('logging', 'log_errors_file'):
            errors_file = config.get('logging', 'log_errors_file')
    
    return os.path.join(log_dir, errors_file)

def ensure_logging_config() -> None:
    """Garante que todas as configurações de logging estejam presentes no config.ini."""
    config = configparser.ConfigParser()
    config_path = os.path.join(get_base_path(), "config.ini")
    
    # Configurações padrão de logging
    default_logging_config = {
        'log_terminal': 'true',
        'log_requests_separate': 'true',
        'log_errors_separate': 'true',
        'log_exclude_routes': '/docs,/openapi.json,/favicon.ico',
        'log_include_routes': '*',
        'log_requests_file': 'requests.log',
        'log_errors_file': 'errors.log'
    }
    
    config_updated = False
    
    if os.path.exists(config_path):
        config.read(config_path)
    
    # Cria seção [logging] se não existir
    if not config.has_section('logging'):
        config.add_section('logging')
        config_updated = True
        print("[INFO] Seção [logging] criada no config.ini")
    
    # Verifica e adiciona cada configuração ausente
    for key, default_value in default_logging_config.items():
        if not config.has_option('logging', key):
            config.set('logging', key, default_value)
            config_updated = True
            print(f"[INFO] Configuração '{key}' adicionada ao config.ini com valor padrão: {default_value}")
    
    # Salva o arquivo se houve alterações
    if config_updated:
        with open(config_path, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        print("[INFO] Configurações de logging atualizadas no config.ini")

def setup_logging() -> None:
    """Configura o sistema de logging da aplicação."""
    global request_logger, error_logger
    
    # Garante que todas as configurações de logging estejam presentes
    ensure_logging_config()
    
    # Remove handlers existentes
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Lê configuração do config.ini
    config = configparser.ConfigParser()
    config_path = os.path.join(get_base_path(), "config.ini")
    log_terminal = True  # Valor padrão
    log_requests_separate = False
    log_errors_separate = False
    
    print(f"[DEBUG] Config path: {config_path}")
    print(f"[DEBUG] Config exists: {os.path.exists(config_path)}")
    
    if os.path.exists(config_path):
        config.read(config_path)
        
        # Lê os valores das configurações
        if config.has_option('logging', 'log_terminal'):
            log_terminal = config.getboolean('logging', 'log_terminal')
        if config.has_option('logging', 'log_requests_separate'):
            log_requests_separate = config.getboolean('logging', 'log_requests_separate')
        if config.has_option('logging', 'log_errors_separate'):
            log_errors_separate = config.getboolean('logging', 'log_errors_separate')
    
    print(f"[DEBUG] log_terminal: {log_terminal}")
    print(f"[DEBUG] log_requests_separate: {log_requests_separate}")
    print(f"[DEBUG] log_errors_separate: {log_errors_separate}")
    print(f"[DEBUG] Requests log path: {get_requests_log_path()}")
    print(f"[DEBUG] Errors log path: {get_errors_log_path()}")
    
    # Configuração do formato
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    
    # Handler para arquivo principal com rotação diária
    file_handler = TimedRotatingFileHandler(
        get_log_path(),
        when='midnight',
        interval=1,
        backupCount=30,  # Mantém 30 dias de logs
        encoding='utf-8',
        utc=False
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    # Define o sufixo do arquivo rotacionado (YYYY-MM-DD)
    file_handler.suffix = "%Y-%m-%d"
    
    # Configuração do logger root
    logging.root.setLevel(logging.INFO)
    logging.root.addHandler(file_handler)
    
    # Handler para console (opcional baseado na configuração)
    console_handler = None
    if log_terminal:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        logging.root.addHandler(console_handler)
    
    # Configuração de loggers específicos para requisições
    if log_requests_separate:
        print(f"[DEBUG] Configurando logger de requisições...")
        global request_logger
        request_logger = logging.getLogger('requests')
        request_logger.setLevel(logging.INFO)
        request_logger.propagate = False  # Evita duplicação no logger root
        
        requests_path = get_requests_log_path()
        print(f"[DEBUG] Criando handler para: {requests_path}")
        # Usando TimedRotatingFileHandler para rotação diária
        request_handler = TimedRotatingFileHandler(
            requests_path,
            when='midnight',
            interval=1,
            backupCount=30,  # Mantém 30 dias de logs
            encoding='utf-8',
            utc=False
        )
        # Define o sufixo do arquivo rotacionado (YYYY-MM-DD)
        request_handler.suffix = "%Y-%m-%d"
        request_handler.setFormatter(formatter)
        request_logger.addHandler(request_handler)
        print(f"[DEBUG] Handler de requisições adicionado")
        
        # Força a criação do arquivo de log
        request_logger.info("Logger de requisições inicializado")
        
        # Força o flush do handler
        for handler in request_logger.handlers:
            handler.flush()
        
        if log_terminal and console_handler:
            request_logger.addHandler(console_handler)
    
    # Configuração de loggers específicos para erros
    if log_errors_separate:
        print(f"[DEBUG] Configurando logger de erros...")
        global error_logger
        error_logger = logging.getLogger('errors')
        error_logger.setLevel(logging.ERROR)
        error_logger.propagate = False  # Evita duplicação no logger root
        
        errors_path = get_errors_log_path()
        print(f"[DEBUG] Criando handler de erros para: {errors_path}")
        # Usando TimedRotatingFileHandler para rotação diária
        error_handler = TimedRotatingFileHandler(
            errors_path,
            when='midnight',
            interval=1,
            backupCount=30,  # Mantém 30 dias de logs
            encoding='utf-8',
            utc=False
        )
        # Define o sufixo do arquivo rotacionado (YYYY-MM-DD)
        error_handler.suffix = "%Y-%m-%d"
        error_handler.setFormatter(formatter)
        error_logger.addHandler(error_handler)
        print(f"[DEBUG] Handler de erros adicionado")
        
        # Força a criação do arquivo de log
        error_logger.error("Logger de erros inicializado")
        
        # Força o flush do handler
        for handler in error_logger.handlers:
            handler.flush()
        
        if log_terminal and console_handler:
            error_logger.addHandler(console_handler)
    
    # Garante que todos os loggers usem a mesma configuração
    logging.getLogger().setLevel(logging.INFO)

def get_request_logger():
    """Retorna o logger específico para requisições ou o logger padrão."""
    global request_logger
    print(f"[DEBUG] get_request_logger: request_logger = {request_logger}")
    if request_logger:
        print(f"[DEBUG] Retornando request_logger específico")
        return request_logger
    print(f"[DEBUG] Retornando logger padrão")
    return logging.getLogger()

def get_error_logger():
    """Retorna o logger específico para erros ou o logger padrão."""
    global error_logger
    if error_logger:
        return error_logger
    return logging.getLogger()

def should_log_route(route_path: str) -> bool:
    """Verifica se uma rota deve ser logada baseado nas configurações."""
    config = configparser.ConfigParser()
    config_path = os.path.join(get_base_path(), "config.ini")
    
    if not os.path.exists(config_path):
        return True
    
    config.read(config_path)
    
    # Verifica rotas excluídas
    if config.has_option('logging', 'log_exclude_routes'):
        exclude_routes = config.get('logging', 'log_exclude_routes').split(',')
        for exclude_route in exclude_routes:
            exclude_route = exclude_route.strip()
            if exclude_route and route_path.startswith(exclude_route):
                return False
    
    # Verifica rotas incluídas (se não for *, deve estar na lista)
    if config.has_option('logging', 'log_include_routes'):
        include_routes = config.get('logging', 'log_include_routes').strip()
        if include_routes != '*':
            include_list = include_routes.split(',')
            for include_route in include_list:
                include_route = include_route.strip()
                if include_route and route_path.startswith(include_route):
                    return True
            return False
    
    return True