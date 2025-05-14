import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import requests
import json
from pathlib import Path
import threading
import queue
import time

class OCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Reconocimiento de Números con Ollama")
        self.root.geometry("800x600")
        
        # Variables
        self.folder_path = tk.StringVar()
        self.processing = False
        self.stop_processing = False
        self.result_queue = queue.Queue()
        
        # Configuración de la interfaz
        self.setup_ui()
        self.check_queue()
        
    def setup_ui(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Frame de selección de carpeta
        folder_frame = ttk.LabelFrame(main_frame, text="Seleccionar Carpeta", padding="10")
        folder_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(folder_frame, text="Carpeta con imágenes:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(folder_frame, textvariable=self.folder_path, width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(folder_frame, text="Examinar...", command=self.browse_folder).pack(side=tk.LEFT, padx=5)
        
        # Frame de resultados
        result_frame = ttk.LabelFrame(main_frame, text="Resultados", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Treeview para mostrar resultados
        columns = ("archivo", "numero_reconocido", "confianza")
        self.tree = ttk.Treeview(result_frame, columns=columns, show="headings")
        
        # Configurar columnas
        self.tree.heading("archivo", text="Archivo")
        self.tree.heading("numero_reconocido", text="Número")
        self.tree.heading("confianza", text="Confianza")
        
        # Ajustar ancho de columnas
        self.tree.column("archivo", width=400)
        self.tree.column("numero_reconocido", width=200, anchor=tk.CENTER)
        self.tree.column("confianza", width=100, anchor=tk.CENTER)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Empaquetar treeview y scrollbar
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Frame de controles
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        self.process_btn = ttk.Button(control_frame, text="Procesar Imágenes", command=self.toggle_processing)
        self.process_btn.pack(side=tk.LEFT, padx=5)
        
        self.export_btn = ttk.Button(control_frame, text="Exportar a CSV", command=self.export_to_csv, state=tk.DISABLED)
        self.export_btn.pack(side=tk.LEFT, padx=5)
        
        # Barra de progreso
        self.progress = ttk.Progressbar(control_frame, mode='determinate', length=200)
        self.progress.pack(side=tk.RIGHT, padx=5)
        
        # Etiqueta de estado
        self.status_var = tk.StringVar(value="Listo")
        ttk.Label(control_frame, textvariable=self.status_var).pack(side=tk.RIGHT, padx=5)
    
    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
            self.scan_images()
    
    def scan_images(self):
        folder = self.folder_path.get()
        if not folder or not os.path.isdir(folder):
            return
            
        # Limpiar resultados anteriores
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Escanear imágenes
        image_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff')
        self.image_files = [f for f in os.listdir(folder) 
                          if os.path.isfile(os.path.join(folder, f)) 
                          and f.lower().endswith(image_extensions)]
        
        self.total_images = len(self.image_files)
        self.processed_images = 0
        self.progress['maximum'] = self.total_images
        self.progress['value'] = 0
        
        # Habilitar/deshabilitar botones
        self.export_btn['state'] = tk.DISABLED
        
        if self.total_images > 0:
            self.process_btn['state'] = tk.NORMAL
            self.status_var.set(f"{self.total_images} imágenes encontradas")
        else:
            self.process_btn['state'] = tk.DISABLED
            self.status_var.set("No se encontraron imágenes")
    
    def toggle_processing(self):
        if not self.processing:
            self.start_processing()
        else:
            self.stop_processing = True
            self.process_btn['state'] = tk.DISABLED
    
    def start_processing(self):
        if not hasattr(self, 'image_files') or not self.image_files:
            return
            
        self.processing = True
        self.stop_processing = False
        self.process_btn['text'] = "Detener"
        self.processed_images = 0
        self.progress['value'] = 0
        
        # Iniciar hilo para el procesamiento
        threading.Thread(target=self.process_images, daemon=True).start()
    
    def process_images(self):
        folder = self.folder_path.get()
        
        for idx, image_file in enumerate(self.image_files):
            if self.stop_processing:
                break
                
            try:
                image_path = os.path.join(folder, image_file)
                
                # Aquí iría la lógica para enviar la imagen a Ollama
                # Por ahora simulamos una respuesta
                time.sleep(1)  # Simulamos procesamiento
                
                # Simulamos un resultado
                result = {
                    "file": image_file,
                    "number": "1234",  # Número reconocido
                    "confidence": 0.95  # Nivel de confianza
                }
                
                # Actualizamos la interfaz a través de la cola
                self.result_queue.put(("update", result))
                
            except Exception as e:
                self.result_queue.put(("error", f"Error procesando {image_file}: {str(e)}"))
            
            # Actualizar progreso
            self.processed_images += 1
            self.result_queue.put(("progress", self.processed_images))
        
        # Finalizar procesamiento
        self.result_queue.put(("done", None))
    
    def check_queue(self):
        try:
            while True:
                msg_type, data = self.result_queue.get_nowait()
                
                if msg_type == "update":
                    # Añadir resultado al treeview
                    self.tree.insert("", tk.END, values=(
                        data["file"],
                        data["number"],
                        f"{data['confidence']*100:.1f}%"
                    ))
                elif msg_type == "progress":
                    # Actualizar barra de progreso
                    self.progress['value'] = data
                    self.status_var.set(f"Procesando... {data}/{self.total_images}")
                elif msg_type == "error":
                    messagebox.showerror("Error", data)
                elif msg_type == "done":
                    self.processing = False
                    self.stop_processing = False
                    self.process_btn['text'] = "Procesar Imágenes"
                    self.status_var.set("Procesamiento completado")
                    self.export_btn['state'] = tk.NORMAL
        except queue.Empty:
            pass
        
        # Volver a programar la verificación
        self.root.after(100, self.check_queue)
    
    def export_to_csv(self):
        if not hasattr(self, 'image_files') or not self.image_files:
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")],
            title="Guardar resultados como..."
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                # Escribir encabezados
                f.write("Archivo,Número,Confianza\n")
                
                # Escribir datos
                for item in self.tree.get_children():
                    values = self.tree.item(item)['values']
                    f.write(f'"{values[0]}",{values[1]},{values[2]}\n')
            
            messagebox.showinfo("Éxito", "Los resultados se exportaron correctamente.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo exportar el archivo: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = OCRApp(root)
    root.mainloop()
