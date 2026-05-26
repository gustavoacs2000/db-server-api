from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from typing import Optional
import xml.etree.ElementTree as ET
import json
import re
from ...database.mariadb import MariaDBConnection
from ...database.sqlite import SQLiteDB
from ...config.settings import load_config

router = APIRouter()

@router.post(
    "/getsql",
    summary="Executar consulta SQL no MariaDB (SEMPRE text/plain)",
    description="""Executa uma consulta SQL SELECT no banco MariaDB e retorna os resultados.
    
    **⚠️ IMPORTANTE: Esta rota SEMPRE trata o body como texto puro, independente do Content-Type enviado.**
    
    **Funcionalidade:**
    - Executa comandos SELECT no banco de dados MariaDB
    - Retorna os dados encontrados em formato JSON com chave "resultado"
    - Ideal para consultas de leitura de dados
    - **Content-Type completamente ignorado**: mesmo enviando application/json, será tratado como texto puro
    - **Nunca processa JSON**: o body é sempre interpretado como comando SQL direto
    
    **Exemplos de uso:**
    - Body: `SELECT * FROM usuarios`
    - Com filtros: `SELECT nome, email FROM clientes WHERE ativo = 1`
    - Com agregação: `SELECT COUNT(*) as total FROM pedidos WHERE data_pedido >= '2024-01-01'`
    """
)
async def get_sql(request: Request):
    try:
        # Lê o body da requisição
        body = await request.body()
        sql = body.decode("utf-8").strip()
        
        # SEMPRE trata como texto plano, independente do content-type
        # Nunca processa como JSON, sempre como texto puro
        
        if not sql or not sql.strip():
            return {"ok": False, "erro": "SQL não fornecido ou vazio"}
        
        config = load_config()
        db = MariaDBConnection(config)
        results = db.execute_query(sql)
        return {"ok": True, "resultado": results}
    except Exception as e:
        return {"ok": False, "erro": str(e)}



@router.post(
    "/getsqldb",
    summary="Executar consulta SQL no SQLite (SEMPRE text/plain)",
    description="""Executa uma consulta SQL SELECT no banco SQLite local e retorna os resultados.
    
    **⚠️ IMPORTANTE: Esta rota SEMPRE trata o body como texto puro, independente do Content-Type enviado.**
    
    **Funcionalidade:**
    - Executa comandos SELECT no banco de dados SQLite local
    - Retorna os dados encontrados em formato JSON com chave "resultado"
    - Ideal para consultas de leitura no banco local
    - **Content-Type completamente ignorado**: mesmo enviando application/json, será tratado como texto puro
    - **Nunca processa JSON**: o body é sempre interpretado como comando SQL direto
    
    **Exemplos de uso:**
    - Body: `SELECT * FROM usuarios`
    - Com filtros: `SELECT nome, email FROM clientes WHERE ativo = 1`
    - Com agregação: `SELECT COUNT(*) as total FROM pedidos WHERE data_pedido >= '2024-01-01'`
    """
)
async def get_sql_db(request: Request):
    try:
        # Lê o body da requisição
        body = await request.body()
        sql = body.decode("utf-8").strip()
        
        # SEMPRE trata como texto plano, independente do content-type
        # Nunca processa como JSON, sempre como texto puro
        
        if not sql or not sql.strip():
            return {"ok": False, "erro": "SQL não fornecido ou vazio"}
        
        db = SQLiteDB()
        results = await db.execute_query(sql)
        return {"ok": True, "resultado": results}
    except Exception as e:
        return {"ok": False, "erro": str(e)}

@router.post(
    "/setsql",
    summary="Executar comando SQL no MariaDB (SEMPRE text/plain)",
    description="""Executa comandos SQL de modificação (INSERT, UPDATE, DELETE) no banco MariaDB.
    
    **⚠️ IMPORTANTE: Esta rota SEMPRE trata o body como texto puro, independente do Content-Type enviado.**
    
    **Funcionalidade:**
    - Executa comandos INSERT, UPDATE, DELETE no banco de dados MariaDB
    - Retorna o número de linhas afetadas
    - Ideal para operações de escrita no banco
    - **Content-Type completamente ignorado**: mesmo enviando application/json, será tratado como texto puro
    - **Nunca processa JSON**: o body é sempre interpretado como comando SQL direto
    
    **Exemplos de uso:**
    - Body: `INSERT INTO usuarios (nome, email) VALUES ('João', 'joao@email.com')`
    - Atualizar dados: `UPDATE clientes SET ativo = 1 WHERE id = 123`
    - Deletar dados: `DELETE FROM pedidos WHERE data_pedido < '2023-01-01'`
    """
)
async def set_sql(request: Request):
    try:
        # Lê o body da requisição
        body = await request.body()
        sql = body.decode("utf-8").strip()
        
        # SEMPRE trata como texto plano, independente do content-type
        # Nunca processa como JSON, sempre como texto puro
        
        if not sql or not sql.strip():
            return {"ok": False, "erro": "SQL não fornecido ou vazio"}
        
        config = load_config()
        db = MariaDBConnection(config)
        affected_rows = db.execute_command(sql)
        return {"ok": True, "linhas_afetadas": affected_rows}
    except Exception as e:
        return {"ok": False, "erro": str(e)}

