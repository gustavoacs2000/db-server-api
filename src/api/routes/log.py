from fastapi import APIRouter, Query, Request
from typing import Optional
from datetime import datetime, timedelta
import json
from ...database.mariadb import MariaDBConnection
from ...database.sqlite import SQLiteDB
from ...config.settings import load_config

router = APIRouter()



@router.get("/{banco}/{tabela}/listar")
async def listar_logs_mariadb(
    banco: str,
    tabela: str,
    status: Optional[str] = None,
    sistema: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None
):
    """Lista logs de uma tabela específica do MariaDB com filtros."""
    try:
        config = load_config()
        db = MariaDBConnection(config)
        
        # Sanitiza os nomes do banco e tabela
        banco_safe = db.sanitize_identifier(banco)
        tabela_safe = db.sanitize_identifier(tabela)
        
        # Constrói a query com filtros
        sql = f"SELECT * FROM {banco_safe}.{tabela_safe} WHERE 1=1"
        if status:
            sql += f" AND status = '{status}'"
        if sistema:
            sql += f" AND sistema = '{sistema}'"
        if data_inicio:
            sql += f" AND data_criacao >= '{data_inicio}'"
        if data_fim:
            sql += f" AND data_criacao <= '{data_fim}'"
        sql += " ORDER BY data_criacao DESC"
        
        results = db.execute_query(sql)
        return {"ok": True, "dados": results}
    except Exception as e:
        return {"ok": False, "erro": str(e)}

@router.post("/{sistema}/{status}")
async def gravar_log_sqlite(sistema: str, status: str, request: Request):
    """Grava log no banco SQLite.
    
    Aceita automaticamente JSON e texto plano, mesmo sem Content-Type especificado.
    
    Exemplos de uso:
    - curl -X POST http://localhost:8000/log/sistema1/info -d "Mensagem de log simples"
    - curl -X POST http://localhost:8000/log/sistema1/error -H "Content-Type: application/json" -d '{"message": "Erro no sistema", "details": "Detalhes do erro"}'  
    - curl -X POST http://localhost:8000/log/sistema1/warning -H "Content-Type: text/plain" -d "Aviso importante do sistema"
    """
    try:
        # Lê o body e detecta automaticamente o formato
        body = await request.body()
        body_str = body.decode('utf-8').strip()
        
        # Detecta automaticamente se é JSON ou texto simples
        log_texto = None
        if body_str.startswith('{') and body_str.endswith('}'):
            try:
                # Tenta fazer parse como JSON
                json_data = json.loads(body_str)
                if isinstance(json_data, dict):
                    # Se é um objeto JSON, converte para string formatada
                    if 'message' in json_data:
                        # Se tem campo 'message', usa como texto principal
                        log_texto = json_data['message']
                        if len(json_data) > 1:
                            # Se tem outros campos, adiciona como contexto
                            outros = {k: v for k, v in json_data.items() if k != 'message'}
                            log_texto += f" | Contexto: {json.dumps(outros, ensure_ascii=False)}"
                    else:
                        # Se não tem campo 'message', serializa todo o JSON
                        log_texto = json.dumps(json_data, ensure_ascii=False, indent=2)
                else:
                    # Se não é um dict, trata como texto simples
                    log_texto = body_str
            except json.JSONDecodeError:
                # Se falhar o parse JSON, trata como texto simples
                log_texto = body_str
        else:
            # Não parece JSON, trata como texto simples
            log_texto = body_str
        
        db = SQLiteDB()
        sql = """
        INSERT INTO log (status, log_texto)
        VALUES (?, ?)
        """
        await db.execute_many(sql, [(status, log_texto)])
        return {"ok": True, "mensagem": "Log gravado com sucesso"}
    except Exception as e:
        return {"ok": False, "erro": str(e)}

@router.get("/listar")
async def listar_logs_sqlite(
    status: Optional[str] = None,
    texto: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None
):
    """Lista logs do SQLite com filtros."""
    try:
        db = SQLiteDB()
        
        # Constrói a query com filtros
        sql = "SELECT * FROM log WHERE 1=1"
        if status:
            sql += f" AND status = '{status}'"
        if texto:
            sql += f" AND log_texto LIKE '%{texto}%'"
        if data_inicio:
            sql += f" AND data_criacao >= '{data_inicio}'"
        if data_fim:
            sql += f" AND data_criacao <= '{data_fim}'"
        sql += " ORDER BY data_criacao DESC"
        
        results = await db.execute_query(sql)
        return {"ok": True, "dados": results}
    except Exception as e:
        return {"ok": False, "erro": str(e)}