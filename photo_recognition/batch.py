import csv
from pathlib import Path

from .processor import ImageProcessor


IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff'}
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / 'media'
MODELS = ('llama3.2-vision', 'llava:7b', 'llava:13b', 'llava:34b')


def find_images(folder):
    return sorted(
        (path for path in Path(folder).iterdir()
         if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda path: path.name.casefold(),
    )


def check_ollama(events):
    try:
        events.put(('connection', (ImageProcessor().available_models(), None)))
    except Exception as error:
        events.put(('connection', ([], f'Ollama unavailable: {error}')))


def process_batch(image_paths, model, output_dir, events, cancelled, processor=None, *, provider_config=None):
    total = len(image_paths)
    try:
        processor = processor or ImageProcessor(provider_config=provider_config)
        for index, image_path in enumerate(image_paths, 1):
            if cancelled.is_set():
                break
            events.put(('log', f'Processing: {image_path.name}'))
            try:
                # Procesar la imagen guardando en la carpeta media
                result = processor.process_image(str(image_path), model, output_dir=str(output_dir))
            except Exception as error:
                result = {'error': 'Provider request failed.' if provider_config and provider_config.remote else str(error)}
            events.put(('result', {'file': image_path.name, **result}))
            # Actualizar progreso
            events.put(('progress', (index, total)))
    except Exception:
        events.put(('error', 'Could not process the batch. Check provider settings and input files.'))
    finally:
        # Finalizar procesamiento
        events.put(('done', cancelled.is_set()))


def write_csv(results, destination):
    def cell(value):
        value = str(value or '')
        return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value

    with Path(destination).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        # Escribir encabezados
        writer.writerow(['File', 'Numbers', 'Status', 'Error', 'Output'])
        # Escribir datos
        for result in results:
            writer.writerow([cell(value) for value in (
                result['file'],
                ', '.join(map(str, result.get('numeros_encontrados', []))),
                'Error' if result.get('error') else 'Completed',
                result.get('error', ''),
                result.get('output_path', ''),
            )])
