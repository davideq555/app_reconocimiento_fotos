from photo_recognition.processor import ImageProcessor


__all__ = ['ImageProcessor']


# Para pruebas locales
if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        processor = ImageProcessor()
        result = processor.process_image(sys.argv[1])
        print('Resultado del reconocimiento:')
        print(result)
    else:
        print('Por favor, proporciona la ruta a una imagen como argumento')
