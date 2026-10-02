import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import requests


PROVIDERS = ('Ollama', 'OpenAI', 'Gemini', 'OpenAI-compatible')


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = 'Ollama'
    api_key: str = field(default='', repr=False)
    base_url: str = field(default='', repr=False)

    @property
    def remote(self):
        return self.provider != 'Ollama'

    @property
    def endpoint(self):
        return {
            'Ollama': 'http://localhost:11434',
            'OpenAI': 'https://api.openai.com/v1',
            'Gemini': 'https://generativelanguage.googleapis.com/v1beta',
            'OpenAI-compatible': self.base_url.rstrip('/'),
        }[self.provider]

    def validate(self):
        if self.provider not in PROVIDERS:
            raise ValueError('Choose a supported provider.')
        if self.remote and (not self.api_key or any(not 33 <= ord(char) <= 126 for char in self.api_key)):
            raise ValueError('Enter a valid API key for the selected provider.')
        if self.provider != 'OpenAI-compatible':
            if self.base_url:
                raise ValueError('Custom URLs are only supported with OpenAI-compatible.')
            return
        try:
            url = urlsplit(self.base_url)
            valid = (url.scheme == 'https' and url.hostname and not url.username and not url.password
                     and not url.query and not url.fragment and (url.port is None or url.port > 0)
                     and not any(char.isspace() or ord(char) < 32 for char in self.base_url)
                     and self.api_key not in self.base_url)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('Enter an HTTPS API base URL without credentials, query parameters or fragments.')


class OllamaProvider:
    def __init__(self, base_url='http://localhost:11434'):
        self.base_url = base_url.rstrip('/')

    def available_models(self):
        with requests.get(f'{self.base_url}/api/tags', timeout=5) as response:
            response.raise_for_status()
            return [model['name'] for model in response.json().get('models', [])]

    def recognize(self, image_base64, prompt, model):
        # Hacer la solicitud a la API de Ollama
        response = requests.post(
            f'{self.base_url}/api/generate',
            json={'model': model, 'prompt': prompt, 'images': [image_base64], 'options': {'temperature': 0.1}},
            stream=True,
            timeout=(5, 180),
            allow_redirects=False,
        )
        # Procesar la respuesta
        try:
            if response.status_code != 200:
                raise ProviderError(f'Error en la API de Ollama: {response.status_code} - {response.text}')
            text = ''
            # Procesar cada línea de la respuesta
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if 'error' in data:
                    raise ProviderError(str(data['error']))
                text += data.get('response', '')
            return text
        finally:
            response.close()


class CloudProvider:
    def __init__(self, config):
        self.config = config

    def available_models(self):
        if self.config.provider != 'OpenAI':
            raise ProviderError('Enter a vision model ID from your provider account.')
        try:
            response = requests.get(f'{self.config.endpoint}/models',
                                    headers={'Authorization': f'Bearer {self.config.api_key}'},
                                    timeout=5, allow_redirects=False)
        except requests.RequestException:
            raise ProviderError('Could not load OpenAI models. Check your connection and try again.') from None
        try:
            if response.status_code != 200:
                reason = {
                    401: 'Check your API key.',
                    403: 'Check your API key permissions and account access.',
                    429: 'Rate limit reached. Try again later.',
                }.get(response.status_code, 'Could not load models. Try again later.')
                raise ProviderError(f'OpenAI HTTP {response.status_code}: {reason}')
            models = response.json()['data']
            if not isinstance(models, list) or any(not isinstance(item, dict) or
                                                  not isinstance(item.get('id'), str) or not item['id']
                                                  for item in models):
                raise ProviderError('OpenAI returned an invalid model list.')
            return sorted({item['id'] for item in models})
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError('OpenAI returned an invalid model list.') from None
        finally:
            response.close()

    def recognize(self, image_base64, prompt, model):
        if not model.strip():
            raise ProviderError('Enter a vision model ID.')
        config = self.config
        if config.provider == 'Gemini':
            model = model.removeprefix('models/')
            if not re.fullmatch(r'[A-Za-z0-9._-]+', model):
                raise ProviderError('Enter a valid Gemini model ID without URL parameters.')
            url = f'{config.endpoint}/models/{model}:generateContent'
            headers = {'x-goog-api-key': config.api_key}
            payload = {
                'contents': [{'role': 'user', 'parts': [
                    {'text': prompt},
                    {'inline_data': {'mime_type': 'image/jpeg', 'data': image_base64}},
                ]}],
                'generationConfig': {'maxOutputTokens': 4096},
            }
        else:
            url = f'{config.endpoint}/chat/completions'
            headers = {'Authorization': f'Bearer {config.api_key}'}
            payload = {
                'model': model,
                'messages': [{'role': 'user', 'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{image_base64}'}},
                ]}],
                'stream': False,
            }
            if config.provider == 'OpenAI':
                payload.update(store=False, max_completion_tokens=4096)
            else:
                payload['max_tokens'] = 1024
        try:
            response = requests.post(url, headers=headers, json=payload,
                                     timeout=(5, 180), allow_redirects=False)
        except requests.Timeout:
            raise ProviderError('Provider timed out. Check the service before retrying; the request may have been billed.') from None
        except requests.RequestException:
            raise ProviderError('Could not connect to the provider. Check your connection and API settings.') from None
        try:
            if response.status_code != 200:
                reason = {
                    400: 'Check the model, image support and request settings.',
                    401: 'Check your API key.',
                    403: 'Check your API key permissions and account access.',
                    404: 'Check the model ID and API base URL.',
                    429: 'Rate limit or quota reached. Check billing and wait before retrying.',
                }.get(response.status_code, 'Provider request failed. Redirects are not followed.')
                raise ProviderError(f'{config.provider} HTTP {response.status_code}: {reason}')
            data = response.json()
            if config.provider == 'Gemini':
                candidate = data['candidates'][0]
                if candidate.get('finishReason') != 'STOP':
                    raise ProviderError('Gemini blocked or did not finish the response. Try another vision model.')
                text = ''.join(part.get('text', '') for part in candidate['content']['parts'] if not part.get('thought'))
            else:
                choice = data['choices'][0]
                if choice.get('finish_reason') != 'stop' or choice['message'].get('refusal'):
                    raise ProviderError('The provider refused or did not finish the response. Try another vision model.')
                text = choice['message']['content']
            if not isinstance(text, str) or not text.strip():
                raise ProviderError('The provider returned no text. Check that the model supports image input.')
            return text.replace(config.api_key, '[REDACTED]')
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError('The provider returned an unexpected response. Check API compatibility and model support.') from None
        finally:
            response.close()


def create_provider(config=None, ollama_url='http://localhost:11434'):
    config = config or ProviderConfig()
    config.validate()
    return CloudProvider(config) if config.remote else OllamaProvider(ollama_url)
