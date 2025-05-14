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
    
    def add_watermark(self, image_path, output_path, text="COPIA", opacity=0.3, quality=85):
        """
        Agrega una marca de agua repetitiva a la imagen, redimensionándola primero para mejor rendimiento.
        
        Args:
            image_path: Ruta de la imagen original
            output_path: Ruta donde se guardará la imagen con marca de agua
            text: Texto de la marca de agua
            opacity: Opacidad de la marca de agua (0.0 a 1.0)
            quality: Calidad de la imagen de salida (1-100)
        """
        try:
            # Abrir la imagen
            with Image.open(image_path) as img:
                # Convertir a RGBA si es necesario
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                # Redimensionar la imagen para hacerla más manejable (25% del tamaño original)
                original_size = img.size
                new_size = (int(original_size[0] * 0.25), int(original_size[1] * 0.25))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Crear una capa para la marca de agua
                watermark = Image.new('RGBA', img.size, (0, 0, 0, 0))
                
                # Configurar la fuente con un tamaño fijo más grande
                try:
                    # Tamaño base para la fuente (ajustar según sea necesario)
                    base_font_size = max(24, int(min(img.size) / 15))
                    font = ImageFont.truetype("arial.ttf", base_font_size)
                except:
                    # Si no se puede cargar la fuente, usar la predeterminada
                    font = ImageFont.load_default()
                
                # Crear un dibujo temporal para calcular el tamaño del texto
                temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
                
                # Usar textbbox para obtener las dimensiones del texto
                bbox = temp_draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                # Espaciado entre marcas de agua
                spacing_x = int(text_width * 3)  # Aumentar el espaciado
                spacing_y = int(text_height * 3)
                
                # Crear un dibujo en la capa de marca de agua
                draw = ImageDraw.Draw(watermark)
                
                # Dibujar la marca de agua en un patrón de tablero de ajedrez
                for i in range(-spacing_x, img.width + spacing_x, spacing_x):
                    for j in range(-spacing_y, img.height + spacing_y, spacing_y):
                        # Posición con desplazamiento para filas impares
                        x = i + ((j // spacing_y) % 2) * (spacing_x // 2)
                        y = j
                        
                        # Dibujar el texto con borde para mejor visibilidad
                        # Primero el borde
                        border_opacity = int(255 * opacity * 0.7)  # Borde ligeramente más transparente
                        for x_offset in [-2, 0, 2]:
                            for y_offset in [-2, 0, 2]:
                                if x_offset != 0 or y_offset != 0:  # No dibujar en la posición central
                                    draw.text(
                                        (x + x_offset, y + y_offset),
                                        text,
                                        font=font,
                                        fill=(0, 0, 0, border_opacity)
                                    )
                        # Luego el texto principal
                        draw.text(
                            (x, y),
                            text,
                            font=font,
                            fill=(255, 255, 255, int(255 * opacity))
                        )
                
                # Rotar ligeramente la marca de agua (15 grados en lugar de 30)
                watermark = watermark.rotate(15, resample=Image.BICUBIC, expand=False)
                
                # Combinar la imagen original con la marca de agua
                result = Image.alpha_composite(img, watermark)
                
                # Convertir a RGB si es necesario para el formato de salida
                if output_path.lower().endswith(('.jpg', '.jpeg')):
                    result = result.convert('RGB')
                
                # Guardar la imagen con calidad reducida
                result.save(output_path, quality=quality, optimize=True)
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
                        
                        # Obtener el nombre del archivo original sin extensión
                        original_name = os.path.splitext(os.path.basename(image_path))[0]
                        
                        # Generar nombre de archivo con formato: nombre_original_nXX_nYY
                        nums_str = "_n".join([""] + [str(num) for num in sorted(numeros_encontrados)]).lstrip("_")
                        nombre_base = f"{original_name}_{nums_str}"
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
