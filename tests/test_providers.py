import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from photo_recognition.providers import OcrProvider, ProviderConfig, ProviderError, create_provider


class ProviderTests(unittest.TestCase):
    def response(self, body, status=200):
        return Mock(status_code=status, json=Mock(return_value=body))

    def completion(self, text='12, 42', finish='stop'):
        return {'choices': [{'message': {'content': text}, 'finish_reason': finish}]}

    def gemini(self, parts=None, finish='STOP'):
        return {'candidates': [{'content': {'parts': parts or [{'text': '12, 42'}]}, 'finishReason': finish}]}

    def test_api_key_is_excluded_from_config_repr(self):
        config = ProviderConfig('OpenAI', api_key='test-only-secret')
        self.assertNotIn('test-only-secret', repr(config))

    def test_keys_are_required_only_for_cloud_providers(self):
        ProviderConfig().validate()
        for name in ('OpenAI', 'Gemini', 'OpenAI-compatible'):
            with self.subTest(provider=name), self.assertRaisesRegex(ValueError, 'API key'):
                ProviderConfig(name).validate()

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            create_provider(ProviderConfig('Unknown'))

    def test_compatible_endpoint_requires_https_without_embedded_credentials(self):
        for url in ('', 'http://example.test/v1', 'https://user:pass@example.test/v1',
                    'https://example.test/v1?key=secret', 'https://example.test/v1#fragment',
                    'https://example.test:invalid/v1', 'https://example.test/white space'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ProviderConfig('OpenAI-compatible', 'test-only-secret', url).validate()

    def test_official_provider_cannot_be_redirected_by_custom_base_url(self):
        with self.assertRaises(ValueError):
            ProviderConfig('OpenAI', 'test-only-secret', 'https://example.test/v1').validate()

    @patch('photo_recognition.providers.requests.get')
    def test_openai_lists_accessible_model_ids_without_guessing_image_capability(self, get):
        response = self.response({'data': [{'id': 'gpt-vision'}, {'id': 'text-model'}, {'id': 'gpt-vision'}]})
        get.return_value = response
        provider = create_provider(ProviderConfig('OpenAI', 'test-only-secret'))
        self.assertEqual(provider.available_models(), ['gpt-vision', 'text-model'])
        get.assert_called_once_with('https://api.openai.com/v1/models',
                                    headers={'Authorization': 'Bearer test-only-secret'},
                                    timeout=5, allow_redirects=False)
        response.close.assert_called_once()

    @patch('photo_recognition.providers.requests.get')
    def test_openai_model_listing_never_displays_response_body_or_key(self, get):
        provider = create_provider(ProviderConfig('OpenAI', 'test-only-secret'))
        for status in (302, 401, 403, 429, 500):
            with self.subTest(status=status):
                response = self.response({'error': 'test-only-secret'}, status)
                response.text = 'test-only-secret'
                get.return_value = response
                with self.assertRaises(ProviderError) as raised:
                    provider.available_models()
                self.assertIn(str(status), str(raised.exception))
                self.assertNotIn('test-only-secret', str(raised.exception))
                response.close.assert_called_once()

    @patch('photo_recognition.providers.requests.get')
    def test_openai_model_listing_sanitizes_bad_json_and_network_errors(self, get):
        provider = create_provider(ProviderConfig('OpenAI', 'test-only-secret'))
        for body in ({}, {'data': None}, {'data': [{'name': 'other-model'}]}):
            with self.subTest(body=body):
                response = self.response(body)
                get.return_value = response
                with self.assertRaises(ProviderError):
                    provider.available_models()
                response.close.assert_called_once()
        get.side_effect = requests.ConnectionError('Authorization: test-only-secret')
        with self.assertRaises(ProviderError) as raised:
            provider.available_models()
        self.assertNotIn('test-only-secret', str(raised.exception))

    @patch('photo_recognition.providers.requests.get')
    def test_other_cloud_providers_do_not_infer_model_discovery(self, get):
        for name, base in (('Gemini', ''), ('OpenAI-compatible', 'https://example.test/v1')):
            with self.subTest(provider=name), self.assertRaises(ProviderError):
                create_provider(ProviderConfig(name, 'test-only-secret', base)).available_models()
        get.assert_not_called()

    @patch('photo_recognition.providers.requests.post')
    def test_openai_sends_image_and_key_in_authorization_header(self, post):
        response = self.response(self.completion())
        post.return_value = response
        provider = create_provider(ProviderConfig('OpenAI', 'test-only-secret'))
        self.assertEqual(provider.recognize('aW1hZ2U=', 'Find numbers', 'vision-model'), '12, 42')
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://api.openai.com/v1/chat/completions')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-only-secret')
        content = kwargs['json']['messages'][0]['content']
        self.assertEqual(content[0], {'type': 'text', 'text': 'Find numbers'})
        self.assertEqual(content[1]['image_url']['url'], 'data:image/jpeg;base64,aW1hZ2U=')
        self.assertFalse(kwargs['allow_redirects'])
        self.assertFalse(kwargs['json']['store'])
        self.assertEqual(kwargs['timeout'], (5, 180))
        response.close.assert_called_once()

    @patch('photo_recognition.providers.requests.post')
    def test_compatible_service_uses_custom_base_url(self, post):
        post.return_value = self.response(self.completion())
        provider = create_provider(ProviderConfig('OpenAI-compatible', 'custom-test-key', 'https://example.test/api/v1/'))
        provider.recognize('image', 'prompt', 'vendor/vision')
        self.assertEqual(post.call_args.args[0], 'https://example.test/api/v1/chat/completions')
        self.assertEqual(post.call_args.kwargs['json']['model'], 'vendor/vision')
        self.assertNotIn('store', post.call_args.kwargs['json'])

    @patch('photo_recognition.providers.requests.post')
    def test_gemini_sends_inline_image_and_header_key(self, post):
        post.return_value = self.response(self.gemini())
        provider = create_provider(ProviderConfig('Gemini', 'test-only-secret'))
        self.assertEqual(provider.recognize('image', 'prompt', 'models/vision-model'), '12, 42')
        url = post.call_args.args[0]
        self.assertEqual(url, 'https://generativelanguage.googleapis.com/v1beta/models/vision-model:generateContent')
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs['headers']['x-goog-api-key'], 'test-only-secret')
        self.assertNotIn('test-only-secret', url)
        self.assertEqual(kwargs['json']['contents'][0]['parts'][1]['inline_data'],
                         {'mime_type': 'image/jpeg', 'data': 'image'})
        self.assertFalse(kwargs['allow_redirects'])

    @patch('photo_recognition.providers.requests.post')
    def test_gemini_model_cannot_inject_url_components(self, post):
        provider = create_provider(ProviderConfig('Gemini', 'test-only-secret'))
        with self.assertRaises(ProviderError):
            provider.recognize('image', 'prompt', '../other?key=value')
        post.assert_not_called()

    @patch('photo_recognition.providers.requests.post')
    def test_gemini_does_not_extract_numbers_from_thinking_parts(self, post):
        post.return_value = self.response(self.gemini([
            {'text': 'Maybe 999', 'thought': True}, {'text': '42'}
        ]))
        provider = create_provider(ProviderConfig('Gemini', 'test-only-secret'))
        self.assertEqual(provider.recognize('image', 'prompt', 'vision-model'), '42')

    @patch('photo_recognition.providers.requests.post')
    def test_http_errors_never_echo_response_body_or_api_key(self, post):
        provider = create_provider(ProviderConfig('OpenAI', 'test-only-secret'))
        for status in (302, 400, 401, 403, 404, 429, 500):
            with self.subTest(status=status):
                response = self.response({'error': 'test-only-secret'}, status)
                response.text = 'test-only-secret'
                post.return_value = response
                with self.assertRaises(ProviderError) as raised:
                    provider.recognize('image', 'prompt', 'vision-model')
                self.assertNotIn('test-only-secret', str(raised.exception))
                self.assertIn(str(status), str(raised.exception))
                response.close.assert_called_once()

    @patch('photo_recognition.providers.requests.post')
    def test_network_exceptions_do_not_expose_headers(self, post):
        provider = create_provider(ProviderConfig('Gemini', 'test-only-secret'))
        for error in (requests.ConnectionError('headers: test-only-secret'), requests.Timeout('test-only-secret')):
            post.side_effect = error
            with self.assertRaises(ProviderError) as raised:
                provider.recognize('image', 'prompt', 'vision-model')
            self.assertNotIn('test-only-secret', str(raised.exception))

    @patch('photo_recognition.providers.requests.post')
    def test_malformed_refused_or_truncated_responses_are_errors(self, post):
        cases = [
            ('OpenAI', {}), ('OpenAI', self.completion(None)),
            ('OpenAI', self.completion('12', 'length')),
            ('OpenAI', {'choices': [{'message': {'refusal': 'blocked', 'content': '12'}, 'finish_reason': 'stop'}]}),
            ('Gemini', {'promptFeedback': {'blockReason': 'SAFETY'}}),
            ('Gemini', self.gemini(finish='MAX_TOKENS')),
        ]
        for name, body in cases:
            with self.subTest(provider=name, body=body):
                post.return_value = self.response(body)
                provider = create_provider(ProviderConfig(name, 'test-only-secret'))
                with self.assertRaises(ProviderError):
                    provider.recognize('image', 'prompt', 'vision-model')
                post.return_value.close.assert_called_once()

    @patch('photo_recognition.providers.requests.post')
    def test_non_json_response_is_reported_safely(self, post):
        response = self.response({})
        response.json.side_effect = ValueError('test-only-secret')
        post.return_value = response
        with self.assertRaises(ProviderError) as raised:
            create_provider(ProviderConfig('OpenAI', 'test-only-secret')).recognize('image', 'prompt', 'vision')
        self.assertNotIn('test-only-secret', str(raised.exception))
        response.close.assert_called_once()

    @patch('photo_recognition.providers.requests.post')
    def test_echoed_api_key_is_redacted_from_successful_response(self, post):
        post.return_value = self.response(self.completion('test-only-secret 42'))
        result = create_provider(ProviderConfig('OpenAI', 'test-only-secret')).recognize('image', 'prompt', 'vision')
        self.assertNotIn('test-only-secret', result)
        self.assertIn('42', result)


