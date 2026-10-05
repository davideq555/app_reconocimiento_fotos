import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from PIL import Image

from photo_recognition.processor import ImageProcessor
from photo_recognition.providers import ProviderConfig


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.photo = self.folder / 'race.jpg'
        Image.new('RGB', (120, 80), 'white').save(self.photo)
        self.processor = ImageProcessor()

    def response(self, text):
        response = Mock(status_code=200)
        response.iter_lines.return_value = [json.dumps({'response': text}).encode()]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_extract_numbers_is_unique_and_sorted(self):
        self.assertEqual(self.processor.extract_numbers('42, 12, 42'), [12, 42])

    def test_path_input_provider_reads_the_original_file(self):
        provider = Mock(image_input='path')
        provider.recognize.return_value = '42, 0815'
        self.processor.provider = provider
        result = self.processor.process_image(str(self.photo))
        self.assertEqual(provider.recognize.call_args.args[0], str(self.photo))
        self.assertEqual(result['numeros_encontrados'], [42, 815])

    @patch('photo_recognition.providers.requests.post')
    def test_recognition_saves_numbered_watermarked_copy_without_changing_original(self, post):
        post.return_value = self.response('42, 12, 42')
        original = self.photo.read_bytes()
        result = self.processor.process_image(str(self.photo), output_dir=str(self.folder / 'out'))
        self.assertTrue(result['success'])
        self.assertEqual(result['numeros_encontrados'], [12, 42])
        self.assertEqual(Path(result['output_path']).name, 'race_n12_n42.jpg')
        with Image.open(result['output_path']) as image:
            self.assertEqual(image.size, (30, 20))
        self.assertEqual(self.photo.read_bytes(), original)
        self.assertEqual(post.call_args.kwargs['timeout'], (5, 180))
        post.return_value.close.assert_called_once()

    @patch('photo_recognition.providers.requests.post')
    def test_no_numbers_does_not_save_output(self, post):
        post.return_value = self.response('')
        result = self.processor.process_image(str(self.photo), output_dir=str(self.folder / 'out'))
        self.assertEqual(result['numeros_encontrados'], [])
        self.assertIsNone(result['output_path'])
        self.assertFalse((self.folder / 'out').exists())

    @patch('photo_recognition.providers.requests.post')
    def test_connection_failure_is_reported(self, post):
        post.side_effect = requests.ConnectionError('offline')
        self.assertIn('offline', self.processor.process_image(str(self.photo))['error'])

    @patch('photo_recognition.providers.requests.post')
    def test_stream_error_is_not_reported_as_success(self, post):
        response = self.response('')
        response.iter_lines.return_value = [b'{"error":"model unavailable"}']
        post.return_value = response
        self.assertIn('model unavailable', self.processor.process_image(str(self.photo))['error'])

    @patch('photo_recognition.providers.requests.post')
    def test_api_failure_closes_response(self, post):
        response = self.response('')
        response.status_code = 404
        response.text = 'model missing'
        post.return_value = response
        self.assertIn('404', self.processor.process_image(str(self.photo))['error'])
        response.close.assert_called_once()

    @patch('photo_recognition.providers.requests.post')
    def test_watermark_failure_is_reported(self, post):
        post.return_value = self.response('42')
        with patch.object(self.processor, 'add_watermark', return_value=False):
            result = self.processor.process_image(str(self.photo), output_dir=str(self.folder / 'out'))
        self.assertIn('error', result)

    @patch('photo_recognition.providers.requests.post')
    def test_existing_output_is_not_overwritten(self, post):
        post.return_value = self.response('42')
        output = self.folder / 'out'
        output.mkdir()
        existing = output / 'race_n42.jpg'
        existing.write_bytes(b'keep this file')
        result = self.processor.process_image(str(self.photo), output_dir=str(output))
        self.assertTrue(result['success'])
        self.assertEqual(Path(result['output_path']).name, 'race_n42_1.jpg')
        self.assertEqual(existing.read_bytes(), b'keep this file')

    @patch('photo_recognition.providers.requests.post')
    def test_gif_output_is_an_actual_jpeg(self, post):
        post.return_value = self.response('42')
        photo = self.folder / 'race.gif'
        Image.new('RGB', (120, 80)).save(photo)
        result = self.processor.process_image(str(photo), output_dir=str(self.folder / 'out'))
        self.assertTrue(result['success'])
        with Image.open(result['output_path']) as image:
            self.assertEqual(image.format, 'JPEG')

    @patch('photo_recognition.providers.requests.get')
    def test_available_models_uses_configured_server_and_timeout(self, get):
        response = self.response('')
        response.json.return_value = {'models': [{'name': 'custom-vision'}]}
        get.return_value = response
        self.assertEqual(self.processor.available_models(), ['custom-vision'])
        get.assert_called_once_with('http://localhost:11434/api/tags', timeout=5)
        response.raise_for_status.assert_called_once()

    @patch('photo_recognition.providers.requests.post')
    def test_cloud_results_use_the_same_numbered_watermark_pipeline(self, post):
        bodies = {
            'OpenAI': {'choices': [{'message': {'content': '12, 42'}, 'finish_reason': 'stop'}]},
            'Gemini': {'candidates': [{'content': {'parts': [{'text': '12, 42'}]}, 'finishReason': 'STOP'}]},
        }
        for provider, body in bodies.items():
            with self.subTest(provider=provider):
                post.return_value = Mock(status_code=200, json=Mock(return_value=body))
                processor = ImageProcessor(provider_config=ProviderConfig(provider, 'test-only-secret'))
                result = processor.process_image(str(self.photo), 'vision-model', str(self.folder / provider))
                self.assertTrue(result['success'])
                self.assertEqual(result['numeros_encontrados'], [12, 42])
                self.assertEqual(Path(result['output_path']).name, 'race_n12_n42.jpg')
                self.assertNotIn('test-only-secret', str(result))
                with Image.open(result['output_path']) as image:
                    self.assertEqual(image.size, (30, 20))

    def test_missing_file_is_reported(self):
        self.assertIn('error', self.processor.process_image(str(self.folder / 'missing.jpg')))

    def test_tiny_image_can_be_watermarked(self):
        Image.new('RGB', (1, 1)).save(self.photo)
        self.assertTrue(self.processor.add_watermark(str(self.photo), str(self.folder / 'tiny.jpg')))


if __name__ == '__main__':
    unittest.main()
