from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
import os
import re
import io
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
import pytesseract
from pdf2image import convert_from_path
import fitz
import PyPDF2
from ...services.ocr import OCRService

router = APIRouter(prefix="/ocr", tags=["OCR"])

@router.post("/pasta")
async def ocr_pasta_old(body: dict):
    """Processa arquivos de uma pasta usando OCR (versão antiga)."""
    try:
        from PIL import Image, ImageEnhance, ImageFilter
        import shutil
        from datetime import datetime

        SUPPORTED_EXTS = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'}
        CONFIGS = {
            'PSM6': '--oem 3 --psm 6 -l eng+por -c preserve_interword_spaces=1',
            'PSM11': '--oem 3 --psm 11 -l eng+por -c preserve_interword_spaces=1'
        }

        caminho_origem = Path(body.get("caminho_origem", "")).resolve()
        caminho_destino = Path(body.get("caminho_destino", "")).resolve()
        modo = body.get("modo", "PSM6")
        config = CONFIGS.get(modo, CONFIGS["PSM6"])

        processados = []
        falhas = []

        if not caminho_origem.is_dir():
            return JSONResponse(status_code=400, content={"ok": False, "erro": "Pasta de origem inválida"})

        os.makedirs(caminho_destino, exist_ok=True)

        def timestamp():
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        def preprocess_image(img: Image.Image) -> Image.Image:
            img = img.convert('L')
            img = ImageEnhance.Contrast(img).enhance(2.0)
            img = img.filter(ImageFilter.SHARPEN)
            w, h = img.size
            return img.resize((w * 2, h * 2), resample=Image.LANCZOS)

        def extract_pdf_text(path: Path) -> str:
            try:
                reader = PyPDF2.PdfReader(str(path))
                texts = [page.extract_text() or '' for page in reader.pages]
                return "\n".join(texts)
            except:
                return ''

        def extract_images_with_fitz(pdf_path: Path) -> list:
            images = []
            try:
                doc = fitz.open(str(pdf_path))
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    image_list = page.get_images(full=True)
                    for img_index, img in enumerate(image_list):
                        xref = img[0]
                        pix = fitz.Pixmap(doc, xref)
                        if pix.n - pix.alpha < 4:
                            img_data = pix.tobytes("png")
                            images.append((f"page_{page_num}_img_{img_index}.png", img_data))
                        pix = None
                doc.close()
            except Exception as e:
                print(f"Erro ao extrair imagens: {e}")
            return images

        # Processa arquivos
        for arquivo in caminho_origem.iterdir():
            if arquivo.suffix.lower() not in SUPPORTED_EXTS:
                continue

            try:
                texto_extraido = ""
                
                if arquivo.suffix.lower() == '.pdf':
                    # Tenta extrair texto diretamente
                    texto_extraido = extract_pdf_text(arquivo)
                    
                    if not texto_extraido.strip():
                        # Se não há texto, extrai imagens e aplica OCR
                        images = extract_images_with_fitz(arquivo)
                        for img_name, img_data in images:
                            img = Image.open(io.BytesIO(img_data))
                            img = preprocess_image(img)
                            texto_img = pytesseract.image_to_string(img, config=config)
                            texto_extraido += texto_img + "\n"
                else:
                    # Processa imagem diretamente
                    img = Image.open(arquivo)
                    img = preprocess_image(img)
                    texto_extraido = pytesseract.image_to_string(img, config=config)

                # Salva o texto extraído
                if texto_extraido.strip():
                    txt_path = caminho_destino / f"{arquivo.stem}.txt"
                    txt_path.write_text(texto_extraido, encoding="utf-8")
                    processados.append({
                        "arquivo": arquivo.name,
                        "texto_extraido": len(texto_extraido),
                        "arquivo_saida": str(txt_path),
                        "timestamp": timestamp()
                    })
                else:
                    falhas.append({
                        "arquivo": arquivo.name,
                        "erro": "Nenhum texto extraído",
                        "timestamp": timestamp()
                    })

            except Exception as e:
                falhas.append({
                    "arquivo": arquivo.name,
                    "erro": str(e),
                    "timestamp": timestamp()
                })

        return {
            "ok": True,
            "processados": len(processados),
            "falhas": len(falhas),
            "detalhes": {
                "processados": processados,
                "falhas": falhas
            }
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "erro": str(e)})