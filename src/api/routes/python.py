from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import subprocess
import sys
import json
import xml.etree.ElementTree as ET
from typing import Dict, Any
from ...services.global_context import global_context_manager

router = APIRouter()

# DEPRECATED: Mantido para compatibilidade, mas agora usa o contexto global
contextos: Dict[str, Dict[str, Any]] = {}

def executar_em_subprocess(code: str) -> dict:
    """Executa código Python em um subprocesso."""
    try:
        # Configurações específicas do Windows para evitar processos cmd.exe intermediários
        import platform
        kwargs = {
            "capture_output": True,
            "text": True,
            "check": True
        }
        
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            kwargs["startupinfo"] = startupinfo
        
        result = subprocess.run(
            [sys.executable, "-c", code],
            **kwargs
        )
        return {"ok": True, "saida": result.stdout}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "erro": e.stderr}
    except Exception as e:
        return {"ok": False, "erro": str(e)}

def executar_em_contexto(code: str, contexto: str = "global") -> dict:
    """Executa código Python em um contexto específico usando o gerenciador global."""
    try:
        # Usa o gerenciador de contexto global
        result = global_context_manager.execute_in_context(contexto, code, globals())
        
        if result["ok"]:
            return {"ok": True, "resultado": result["result"]}
        else:
            return {"ok": False, "erro": result["traceback"]}
            
    except Exception as e:
        import traceback
        return {"ok": False, "erro": traceback.format_exc()}

