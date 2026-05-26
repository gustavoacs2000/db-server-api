import mariadb
from typing import Any, Dict, List
from configparser import ConfigParser
from ..config.settings import get_db_config, mariadb_ativo

class MariaDBConnection:
    def __init__(self, config: ConfigParser):
        self.config = config
        if not mariadb_ativo(config):
            raise RuntimeError("MariaDB está desabilitado por configuração")
        self.conn_params = get_db_config(config)

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Executa uma consulta SELECT e retorna os resultados."""
        conn = mariadb.connect(**self.conn_params)
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query)
            results = cursor.fetchall()
            return results
        finally:
            conn.close()

    def execute_command(self, command: str) -> int:
        """Executa um comando INSERT/UPDATE/DELETE e retorna o número de linhas afetadas."""
        conn = mariadb.connect(**self.conn_params)
        try:
            cursor = conn.cursor()
            cursor.execute(command)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def execute_many(self, command: str, params: List[tuple]) -> int:
        """Executa um comando com múltiplos conjuntos de parâmetros."""
        conn = mariadb.connect(**self.conn_params)
        try:
            cursor = conn.cursor()
            cursor.executemany(command, params)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def sanitize_identifier(self, identifier: str) -> str:
        """Sanitiza identificadores SQL para prevenir SQL injection."""
        # Remove caracteres não permitidos e aspas
        sanitized = "".join(c for c in identifier if c.isalnum() or c == "_")
        return sanitized