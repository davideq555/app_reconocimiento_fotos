import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                           QWidget, QLabel, QFileDialog, QProgressBar, QMessageBox,
                           QTextEdit, QHBoxLayout, QComboBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon
from image_processor import ImageProcessor
import json

class ImageProcessingThread(QThread):
    progress_updated = pyqtSignal(int)
    processing_finished = pyqtSignal(dict)
    log_message = pyqtSignal(str)
    
    def __init__(self, folder_path, model_name):
        super().__init__()
        self.folder_path = folder_path
        self.model_name = model_name
        self.processor = ImageProcessor()
        # Crear carpeta media si no existe
        self.media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media')
        os.makedirs(self.media_dir, exist_ok=True)
        
    def run(self):
        try:
            results = {}
            image_files = [f for f in os.listdir(self.folder_path) 
                         if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))]
            
            total_images = len(image_files)
            self.log_message.emit(f"Encontradas {total_images} imágenes para procesar")
            
            for idx, image_file in enumerate(image_files, 1):
                if self.isInterruptionRequested():
                    self.log_message.emit("Proceso cancelado por el usuario")
                    return
                    
                image_path = os.path.join(self.folder_path, image_file)
                self.log_message.emit(f"Procesando: {image_file}...")
                
                try:
                    # Procesar la imagen guardando en la carpeta media
                    result = self.processor.process_image(
                        image_path, 
                        self.model_name,
                        output_dir=self.media_dir
                    )
                    results[image_file] = result
                    
                    if isinstance(result, dict) and result.get('success', False):
                        nums = result.get('numeros_encontrados', [])
                        if nums:
                            output_file = os.path.basename(result.get('output_path', ''))
                            self.log_message.emit(f"  - Números encontrados: {', '.join(map(str, nums))}")
                            if output_file:
                                self.log_message.emit(f"  - Imagen guardada como: {output_file}")
                        else:
                            self.log_message.emit("  - No se encontraron números")
                    else:
                        error_msg = result.get('error', 'Error desconocido') if isinstance(result, dict) else str(result)
                        self.log_message.emit(f"  - Error: {error_msg}")
                        
                except Exception as e:
                    error_msg = f"Error inesperado: {str(e)}"
                    results[image_file] = {"success": False, "error": error_msg}
                    self.log_message.emit(f"  - {error_msg}")
                
                progress = int((idx / total_images) * 100)
                self.progress_updated.emit(progress)
            
            self.processing_finished.emit(results)
            
        except Exception as e:
            self.log_message.emit(f"Error en el procesamiento: {str(e)}")
            self.processing_finished.emit({"error": f"Error en el procesamiento: {str(e)}"})

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Reconocedor de Números con Ollama")
        self.setGeometry(100, 100, 800, 600)
        
        # Variables
        self.folder_path = ""
        self.processing_thread = None
        self.results = {}
        
        # Configuración de la interfaz
        self.setup_ui()
        
    def setup_ui(self):
        # Widget principal
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Selección de carpeta
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("Carpeta no seleccionada")
        folder_btn = QPushButton("Seleccionar Carpeta")
        folder_btn.clicked.connect(self.select_folder)
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(folder_btn)
        
        # Modelo seleccionado
        model_layout = QHBoxLayout()
        model_label = QLabel("Modelo de Ollama:")
        self.model_combo = QComboBox()
        self.model_combo.addItems(["llama3.2-vision", "llava:7b", "llava:13b", "llava:34b"])
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo)
        
        # Botón de procesar
        self.process_btn = QPushButton("Procesar Imágenes")
        self.process_btn.clicked.connect(self.process_images)
        self.process_btn.setEnabled(False)
        
        # Barra de progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        # Área de registro
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        
        # Agregar widgets al layout
        layout.addLayout(folder_layout)
        layout.addLayout(model_layout)
        layout.addWidget(self.process_btn)
        layout.addWidget(self.progress_bar)
        layout.addWidget(QLabel("Registro:"))
        layout.addWidget(self.log_area)
        
        # Estilos
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                font-size: 14px;
                border-radius: 4px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
            }
            QLabel {
                font-size: 14px;
            }
            QComboBox {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 4px;
                min-width: 200px;
            }
        """)
    
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta")
        if folder:
            self.folder_path = folder
            self.folder_label.setText(folder)
            self.process_btn.setEnabled(True)
            self.log(f"Carpeta seleccionada: {folder}")
    
    def process_images(self):
        if not self.folder_path:
            QMessageBox.warning(self, "Error", "Por favor selecciona una carpeta primero")
            return
            
        self.process_btn.setEnabled(False)
        self.process_btn.setText("Procesando...")
        self.progress_bar.setValue(0)
        self.log("Iniciando procesamiento de imágenes...")
        
        model_name = self.model_combo.currentText()
        self.processing_thread = ImageProcessingThread(self.folder_path, model_name)
        self.processing_thread.progress_updated.connect(self.update_progress)
        self.processing_thread.processing_finished.connect(self.processing_finished)
        self.processing_thread.log_message.connect(self.log)
        self.processing_thread.start()
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def processing_finished(self, results):
        self.results = results
        self.process_btn.setEnabled(True)
        self.process_btn.setText("Procesar Imágenes")
        self.log("Procesamiento completado")
        
        # Mostrar resumen
        total = len(results)
        success = sum(1 for r in results.values() if isinstance(r, dict) and r.get('success', False))
        
        # Mostrar los números encontrados
        for filename, result in results.items():
            if isinstance(result, dict):
                if result.get('success'):
                    nums = result.get('numeros_encontrados', [])
                    if nums:
                        self.log(f"{filename}: Encontrados números: {', '.join(map(str, nums))}")
                    else:
                        self.log(f"{filename}: No se encontraron números")
                else:
                    self.log(f"{filename}: {result.get('error', 'Error desconocido')}")
        
        self.log(f"Resumen: {success} de {total} imágenes procesadas correctamente")
    
    
    def log(self, message):
        self.log_area.append(f"> {message}")
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())
    
    def closeEvent(self, event):
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.requestInterruption()
            self.processing_thread.wait()
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    # Establecer el estilo de la aplicación
    app.setStyle('Fusion')
    
    # Crear y mostrar la ventana principal
    window = MainWindow()
    window.show()
    
    # Verificar si Ollama está instalado
    try:
        import ollama
        try:
            ollama.list()
        except Exception as e:
            QMessageBox.critical(
                None, 
                "Error de Conexión", 
                "No se pudo conectar con Ollama. Asegúrate de que el servidor de Ollama esté en ejecución."
            )
    except ImportError:
        QMessageBox.critical(
            None, 
            "Error de Dependencias", 
            "El paquete 'ollama' no está instalado. Por favor, instálalo con: pip install ollama"
        )
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
