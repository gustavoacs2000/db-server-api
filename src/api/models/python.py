from pydantic import BaseModel, Field
from typing import Optional

class PythonExecuteRequest(BaseModel):
    """Modelo para requisição de execução de código Python."""
    
    code: str = Field(
        ...,
        description="Código Python a ser executado",
        example="print('Hello World')"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "code": "print('Hello World')"
                },
                {
                    "code": "x = 5\ny = 10\nresult = x + y\nprint(f'Resultado: {result}')"
                },
                {
                    "code": "import datetime\nprint(datetime.datetime.now())"
                }
            ]
        }

class PythonAsyncExecuteRequest(BaseModel):
    """Modelo para requisição de execução de código Python assíncrono."""
    
    code: str = Field(
        ...,
        description="Código Python assíncrono a ser executado",
        example="import asyncio\nawait asyncio.sleep(1)\nprint('Async done')"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "code": "import asyncio\nawait asyncio.sleep(1)\nprint('Async done')"
                },
                {
                    "code": "import aiohttp\nasync with aiohttp.ClientSession() as session:\n    async with session.get('https://httpbin.org/json') as resp:\n        data = await resp.json()\n        print(data)"
                },
                {
                    "code": "result = await some_async_function()\nprint(result)"
                }
            ]
        }