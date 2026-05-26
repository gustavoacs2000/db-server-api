import os
import sys
import pytesseract

def ajustar_path_poppler() -> None:
    """Ajusta o PATH para incluir o diretório bin do Poppler."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    poppler_bin = os.path.join(base, "poppler", "Library", "bin")
    os.environ["PATH"] = os.pathsep.join([os.environ["PATH"], poppler_bin])

def ajustar_path_tesseract() -> None:
    """Configura os caminhos do Tesseract OCR."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tesseract_exe = os.path.join(base, "tesseract", "tesseract.exe")
    tessdata_dir = os.path.join(base, "tesseract", "tessdata")
    pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    os.environ["TESSDATA_PREFIX"] = tessdata_dir

def get_records_dir() -> str:
    """Retorna o caminho correto para a pasta records baseado no contexto de execução."""
    if getattr(sys, "frozen", False):
        # Executando como executável PyInstaller
        base_dir = os.path.dirname(sys.executable)
    else:
        # Executando como código fonte
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    records_dir = os.path.join(base_dir, "records")
    os.makedirs(records_dir, exist_ok=True)
    return records_dir

def setup_paths() -> None:
    """Configura todos os caminhos necessários para a aplicação."""
    ajustar_path_poppler()
    ajustar_path_tesseract()