import socket
import unicodedata
from typing import Optional

def get_free_port(start_port: int = 8000, end_port: int = 9000) -> Optional[int]:
    """Encontra uma porta livre no intervalo especificado."""
    for port in range(start_port, end_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    return None

def sanitize_filename(filename: str) -> str:
    """Remove caracteres inválidos de nomes de arquivo."""
    # Remove acentos
    filename = unicodedata.normalize('NFKD', filename)
    filename = ''.join(c for c in filename if not unicodedata.combining(c))
    
    # Remove caracteres inválidos
    invalid_chars = '<>:"\\/|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    
    # Limita o tamanho
    max_length = 255
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length-len(ext)] + ext
    
    return filename

def format_xml(data: dict) -> str:
    """Formata um dicionário como XML."""
    import xml.etree.ElementTree as ET
    from typing import Any
    
    def dict_to_xml(data: Any, root_name: str = "root") -> ET.Element:
        root = ET.Element(root_name)
        
        def _convert(parent: ET.Element, data: Any):
            if isinstance(data, dict):
                for key, value in data.items():
                    child = ET.SubElement(parent, str(key))
                    _convert(child, value)
            elif isinstance(data, (list, tuple)):
                for item in data:
                    child = ET.SubElement(parent, "item")
                    _convert(child, item)
            else:
                parent.text = str(data)
        
        _convert(root, data)
        return root
    
    root = dict_to_xml(data)
    return ET.tostring(root, encoding="unicode", method="xml")

def format_json(data: dict) -> str:
    """Formata um dicionário como JSON."""
    import json
    return json.dumps(data, ensure_ascii=False, indent=2)