class OcrProviderTests(unittest.TestCase):
    def box(self, x, y, width, height):
        return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]

    def result(self, *detections):
        return SimpleNamespace(
            txts=[text for text, _, _ in detections],
            scores=[conf for _, conf, _ in detections],
            boxes=[box for _, _, box in detections],
        )

    def test_ocr_is_a_local_provider_without_key_requirement(self):
        config = ProviderConfig('OCR (local)')
        config.validate()
        self.assertFalse(config.remote)
        self.assertIsInstance(create_provider(config), OcrProvider)

    def test_filter_keeps_confident_pure_digits_ordered_by_area(self):
        result = self.result(
            ('42', 0.9, self.box(0, 0, 10, 10)),       # small bib
            ('103', 0.9, self.box(0, 0, 50, 40)),      # largest detection first
            ('10:42:17', 1.0, self.box(0, 0, 90, 30)), # clock text
            ('21k', 0.9, self.box(0, 0, 60, 20)),      # shirt print, not pure digits
            ('7', 0.3, self.box(0, 0, 30, 30)),        # below confidence threshold
            ('123456', 0.9, self.box(0, 0, 80, 20)),   # longer than a bib number
            ('42', 0.8, self.box(0, 0, 5, 5)),         # duplicate digit string
        )
        self.assertEqual(OcrProvider.filter_numbers(result), ['103', '42'])

    def test_filter_tolerates_empty_or_missing_detections(self):
        self.assertEqual(OcrProvider.filter_numbers(None), [])
        empty = SimpleNamespace(txts=None, scores=None, boxes=None)
        self.assertEqual(OcrProvider.filter_numbers(empty), [])

    def test_recognize_reads_the_image_file_through_the_engine(self):
        engine = Mock(return_value=self.result(('815', 0.99, self.box(0, 0, 40, 20))))
        provider = OcrProvider(engine=engine)
        self.assertEqual(provider.recognize('/tmp/photo.jpg', 'ignored prompt', 'RapidOCR'), '815')
        engine.assert_called_once_with('/tmp/photo.jpg')

    def test_available_models_verifies_the_engine_loads(self):
        provider = OcrProvider(engine=Mock())
        self.assertEqual(provider.available_models(), ['RapidOCR'])

    def test_engine_failure_is_reported_as_provider_error(self):
        provider = OcrProvider(engine=Mock(side_effect=RuntimeError('bad image')))
        with self.assertRaises(ProviderError):
            provider.recognize('/tmp/photo.jpg', 'prompt', 'RapidOCR')

    def test_missing_rapidocr_package_is_a_provider_error(self):
        provider = OcrProvider()
        with patch.dict(sys.modules, {'rapidocr': None}):
            with self.assertRaisesRegex(ProviderError, 'pip install'):
                provider.available_models()


if __name__ == '__main__':
    unittest.main()
