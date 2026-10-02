# Photo Recognition

A Python desktop application that finds participant numbers in photos using **Ollama, OpenAI, Gemini, or an OpenAI-compatible vision service**. The unified Tkinter interface uses **ttkbootstrap**, with light/dark themes, a results table, progress counters, an activity log, cancellation, and CSV export. On startup it detects the desktop's system font (desktop settings or fontconfig on Linux, the native default on Windows/macOS) and applies it across the interface.

## Requirements

- Python **3.10 or newer**, with Tkinter/Tk available.
- Either local Ollama with a downloaded vision model, or an API key and access to a cloud vision model.
- Internet access for installation and cloud recognition. Ollama recognition can run locally after downloading a model.

Tkinter is an OS/Python component, not a pip dependency. If `python -m tkinter` fails, install your distribution's Tkinter/Tk package or use a Python build that includes it.

## Quick start

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

For **local recognition**, run `ollama pull llama3.2-vision` once and, if Ollama is not already running, start `ollama serve` in a separate terminal. The local endpoint is `http://localhost:11434`. Ollama is not required when using a cloud provider.

`python app.py` and `python -m photo_recognition` launch the **same application**. PyQt6, ttkthemes, and the Ollama Python SDK are no longer required.

## Workflow

1. Select an image folder. Supported extensions: PNG, JPG, JPEG, BMP, GIF, TIF, TIFF. Only files directly inside the folder are processed.
2. Choose a **Provider** and vision model. Ollama automatically loads only models installed on your local server; **Check Ollama** refreshes the list. For OpenAI, use **Add API key** at the top of the window to paste your key in a masked dialog; the app then loads the models listed for that key. Not every listed model supports images. For Gemini and OpenAI-compatible services, enter the exact model ID manually.
3. Choose a separate output folder, or keep the default `media/` inside the repository.
4. Click **Start recognition**. Cloud batches ask for confirmation before uploading any images. The table shows detected numbers or a per-image error, while the **Activity** tab contains details.
5. Use **Export CSV** after completion or cancellation to save the current results.

**Cancel** stops before the next image, allowing the current request to finish. Closing during recognition asks for confirmation and may leave the current output incomplete. Existing completed files remain on disk. Starting another batch clears the previous in-memory results, so export them first if needed.

The interface stays responsive while recognition or connection checks run in background threads. The connection timeout is 5 seconds; recognition allows up to 180 seconds of inactivity while reading the response.

## Cloud providers and API keys

| Provider | What to enter | API |
| --- | --- | --- |
| Ollama | Installed vision model ID; no API key | Local `/api/generate` |
| OpenAI | API key; select an image-capable model from the fetched list or type its ID | OpenAI `/v1/models` for the list, `/v1/chat/completions` for recognition |
| Gemini | Gemini Developer API key and a supported model ID | Google `generateContent` |
| OpenAI-compatible | That service's API key, vision model ID, and HTTPS API base URL | `<base URL>/chat/completions` |

For **OpenAI-compatible**, enter the base URL supplied by the service, including its API version path if required (usually `/v1`), not the full `/chat/completions` endpoint. Compatibility requires Bearer authentication, base64 `image_url` inputs, and standard non-streaming Chat Completions responses. Text-only services, native Anthropic endpoints, and provider-specific authentication schemes need a separate adapter; they are not automatically supported.

Ollama models come solely from the local `/api/tags` response, and the dropdown is cleared if the check fails. After saving an OpenAI key, the app requests that key's model IDs from OpenAI; **Refresh OpenAI models** repeats the lookup. Once the list loads, type any part of the name directly into **Vision model ID**: its dropdown filters instantly, ignoring case, and shows the match count below it. Open the dropdown to select a complete model ID; delete the text to see every model again. Typing never sends another API request. This also works for Ollama, while Gemini and OpenAI-compatible model IDs remain manual. The model-list API does not label models as vision-capable, so select one that accepts image inputs. An empty list or HTTP 401/403 appears in the settings/Activity area, without revealing the key; you can still type a model ID manually. The API-key button remains visible at the top of the window; scroll the settings panel if the compatible provider URL field is below the visible area.

### Key handling, privacy and costs

