import configparser
import os
import sys
import logging

CONFIG_OVERRIDE: str | None = None

def get_base_path() -> str:
    """Retorna o diretório base da aplicação."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_default_config() -> str:
    """Cria um arquivo config.ini padrão no diretório base."""
    config_path = os.path.join(get_base_path(), "config.ini")
    if os.path.exists(config_path):
        return config_path

    cfg = configparser.ConfigParser()
    cfg["server"] = {
        "port": "0"
    }
    cfg["database"] = {
        "usar_mariadb": "false",
        "host": "localhost",
        "port": "3306",
        "user": "root",
        "password": "Db@123",
        "database": ""
    }
    cfg["stream"] = {
        "habilitado": "true"
    }
    cfg["security"] = {
        "token": "RpaDbServerApi12345678"
    }

    with open(config_path, "w", encoding="utf-8") as f:
        cfg.write(f)
    
    logging.info("Arquivo config.ini padrão criado em: %s", config_path)
    return config_path

def load_config() -> configparser.ConfigParser:
    """Carrega as configurações do arquivo config.ini."""
    # Sempre usa o config.ini na pasta raiz (onde está o executável)
    config_path = os.path.join(get_base_path(), "config.ini")
    
    # Se existe um override específico, usa ele
    if CONFIG_OVERRIDE and os.path.exists(CONFIG_OVERRIDE):
        config_path = CONFIG_OVERRIDE
    
    # Se o config.ini não existe na pasta raiz, cria um padrão
    if not os.path.exists(config_path):
        config_path = create_default_config()
    
    # Carrega o arquivo de configuração
    cfg = configparser.ConfigParser()
    cfg.read(config_path, encoding="utf-8")
    logging.info("config.ini carregado de: %s", config_path)
    return cfg

def stream_ativo() -> bool:
    """Verifica se o streaming está habilitado nas configurações."""
    cfg = load_config()
    return cfg.getboolean("stream", "habilitado", fallback=True)

def get_api_token() -> str:
    """Retorna o token de API das configurações."""
    return load_config().get("security", "token", fallback="")

def get_db_config(cfg: configparser.ConfigParser) -> dict:
    """Retorna as configurações do banco de dados MariaDB."""
    if not cfg.getboolean("database", "usar_mariadb", fallback=True):
        raise RuntimeError("MariaDB está desabilitado por configuração.")
    return {
        "host": cfg.get("database", "host"),
        "port": cfg.getint("database", "port"),
        "user": cfg.get("database", "user"),
        "password": cfg.get("database", "password"),
        "database": cfg.get("database", "database")
    }

def mariadb_ativo(cfg: configparser.ConfigParser) -> bool:
    """Verifica se o MariaDB está habilitado nas configurações."""
    return cfg.getboolean("database", "usar_mariadb", fallback=True)