@router.post(
    "/setsqldb",
    summary="Executar comando SQL no SQLite (SEMPRE text/plain)",
    description="""Executa comandos SQL de modificação (INSERT, UPDATE, DELETE) no banco SQLite local.
    
    **⚠️ IMPORTANTE: Esta rota SEMPRE trata o body como texto puro, independente do Content-Type enviado.**
    
    **Funcionalidade:**
    - Executa comandos INSERT, UPDATE, DELETE no banco de dados SQLite local
    - Retorna o número de linhas afetadas
    - Ideal para operações de escrita no banco local
    - **Content-Type completamente ignorado**: mesmo enviando application/json, será tratado como texto puro
    - **Nunca processa JSON**: o body é sempre interpretado como comando SQL direto
    
    **Exemplos de uso:**
    - Body: `INSERT INTO usuarios (nome, email) VALUES ('João', 'joao@email.com')`
    - Atualizar dados: `UPDATE clientes SET ativo = 1 WHERE id = 123`
    - Deletar dados: `DELETE FROM pedidos WHERE data_pedido < '2023-01-01'`
    """
)
async def set_sql_db(request: Request):
    try:
        # Lê o body da requisição
        body = await request.body()
        sql = body.decode("utf-8").strip()
        
        # SEMPRE trata como texto plano, independente do content-type
        # Nunca processa como JSON, sempre como texto puro
        
        if not sql or not sql.strip():
            return {"ok": False, "erro": "SQL não fornecido ou vazio"}
        
        db = SQLiteDB()
        affected = await db.execute_command(sql)
        return {"ok": True, "linhas_afetadas": affected}
    except Exception as e:
        return {"ok": False, "erro": str(e)}

@router.post(
    "/setsqldbfull",
    summary="Executar múltiplas instruções SQL no SQLite (SEMPRE text/plain)",
    description="""Executa um script com múltiplas instruções SQL (ex.: vários INSERTs separados por ponto e vírgula) no banco SQLite local.
    
    **⚠️ IMPORTANTE: Esta rota SEMPRE trata o body como texto puro, independente do Content-Type enviado.**
    
    **Funcionalidade:**
    - Aceita múltiplas instruções separadas por `;` em um único body
    - Executa tudo em uma única transação
    - Retorna o total de mudanças aplicadas conforme reportado pelo SQLite
    - **Content-Type completamente ignorado**: mesmo enviando application/json, será tratado como texto puro
    - **Nunca processa JSON**: o body é sempre interpretado como script SQL direto
    
    **Exemplo de uso:**
    ```sql
    INSERT INTO log (status, log_texto) VALUES ('info', 'Teste 1 - setsqldbfull');
    INSERT INTO log (status, log_texto) VALUES ('info', 'Teste 2 - setsqldbfull');
    ```
    """
)
async def set_sql_db_full(request: Request):
    try:
        body = await request.body()
        script = body.decode("utf-8").strip()

        if not script:
            return {"ok": False, "erro": "SQL não fornecido ou vazio"}

        db = SQLiteDB()
        total_changes = await db.execute_script(script)
        return {"ok": True, "linhas_afetadas_total": total_changes}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@router.post(
    "/attachsqldb",
    summary="Registrar ATTACH DATABASE no SQLite (SEMPRE text/plain)",
    description="""Registra um ATTACH DATABASE persistente (por alias) que será aplicado em todas as conexões de SQLite.

    Envie o comando em texto puro, por exemplo:
    ATTACH DATABASE 'file:C:/RPA/Contas Manuais/origem/db_server_api.db?mode=ro' AS origem;

    Depois, qualquer /getsqldb ou /setsqldb enxergará o alias (ex.: origem.minha_tabela).
    """
)
async def attach_sql_db(request: Request):
    try:
        body = await request.body()
        cmd = body.decode("utf-8").strip()
        if not cmd:
            return {"ok": False, "erro": "Comando ATTACH não fornecido ou vazio"}

        m = re.search(r"ATTACH\s+DATABASE\s+'([^']+)'\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)", cmd, re.IGNORECASE)
        if not m:
            return {"ok": False, "erro": "Formato inválido. Use: ATTACH DATABASE 'file:...?...' AS alias;"}

        uri, alias = m.group(1), m.group(2)
        db = SQLiteDB()
        db.register_attachment(alias, uri)

        # Validação rápida: consulta em sqlite_master do alias
        await db.execute_query(f"SELECT name FROM {alias}.sqlite_master LIMIT 1")

        return {"ok": True, "registrado": {"alias": alias, "uri": uri}}
    except Exception as e:
        return {"ok": False, "erro": str(e)}

@router.post(
    "/detachsqldb",
    summary="Remover ATTACH DATABASE no SQLite (text/plain)",
    description="Remove o alias registrado e executa DETACH DATABASE."
)
async def detach_sql_db(request: Request):
    try:
        body = await request.body()
        cmd = body.decode("utf-8").strip()
        if not cmd:
            return {"ok": False, "erro": "Comando DETACH não fornecido ou vazio"}

        m = re.search(r"DETACH\s+DATABASE\s+([A-Za-z_][A-Za-z0-9_]*)", cmd, re.IGNORECASE)
        if not m:
            return {"ok": False, "erro": "Formato inválido. Use: DETACH DATABASE alias;"}

        alias = m.group(1)
        db = SQLiteDB()
        detached = await db.detach_attachment(alias)
        return {"ok": True, "alias": alias, "detached": detached}
    except Exception as e:
        return {"ok": False, "erro": str(e)}