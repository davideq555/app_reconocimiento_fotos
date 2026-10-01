import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import ttkbootstrap as ttk

from photo_recognition.ui import OCRApp


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = ttk.Window(themename='flatly')
            cls.root.withdraw()
        except tk.TclError as error:
            raise unittest.SkipTest(f'Display unavailable: {error}')

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / 'photo.jpg').touch()
        self.app = OCRApp(self.root)
        self.app.folder_path.set(str(self.folder))
        self.app.output_path.set(str(self.folder / 'output'))

    def tearDown(self):
        self.app.cancelled.set()
        if self.app.worker:
            self.app.worker.join(2)
        self.app.closed = True
        self.root.after_cancel(self.app.after_id)
        for widget in self.root.winfo_children():
            widget.destroy()

    def wait_for_completion(self):
        deadline = time.monotonic() + 3
        while self.app.processing and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.app.processing)

    def test_light_and_dark_themes(self):
        self.assertEqual(self.root.style.theme_use(), 'flatly')
        self.app.dark_mode.set(True)
        self.app.toggle_theme()
        self.assertEqual(self.root.style.theme_use(), 'darkly')
        self.app.dark_mode.set(False)
        self.app.toggle_theme()
        self.assertEqual(self.root.style.theme_use(), 'flatly')

    @patch('photo_recognition.batch.ImageProcessor')
    def test_full_worker_result_flow_and_export(self, processor):
        # Aquí iría la lógica para enviar la imagen a Ollama
        # Por ahora simulamos una respuesta
        def recognize(*args, **kwargs):
            time.sleep(0.02)  # Simulamos procesamiento
            # Simulamos un resultado
            result = {
                'number': '1234',  # Número reconocido
                'confidence': 0.95,  # Nivel de confianza
                'success': True,
                'numeros_encontrados': [1234],
                'output_path': str(self.folder / 'output' / 'photo_n1234.jpg'),
            }
            # Actualizamos la interfaz a través de la cola
            return result

        processor.return_value.process_image.side_effect = recognize
        self.app.start_processing()
        self.assertTrue(self.app.processing)
        self.assertTrue(self.app.folder_btn.instate(['disabled']))
        self.wait_for_completion()
        row = self.app.tree.item(self.app.tree.get_children()[0])['values']
        self.assertEqual(row[0], 'photo.jpg')
        self.assertEqual(str(row[1]), '1234')
        self.assertEqual(row[2], 'Recognized')
        self.assertEqual(self.app.stats['Processed'].get(), '1')
        self.assertEqual(self.app.stats['With numbers'].get(), '1')
        self.assertFalse(self.app.export_btn.instate(['disabled']))
        destination = self.folder / 'export.csv'
        with patch('photo_recognition.ui.filedialog.asksaveasfilename', return_value=str(destination)):
            self.app.export_to_csv()
        self.assertIn('1234', destination.read_text(encoding='utf-8-sig'))

    @patch('photo_recognition.ui.messagebox.showerror')
    def test_invalid_folder_does_not_start_worker(self, showerror):
        self.app.folder_path.set(str(self.folder / 'missing'))
        self.app.start_processing()
        self.assertFalse(self.app.processing)
        showerror.assert_called_once()

    @patch('photo_recognition.ui.messagebox.showerror')
    def test_same_output_folder_is_rejected(self, showerror):
        self.app.output_path.set(str(self.folder))
        self.app.start_processing()
        self.assertFalse(self.app.processing)
        showerror.assert_called_once()

    @patch('photo_recognition.batch.ImageProcessor')
    def test_backend_failure_restores_controls(self, processor):
        processor.return_value.process_image.side_effect = RuntimeError('Ollama offline')
        self.app.start_processing()
        self.wait_for_completion()
        self.assertEqual(self.app.stats['Errors'].get(), '1')
        self.assertFalse(self.app.process_btn.instate(['disabled']))
        self.assertIn('Ollama offline', self.app.log_area.get('1.0', tk.END))

    @patch('photo_recognition.batch.ImageProcessor')
    def test_cancel_keeps_completed_result_and_can_restart(self, processor):
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        (self.folder / 'second.jpg').touch()

        def recognize(*args, **kwargs):
            entered.set()
            release.wait(2)
            return {'success': True, 'numeros_encontrados': [42]}

        processor.return_value.process_image.side_effect = recognize
        self.app.start_processing()
        self.assertTrue(entered.wait(2))
        self.app.cancel()
        release.set()
        self.wait_for_completion()
        self.assertEqual(len(self.app.results), 1)
        self.assertIn('Cancelled', self.app.status_var.get())
        self.app.start_processing()
        self.wait_for_completion()
        self.assertEqual(len(self.app.results), 2)
        self.assertEqual(self.app.stats['Processed'].get(), '2')

    def select_cloud(self, provider='OpenAI'):
        self.app.provider_name.set(provider)
        self.app.provider_changed()
        self.app.model_name.set('vision-model')
        self.app.api_key.set('test-only-secret')

    def test_provider_switch_clears_key_and_updates_controls(self):
        self.select_cloud()
        self.assertEqual(self.app.api_key_entry.cget('show'), '*')
        self.assertTrue(self.app.connection_btn.instate(['disabled']))
        self.app.provider_name.set('Gemini')
        self.app.provider_changed()
        self.assertEqual(self.app.api_key.get(), '')
        self.assertEqual(self.app.model_name.get(), '')
        self.app.provider_name.set('Ollama')
        self.app.provider_changed()
        self.assertEqual(self.app.model_name.get(), 'llama3.2-vision')
        self.assertFalse(self.app.connection_btn.instate(['disabled']))

    @patch('photo_recognition.ui.messagebox.showerror')
    @patch('photo_recognition.batch.ImageProcessor')
    def test_missing_cloud_key_is_rejected_without_request(self, processor, showerror):
        self.select_cloud()
        self.app.api_key.set('')
        self.app.start_processing()
        self.assertFalse(self.app.processing)
        processor.assert_not_called()
        showerror.assert_called_once()

    @patch('photo_recognition.ui.messagebox.askyesno', return_value=False)
    @patch('photo_recognition.batch.ImageProcessor')
    def test_declining_upload_keeps_results_and_does_not_start_worker(self, processor, confirm):
        self.select_cloud()
        previous = {'file': 'previous.jpg', 'numeros_encontrados': [42]}
        self.app.results.append(previous)
        self.app.start_processing()
        processor.assert_not_called()
        self.assertFalse(self.app.processing)
        self.assertEqual(self.app.results, [previous])
        self.assertIn('https://api.openai.com/v1', confirm.call_args.args[1])
        self.assertNotIn('test-only-secret', confirm.call_args.args[1])

    @patch('photo_recognition.ui.messagebox.askyesno', return_value=True)
    @patch('photo_recognition.batch.ImageProcessor')
    def test_cloud_config_is_snapshotted_for_worker(self, processor, confirm):
        self.select_cloud()
        processor.return_value.process_image.return_value = {'success': True, 'numeros_encontrados': [42]}
        self.app.start_processing()
        self.assertTrue(self.app.provider_combo.instate(['disabled']))
        self.assertTrue(self.app.api_key_entry.instate(['disabled']))
        self.wait_for_completion()
        config = processor.call_args.kwargs['provider_config']
        self.assertEqual(config.provider, 'OpenAI')
        self.assertEqual(config.api_key, 'test-only-secret')
        self.assertNotIn('test-only-secret', self.app.log_area.get('1.0', tk.END))
        self.assertTrue(self.app.provider_combo.instate(['readonly']))
        confirm.assert_called_once()

    def test_late_ollama_check_cannot_change_cloud_model_list(self):
        self.select_cloud('Gemini')
        self.app.result_queue.put(('connection', (['local-model'], None)))
        self.root.after_cancel(self.app.after_id)
        self.app.check_queue()
        self.assertTrue(self.app.connection_btn.instate(['disabled']))
        self.assertNotIn('local-model', self.app.model_combo.cget('values'))

    @patch('photo_recognition.ui.messagebox.askyesno', return_value=True)
    @patch('photo_recognition.batch.ImageProcessor')
    def test_provider_initialization_failure_finishes_with_error(self, processor, confirm):
        self.select_cloud()
        processor.side_effect = RuntimeError('test-only-secret')
        self.app.start_processing()
        self.wait_for_completion()
        self.assertIn('Failed', self.app.status_var.get())
        self.assertNotIn('test-only-secret', self.app.log_area.get('1.0', tk.END))
        self.assertFalse(self.app.process_btn.instate(['disabled']))

    def test_entry_points_share_the_same_application(self):
        import app
        import main
        import image_processor
        from photo_recognition.processor import ImageProcessor
        from photo_recognition.ui import main as launch

        self.assertIs(app.main, launch)
        self.assertIs(main.main, launch)
        self.assertIs(image_processor.ImageProcessor, ImageProcessor)


if __name__ == '__main__':
    unittest.main()
