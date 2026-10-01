import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.widgets.scrolled import ScrolledFrame

from .batch import DEFAULT_OUTPUT_DIR, MODELS, check_ollama, find_images, process_batch, write_csv
from .providers import PROVIDERS, ProviderConfig


class OCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Photo Recognition')
        self.root.geometry('1120x760')
        self.root.minsize(960, 640)

        # Variables
        self.folder_path = tk.StringVar()
        self.output_path = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.model_name = tk.StringVar(value=MODELS[0])
        self.provider_name = tk.StringVar(value='Ollama')
        self.api_key = tk.StringVar()
        self.base_url = tk.StringVar()
        self.batch_error = None
        self.connection_pending = False
        self.dark_mode = tk.BooleanVar(value=False)
        self.processing = False
        self.closed = False
        self.cancelled = threading.Event()
        self.result_queue = queue.Queue()
        self.image_files = []
        self.results = []
        self.worker = None
        self.total_images = 0
        self.processed_images = 0
        self.status_var = tk.StringVar(value='Choose a folder to get started')
        self.connection_var = tk.StringVar(value='Local Ollama · not checked')
        self.stats = {name: tk.StringVar(value='0') for name in ('Images', 'Processed', 'With numbers', 'Errors')}

        # Configuración de la interfaz
        self.setup_ui()
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.check_queue()

    def setup_ui(self):
        # Frame principal
        # Widget principal
        main_frame = ttk.Frame(self.root, padding=24)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)

        header = ttk.Frame(main_frame)
        header.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 20))
        ttk.Label(header, text='Photo Recognition', font=('TkDefaultFont', 24, 'bold'), bootstyle='primary').pack(side=tk.LEFT)
        ttk.Checkbutton(header, text='Dark mode', variable=self.dark_mode,
                        command=self.toggle_theme, bootstyle='round-toggle').pack(side=tk.RIGHT)
        ttk.Label(main_frame, text='Find participant numbers. Choose local or cloud recognition.',
                  bootstyle='secondary').grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 20))

        sidebar = ScrolledFrame(main_frame, width=310, height=420, autohide=True)
        sidebar.grid(row=2, column=0, sticky='nsew', padx=(0, 24))

        # Frame de selección de carpeta
        # Selección de carpeta
        folder_frame = ttk.Labelframe(sidebar, text='  1. Image folder  ', padding=16)
        folder_frame.pack(fill=tk.X, pady=(0, 16))
        self.folder_entry = ttk.Entry(folder_frame, textvariable=self.folder_path, width=30)
        self.folder_entry.pack(fill=tk.X, pady=(0, 10))
        self.folder_btn = ttk.Button(folder_frame, text='Browse images', command=self.browse_folder, bootstyle='primary-outline')
        self.folder_btn.pack(fill=tk.X)
        ttk.Label(folder_frame, text='JPG · PNG · BMP · GIF · TIFF', bootstyle='secondary').pack(anchor='w', pady=(10, 0))

        settings = ttk.Labelframe(sidebar, text='  2. Recognition  ', padding=16)
        settings.pack(fill=tk.X, pady=(0, 16))
        ttk.Label(settings, text='Provider').pack(anchor='w', pady=(0, 6))
        self.provider_combo = ttk.Combobox(settings, textvariable=self.provider_name, values=PROVIDERS, state='readonly', width=28)
        self.provider_combo.pack(fill=tk.X, pady=(0, 12))
        self.provider_combo.bind('<<ComboboxSelected>>', self.provider_changed)
        # Modelo seleccionado
        ttk.Label(settings, text='Vision model ID').pack(anchor='w', pady=(0, 6))
        self.model_combo = ttk.Combobox(settings, textvariable=self.model_name, values=MODELS, width=28)
        self.model_combo.pack(fill=tk.X)

        self.key_fields = ttk.Frame(settings)
        ttk.Label(self.key_fields, text='API key · session only').pack(anchor='w', pady=(12, 6))
        self.api_key_entry = ttk.Entry(self.key_fields, textvariable=self.api_key, show='*', width=28)
        self.api_key_entry.pack(fill=tk.X)
        self.url_fields = ttk.Frame(settings)
        ttk.Label(self.url_fields, text='HTTPS API base URL (including /v1)').pack(anchor='w', pady=(12, 6))
        self.base_url_entry = ttk.Entry(self.url_fields, textvariable=self.base_url, width=28)
        self.base_url_entry.pack(fill=tk.X)
        self.connection_frame = ttk.Frame(settings)
        self.connection_frame.pack(fill=tk.X)
        self.connection_btn = ttk.Button(self.connection_frame, text='Check Ollama', command=self.check_connection, bootstyle='secondary-outline')
        self.connection_btn.pack(fill=tk.X, pady=(12, 6))
        ttk.Label(self.connection_frame, textvariable=self.connection_var, bootstyle='secondary', wraplength=255).pack(anchor='w')

        output_frame = ttk.Labelframe(sidebar, text='  3. Output copies  ', padding=16)
        output_frame.pack(fill=tk.X)
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_path, width=30)
        self.output_entry.pack(fill=tk.X, pady=(0, 10))
        self.output_btn = ttk.Button(output_frame, text='Choose destination', command=self.browse_output, bootstyle='secondary-outline')
        self.output_btn.pack(fill=tk.X)
        ttk.Label(output_frame, text='Numbered filenames + COPIA watermark\n25% dimensions. Originals stay untouched.',
                  bootstyle='secondary', wraplength=255).pack(anchor='w', pady=(12, 0))

        workspace = ttk.Frame(main_frame)
        workspace.grid(row=2, column=1, sticky='nsew')
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(1, weight=1)
        summary = ttk.Frame(workspace)
        summary.grid(row=0, column=0, sticky='ew', pady=(0, 16))
        for column, (name, value) in enumerate(self.stats.items()):
            summary.columnconfigure(column, weight=1)
            card = ttk.Frame(summary, padding=12, bootstyle='light')
            card.grid(row=0, column=column, sticky='ew', padx=(0, 8 if column < 3 else 0))
            ttk.Label(card, textvariable=value, font=('TkDefaultFont', 22, 'bold'), bootstyle='inverse-light').pack(anchor='w')
            ttk.Label(card, text=name, bootstyle='inverse-light').pack(anchor='w')

        notebook = ttk.Notebook(workspace)
        notebook.grid(row=1, column=0, sticky='nsew')
        # Frame de resultados
        result_frame = ttk.Frame(notebook, padding=12)
        notebook.add(result_frame, text='  Results  ')
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)

        # Treeview para mostrar resultados
        columns = ('file', 'numbers', 'status')
        self.tree = ttk.Treeview(result_frame, columns=columns, show='headings', bootstyle='primary', height=12)
        # Configurar columnas
        for key, label in zip(columns, ('Photo', 'Numbers', 'Status')):
            self.tree.heading(key, text=label)
        # Ajustar ancho de columnas
        self.tree.column('file', width=240, minwidth=100)
        self.tree.column('numbers', width=140, minwidth=80)
        self.tree.column('status', width=130, minwidth=80)
        # Scrollbar
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.tree.yview)
        horizontal = ttk.Scrollbar(result_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        # Empaquetar treeview y scrollbar
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')

        # Área de registro
        log_frame = ttk.Frame(notebook, padding=12)
        notebook.add(log_frame, text='  Activity  ')
        self.log_area = tk.Text(log_frame, wrap='word', state=tk.DISABLED, borderwidth=0, font=('TkFixedFont', 10))
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_area.yview)
        self.log_area.configure(yscrollcommand=log_scroll.set)
        self.log_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Frame de controles
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(20, 0))
        # Botón de procesar
        self.process_btn = ttk.Button(control_frame, text='Start recognition', command=self.start_processing, bootstyle='success')
        self.process_btn.pack(side=tk.LEFT)
        self.cancel_btn = ttk.Button(control_frame, text='Cancel', command=self.cancel, bootstyle='danger-outline', state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=10)
        self.export_btn = ttk.Button(control_frame, text='Export CSV', command=self.export_to_csv, state=tk.DISABLED, bootstyle='primary-outline')
        self.export_btn.pack(side=tk.RIGHT)

        # Barra de progreso
        self.progress = ttk.Progressbar(main_frame, mode='determinate', bootstyle='success-striped')
        self.progress.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(14, 8))
        # Etiqueta de estado
        ttk.Label(main_frame, textvariable=self.status_var, bootstyle='secondary').grid(row=5, column=0, columnspan=2, sticky='w')
        # Agregar widgets al layout
        # Estilos
        self.toggle_theme()
        self.provider_changed()

    def provider_changed(self, event=None):
        if self.processing:
            return
        local = self.provider_name.get() == 'Ollama'
        self.api_key.set('')
        self.base_url.set('')
        self.model_name.set(MODELS[0] if local else '')
        self.model_combo.configure(values=MODELS if local else ())
        self.key_fields.pack_forget()
        self.url_fields.pack_forget()
        if not local:
            self.key_fields.pack(fill=tk.X, before=self.connection_frame)
        if self.provider_name.get() == 'OpenAI-compatible':
            self.url_fields.pack(fill=tk.X, before=self.connection_frame)
        self.connection_btn.configure(state=tk.NORMAL if local and not self.connection_pending else tk.DISABLED)
        self.connection_var.set(
            'Local Ollama · not checked' if local else
            'Enter a vision model ID from your account. Photos leave this device; API charges may apply.'
        )

    def toggle_theme(self):
        self.root.style.theme_use('darkly' if self.dark_mode.get() else 'flatly')

    def browse_folder(self):
        folder = filedialog.askdirectory(parent=self.root)
        if folder:
            self.folder_path.set(folder)
            try:
                self.scan_images()
            except OSError as error:
                messagebox.showerror('Cannot read folder', str(error), parent=self.root)

    def browse_output(self):
        folder = filedialog.askdirectory(parent=self.root)
        if folder:
            self.output_path.set(folder)

    def scan_images(self):
        # Escanear imágenes
        self.image_files = find_images(Path(self.folder_path.get()).expanduser())
        self.total_images = len(self.image_files)
        self.stats['Images'].set(str(self.total_images))
        self.status_var.set(f'{self.total_images} images ready' if self.image_files else 'No supported images found')
        return self.image_files

    def start_processing(self):
        if self.processing:
            return
        try:
            if not self.folder_path.get().strip() or not self.output_path.get().strip() or not self.model_name.get().strip():
                raise ValueError('Choose image and output folders, and a vision model.')
            images = tuple(self.scan_images())
            if not images:
                raise ValueError('The selected folder has no supported images.')
            folder = Path(self.folder_path.get()).expanduser().resolve()
            output = Path(self.output_path.get()).expanduser().resolve()
            if output == folder:
                raise ValueError('Choose a separate output folder to keep generated copies out of the input batch.')
            if output.exists() and not output.is_dir():
                raise ValueError('The output destination must be a folder.')
            config = ProviderConfig(self.provider_name.get(), self.api_key.get().strip(), self.base_url.get().strip())
            config.validate()
        except (OSError, ValueError) as error:
            messagebox.showerror('Cannot start', str(error), parent=self.root)
            return

        if config.remote and not messagebox.askyesno(
            'Send photos to a cloud provider?',
            f'{len(images)} resized photos will be sent to {config.provider} at:\n{config.endpoint}\n\n'
            'Requests use the API key entered for this session and may incur charges. '
            'The provider\'s data policies apply. Continue?',
            parent=self.root,
        ):
            return

        self.batch_error = None
        # Limpiar resultados anteriores
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results.clear()
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.delete('1.0', tk.END)
        self.log_area.configure(state=tk.DISABLED)
        self.processed_images = 0
        for name in ('Processed', 'With numbers', 'Errors'):
            self.stats[name].set('0')
        self.progress.configure(maximum=len(images), value=0)
        self.cancelled = threading.Event()
        self.set_processing(True)
        self.status_var.set(f'Processing 0 / {len(images)} images')
        # Iniciar hilo para el procesamiento
        self.worker = threading.Thread(target=process_batch, args=(
            images, self.model_name.get().strip(), output, self.result_queue, self.cancelled,
        ), kwargs={'provider_config': config}, daemon=True)
        self.worker.start()

    def set_processing(self, processing):
        self.processing = processing
        # Habilitar/deshabilitar botones
        state = tk.DISABLED if processing else tk.NORMAL
        for widget in (self.folder_entry, self.folder_btn, self.output_entry, self.output_btn,
                       self.model_combo, self.process_btn, self.api_key_entry, self.base_url_entry):
            widget.configure(state=state)
        self.provider_combo.configure(state=tk.DISABLED if processing else 'readonly')
        self.process_btn.configure(text='Recognizing...' if processing else 'Start recognition')
        self.cancel_btn.configure(state=tk.NORMAL if processing else tk.DISABLED)
        self.export_btn.configure(state=tk.NORMAL if self.results and not processing else tk.DISABLED)

    def cancel(self):
        self.cancelled.set()
        self.cancel_btn.configure(state=tk.DISABLED)
        self.status_var.set('Cancelling after the current image finishes...')

    def check_queue(self):
        if self.closed:
            return
        try:
            for _ in range(100):
                msg_type, data = self.result_queue.get_nowait()
                if msg_type == 'result':
                    self.results.append(data)
                    numbers = data.get('numeros_encontrados', [])
                    status = 'Error' if data.get('error') else ('Recognized' if numbers else 'No numbers')
                    # Añadir resultado al treeview
                    item = self.tree.insert('', tk.END, values=(data['file'], ', '.join(map(str, numbers)), status))
                    self.tree.see(item)
                    for name, increment in (('With numbers', bool(numbers)), ('Errors', bool(data.get('error')))):
                        self.stats[name].set(str(int(self.stats[name].get()) + increment))
                    self.log(f"{data['file']}: {data.get('error') or status}")
                    if data.get('output_path'):
                        self.log(f"Saved: {data['output_path']}")
                elif msg_type == 'progress':
                    # Actualizar barra de progreso
                    self.processed_images, total = data
                    self.progress['value'] = self.processed_images
                    self.stats['Processed'].set(str(self.processed_images))
                    if not self.cancelled.is_set():
                        self.status_var.set(f'Processing {self.processed_images} / {total} images')
                elif msg_type == 'log':
                    self.log(data)
                elif msg_type == 'error':
                    self.batch_error = data
                    self.log(data)
                elif msg_type == 'done':
                    self.set_processing(False)
                    # Mostrar resumen
                    status = 'Failed' if self.batch_error else ('Cancelled' if data else 'Completed')
                    self.status_var.set(f"{status} · {self.processed_images}/{self.total_images} images · {self.stats['Errors'].get()} errors")
                    # Mostrar los números encontrados
                    self.log(self.status_var.get())
                elif msg_type == 'connection':
                    models, error = data
                    self.connection_pending = False
                    if self.provider_name.get() != 'Ollama':
                        continue
                    self.connection_btn.configure(state=tk.NORMAL)
                    self.connection_var.set('Unavailable · see Activity' if error else f'Connected · {len(models)} models installed')
                    if not error:
                        self.model_combo.configure(values=tuple(dict.fromkeys((*models, *MODELS))))
                    self.log(error or 'Ollama connection verified. Choose an installed vision model.')
        except queue.Empty:
            pass
        # Volver a programar la verificación
        self.after_id = self.root.after(75, self.check_queue)

    def log(self, message):
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.insert(tk.END, f'{message}\n')
        self.log_area.see(tk.END)
        self.log_area.configure(state=tk.DISABLED)

    def check_connection(self):
        if self.provider_name.get() != 'Ollama' or self.connection_pending:
            return
        self.connection_pending = True
        # Verificar si Ollama está instalado
        self.connection_btn.configure(state=tk.DISABLED)
        self.connection_var.set('Checking local Ollama...')
        threading.Thread(target=check_ollama, args=(self.result_queue,), daemon=True).start()

    def export_to_csv(self):
        if not self.results or self.processing:
            return
        file_path = filedialog.asksaveasfilename(parent=self.root, defaultextension='.csv',
                                               filetypes=[('CSV files', '*.csv')], title='Export results')
        if file_path:
            try:
                write_csv(self.results, file_path)
                self.status_var.set(f'Exported {len(self.results)} results')
            except OSError as error:
                messagebox.showerror('Export failed', str(error), parent=self.root)

    def close(self):
        if self.processing and not messagebox.askyesno(
            'Recognition in progress', 'Stop and close? The current image may not be saved. Exported files will be kept.',
            parent=self.root,
        ):
            return
        self.cancelled.set()
        self.api_key.set('')
        self.closed = True
        self.root.after_cancel(self.after_id)
        self.root.destroy()


def main():
    # Establecer el estilo de la aplicación
    root = ttk.Window(themename='flatly')
    # Crear y mostrar la ventana principal
    OCRApp(root)
    root.mainloop()
