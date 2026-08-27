# Run On The Host

Use this path to run `kiosk-core` directly on the host instead of inside the
top-level Compose stack. This mode starts `kiosk-core`'s HTTP API only — no
browser UI is started by these steps; interact with it directly through its
REST endpoints (see [API Reference](../api-reference.md)) or an external
client that uploads audio to those endpoints.

## Clone

```bash
git clone https://github.com/intel-retail/voice-enabled-interactions.git
cd voice-enabled-interactions/smart-kiosk-assistant
```

## Start Downstream Services

Before starting `kiosk-core` on the host, make sure these downstream services are available:

- `audio-analyzer` at `http://127.0.0.1:8010/v1/audio/transcriptions`
- `text-to-speech` at `http://127.0.0.1:8011/v1/audio/speech`
- `rag-service` at `http://127.0.0.1:8020/api/v1/query`

The simplest way is to pull the prebuilt images for `audio-analyzer`
and `text-to-speech` from Docker Hub, build `rag-service` locally, and
run `kiosk-core` on the host. The kiosk compose file in
`smart-kiosk-assistant/` already wires these three services together;
start only those three:

```bash
docker compose pull audio-analyzer text-to-speech
docker compose up -d audio-analyzer text-to-speech rag-service
```

`rag-service` builds locally because it ships in this repository under
[../rag-service/](https://github.com/intel-retail/voice-enabled-interactions/tree/main/smart-kiosk-assistant/rag-service).
The other two are pulled from `intel/audio-analyzer` and `intel/text-to-speech` on Docker Hub.

## Python Setup

`kiosk-core` requires **Python 3.12** (matching the `python:3.12-slim` base
image used by the project's Dockerfile).

`openwakeword` declares a dependency on `tflite-runtime`, which does not
publish wheels for Python 3.12+. `kiosk-core` only uses openwakeword's ONNX
inference path (`KIOSK_CORE_WAKEWORD_INFERENCE_FRAMEWORK` defaults to
`onnx`), so `tflite-runtime` is never actually needed at runtime. Install
`requirements.txt` first (it pins openwakeword's real runtime dependencies),
then `openwakeword` itself with `--no-deps` in a separate pip invocation,
exactly as the Dockerfile does:

```bash
sudo apt-get install -y --no-install-recommends libportaudio2

python3.12 -m venv .venv
source .venv/bin/activate
python --version   # should report Python 3.12.x
pip install --upgrade pip
pip install -r requirements.txt
pip install --no-deps openwakeword==0.6.0
```

> **Note:** Because `tflite-runtime` is skipped, setting
> `KIOSK_CORE_WAKEWORD_INFERENCE_FRAMEWORK=tflite` (or requesting the
> `tflite` framework per-session) is not supported in this environment;
> openwakeword will log a warning and fall back to its ONNX backend.
> `pip check` will report `openwakeword requires tflite-runtime, which is
> not installed` — this is expected and harmless (see `requirements.txt`).

## Start kiosk-core

Run the API on the host:

```bash
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8012
```

Default URLs used by `kiosk-core` in this host-run mode:

- `KIOSK_CORE_ANALYZER_URL=http://127.0.0.1:8010/v1/audio/transcriptions`
- `KIOSK_CORE_RAG_URL=http://127.0.0.1:8020/api/v1/query`
- `KIOSK_CORE_TTS_URL=http://127.0.0.1:8011/v1/audio/speech`

## Verify

```bash
curl --noproxy '*' http://127.0.0.1:8012/health   # {"status":"ok"}
```

## Notes

- TTS audio clips are written under `generated_audio/` in the project directory.
- For endpoint details, see [API Reference](../api-reference.md).
