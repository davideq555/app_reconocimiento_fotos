import csv
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from photo_recognition.batch import check_ollama, check_openai_models, find_images, process_batch, write_csv
from photo_recognition.providers import ProviderConfig


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.events = queue.Queue()
        self.cancelled = threading.Event()

    def test_scan_accepts_images_only_and_sorts_names(self):
        for name in ('b.JPG', 'a.png', 'notes.txt', 'c.tiff', 'd.gif'):
            (self.folder / name).touch()
        (self.folder / 'directory.jpg').mkdir()
        self.assertEqual(
            [path.name for path in find_images(self.folder)],
            ['a.png', 'b.JPG', 'c.tiff', 'd.gif'],
        )

    def test_batch_reports_real_results_progress_and_completion(self):
        processor = Mock()
        processor.process_image.return_value = {
            'success': True, 'numeros_encontrados': [42], 'output_path': 'photo_n42.jpg'
        }
        photo = self.folder / 'photo.jpg'
        process_batch([photo], 'vision', self.folder, self.events, self.cancelled, processor)
        processor.process_image.assert_called_once_with(str(photo), 'vision', output_dir=str(self.folder))
        self.assertEqual(self.events.get_nowait(), ('log', 'Processing: photo.jpg'))
        kind, result = self.events.get_nowait()
        self.assertEqual(kind, 'result')
        self.assertEqual(result['file'], 'photo.jpg')
        self.assertEqual(result['numeros_encontrados'], [42])
        self.assertEqual(self.events.get_nowait(), ('progress', (1, 1)))
        self.assertEqual(self.events.get_nowait(), ('done', False))

    def test_failed_image_does_not_stop_remaining_images(self):
        processor = Mock()
        processor.process_image.side_effect = [RuntimeError('offline'), {'success': True}]
        process_batch([self.folder / 'a.jpg', self.folder / 'b.jpg'], 'vision', self.folder,
                      self.events, self.cancelled, processor)
        messages = [event for event in self.events.queue if event[0] != 'log']
        self.assertEqual(messages[0][1]['error'], 'offline')
        self.assertTrue(messages[2][1]['success'])
        self.assertEqual(messages[-1], ('done', False))

    def test_cancel_before_start_does_not_process_images(self):
        self.cancelled.set()
        processor = Mock()
        process_batch([self.folder / 'a.jpg'], 'vision', self.folder,
                      self.events, self.cancelled, processor)
        processor.process_image.assert_not_called()
        self.assertEqual(self.events.get_nowait(), ('done', True))

    def test_cancel_preserves_current_result_and_skips_next_image(self):
        processor = Mock()

        def recognize(*args, **kwargs):
            self.cancelled.set()
            return {'success': True, 'numeros_encontrados': [123]}

        processor.process_image.side_effect = recognize
        process_batch([self.folder / 'a.jpg', self.folder / 'b.jpg'], 'vision', self.folder,
                      self.events, self.cancelled, processor)
        self.assertEqual(processor.process_image.call_count, 1)
        self.assertEqual(self.events.get_nowait()[0], 'log')
        self.assertEqual(self.events.get_nowait()[1]['numeros_encontrados'], [123])
        self.assertEqual(list(self.events.queue)[-1], ('done', True))

    def test_empty_batch_always_finishes(self):
        process_batch([], 'vision', self.folder, self.events, self.cancelled, Mock())
        self.assertEqual(self.events.get_nowait(), ('done', False))

    @patch('photo_recognition.batch.ImageProcessor')
    def test_ollama_check_reports_models(self, processor):
        processor.return_value.available_models.return_value = ['vision']
        check_ollama(self.events)
        self.assertEqual(self.events.get_nowait(), ('connection', (['vision'], None)))

    @patch('photo_recognition.batch.ImageProcessor')
    def test_ollama_check_reports_offline_server(self, processor):
        processor.return_value.available_models.side_effect = RuntimeError('offline')
        check_ollama(self.events)
        self.assertEqual(self.events.get_nowait(), ('connection', ([], 'Ollama unavailable: offline')))

    @patch('photo_recognition.batch.create_provider')
    def test_openai_listing_worker_reports_only_model_ids_and_request_identity(self, create_provider):
        create_provider.return_value.available_models.return_value = ['gpt-vision']
        config = ProviderConfig('OpenAI', 'test-only-secret')
        check_openai_models(self.events, config, 7)
        create_provider.assert_called_once_with(config)
        self.assertEqual(self.events.get_nowait(), ('openai_models', (7, ['gpt-vision'], None)))
        self.assertNotIn('test-only-secret', str(list(self.events.queue)))

    @patch('photo_recognition.batch.create_provider')
    def test_openai_listing_worker_sanitizes_unexpected_exceptions(self, create_provider):
        create_provider.side_effect = RuntimeError('test-only-secret')
        check_openai_models(self.events, ProviderConfig('OpenAI', 'test-only-secret'), 3)
        self.assertEqual(self.events.get_nowait(),
                         ('openai_models', (3, [], 'Could not load OpenAI models. Try again.')))

    @patch('photo_recognition.batch.ImageProcessor')
    def test_provider_configuration_reaches_processor_without_entering_events(self, processor):
        processor.return_value.process_image.return_value = {'success': True, 'numeros_encontrados': [42]}
        config = ProviderConfig('OpenAI', 'test-only-secret')
        process_batch([self.folder / 'photo.jpg'], 'vision', self.folder,
                      self.events, self.cancelled, provider_config=config)
        processor.assert_called_once_with(provider_config=config)
        self.assertNotIn('test-only-secret', str(list(self.events.queue)))

    def test_invalid_provider_still_emits_error_and_completion(self):
        process_batch([self.folder / 'photo.jpg'], 'vision', self.folder,
                      self.events, self.cancelled, provider_config=ProviderConfig('OpenAI'))
        self.assertEqual(self.events.get_nowait()[0], 'error')
        self.assertEqual(self.events.get_nowait(), ('done', False))

    def test_unexpected_cloud_failure_does_not_expose_key_in_events(self):
        processor = Mock()
        processor.process_image.side_effect = RuntimeError('test-only-secret')
        process_batch([self.folder / 'photo.jpg'], 'vision', self.folder,
                      self.events, self.cancelled, processor, provider_config=ProviderConfig('OpenAI', 'test-only-secret'))
        self.assertNotIn('test-only-secret', str(list(self.events.queue)))

    def test_csv_quotes_filenames_and_neutralizes_spreadsheet_formulas(self):
        destination = self.folder / 'results.csv'
        write_csv([
            {'file': 'photo,"one".jpg', 'success': True, 'numeros_encontrados': [12, 42]},
            {'file': '=formula.jpg', 'error': '=unsafe'},
        ], destination)
        with destination.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][0], 'photo,"one".jpg')
        self.assertEqual(rows[1][1], '12, 42')
        self.assertEqual(rows[2][0], "'=formula.jpg")
        self.assertEqual(rows[2][3], "'=unsafe")


if __name__ == '__main__':
    unittest.main()
