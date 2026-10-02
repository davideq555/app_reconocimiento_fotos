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
        ollama_patch = patch('photo_recognition.ui.check_ollama')
        ollama_patch.start()
        self.addCleanup(ollama_patch.stop)
        openai_patch = patch('photo_recognition.ui.check_openai_models')
        self.mock_openai_check = openai_patch.start()
        self.addCleanup(openai_patch.stop)
        self.app = OCRApp(self.root)
        self.apply_connection(['vision-model'])
        self.app.model_name.set('vision-model')
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

    def apply_connection(self, models, error=None):
        self.app.result_queue.put(('connection', (models, error)))
        self.root.after_cancel(self.app.after_id)
        self.app.check_queue()

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
        self.assertTrue(self.app.model_combo.instate(['disabled']))
        self.wait_for_completion()
        self.assertFalse(self.app.model_combo.instate(['disabled']))
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
        self.assertEqual(self.app.key_button.cget('text'), 'Add API key')
        self.assertTrue(self.app.connection_btn.instate(['disabled']))
        self.app.provider_name.set('Gemini')
        self.app.provider_changed()
        self.assertEqual(self.app.api_key.get(), '')
        self.assertEqual(self.app.model_name.get(), '')
        self.app.provider_name.set('Ollama')
        self.app.provider_changed()
        self.assertEqual(self.app.model_name.get(), '')
        self.assertEqual(tuple(self.app.model_combo.cget('values')), ())
        self.assertTrue(self.app.connection_btn.instate(['disabled']))
        self.apply_connection(['local-vision'])
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
        self.assertTrue(self.app.key_button.instate(['disabled']))
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

    def test_initial_ollama_models_are_empty_until_local_check_completes(self):
        self.app.provider_name.set('Ollama')
        self.app.provider_changed()
        self.assertEqual(tuple(self.app.model_combo.cget('values')), ())
        self.assertEqual(self.app.model_name.get(), '')
        self.assertFalse(self.app.model_combo.instate(['readonly']))

    def test_refresh_replaces_model_list_and_invalid_selection(self):
        self.app.check_connection()
        self.assertEqual(tuple(self.app.model_combo.cget('values')), ())
        self.assertEqual(self.app.model_name.get(), '')
        self.apply_connection(['glm-ocr:latest', 'medgemma:4b'])
        self.assertEqual(self.app.model_combo.cget('values'), ('glm-ocr:latest', 'medgemma:4b'))
        self.assertEqual(self.app.model_name.get(), '')
        self.app.model_name.set('medgemma:4b')
        self.apply_connection(['new-vision:latest'])
        self.assertEqual(self.app.model_combo.cget('values'), ('new-vision:latest',))
        self.assertEqual(self.app.model_name.get(), '')

    def test_empty_or_failed_local_check_clears_old_selection(self):
        self.apply_connection([], None)
        self.assertEqual(self.app.model_name.get(), '')
        self.assertEqual(tuple(self.app.model_combo.cget('values')), ())
        self.apply_connection(['vision-model'])
        self.apply_connection([], 'offline')
        self.assertEqual(self.app.model_name.get(), '')
        self.assertEqual(tuple(self.app.model_combo.cget('values')), ())
        self.assertIn('Unavailable', self.app.connection_var.get())

    @patch('photo_recognition.ui.messagebox.showerror')
    @patch('photo_recognition.batch.ImageProcessor')
    def test_no_local_model_cannot_start_batch(self, processor, showerror):
        self.apply_connection([])
        self.app.start_processing()
        processor.assert_not_called()
        showerror.assert_called_once()

    def test_visible_button_adds_key_without_exposing_it(self):
        self.assertEqual(self.app.key_button.cget('text'), 'Add API key')
        self.app.key_button.invoke()
        self.assertTrue(self.app.key_dialog.winfo_exists())
        self.assertEqual(self.app.key_dialog_entry.cget('show'), '*')
        self.app.key_dialog_entry.insert(0, 'test-only-secret')
        self.app.key_dialog_save.invoke()
        self.assertEqual(self.app.provider_name.get(), 'OpenAI')
        self.assertEqual(self.app.api_key.get(), 'test-only-secret')
        self.assertEqual(self.app.key_button.cget('text'), 'Change API key')
        self.assertNotIn('test-only-secret', self.app.key_button.cget('text'))

    def test_cancel_key_dialog_does_not_overwrite_existing_key(self):
        self.select_cloud()
        self.app.key_button.invoke()
        self.app.key_dialog_entry.delete(0, tk.END)
        self.app.key_dialog_entry.insert(0, 'another-secret')
        self.app.key_dialog_cancel.invoke()
        self.assertEqual(self.app.api_key.get(), 'test-only-secret')

    def wait_for_openai_models(self):
        deadline = time.monotonic() + 3
        while self.app.openai_models_pending and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.app.openai_models_pending)

    def test_saving_openai_key_fetches_model_list_without_autoselecting_text_model(self):
        self.mock_openai_check.side_effect = lambda events, config, request_id: events.put(
            ('openai_models', (request_id, ['text-model', 'gpt-vision'], None)))
        self.app.key_button.invoke()
        self.app.key_dialog_entry.insert(0, 'test-only-secret')
        self.app.key_dialog_save.invoke()
        self.wait_for_openai_models()
        self.assertEqual(self.app.model_combo.cget('values'), ('text-model', 'gpt-vision'))
        self.assertEqual(self.app.model_name.get(), '')
        self.assertEqual(self.app.connection_btn.cget('text'), 'Refresh OpenAI models')
        self.assertFalse(self.app.connection_btn.instate(['disabled']))
        self.assertIn('not all support images', self.app.connection_var.get())
        self.assertNotIn('test-only-secret', self.app.log_area.get('1.0', tk.END))

    def test_search_filters_openai_models_case_insensitively_without_api_requests(self):
        self.select_cloud()
        self.app.model_name.set('')
        self.app.result_queue.put(('openai_models', (self.app.openai_request_id,
                                                     ['gpt-vision', 'gpt-4o', 'VISION-mini', 'text-only'], None)))
        self.root.after_cancel(self.app.after_id)
        self.app.check_queue()
        self.assertEqual(self.app.match_count.get(), '4 models')
        self.assertFalse(self.app.model_combo.instate(['readonly']))
        self.assertFalse(hasattr(self.app, 'search_entry'))
        self.app.model_combo.delete(0, tk.END)
        self.app.model_combo.insert(0, '  vIsIoN  ')
        self.assertEqual(self.app.model_combo.cget('values'), ('gpt-vision', 'VISION-mini'))
        self.assertEqual(self.app.model_name.get(), '  vIsIoN  ')
        self.assertEqual(self.app.match_count.get(), '2 of 4 models')
        self.assertEqual(self.mock_openai_check.call_count, 0)
        self.app.model_name.set('no-matches')
        self.assertEqual(tuple(self.app.model_combo.cget('values')), ())
        self.assertEqual(self.app.match_count.get(), '0 of 4 models')
        self.app.model_name.set('')
        self.assertEqual(len(self.app.model_combo.cget('values')), 4)

    @patch('photo_recognition.ui.messagebox.askyesno', return_value=True)
    @patch('photo_recognition.batch.ImageProcessor')
    def test_selected_filtered_openai_model_is_used_for_recognition(self, processor, confirm):
        self.select_cloud()
        self.app.result_queue.put(('openai_models', (self.app.openai_request_id,
                                                     ['gpt-vision', 'text-model'], None)))
        self.root.after_cancel(self.app.after_id)
        self.app.check_queue()
        self.app.model_name.set('vision')
        self.assertEqual(self.app.model_combo.cget('values'), ('gpt-vision',))
        self.app.model_name.set('gpt-vision')
        processor.return_value.process_image.return_value = {'success': True, 'numeros_encontrados': [12]}
        self.app.start_processing()
        self.wait_for_completion()
        processor.return_value.process_image.assert_called_once_with(
            str(self.folder / 'photo.jpg'), 'gpt-vision', output_dir=str(self.folder / 'output'))
        confirm.assert_called_once()

    @patch('photo_recognition.ui.messagebox.showerror')
    @patch('photo_recognition.ui.messagebox.askyesno')
    @patch('photo_recognition.batch.ImageProcessor')
    def test_partial_openai_search_does_not_start_recognition(self, processor, confirm, showerror):
        self.select_cloud()
        self.app.result_queue.put(('openai_models', (self.app.openai_request_id,
                                                     ['gpt-vision', 'text-model'], None)))
        self.root.after_cancel(self.app.after_id)
        self.app.check_queue()
        self.app.model_combo.delete(0, tk.END)
        self.app.model_combo.insert(0, 'vision')
        self.app.start_processing()
        processor.assert_not_called()
        confirm.assert_not_called()
        showerror.assert_called_once()
        self.assertIn('complete model ID', showerror.call_args.args[1])

    def test_search_keeps_only_valid_selection_and_preserves_manual_openai_id(self):
        self.select_cloud()
        self.app.result_queue.put(('openai_models', (self.app.openai_request_id,
                                                     ['gpt-vision', 'text-model'], None)))
        self.root.after_cancel(self.app.after_id)
        self.app.check_queue()
        self.app.model_name.set('text-model')
        self.assertEqual(self.app.model_combo.cget('values'), ('gpt-vision', 'text-model'))
        self.app.model_name.set('VISION')
        self.assertEqual(self.app.model_combo.cget('values'), ('gpt-vision',))
        self.assertEqual(self.app.model_name.get(), 'VISION')
        self.app.model_name.set('custom-vision-model')
        self.assertEqual(self.app.model_name.get(), 'custom-vision-model')

    def test_search_stays_active_after_openai_refresh(self):
        self.select_cloud()
        self.app.model_name.set('vision')
        self.mock_openai_check.side_effect = lambda events, config, request_id: events.put(
            ('openai_models', (request_id, ['gpt-vision', 'text-model'], None)))
        self.app.check_connection()
        self.wait_for_openai_models()
        self.assertEqual(self.app.model_name.get(), 'vision')
        self.assertEqual(self.app.model_combo.cget('values'), ('gpt-vision',))
        self.app.connection_btn.invoke()
        self.wait_for_openai_models()
        self.assertEqual(self.app.model_combo.cget('values'), ('gpt-vision',))
        self.app.model_name.set('')
        self.assertEqual(self.app.model_combo.cget('values'), ('gpt-vision', 'text-model'))

    def test_search_filters_ollama_and_clears_unmatched_selection(self):
        self.apply_connection(['glm-ocr:latest', 'medgemma:4b', 'qwen3:latest'])
        self.app.model_name.set('GEM')
        self.assertEqual(self.app.model_combo.cget('values'), ('medgemma:4b',))
        self.assertEqual(self.app.model_name.get(), 'GEM')
        self.app.model_name.set('missing')
        self.assertEqual(self.app.model_name.get(), 'missing')
        self.app.model_name.set('')
        self.assertEqual(len(self.app.model_combo.cget('values')), 3)

    @patch('photo_recognition.ui.messagebox.showerror')
    @patch('photo_recognition.batch.ImageProcessor')
    def test_ollama_search_text_is_not_submitted_as_model(self, processor, showerror):
        self.apply_connection(['glm-ocr:latest', 'medgemma:4b'])
        self.app.model_combo.delete(0, tk.END)
        self.app.model_combo.insert(0, 'gem')
        self.assertEqual(self.app.model_combo.cget('values'), ('medgemma:4b',))
        self.app.start_processing()
        processor.assert_not_called()
        showerror.assert_called_once()

    def test_search_is_reset_when_switching_to_manual_provider(self):
        self.apply_connection(['vision-model', 'other-model'])
        self.app.model_name.set('vision')
        self.app.provider_name.set('Gemini')
        self.app.provider_changed()
        self.assertEqual(self.app.model_name.get(), '')
        self.assertEqual(self.app.available_models, ())
        self.assertFalse(hasattr(self.app, 'search_entry'))
        self.app.model_name.set('manual-gemini-id')
        self.assertEqual(self.app.model_name.get(), 'manual-gemini-id')
        self.app.provider_name.set('Ollama')
        self.app.provider_changed()
        self.assertEqual(tuple(self.app.model_combo.cget('values')), ())

    def test_openai_refresh_replaces_old_models(self):
        self.select_cloud()
        self.app.model_name.set('')
        self.mock_openai_check.side_effect = lambda events, config, request_id: events.put(
            ('openai_models', (request_id,
                               ['first-model'] if self.mock_openai_check.call_count == 1 else ['second-model'], None)))
        self.app.check_connection()
        self.wait_for_openai_models()
        self.assertEqual(self.app.model_combo.cget('values'), ('first-model',))
        self.app.connection_btn.invoke()
        self.wait_for_openai_models()
        self.assertEqual(self.app.model_combo.cget('values'), ('second-model',))

    def test_openai_lookup_failure_allows_manual_model_id(self):
        self.select_cloud()
        self.mock_openai_check.side_effect = lambda events, config, request_id: events.put(
            ('openai_models', (request_id, [], 'OpenAI HTTP 401: Check your API key.')))
        self.app.check_connection()
        self.wait_for_openai_models()
        self.assertEqual(tuple(self.app.model_combo.cget('values')), ())
        self.app.model_name.set('manually-entered-vision-model')
        self.assertEqual(self.app.model_name.get(), 'manually-entered-vision-model')
        self.assertIn('401', self.app.connection_var.get())
        self.assertNotIn('test-only-secret', self.app.log_area.get('1.0', tk.END))

    def test_old_openai_key_cannot_replace_models_from_new_key(self):
        self.select_cloud()
        self.app.check_connection()
        old_request = self.app.openai_request_id
        self.app.key_button.invoke()
        self.app.key_dialog_entry.delete(0, tk.END)
        self.app.key_dialog_entry.insert(0, 'new-test-only-secret')
        self.app.key_dialog_save.invoke()
        new_request = self.app.openai_request_id
        self.assertNotEqual(old_request, new_request)
        self.app.result_queue.put(('openai_models', (old_request, ['old-model'], None)))
        self.app.result_queue.put(('openai_models', (new_request, ['new-model'], None)))
        self.root.after_cancel(self.app.after_id)
        self.app.check_queue()
        self.assertEqual(self.app.model_combo.cget('values'), ('new-model',))
        self.assertNotIn('new-test-only-secret', self.app.log_area.get('1.0', tk.END))

    def test_late_openai_response_is_ignored_after_provider_switch(self):
        self.select_cloud()
        self.app.check_connection()
        previous_request = self.app.openai_request_id
        self.app.provider_name.set('Gemini')
        self.app.provider_changed()
        self.app.result_queue.put(('openai_models', (previous_request, ['old-model'], None)))
        self.root.after_cancel(self.app.after_id)
        self.app.check_queue()
        self.assertNotIn('old-model', self.app.model_combo.cget('values'))

    def test_app_uses_detected_system_fonts(self):
        from tkinter import font
        families = font.families()
        self.assertIn(self.app.ui_family, families)
        self.assertIn(self.app.mono_family, families)
        self.assertEqual(font.nametofont('TkDefaultFont').actual('family'), self.app.ui_family)
        self.assertEqual(font.nametofont('TkFixedFont').actual('family'), self.app.mono_family)
        if any(family != 'fixed' for family in families):
            self.assertNotEqual(self.app.ui_family, 'fixed')
        self.app.dark_mode.set(True)
        self.app.toggle_theme()
        self.assertEqual(font.nametofont('TkDefaultFont').actual('family'), self.app.ui_family)

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