- Click **Add API key** in the window header (you can select a cloud provider in the dialog), then paste the key in its masked input. Do not paste it into chat, source code, or the model/URL fields. Keys stay in process memory and are not written to configuration, CSV, or activity logs. This is not an encrypted credential vault.
- Changing providers clears the key, custom URL, and model selection to prevent accidental credential reuse. Closing clears the key field. The application does not load API keys from `.env` files or environment variables.
- Each cloud batch confirms the provider, destination, and photo count before sending resized JPEG copies (maximum 1024 pixels on the longest side). Provider data-retention and billing policies apply. OpenAI requests set `store=false`, which is not a guarantee of zero retention.
- Official provider URLs are fixed. Custom URLs require HTTPS and cannot embed credentials or query parameters. Recognition requests do not follow redirects.
- HTTP error bodies are not displayed; authentication, quota, network, malformed-response, and incomplete-response errors are reported without exposing the key. There are no automatic retries or provider fallbacks. A timed-out or cancelled in-flight request may still be billed.

Integration references: [OpenAI image inputs](https://developers.openai.com/api/docs/guides/images-vision), [OpenAI model-list API](https://developers.openai.com/api/reference/resources/models/methods/list/), and [Gemini image understanding](https://ai.google.dev/gemini-api/docs/generate-content/image-understanding).

## Output behavior

- Originals are left untouched.
- Images with detected numbers get copies named like `photo_n12_n42.jpg`.
- Copies receive a repeated **COPIA** watermark and are resized to 25% of their original width and height.
- Existing output filenames are preserved; repeated processing adds a suffix such as `_1`.
- PNG/JPEG output retains its format; other supported input formats are converted to JPEG. Animated images use their first frame.
- Images without detected numbers remain in the results but do not produce an output copy.
- CSV includes filename, numbers, status, error details, and output path. There is no fabricated confidence score or JSON export.

Vision model results can be incorrect. Review the detected numbers before using them to identify participants. Digit sequences are deduplicated and converted to integers, so leading zeros are not retained.

## Project structure

```text
photo_recognition/
    __main__.py       Package launcher
    ui.py             ttkbootstrap widgets and main-thread event handling
    batch.py          File discovery, worker events, cancellation, CSV export
    processor.py      Image preparation, number extraction, watermarking
    providers.py      Provider configuration and Ollama/OpenAI/Gemini HTTP adapters
main.py               Primary launcher
app.py                Compatible alternate launcher and OCRApp import
image_processor.py    Compatible ImageProcessor import and single-image CLI
requirements.txt      Pinned runtime dependencies
tests/                Processor, batch, and desktop UI tests
```

The UI snapshots the selected files, provider configuration, model, and destination before launching a worker. Workers publish queue events and never read or modify Tkinter widgets. All rendering happens on the Tk main thread. The processor remains usable without a display:

```bash
python image_processor.py path/to/photo.jpg
```

To change which numbers the model looks for, edit the prompt in `photo_recognition/processor.py`.

## Verification

```bash
python -m unittest discover -s tests -v
python -m compileall -q photo_recognition tests main.py app.py image_processor.py
git diff --check
```

Tests mock every provider and use temporary images; they do not download models, require real API keys, contact external services, or incur charges. UI tests create real Tk widgets and skip explicitly if no graphical display is available. Run the suite in a desktop session to cover theme switching, provider/key controls, upload consent, processing, cancellation, restart, export, and error recovery. Recognition quality and account/model availability still need a manual check with your chosen provider and representative photos.

## Troubleshooting

- **Ollama unavailable or empty model list:** verify the server is running and port 11434 is accessible. The model dropdown shows only names returned by the local server, and stays empty if it cannot be reached. Use **Check Ollama** to refresh, then read the Activity tab.
- **Model not found or image input unsupported:** select an exact model ID available in your provider account, with image-input support. For Ollama, download the model first.
- **HTTP 401/403:** check the API key, API access, and account permissions. A consumer chat subscription is not necessarily API access.
- **HTTP 429:** check provider quota, rate limits and billing. The app does not automatically retry paid requests.
- **Unexpected or incomplete response:** verify the endpoint's Chat Completions compatibility and choose a model that can finish within the request's output limit.
- **No images:** check the extension and ensure the images are directly inside the chosen folder.
- **Saving failed:** choose a writable output directory. Failed watermarking is reported as an error; inspect any partial copy before sharing it.

## License

MIT, as declared by the original project.
