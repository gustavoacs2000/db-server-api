from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from seleniumbase import Driver
from typing import Dict, Any, Optional

class BrowserService:
    """Serviço para gerenciamento de contextos de navegador."""
    
    def __init__(self):
        self.browser_contexts: Dict[str, Dict[str, Any]] = {}

    def criar_contexto_playwright(self, contexto_id: str, stealth: bool = True,
                                headless: bool = True) -> Dict[str, Any]:
        """Cria um novo contexto Playwright."""
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

            if stealth:
                Stealth(page)._emulate_webdriver()
                Stealth(page)._emulate_languages()
                Stealth(page)._emulate_timezone()
                Stealth(page)._emulate_webgl_vendor()
                Stealth(page)._emulate_chrome_version()
                Stealth(page)._emulate_permissions()

            self.browser_contexts[contexto_id] = {
                "type": "playwright",
                "playwright": pw,
                "browser": browser,
                "context": context,
                "page": page
            }

            return self.browser_contexts[contexto_id]

        except Exception as e:
            print(f"Erro ao criar contexto Playwright: {str(e)}")
            self.fechar_contexto(contexto_id)
            raise

    def criar_contexto_selenium(self, contexto_id: str, headless: bool = True) -> Dict[str, Any]:
        """Cria um novo contexto Selenium."""
        try:
            driver = Driver(uc=True, headless=headless)
            
            self.browser_contexts[contexto_id] = {
                "type": "selenium",
                "driver": driver
            }

            return self.browser_contexts[contexto_id]

        except Exception as e:
            print(f"Erro ao criar contexto Selenium: {str(e)}")
            self.fechar_contexto(contexto_id)
            raise

    def get_contexto(self, contexto_id: str) -> Optional[Dict[str, Any]]:
        """Retorna um contexto existente."""
        return self.browser_contexts.get(contexto_id)

    def fechar_contexto(self, contexto_id: str) -> None:
        """Fecha um contexto de navegador."""
        if contexto_id in self.browser_contexts:
            try:
                contexto = self.browser_contexts[contexto_id]
                if contexto["type"] == "playwright":
                    contexto["page"].close()
                    contexto["context"].close()
                    contexto["browser"].close()
                    contexto["playwright"].stop()
                elif contexto["type"] == "selenium":
                    contexto["driver"].quit()
                
                del self.browser_contexts[contexto_id]
            except Exception as e:
                print(f"Erro ao fechar contexto {contexto_id}: {str(e)}")

    def fechar_todos_contextos(self) -> None:
        """Fecha todos os contextos de navegador."""
        for contexto_id in list(self.browser_contexts.keys()):
            self.fechar_contexto(contexto_id)

    def executar_javascript(self, contexto_id: str, script: str) -> Any:
        """Executa código JavaScript no contexto especificado."""
        contexto = self.get_contexto(contexto_id)
        if not contexto:
            raise ValueError(f"Contexto {contexto_id} não encontrado")

        try:
            if contexto["type"] == "playwright":
                return contexto["page"].evaluate(script)
            elif contexto["type"] == "selenium":
                return contexto["driver"].execute_script(script)
        except Exception as e:
            print(f"Erro ao executar JavaScript no contexto {contexto_id}: {str(e)}")
            raise

    def navegar(self, contexto_id: str, url: str) -> None:
        """Navega para uma URL no contexto especificado."""
        contexto = self.get_contexto(contexto_id)
        if not contexto:
            raise ValueError(f"Contexto {contexto_id} não encontrado")

        try:
            if contexto["type"] == "playwright":
                contexto["page"].goto(url)
            elif contexto["type"] == "selenium":
                contexto["driver"].get(url)
        except Exception as e:
            print(f"Erro ao navegar para {url} no contexto {contexto_id}: {str(e)}")
            raise