@router.post(
    "/executepy",
    summary="Executar código Python (SEMPRE text/plain)",
    description="""Executa código Python com diferentes opções de contexto e formato de resposta.
    
    **⚠️ IMPORTANTE: Esta rota SEMPRE trata o body como text/plain, independente do Content-Type enviado.**
    
    **Formato aceito:**
    - **APENAS Text/plain**: código python direto no body da requisição
    - **Content-Type ignorado**: mesmo enviando application/json, será tratado como texto
    
    **Parâmetros de query opcionais:**
    - `contexto`: Nome do contexto de execução (padrão: subprocesso isolado)
    - `isolado`: Se true, limpa o contexto antes da execução (padrão: false)
    - `formato`: Formato da resposta - json, xml, array, arrayc (padrão: json)
    
    **Exemplos de uso:**
    - Body: `print('Hello World')`
    - Com contexto: `contador += 1\nprint(contador)` + query param `?contexto=meu_contexto`
    - Múltiplas linhas: `x = 10\ny = 20\nprint(x + y)`
    """
)
async def execute_python(request: Request, contexto: str = "", isolado: bool = False, formato: str = "json"):
    try:
        # Lê o body da requisição
        body = await request.body()
        body_text = body.decode("utf-8")
        
        # Obtém content-type (pode ser None ou vazio)
        content_type = request.headers.get("content-type", "").lower()
        
        codigo = None
        formato_detectado = None
        
        # SEMPRE força text/plain - ignora content-type JSON
        # Só tenta JSON se o conteúdo claramente parece ser JSON E não há contexto específico
        body_stripped = body_text.strip()
        if contexto == "global_async" and body_stripped.startswith('{') and body_stripped.endswith('}'):
            try:
                # Tenta como JSON apenas se contexto padrão E parece ser JSON
                import json
                data = json.loads(body_text)
                if "code" in data:
                    codigo = data.get("code")
                    formato_detectado = "json_fallback"
                else:
                    # Se não tem campo 'code', trata como texto
                    codigo = body_text
                    formato_detectado = "texto_forcado"
            except json.JSONDecodeError:
                # Se não for JSON válido, trata como texto
                codigo = body_text
                formato_detectado = "texto_forcado"
        else:
            # SEMPRE prioriza text/plain, mesmo com content-type JSON
            codigo = body_text
            formato_detectado = "texto_forcado"
        
        if not codigo or not codigo.strip():
            return {"ok": False, "erro": "Código não pode estar vazio", "formato_detectado": formato_detectado}

        # Sem contexto -> subprocesso
        if not contexto:
            # Configurações específicas do Windows para evitar processos cmd.exe intermediários
            import platform
            kwargs = {
                "capture_output": True,
                "text": True
            }
            
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                kwargs["startupinfo"] = startupinfo
            
            proc = subprocess.run([sys.executable, "-c", codigo], **kwargs)
            return {
                "ok": proc.returncode == 0,
                "saida": proc.stdout,
                "erro": proc.stderr if proc.returncode else ""
            }

        # Com contexto - usa o gerenciador global
        if isolado:
            # Para execução isolada, cria um contexto temporário
            temp_context = {}
            exec(codigo, temp_context)
            saida = temp_context.get("_", None)
        else:
            # Usa o contexto global compartilhado
            result = global_context_manager.execute_in_context(contexto, codigo, globals())
            if result["ok"]:
                saida = result["result"]
            else:
                raise Exception(result["error"])

        # Formatação da resposta
        if formato == "xml":
            root = ET.Element("resultado")
            if isinstance(saida, list):
                for item in saida:
                    el = ET.SubElement(root, "item")
                    if isinstance(item, dict):
                        for k, v in item.items():
                            c = ET.SubElement(el, k)
                            c.text = str(v) if v is not None else ""
                    else:
                        el.text = str(item)
            elif isinstance(saida, dict):
                el = ET.SubElement(root, "item")
                for k, v in saida.items():
                    c = ET.SubElement(el, k)
                    c.text = str(v) if v is not None else ""
            else:
                root.text = str(saida)
            from fastapi.responses import Response
            return Response(content=ET.tostring(root, encoding="utf-8"), media_type="application/xml")

        if formato == "array":
            if isinstance(saida, list) and all(isinstance(x, dict) for x in saida):
                cols = list(saida[0].keys())
                data = [[item.get(c) for c in cols] for item in saida]
                return JSONResponse(content=data)
            if isinstance(saida, list):
                return JSONResponse(content=saida)
            return JSONResponse(content=[[saida]])

        if formato == "arrayc":
            if isinstance(saida, list) and all(isinstance(x, dict) for x in saida):
                cols = list(saida[0].keys())
                data = [cols] + [[item.get(c) for c in cols] for item in saida]
                return JSONResponse(content=data)
            if isinstance(saida, list):
                return JSONResponse(content=[["valor"]] + [[x] for x in saida])
            return JSONResponse(content=[["valor"], [saida]])

        # Formato padrão
        return {
            "ok": True, 
            "saida": saida if isinstance(saida, (dict, list)) else str(saida),
            "formato_detectado": formato_detectado,
            "content_type_original": content_type or "não especificado"
        }
    except Exception as e:
        import traceback
        return {"ok": False, "erro": traceback.format_exc()}

