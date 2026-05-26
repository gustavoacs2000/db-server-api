import os
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from pdf2image import convert_from_path
import fitz
import PyPDF2
import pdfplumber
from typing import List, Optional

class OCRService:
    @staticmethod
    def pre_processar_imagem(imagem: Image.Image) -> Image.Image:
        """Aplica pré-processamento na imagem para melhorar o OCR."""
        # Converte para escala de cinza
        imagem = imagem.convert('L')
        
        # Aumenta o contraste
        enhancer = ImageEnhance.Contrast(imagem)
        imagem = enhancer.enhance(2)
        
        # Aplica filtro para reduzir ruído
        imagem = imagem.filter(ImageFilter.MedianFilter())
        
        # Binarização
        imagem = imagem.point(lambda x: 0 if x < 128 else 255, '1')
        
        return imagem

    @staticmethod
    def extrair_texto_imagem(caminho_imagem: str, pre_processar: bool = False) -> str:
        """Extrai texto de uma imagem usando OCR."""
        try:
            imagem = Image.open(caminho_imagem)
            if pre_processar:
                imagem = OCRService.pre_processar_imagem(imagem)
            texto = pytesseract.image_to_string(imagem, lang='por')
            return texto
        except Exception as e:
            print(f"Erro ao processar imagem {caminho_imagem}: {str(e)}")
            return ""

    @staticmethod
    def extrair_texto_pdf(caminho_pdf: str, pre_processar: bool = False) -> str:
        """Extrai texto de um arquivo PDF usando OCR quando necessário."""
        texto_completo = []

        # Tenta extrair texto diretamente primeiro
        try:
            with pdfplumber.open(caminho_pdf) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if texto:
                        texto_completo.append(texto)
        except Exception as e:
            print(f"Erro ao extrair texto direto do PDF: {str(e)}")

        # Se não conseguiu extrair texto, usa OCR
        if not texto_completo:
            try:
                imagens = convert_from_path(caminho_pdf)
                for i, imagem in enumerate(imagens):
                    if pre_processar:
                        imagem = OCRService.pre_processar_imagem(imagem)
                    texto = pytesseract.image_to_string(imagem, lang='por')
                    texto_completo.append(texto)
            except Exception as e:
                print(f"Erro ao processar PDF com OCR: {str(e)}")

        return "\n\n".join(texto_completo)

    @staticmethod
    def extrair_imagens_pdf(caminho_pdf: str, pasta_destino: str) -> List[str]:
        """Extrai imagens de um arquivo PDF."""
        imagens_salvas = []
        try:
            pdf_document = fitz.open(caminho_pdf)
            for pagina_num in range(len(pdf_document)):
                pagina = pdf_document[pagina_num]
                imagens = pagina.get_images(full=True)
                
                for img_index, img in enumerate(imagens):
                    xref = img[0]
                    base_image = pdf_document.extract_image(xref)
                    image_bytes = base_image["image"]
                    
                    # Determina a extensão da imagem
                    ext = base_image["ext"]
                    nome_arquivo = f"pagina_{pagina_num + 1}_img_{img_index + 1}.{ext}"
                    caminho_imagem = os.path.join(pasta_destino, nome_arquivo)
                    
                    with open(caminho_imagem, "wb") as arquivo_imagem:
                        arquivo_imagem.write(image_bytes)
                    imagens_salvas.append(caminho_imagem)
            
            return imagens_salvas
        except Exception as e:
            print(f"Erro ao extrair imagens do PDF: {str(e)}")
            return []

    @staticmethod
    def processar_pasta(pasta_origem: str, pasta_destino: str, pre_processar: bool = False,
                       extrair_imagens: bool = False, rasterizar: bool = False) -> dict:
        """Processa todos os arquivos de uma pasta para extrair texto via OCR."""
        resultados = {
            "sucessos": 0,
            "falhas": 0,
            "arquivos_processados": []
        }

        # Cria a pasta de destino se não existir
        os.makedirs(pasta_destino, exist_ok=True)

        for arquivo in os.listdir(pasta_origem):
            caminho_arquivo = os.path.join(pasta_origem, arquivo)
            nome_base = os.path.splitext(arquivo)[0]
            
            try:
                if arquivo.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
                    texto = OCRService.extrair_texto_imagem(caminho_arquivo, pre_processar)
                    caminho_texto = os.path.join(pasta_destino, f"{nome_base}.txt")
                    with open(caminho_texto, 'w', encoding='utf-8') as f:
                        f.write(texto)
                    resultados["sucessos"] += 1
                    resultados["arquivos_processados"].append({
                        "arquivo": arquivo,
                        "status": "sucesso",
                        "tipo": "imagem"
                    })

                elif arquivo.lower().endswith('.pdf'):
                    # Extrai texto do PDF
                    texto = OCRService.extrair_texto_pdf(caminho_arquivo, pre_processar)
                    caminho_texto = os.path.join(pasta_destino, f"{nome_base}.txt")
                    with open(caminho_texto, 'w', encoding='utf-8') as f:
                        f.write(texto)

                    # Extrai imagens se solicitado
                    if extrair_imagens:
                        pasta_imagens = os.path.join(pasta_destino, f"{nome_base}_imagens")
                        os.makedirs(pasta_imagens, exist_ok=True)
                        imagens_extraidas = OCRService.extrair_imagens_pdf(caminho_arquivo, pasta_imagens)

                    resultados["sucessos"] += 1
                    resultados["arquivos_processados"].append({
                        "arquivo": arquivo,
                        "status": "sucesso",
                        "tipo": "pdf",
                        "imagens_extraidas": len(imagens_extraidas) if extrair_imagens else 0
                    })

            except Exception as e:
                resultados["falhas"] += 1
                resultados["arquivos_processados"].append({
                    "arquivo": arquivo,
                    "status": "falha",
                    "erro": str(e)
                })

        return resultados