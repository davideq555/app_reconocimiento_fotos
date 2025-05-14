import os
import base64
import json
import requests
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from io import BytesIO

class ImageProcessor:
    def __init__(self, ollama_url="http://localhost:11434"):
        self.ollama_url = ollama_url
    
    def encode_image_to_base64(self, image_path):
        """Codifica una imagen a base64"""
        with Image.open(image_path) as img:
            # Convertir a RGB si es necesario
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Redimensionar si es muy grande (máximo 1024px en el lado más largo)
            max_size = (1024, 1024)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Convertir a base64
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    def extract_numbers(self, text):
        """Extrae números del texto de respuesta"""
        import re
        # Buscar secuencias de dígitos
        numbers = re.findall(r'\d+', text)
        # Convertir a enteros y eliminar duplicados
        unique_numbers = list(set(int(num) for num in numbers))
        return unique_numbers
    
    def add_watermark(self, image_path, output_path, text="COPIA", opacity=0.5):
        """Agrega una marca de agua a la imagen"""
        try:
            # Abrir la imagen
            base_image = Image.open(image_path).convert("RGBA")
            
            # Crear una imagen para la marca de agua
            txt = Image.new('RGBA', base_image.size, (255, 255, 255, 0))
            
            # Configurar la fuente (usando una fuente por defecto si no se encuentra la especificada)
            try:
                font_size = int(min(base_image.size) / 10)  # Tamaño de fuente relativo al tamaño de la imagen
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                # Si no se puede cargar la fuente, usar la fuente por defecto
                font = ImageFont.load_default()
            
            # Dibujar el texto en el centro
            d = ImageDraw.Draw(txt)
            text_width, text_height = d.textsize(text, font=font)
            position = ((base_image.width - text_width) // 2, 
                       (base_image.height - text_height) // 2)
            
            # Dibujar el texto con un borde para mejor visibilidad
            d.text(position, text, font=font, fill=(255, 255, 255, int(255 * opacity)), 
                  stroke_width=3, stroke_fill=(0, 0, 0, int(255 * opacity)))
            
            # Combinar la imagen original con la marca de agua
            watermarked = Image.alpha_composite(base_image, txt)
            
            # Guardar la imagen resultante
            if output_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                watermarked = watermarked.convert('RGB')  # Convertir a RGB para JPEG
            
            watermarked.save(output_path)
            return True
            
        except Exception as e:
            print(f"Error al agregar marca de agua: {str(e)}")
            return False
    
    def process_image(self, image_path, model_name="llama3.2-vision", output_dir=None):
        """
        Procesa una imagen utilizando la API de Ollama para reconocer números.
        
        Args:
            image_path (str): Ruta a la imagen a procesar
            model_name (str): Nombre del modelo de Ollama a utilizar
            output_dir (str, opcional): Directorio donde guardar la imagen procesada
            
        Returns:
            dict: Diccionario con los resultados del procesamiento
        """
        try:
            # Verificar que el archivo existe
            if not os.path.exists(image_path):
                return {"error": f"El archivo {image_path} no existe"}
            
            # Codificar la imagen a base64
            try:
                image_base64 = self.encode_image_to_base64(image_path)
            except Exception as e:
                return {"error": f"Error al procesar la imagen: {str(e)}"}
            
            # Preparar el prompt para el modelo
            prompt = """Analiza esta imagen y encuentra todos los números visibles de los participantes del primer plano. 
            No consideres números que estén en el segundo plano, ni números que estén desenfocados.
            Responde solo con los números encontrados separados por comas."""
            
            # Hacer la solicitud a la API de Ollama
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "images": [image_base64],
                    "options": {
                        "temperature": 0.1
                    }
                },
                stream=True
            )
            
            if response.status_code != 200:
                return {"error": f"Error en la API de Ollama: {response.status_code} - {response.text}"}
            
            # Procesar la respuesta
            try:
                texto_completo = ""
                
                # Procesar cada línea de la respuesta
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "response" in data:
                                texto_completo += data["response"]
                        except json.JSONDecodeError:
                            continue
                
                # Extraer números del texto
                numeros_encontrados = self.extract_numbers(texto_completo)
                
                # Procesar la salida si se especificó un directorio de salida
                output_path = None
                if output_dir and numeros_encontrados:
                    try:
                        # Crear directorio de salida si no existe
                        os.makedirs(output_dir, exist_ok=True)
                        
                        # Generar nombre de archivo con formato nXX_nYY
                        nombre_base = "_n".join([""] + [str(num) for num in sorted(numeros_encontrados)]).lstrip("_")
                        extension = os.path.splitext(image_path)[1].lower()
                        
                        # Asegurar que la extensión sea compatible
                        if extension not in ['.jpg', '.jpeg', '.png']:
                            extension = '.jpg'
                            
                        output_filename = f"{nombre_base}{extension}"
                        output_path = os.path.join(output_dir, output_filename)
                        
                        # Copiar la imagen original
                        shutil.copy2(image_path, output_path)
                        
                        # Agregar marca de agua
                        self.add_watermark(output_path, output_path)
                        
                    except Exception as e:
                        print(f"Error al guardar la imagen procesada: {str(e)}")
                
                return {
                    "success": True,
                    "texto_original": texto_completo,
                    "numeros_encontrados": numeros_encontrados,
                    "mensaje": f"Se encontraron {len(numeros_encontrados)} números" if numeros_encontrados else "No se encontraron números",
                    "output_path": output_path if output_dir and numeros_encontrados else None
                }
                
            except Exception as e:
                return {"error": f"Error al procesar la respuesta: {str(e)}"}
                
        except Exception as e:
            return {"error": f"Error inesperado: {str(e)}"}


# Para pruebas locales
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        processor = ImageProcessor()
        result = processor.process_image(sys.argv[1])
        print("Resultado del reconocimiento:")
        print(result)
    else:
        print("Por favor, proporciona la ruta a una imagen como argumento")
