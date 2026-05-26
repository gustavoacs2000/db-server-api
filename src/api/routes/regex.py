from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
import os
import re
from pathlib import Path
import json
from ..models.regex import RegexActivatorRequest

router = APIRouter(prefix="/regex", tags=["Regex"])

# Dicionário para armazenar contextos de regex
contextos_regex: Dict[str, Dict[str, Any]] = {}

@router.post(
    "/ativador",
    summary="Carregar ativadores de regex",
    description="""Carrega ativadores de regex a partir de código Python que define padrões e função de extração.
    
    **Funcionalidade:**
    - Executa código Python que deve definir `regex_ativadores` (lista) e função `extrair`
    - Armazena o contexto para uso posterior em processamento de dados
    - Valida se os ativadores são uma lista e se a função extrair é callable
    
    **Parâmetros:**
    - `code`: Código Python com definições de regex_ativadores e função extrair
    - `contexto`: Nome do contexto para armazenar (opcional, padrão: "default_regex")
    
    **Exemplos de uso:**
    - Números: `{"code": "regex_ativadores = [r'\\\\d+']; def extrair(text): return re.findall(r'\\\\d+', text)"}`
    - Emails: `{"code": "regex_ativadores = [r'[\\\\w.-]+@[\\\\w.-]+\\\\.[a-zA-Z]{2,}']; def extrair(text): return re.findall(regex_ativadores[0], text)"}`
    - Múltiplos padrões: `{"code": "regex_ativadores = [r'\\\\d+', r'[A-Z]{2,}']; def extrair(text): return [re.findall(p, text) for p in regex_ativadores]"}`
    """
)
async def carregar_ativador(request: RegexActivatorRequest):
    try:
        codigo = request.code
        contexto = request.contexto

        if not codigo.strip():
            return {"ok": False, "erro": "Código vazio"}

        # Executa o código para extrair ativadores e função
        ctx = {}
        exec(codigo, ctx)
        ativadores = ctx.get("regex_ativadores")
        func_extrair = ctx.get("extrair")

        if not isinstance(ativadores, list):
            return {"ok": False, "erro": "regex_ativadores deve ser uma lista"}

        if not callable(func_extrair):
            return {"ok": False, "erro": "extrair deve ser uma função"}

        # Armazena o contexto
        contextos_regex[contexto] = ctx

        return {
            "ok": True, 
            "ativadores": ativadores, 
            "mensagem": f"Contexto '{contexto}' carregado com sucesso"
        }

    except Exception as e:
        return {"ok": False, "erro": str(e)}

@router.post("/dados")
async def processar_dados_regex(body: dict):
    """Processa arquivos de texto aplicando regex configurado."""
    try:
        caminho_origem = body.get("caminho_origem")
        caminho_destino = body.get("caminho_destino")
        contexto = body.get("contexto", "default_regex")
        ignorecase = body.get("ignorecase", False)
        dotall = body.get("dotall", False)
        salvar_arquivo = body.get("salvar_arquivo", True)

        if not caminho_origem or not os.path.exists(caminho_origem):
            return JSONResponse(status_code=400, content={"ok": False, "erro": "Caminho de origem inválido"})

        if contexto not in contextos_regex:
            return JSONResponse(status_code=400, content={"ok": False, "erro": f"Contexto '{contexto}' não encontrado. Execute /regex/ativador primeiro."})

        ctx = contextos_regex[contexto]
        ativadores = ctx.get("regex_ativadores", [])
        func_extrair = ctx.get("extrair")

        if not ativadores or not func_extrair:
            return JSONResponse(status_code=400, content={"ok": False, "erro": "Contexto inválido ou incompleto"})

        # Cria diretório de destino se necessário
        if caminho_destino:
            os.makedirs(caminho_destino, exist_ok=True)

        resultados = []
        origem_path = Path(caminho_origem)

        # Processa arquivos
        if origem_path.is_file():
            arquivos = [origem_path]
        else:
            arquivos = list(origem_path.glob("*.txt"))

        for arquivo in arquivos:
            try:
                with open(arquivo, 'r', encoding='utf-8') as f:
                    conteudo = f.read()

                # Verifica se algum ativador está presente
                ativado = False
                for ativador in ativadores:
                    flags = 0
                    if ignorecase:
                        flags |= re.IGNORECASE
                    if dotall:
                        flags |= re.DOTALL
                    
                    if re.search(ativador, conteudo, flags):
                        ativado = True
                        break

                if ativado:
                    # Aplica a função de extração
                    try:
                        resultado_extracao = func_extrair(conteudo)
                        
                        resultado_arquivo = {
                            "arquivo": str(arquivo),
                            "ativado": True,
                            "dados_extraidos": resultado_extracao
                        }

                        # Salva resultado em arquivo JSON se solicitado
                        if salvar_arquivo and caminho_destino:
                            nome_json = arquivo.stem + ".json"
                            caminho_json = Path(caminho_destino) / nome_json
                            
                            with open(caminho_json, 'w', encoding='utf-8') as f:
                                json.dump(resultado_extracao, f, ensure_ascii=False, indent=2)
                            
                            resultado_arquivo["arquivo_saida"] = str(caminho_json)

                    except Exception as e:
                        resultado_arquivo = {
                            "arquivo": str(arquivo),
                            "ativado": True,
                            "erro_extracao": str(e)
                        }
                else:
                    resultado_arquivo = {
                        "arquivo": str(arquivo),
                        "ativado": False
                    }

                resultados.append(resultado_arquivo)

            except Exception as e:
                resultados.append({
                    "arquivo": str(arquivo),
                    "erro": str(e)
                })

        return {
            "ok": True,
            "contexto": contexto,
            "arquivos_processados": len(resultados),
            "resultados": resultados
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "erro": str(e)})