import os
import aiosqlite
from typing import Any, Dict, List
from ..config.settings import get_base_path

# Registro global de ATTACHs (alias -> URI do banco)
ATTACHMENTS: Dict[str, str] = {}

class SQLiteDB:
    def __init__(self):
        self.db_name = "db_server_api.db"
        self.db_path = os.path.join(get_base_path(), self.db_name)

    async def initialize(self) -> None:
        """Inicializa o banco de dados SQLite com a estrutura necessária."""
        if not os.path.exists(self.db_path):
            print(f"[DB] Criando banco SQLite em {self.db_path}")
        else:
            print(f"[DB] Usando banco SQLite existente: {self.db_path}")

        async with aiosqlite.connect(self.db_path, uri=True) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_criacao TEXT DEFAULT (datetime('now','localtime')),
                status TEXT,
                log_texto TEXT
            )
            """)
            await db.commit()

    async def _apply_attachments(self, db) -> None:
        """Aplica todos os ATTACHs registrados na conexão fornecida."""
        for alias, uri in ATTACHMENTS.items():
            # Usa exatamente o URI informado (pode conter file:... e query params como mode=ro)
            await db.execute(f"ATTACH DATABASE '{uri}' AS {alias}")

    def register_attachment(self, alias: str, uri: str) -> None:
        """Registra (ou atualiza) um ATTACH persistente por alias."""
        ATTACHMENTS[alias] = uri

    def list_attachments(self) -> Dict[str, str]:
        return ATTACHMENTS.copy()

    async def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Executa uma consulta SELECT e retorna os resultados."""
        async with aiosqlite.connect(self.db_path, uri=True) as db:
            await self._apply_attachments(db)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def execute_command(self, command: str) -> int:
        """Executa um comando INSERT/UPDATE/DELETE e retorna o número de linhas afetadas."""
        async with aiosqlite.connect(self.db_path, uri=True) as db:
            await self._apply_attachments(db)
            cursor = await db.execute(command)
            await db.commit()
            return cursor.rowcount

    async def execute_many(self, command: str, params: List[tuple]) -> int:
        """Executa um comando com múltiplos conjuntos de parâmetros."""
        async with aiosqlite.connect(self.db_path, uri=True) as db:
            await self._apply_attachments(db)
            cursor = await db.executemany(command, params)
            await db.commit()
            return cursor.rowcount

    async def execute_script(self, script: str) -> int:
        """Executa múltiplas instruções SQL separadas por ponto e vírgula em uma única transação.
        Retorna o total de mudanças aplicadas (linhas afetadas) conforme reportado pelo SQLite.
        """
        async with aiosqlite.connect(self.db_path, uri=True) as db:
            before = db.total_changes
            await self._apply_attachments(db)
            await db.executescript(script)
            await db.commit()
            after = db.total_changes
            return max(0, after - before)

    async def detach_attachment(self, alias: str) -> bool:
        """Remove um ATTACH registrado e tenta executar DETACH na conexão."""
        async with aiosqlite.connect(self.db_path, uri=True) as db:
            try:
                # Garante que o alias esteja anexado nesta conexão, caso registrado
                if alias in ATTACHMENTS:
                    await self._apply_attachments(db)
                await db.execute(f"DETACH DATABASE {alias}")
                await db.commit()
                # Remove do registro para não ser reaplicado em novas conexões
                if alias in ATTACHMENTS:
                    del ATTACHMENTS[alias]
                return True
            except Exception:
                # Mesmo se falhar o DETACH, removemos do registro
                if alias in ATTACHMENTS:
                    del ATTACHMENTS[alias]
                return False