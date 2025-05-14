# Aplicación de Reconocimiento de Números con Ollama

Esta aplicación permite reconocer números en imágenes utilizando Ollama como motor de reconocimiento de imágenes. La interfaz gráfica facilita la selección de carpetas y el procesamiento de múltiples imágenes de manera sencilla.

## Características Principales

- Interfaz gráfica intuitiva y fácil de usar
- Soporte para múltiples formatos de imagen (PNG, JPG, JPEG, BMP, GIF)
- Barra de progreso en tiempo real
- Registro detallado del proceso
- Exportación de resultados a formato JSON
- Compatible con Windows, macOS y Linux
- Soporte para diferentes modelos de Ollama (llava:7b, llava:13b, llava:34b)

## Requisitos Previos

- Python 3.8 o superior
- Ollama instalado y en ejecución (https://ollama.ai/)
- Conexión a Internet para descargar los modelos

## Instalación

1. Clona o descarga este repositorio
2. Instala las dependencias:

```bash
pip install -r requirements.txt
```

3. Asegúrate de tener instalado el paquete `ollama`:

```bash
pip install ollama
```

4. Descarga el modelo deseado de Ollama (por ejemplo, llava:7b):

```bash
ollama pull llava:7b
```

## Uso

1. Asegúrate de que el servidor de Ollama esté en ejecución:

```bash
ollama serve
```

2. Ejecuta la aplicación:

```bash
python main.py
```

3. En la interfaz de la aplicación:
   - Haz clic en "Seleccionar Carpeta" para elegir la carpeta con las imágenes
   - Selecciona el modelo de Ollama que deseas utilizar
   - Haz clic en "Procesar Imágenes" para comenzar el reconocimiento
   - Monitorea el progreso en la barra y el área de registro
   - Una vez finalizado, puedes guardar los resultados en un archivo JSON

## Estructura del Proyecto

- `main.py`: Aplicación principal con la interfaz gráfica
- `image_processor.py`: Módulo para el procesamiento de imágenes con Ollama
- `requirements.txt`: Dependencias del proyecto

## Personalización

Puedes modificar el prompt en `image_processor.py` para ajustar el comportamiento del reconocimiento según tus necesidades específicas.

## Notas

- El rendimiento puede variar según el hardware y el tamaño de las imágenes
- Para imágenes grandes, la aplicación redimensionará automáticamente manteniendo la relación de aspecto
- Se recomienda tener al menos 8GB de RAM para un rendimiento óptimo con modelos más grandes

## Solución de Problemas

Si la aplicación no puede conectarse a Ollama:
1. Asegúrate de que el servidor de Ollama esté en ejecución
2. Verifica que el puerto 11434 esté accesible
3. Comprueba que hayas descargado el modelo que intentas utilizar

## Licencia

Este proyecto está bajo la Licencia MIT.