@router.post(
    "/executepyas",
    summary="Executar código Python assíncrono (SEMPRE text/plain)",
    description="""Executa código Python assíncrono com contexto e formatação.
    
    **⚠️ IMPORTANTE: Esta rota SEMPRE trata o body como text/plain, independente do Content-Type enviado.**
    
    **Formato aceito:**
    - **APENAS Text/plain**: código python direto no body da requisição
    - **Content-Type ignorado**: mesmo enviando application/json, será tratado como texto
    
    **Parâmetros de query opcionais:**
    - `contexto`: Nome do contexto de execução (padrão: "global_async")
    - `formato`: Formato da resposta - json, xml, array, arrayc (padrão: json)
    
    **Exemplos de uso:**
    - Body: `import asyncio\nawait asyncio.sleep(1)\nprint('Async done')`
    - Com aiohttp: `import aiohttp\nasync with aiohttp.ClientSession() as session:\n    async with session.get('https://httpbin.org/json') as resp:\n        data = await resp.json()\n        print(data)`
    - Múltiplas operações: `import asyncio\ntasks = [asyncio.sleep(1) for _ in range(3)]\nawait asyncio.gather(*tasks)\nprint('All done')`
    """
)
async def execute_python_async(request: Request, contexto: str = "global_async", formato: str = "json"):
    try:
        # Lê o body da requisição
        body = await request.body()
        body_text = body.decode("utf-8")
        
        # Obtém content-type (pode ser None ou vazio)
        content_type = request.headers.get("content-type", "").lower()
        
        codigo = None
        formato_detectado = None
        
        # SEMPRE força text/plain - ignora content-type JSON
        # Só tenta JSON se o conteúdo claramente parece ser JSON E contexto padrão
        body_stripped = body_text.strip()
        if contexto == "global_async" and body_stripped.startswith('{') and body_stripped.endswith('}'):
            try:
                # Tenta como JSON apenas se contexto padrão E parece ser JSON
                import json
                data = json.loads(body_text)
                if "code" in data:
                    codigo = data.get("code")
                    formato_detectado = "json_fallback"
                else:
                    # Se não tem campo 'code', trata como texto
                    codigo = body_text
                    formato_detectado = "texto_forcado"
            except json.JSONDecodeError:
                # Se não for JSON válido, trata como texto
                codigo = body_text
                formato_detectado = "texto_forcado"
        else:
            # SEMPRE prioriza text/plain, mesmo com content-type JSON
            codigo = body_text
            formato_detectado = "texto_forcado"
        
        if not codigo or not codigo.strip():
            return {"ok": False, "erro": "Código não pode estar vazio", "formato_detectado": formato_detectado}

        # Executa o código usando o gerenciador de contexto global
        result = global_context_manager.execute_in_context(contexto, codigo, globals())
        
        if not result["ok"]:
            raise Exception(result["error"])
            
        saida = result["result"]

        # Formatação da resposta
        if formato == "xml":
            root = ET.Element("resultado")
            if isinstance(saida, list):
                for item in saida:
                    el = ET.SubElement(root, "item")
                    if isinstance(item, dict):
                        for k, v in item.items():
                            c = ET.SubElement(el, k)
                            c.text = str(v) if v is not None else ""
                    else:
                        el.text = str(item)
            elif isinstance(saida, dict):
                el = ET.SubElement(root, "item")
                for k, v in saida.items():
                    c = ET.SubElement(el, k)
                    c.text = str(v) if v is not None else ""
            else:
                root.text = str(saida)
            from fastapi.responses import Response
            return Response(content=ET.tostring(root, encoding="utf-8"), media_type="application/xml")

        if formato == "array":
            if isinstance(saida, list) and all(isinstance(x, dict) for x in saida):
                cols = list(saida[0].keys())
                data = [[item.get(c) for c in cols] for item in saida]
                return JSONResponse(content=data)
            if isinstance(saida, list):
                return JSONResponse(content=saida)
            return JSONResponse(content=[[saida]])

        if formato == "arrayc":
            if isinstance(saida, list) and all(isinstance(x, dict) for x in saida):
                cols = list(saida[0].keys())
                data = [cols] + [[item.get(c) for c in cols] for item in saida]
                return JSONResponse(content=data)
            if isinstance(saida, list):
                return JSONResponse(content=[["valor"]] + [[x] for x in saida])
            return JSONResponse(content=[["valor"], [saida]])

        # Formato padrão
        return {
            "ok": True, 
            "saida": saida if isinstance(saida, (dict, list)) else str(saida),
            "formato_detectado": formato_detectado,
            "content_type_original": content_type or "não especificado"
        }
    except Exception as e:
        import traceback
        return {"ok": False, "erro": traceback.format_exc()}

@router.post("/executepy/limpar")
def limpar_contexto(request: Request):
    """Limpa um contexto de execução específico."""
    nome = request.query_params.get("contexto", "global")
    if nome in contextos:
        del contextos[nome]
        return {"ok": True, "mensagem": f"Contexto '{nome}' limpo com sucesso."}
    return {"ok": False, "mensagem": f"Contexto '{nome}' não existe."}