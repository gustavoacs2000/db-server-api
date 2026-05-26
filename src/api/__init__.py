# Módulo de API do RPA DB Server
from fastapi import FastAPI
from ..core.middleware import BodyReaderMiddleware, validar_token, handle_exceptions
from ..database.sqlite import SQLiteDB

def create_app() -> FastAPI:
    """Cria e configura a aplicação FastAPI."""
    app = FastAPI()
    
    # Adiciona middlewares
    app.add_middleware(BodyReaderMiddleware)
    app.middleware("http")(validar_token)
    app.middleware("http")(handle_exceptions)
    
    return app