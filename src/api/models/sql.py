from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class SQLQueryRequest(BaseModel):
    """Modelo para requisição de consulta SQL (SELECT)."""
    
    sql: str = Field(
        ...,
        description="Comando SQL SELECT a ser executado",
        example="SELECT * FROM usuarios WHERE ativo = 1"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "sql": "SELECT * FROM usuarios WHERE ativo = 1"
                },
                {
                    "sql": "SELECT nome, email FROM clientes ORDER BY nome LIMIT 10"
                },
                {
                    "sql": "SELECT COUNT(*) as total FROM pedidos WHERE data_pedido >= '2024-01-01'"
                }
            ]
        }

class SQLCommandRequest(BaseModel):
    """Modelo para requisição de comando SQL (INSERT, UPDATE, DELETE)."""
    
    sql: str = Field(
        ...,
        description="Comando SQL de modificação a ser executado",
        example="INSERT INTO usuarios (nome, email) VALUES ('João', 'joao@email.com')"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "sql": "INSERT INTO usuarios (nome, email) VALUES ('João', 'joao@email.com')"
                },
                {
                    "sql": "UPDATE produtos SET preco = 29.99 WHERE id = 1"
                },
                {
                    "sql": "DELETE FROM logs WHERE data_log < '2024-01-01'"
                }
            ]
        }