from typing import Dict, Any, Optional
import threading

class GlobalContextManager:
    """Gerenciador de contexto global único para todo o sistema.
    
    Este serviço mantém um contexto único compartilhado entre todas as rotas:
    - Python (/executepy, /executepyas)
    - Browser (/browser/executar, /browser/console)
    - Stream (se necessário)
    
    O contexto é thread-safe e persiste variáveis entre execuções.
    """
    
    def __init__(self):
        self._contexts: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    def get_context(self, context_name: str = "global") -> Dict[str, Any]:
        """Obtém ou cria um contexto.
        
        Args:
            context_name: Nome do contexto (padrão: "global")
            
        Returns:
            Dicionário do contexto
        """
        with self._lock:
            if context_name not in self._contexts:
                self._contexts[context_name] = {}
            return self._contexts[context_name]
    
    def set_variable(self, context_name: str, key: str, value: Any) -> None:
        """Define uma variável no contexto.
        
        Args:
            context_name: Nome do contexto
            key: Nome da variável
            value: Valor da variável
        """
        with self._lock:
            context = self.get_context(context_name)
            context[key] = value
    
    def get_variable(self, context_name: str, key: str, default: Any = None) -> Any:
        """Obtém uma variável do contexto.
        
        Args:
            context_name: Nome do contexto
            key: Nome da variável
            default: Valor padrão se a variável não existir
            
        Returns:
            Valor da variável ou valor padrão
        """
        with self._lock:
            context = self.get_context(context_name)
            return context.get(key, default)
    
    def update_context(self, context_name: str, updates: Dict[str, Any]) -> None:
        """Atualiza múltiplas variáveis no contexto.
        
        Args:
            context_name: Nome do contexto
            updates: Dicionário com as atualizações
        """
        with self._lock:
            context = self.get_context(context_name)
            context.update(updates)
    
    def clear_context(self, context_name: str) -> bool:
        """Limpa um contexto específico.
        
        Args:
            context_name: Nome do contexto
            
        Returns:
            True se o contexto foi limpo, False se não existia
        """
        with self._lock:
            if context_name in self._contexts:
                del self._contexts[context_name]
                return True
            return False
    
    def list_contexts(self) -> list:
        """Lista todos os contextos existentes.
        
        Returns:
            Lista com nomes dos contextos
        """
        with self._lock:
            return list(self._contexts.keys())
    
    def get_context_info(self, context_name: str) -> Optional[Dict[str, Any]]:
        """Obtém informações sobre um contexto.
        
        Args:
            context_name: Nome do contexto
            
        Returns:
            Dicionário com informações do contexto ou None se não existir
        """
        with self._lock:
            if context_name in self._contexts:
                context = self._contexts[context_name]
                return {
                    "name": context_name,
                    "variables_count": len(context),
                    "variables": list(context.keys())
                }
            return None
    
    def execute_in_context(self, context_name: str, code: str, globals_dict: Dict[str, Any] = None) -> Dict[str, Any]:
        """Executa código Python no contexto especificado.
        
        Args:
            context_name: Nome do contexto
            code: Código Python para executar
            globals_dict: Dicionário de globals adicionais
            
        Returns:
            Resultado da execução
        """
        with self._lock:
            try:
                context = self.get_context(context_name)
                
                # Prepara o ambiente de execução
                exec_globals = globals_dict.copy() if globals_dict else {}
                exec_globals.update(context)
                
                # Adiciona declarações global para todas as variáveis do contexto
                context_vars = list(context.keys())
                if context_vars:
                    global_declarations = "\n".join([f"global {var}" for var in context_vars if var.isidentifier()])
                    wrapped_code = f"{global_declarations}\n{code}"
                else:
                    wrapped_code = code
                
                # Executa o código
                exec_locals = {}
                exec(wrapped_code, exec_globals, exec_locals)
                
                # Atualiza o contexto com novas variáveis
                for key, value in exec_locals.items():
                    if not key.startswith('_'):
                        context[key] = value
                
                # Atualiza também com variáveis modificadas nos globals
                for key in context_vars:
                    if key in exec_globals:
                        context[key] = exec_globals[key]
                
                # Retorna a última expressão se possível
                last_expr = None
                try:
                    lines = code.strip().split('\n')
                    if lines:
                        last_line = lines[-1].strip()
                        if last_line and not last_line.startswith(('#', 'import', 'from', 'def', 'class', 'if', 'for', 'while', 'try', 'with')):
                            last_expr = eval(last_line, exec_globals, context)
                except:
                    pass
                
                return {
                    "ok": True,
                    "result": last_expr,
                    "context_updated": True
                }
                
            except Exception as e:
                import traceback
                return {
                    "ok": False,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }

# Instância global única
global_context_manager = GlobalContextManager()