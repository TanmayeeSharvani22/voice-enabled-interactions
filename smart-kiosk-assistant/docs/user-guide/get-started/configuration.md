# Configuration

`kiosk-core` and `kiosk-ui` are configured through environment variables
(see [Environment Variables](#environment-variables)).

The three model-hosting services (`audio-analyzer`, `text-to-speech`,
`rag-service`) are configured through YAML files that the kiosk pins
and mounts into the containers. The most common changes are the
[model](#model-selection) and the [inference device](#inference-device).

## Model Selection

Each model-hosting service reads the model identifier from the same
pinned config file used for device selection:

| Service | File | Model fields |
|---|---|---|
| `audio-analyzer` | [`configs/audio-analyzer/config.yaml`](https://github.com/intel-retail/voice-enabled-interactions/blob/main/smart-kiosk-assistant/configs/audio-analyzer/config.yaml) | `models.asr.name` (e.g. `whisper-tiny`, `whisper-base`); `sentiment.model` (optional) |
| `text-to-speech` | [`configs/text-to-speech/config.yaml`](https://github.com/intel-retail/voice-enabled-interactions/blob/main/smart-kiosk-assistant/configs/text-to-speech/config.yaml) | `models.tts.name` (e.g. `microsoft/speecht5_tts`, Qwen-TTS variant); `model_variant` |
| `rag-service` | [`rag-service/config.yaml`](https://github.com/intel-retail/voice-enabled-interactions/blob/main/smart-kiosk-assistant/rag-service/config.yaml) | `models.llm.hf_id`, `models.embedding.hf_id`, `retrieval.reranker.hf_id`; per-model `weight_format` (`int4`, `int8`, `fp16`) |

Use Hugging Face IDs where the field name is `hf_id`. Models are
downloaded and exported on first start into the per-service `models/`
directory; subsequent starts reuse the cache.

### Supported / validated models

The kiosk ships with the following defaults. These are the models the
stack has been validated with — they are the recommended starting point.
The **Devices** column lists the supported inference devices for each:

| Service | Field | Default (validated) | Other examples | Devices |
|---|---|---|---|---|
| `audio-analyzer` ASR | `models.asr.name` | `whisper-base` | `whisper-tiny`, `whisper-small`, `whisper-medium`, `whisper-large` | `CPU`, `GPU` (`provider: openvino` required for `GPU`; `NPU` is not supported — see [ASR Support Matrix](#asr-support-matrix)) |
| `audio-analyzer` sentiment | `sentiment.model` | `speechbrain/emotion-recognition-wav2vec2-IEMOCAP` | other SpeechBrain emotion-recognition models | `CPU`, `GPU` (disabled by default) |
| `text-to-speech` | `models.tts.name` | `microsoft/speecht5_tts` (SpeechT5) | `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` (Qwen-TTS) | `CPU`, `GPU` (`int4` on iGPU produces noise; use `fp16` or `int8` on GPU) |
| `rag-service` LLM | `models.llm.hf_id` | `Qwen/Qwen3-4B-Instruct-2507` | other OpenVINO-exportable instruct LLMs | `CPU`, `GPU` (`GPU` recommended for acceptable latency) |
| `rag-service` embedding | `models.embedding.hf_id` | `BAAI/bge-large-en-v1.5` | `BAAI/bge-base-en-v1.5`, `BAAI/bge-small-en-v1.5` | `CPU`, `GPU` (`CPU` is usually fast enough) |
| `rag-service` reranker | `retrieval.reranker.hf_id` | `BAAI/bge-reranker-base` | `BAAI/bge-reranker-large` | `CPU`, `GPU` (optional) |

> [!IMPORTANT]
> **Changing models is at your own discretion.** The defaults above are
> the only combinations validated with this stack. Configuring models,
> variants, devices, or precisions other than the defaults may negatively
> affect the functionality, accuracy, latency, or stability of the
> application. You are responsible for ensuring the configuration you
> choose is correct and works for your use case — make changes only if you
> understand the implications.
>
> In particular:
> - Some models do not function properly at aggressive quantization. If a
>   model produces garbled, empty, or low-quality output at `int4`, switch
>   that model's `weight_format`/`dtype` to `int8` or `fp16`.
> - A model must be exportable to OpenVINO IR for the OpenVINO backend; not
>   every Hugging Face model is supported.
> - Larger models increase first-run download/export time, memory use, and
>   per-request latency, and may not fit on the selected device.
> - After any change, restart the affected service and verify it loads and
>   responds correctly before relying on it.

## Inference Device

Each model-hosting service reads its device from a pinned config file:

| Service | File | Fields |
|---|---|---|
| `audio-analyzer` | [`configs/audio-analyzer/config.yaml`](https://github.com/intel-retail/voice-enabled-interactions/blob/main/smart-kiosk-assistant/configs/audio-analyzer/config.yaml) | `models.asr.device`, `sentiment.device` |
| `text-to-speech` | [`configs/text-to-speech/config.yaml`](https://github.com/intel-retail/voice-enabled-interactions/blob/main/smart-kiosk-assistant/configs/text-to-speech/config.yaml) | `models.tts.device` |
| `rag-service` | [`rag-service/config.yaml`](https://github.com/intel-retail/voice-enabled-interactions/blob/main/smart-kiosk-assistant/rag-service/config.yaml) | `models.llm.device`, `models.embedding.device`, `retrieval.reranker.device` |

The supported devices for each model are listed in the
[Supported / validated models](#supported--validated-models) table above.

Use uppercase device names (`CPU`, `GPU`, and — for `audio-analyzer` ASR and
`queue-service` only — `NPU`). `rag-service` expects them as quoted strings;
`audio-analyzer` and `text-to-speech` unquoted.

> [!IMPORTANT]
> **`text-to-speech` does not support `NPU`.** `models.tts.device` only
> accepts `CPU`/`GPU` (see `configs/text-to-speech/config.yaml`); there is no
> NPU device mapping for this service in `docker-compose.yml`. Do not set
> `models.tts.device: NPU` — it is not a supported configuration.

After editing, restart the affected service and confirm OpenVINO picked
the device:

```bash
docker compose up -d --build --force-recreate <service-name>
docker compose logs <service-name> | grep -i -E "device|compiling|GPU|CPU"
```

OpenVINO prints a `Compiling model on <DEVICE>` line on first load.

> GPU execution is delegated to the OpenVINO backend used by each
> service. Whether a given model actually runs on GPU and how it
> performs depends on the OpenVINO version and operator coverage for
> that model.

## Audio Analyzer ASR Provider/Device (`config.yaml`)

For ASR provider/device selection, use:

1. `configs/audio-analyzer/config.yaml`

This repository treats it as the single source of truth. Configure:

- `models.asr.provider`
- `models.asr.device`

There is exactly one checked-in Compose file in this project: `docker-compose.yml`.
No checked-in hardware-specific Compose override files are used (the Makefile may generate a temporary runtime override under `/tmp` to inject `/dev/accel` when NPU is configured for `queue-service` or `identity-service`).
`docker-compose.yml` provides container runtime access, while ASR
provider/device selection remains in `config.yaml` only. Provider/device
is validated before startup by `make check-env`; startup is rejected early
with actionable errors when configured hardware is unavailable.

The NPU device mapping is controlled by `ACCEL_MOUNT_PATH` in the Compose
environment. The checked-in Compose file defaults that mapping to
`/dev/null`, so CPU/GPU-only hosts can start cleanly. `make up` auto-detects
the host Intel NPU node and exports that path for the Compose run whenever
NPU is configured for any component (see
[NPU Deployment Workflow](#npu-deployment-workflow) below for which
components actually work on NPU). For direct `docker compose up`, set
`ACCEL_MOUNT_PATH` in `.env` or the shell to the host NPU device node first.

> [!NOTE]
> This `ACCEL_MOUNT_PATH` / `make up` NPU auto-detection mechanism is real
> and used by `queue-service` and `identity-service` (face/re-id), which do
> run on NPU — see [NPU Deployment Workflow](#npu-deployment-workflow). It
> does **not** mean `models.asr.device=NPU` works; see
> [ASR Support Matrix](#asr-support-matrix) below.

### OpenVINO Whisper on NPU — Not Currently Supported

> [!WARNING]
> Setting `provider: openvino, device: NPU` passes `make check-env`'s
> device-visibility check (OpenVINO does report an `NPU` device) but the
> container then fails at startup when it tries to compile the Whisper
> model. See [ASR Support Matrix](#asr-support-matrix) below for the exact
> error and root cause. Use `CPU` or `GPU` for `models.asr.device` instead.

### Other Supported ASR Configurations

OpenAI + CPU:

```yaml
models:
  asr:
    provider: openai
    device: CPU
```

OpenVINO + GPU:

```yaml
models:
  asr:
    provider: openvino
    device: GPU
```

OpenVINO + CPU:

```yaml
models:
  asr:
    provider: openvino
    device: CPU
```

### Unsupported Combinations: OpenAI + GPU/NPU, and OpenVINO + NPU

`models.asr.provider=openai` supports `CPU` only in this stack.
The following are not supported by the current OpenAI/PyTorch Whisper backend:

- `models.asr.provider=openai` with `models.asr.device=GPU`
- `models.asr.provider=openai` with `models.asr.device=NPU`

`models.asr.provider=openvino` with `models.asr.device=NPU` is also **not
supported** — see [ASR Support Matrix](#asr-support-matrix) below for the
observed compile-time error.

- Use `openvino + GPU` for GPU execution.
- Use `openvino + CPU` or `openai + CPU` for CPU execution.
- NPU is not currently a working option for ASR with any provider.

### ASR Support Matrix

| Provider | CPU | GPU | NPU |
|---|---|---|---|
| `openai` | Yes | No | No |
| `whispercpp` | Yes | No | No |
| `openvino` | Yes | Yes (Intel GPU required) | No — see note below |

If `GPU` is configured and unavailable on the host, `make check-env` fails
before any container startup. The stack does not silently fall back to
another device.

> [!IMPORTANT]
> **`openvino` + `NPU` was tested end-to-end and does not currently work.**
> `WhisperPipeline` (both the OpenVINO GenAI backend and the plain OpenVINO
> encoder/decoder backend, i.e. `use_ov_genai: True` or `False`) fails to
> compile on NPU for both `whisper-base` and `whisper-small`:
> ```
> Missing upper bound for one or more nodes.
> ```
> (GenAI backend surfaces this as `Check '!self_attn_nodes.empty()' failed
> at .../npuw/llm_compiled_model_utils.cpp`.) This is the same class of
> problem as the `rag-service` embedding/reranker models and the
> `identity-service` voice model: the exported IR has a dynamic/unbounded
> sequence-length dimension that the NPU compiler rejects. It is not fixed
> by choosing a smaller model or switching the GenAI flag. Use `CPU` or
> `GPU` for ASR; do not set `models.asr.device: NPU`.
>
> This contradicts the upstream `audio-analyzer` source
> (`utils/openvino_runtime_validation.py`, `_OPENVINO_NPU_INFERENCE_UNSUPPORTED`),
> whose comment claims "whisper-tiny/base/small/medium all pass NPU
> inference" and only denylists `whisper-large` as NPU-unsupported (a
> *runtime execution* failure, `ZE_RESULT_ERROR_UNINITIALIZED`). What was
> actually observed here is a *compile-time* failure for `whisper-base`
> that the validation module's `_OPENVINO_NPU_INFERENCE_UNSUPPORTED`
> denylist does not catch, so `make check-env`/startup validation passes
> but the container then crash-loops. Unlike `identity-service`'s voice
> model or diarization's embedding model (see
> `components/asr/diarization/ov_pyannote_diarizer.py`, which pads/crops to
> a static frame count specifically for NPU), no static-shape workaround
> exists in the Whisper ASR code path. Re-validate against a newer
> `audio-analyzer` release before reporting ASR NPU as supported again.

## Audio Analyzer Diarization Device (`config.yaml`)

Diarization (`models.diarization.device`) is a **separate component from ASR**
(see [ASR Support Matrix](#asr-support-matrix) above) with its own,
more limited device support. Do not assume ASR's `CPU`/`GPU`/`NPU` support
applies to diarization — it does not.

> [!IMPORTANT]
> **In the currently released Kiosk image, diarization only supports `CPU`.**
> The diarizer (`pyannote/speaker-diarization-3.1`, a PyTorch/SpeechBrain
> model) is loaded with `torch.device(<configured value>)`. PyTorch has no
> `"gpu"` device string (Intel GPU support in PyTorch requires `"xpu"`, which
> this component does not use) and no `"npu"` device string at all. Setting
> `device: GPU` or `device: NPU` is **accepted by the config schema** but
> fails at diarizer-load time with an error like:
> ```
> Expected one of cpu, cuda, ipu, xpu, ... device type at start of device string: gpu
> ```
> This is **non-fatal**: the failure is caught, logged as a warning, and
> diarization is disabled for that session — the container stays healthy and
> ASR keeps working, but speaker labels are not produced.
>
> **Use `device: CPU` for diarization.** Do not configure `GPU` or `NPU` for
> `models.diarization.device` — they do not work in this image and will
> silently disable diarization rather than accelerate it.

An OpenVINO-backed diarization path that genuinely supports `GPU`/`NPU`
exists in a newer upstream `edge-ai-libraries` `audio-analyzer` checkout,
but **is not part of the currently released Kiosk image** covered by this
document. Do not configure `GPU`/`NPU` for diarization based on that
upstream code until a Kiosk image that includes it is released.

## Queue Service Device (`QUEUE_DEVICE`)

`queue-service` runs the YOLO26 person detector through a DLStreamer
(`gvainference`) pipeline. The inference device is controlled by
`model.device` in `queue-service/conf/queue-config.yaml`, and can be
overridden without editing that file via `QUEUE_DEVICE` in `.env`
(mapped by `docker-compose.yml` to `QUEUE_SERVICE__MODEL__DEVICE`, read by
`queue-service/src/config_loader.py`).

- Default: `QUEUE_DEVICE=CPU` — always available, no extra device mapping
  needed.
- `QUEUE_DEVICE=GPU` / `QUEUE_DEVICE=NPU` — supported, using the same
  `/dev/dri` and `ACCEL_MOUNT_PATH`-driven `/dev/accel` mapping described
  under [Audio Analyzer ASR Provider/Device](#audio-analyzer-asr-providerdevice-configyaml)
  above. For NPU, set `ACCEL_MOUNT_PATH` to the host NPU device node
  (auto-detected by `make up`) before starting `queue-service`.

Verify the configured device actually reached the pipeline:

```bash
docker logs queue-service 2>&1 | grep "gvainference model"
# Expected: ... gvainference model=... device=NPU ...  (or CPU/GPU, matching QUEUE_DEVICE)
```

> Editing `queue-config.yaml`'s `model.device` directly also works and takes
> precedence in the same way as any other YAML default — `QUEUE_DEVICE` only
> needs to be set when you want to override it without touching the file.

## Identity Service Device (`IDENTITY_DEVICE`)

`identity-service` performs face detection/re-identification
(`face-detection-retail-0005`, `face-reidentification-retail-0095`) and
voice-print embedding (`ecapa-tdnn-voice`) — all three are **OpenVINO IR
models**, loaded via `openvino.Core().compile_model(model, device)`, and
`IDENTITY_DEVICE` is correctly wired end-to-end from `.env` through
`docker-compose.yml` to the OpenVINO compile call. The device-selection
code itself has no bug and no model-format limitation.

> [!NOTE]
> **Face detection/re-identification support `CPU`, `GPU`, and `NPU`.**
> The `identity-service` container has NPU device passthrough via the same
> `ACCEL_MOUNT_PATH`/`/dev/accel` mechanism used by `audio-analyzer` and
> `queue-service`. Set `IDENTITY_DEVICE=NPU` in `.env` together with
> `ACCEL_MOUNT_PATH` pointing to the host NPU device node (auto-detected by
> `make up`) to run face detection/re-identification on the NPU.
>
> **Voice-print embedding (`ecapa-tdnn-voice`) does not support `NPU`.**
> Its OpenVINO IR contains an internal STFT reshape with an unbounded
> dynamic dimension (`aten::view/Reshape`), which the NPU compiler rejects
> at compile time (`Got negative shape dim bound`). With
> `IDENTITY_DEVICE=NPU`, the service starts with face engine enabled and
> voice engine disabled (`inference_ready=false`, since voice verification
> requires both). Use `IDENTITY_DEVICE=CPU` or `IDENTITY_DEVICE=GPU` if
> voice authentication is required.
>
> The face/voice model files are **not downloaded by default** — run
> `./setup_models.sh --identity` first. Without them, the face/voice engines
> stay disabled (`inference_ready=false`) regardless of the configured device.

## OVMS-LLM Device (`TARGET_DEVICE`)

`TARGET_DEVICE` controls the inference device for the `ovms-llm` container
only (the LLM served by OpenVINO Model Server for the ordering agent).
`rag-service`'s own embedding/reranker components have their own,
independent device configuration — see
[RAG Service Embedding/Reranker Device](#rag-service-embeddingreranker-device-rag_embedding_device-rag_reranker_device)
below.

- **Currently supported:** `TARGET_DEVICE=CPU`, `TARGET_DEVICE=GPU`, `TARGET_DEVICE=NPU`.

> [!NOTE]
> **`TARGET_DEVICE=NPU` device passthrough works for `ovms-llm`.**
> The `ovms-llm` container has NPU device passthrough via the same
> `ACCEL_MOUNT_PATH`/`/dev/accel` mechanism used by `audio-analyzer` and
> `queue-service`. Set `TARGET_DEVICE=NPU` in `.env` together with
> `ACCEL_MOUNT_PATH` pointing to the host NPU device node (auto-detected by
> `make up`) to compile the LLM for the NPU. OVMS logs
> `Available devices for Open VINO: CPU, GPU, NPU` and the model
> (`Qwen3-4B-int8-ov`) compiles successfully.
>
> **NPU inference has been observed to fail at request time** on at least
> one validated host, even after a successful compile — with two distinct
> symptoms seen: a short chat-completion request failed with
> `zeFenceHostSynchronize result: ZE_RESULT_ERROR_UNKNOWN` inside OVMS's
> LLM executor, and a longer RAG-augmented prompt (routed through
> `rag-service`) failed with `Input length exceeds the maximum allowed
> length`. Both point to NPU driver/runtime or static-shape/context-length
> limitations for this model's KV-cache/stateful execution graph, not a
> configuration issue. Validate end-to-end generation with realistic
> prompt lengths (not just `/v3/models` or container health) before
> relying on `TARGET_DEVICE=NPU` for `ovms-llm` in production.
>
> **Use `TARGET_DEVICE=CPU` or `TARGET_DEVICE=GPU`** if the host does not
> have an NPU, `ACCEL_MOUNT_PATH` is not set, or NPU generation requests
> fail as described above.

## RAG Service Embedding/Reranker Device (`RAG_EMBEDDING_DEVICE`, `RAG_RERANKER_DEVICE`)

`rag-service`'s embedding (`BAAI/bge-large-en-v1.5`) and reranker
(`BAAI/bge-reranker-base`) components are OpenVINO IR models exported
in-process by `optimum-intel` (`rag-service/utils/ensure_model.py`) and
loaded via `OVModelForFeatureExtraction`/equivalent
(`rag-service/components/embedding_component.py`,
`reranker_component.py`). Their device is set independently of
`TARGET_DEVICE` via `RAG_EMBEDDING_DEVICE` / `RAG_RERANKER_DEVICE` in
`.env` (mapped by `docker-compose.yml` to
`SMART_KIOSK_RAG__MODELS__EMBEDDING__DEVICE` /
`SMART_KIOSK_RAG__RETRIEVAL__RERANKER__DEVICE`).

- **Currently supported:** `RAG_EMBEDDING_DEVICE`/`RAG_RERANKER_DEVICE` =
  `CPU` or `GPU`. Default: `GPU`.
- **Currently unsupported:** `NPU`.

> [!IMPORTANT]
> **`NPU` is not supported for the embedding/reranker models.**
> `optimum-intel`'s default export produces OpenVINO IR with dynamic
> (unbounded) sequence-length and batch shapes — required because queries
> and knowledge-base documents vary in length and the reranker batches
> multiple candidates per call (`rag-service/config.yaml`'s
> `models.embedding.batch_size`). The NPU compiler rejects this IR
> (`Missing upper bound for one or more nodes`); setting either variable to
> `NPU` will crash `rag-service` at startup.
>
> Forcing static/bounded shapes to work around this is not recommended:
> it would require padding every input to a fixed max length (wasting
> compute on short queries) and serializing what is currently a batched
> reranker call into one NPU invocation per candidate — likely slower
> overall than `GPU`/`CPU`, for a component that is not the latency
> bottleneck (the LLM is). `CPU` is normally fast enough for
> embedding/reranking; `GPU` is the default to match prior behavior.

## Environment Variables

kiosk-core has no config file. All settings are controlled through environment variables.

### kiosk-core API (`main:app`)

| Variable | Default | Description |
|---|---|---|
| `KIOSK_CORE_ANALYZER_URL` | `http://127.0.0.1:8010/v1/audio/transcriptions` | audio-analyzer transcription endpoint |
| `KIOSK_CORE_RAG_URL` | `http://127.0.0.1:8020/api/v1/query` | RAG query endpoint |
| `KIOSK_CORE_TTS_URL` | `http://127.0.0.1:8011/v1/audio/speech` | TTS speech synthesis endpoint |
| `KIOSK_CORE_TTS_MODEL` | `qwen-tts` | Model name sent to the TTS service |
| `KIOSK_CORE_TTS_VOICE` | *(unset)* | Voice name sent to the TTS service |
| `KIOSK_CORE_TTS_LANGUAGE` | `English` | Language sent to the TTS service |
| `KIOSK_CORE_TTS_INSTRUCTIONS` | *(unset)* | Optional style instructions for TTS |
| `KIOSK_CORE_SAMPLE_RATE` | `16000` | Default audio sample rate in Hz |
| `KIOSK_CORE_CHUNK_SECONDS` | `4.0` | Length of each audio chunk sent to audio-analyzer |
| `KIOSK_CORE_SILENCE_TIMEOUT_SECONDS` | `1.5` | Silence duration after speech that ends a session |
| `KIOSK_CORE_MAX_SESSION_SECONDS` | `20.0` | Hard cap on session duration |
| `KIOSK_CORE_SILENCE_THRESHOLD` | `900` | RMS threshold below which audio is treated as silence |
| `KIOSK_CORE_BLOCK_DURATION_SECONDS` | `0.1` | PortAudio capture block size |
| `KIOSK_CORE_PREROLL_SECONDS` | `0.3` | Audio buffered before speech starts |
| `KIOSK_CORE_HTTP_TIMEOUT_SECONDS` | `120.0` | HTTP client timeout for downstream calls |

### Gradio UI (`gradio_app.py`)

| Variable | Default | Description |
|---|---|---|
| `KIOSK_CORE_UI_BASE_URL` | `http://127.0.0.1:8012` | Base URL of the kiosk-core API |
| `KIOSK_CORE_UI_ANALYZER_URL` | `http://127.0.0.1:8010/v1/audio/transcriptions` | Passed to start-file sessions as `analyzer_url` |
| `KIOSK_CORE_UI_RAG_URL` | `http://127.0.0.1:8020/api/v1/query` | Passed to start-file sessions as `rag_url` |
| `KIOSK_CORE_UI_TTS_URL` | `http://127.0.0.1:8011/v1/audio/speech` | Passed to start-file sessions as `tts_url` |
| `KIOSK_CORE_UI_TIMEOUT_SECONDS` | `120.0` | HTTP client timeout in the UI |
| `KIOSK_CORE_UI_POLL_INTERVAL_SECONDS` | `0.35` | How often the UI polls for session state updates |

### Kiosk UI runtime mode {#kiosk_ui_mode}

The React kiosk UI (`kiosk-ui/`) ships as a single image that can serve
either of two screens, selected at container start — no rebuild:

| Variable | Default | Description |
|---|---|---|
| `KIOSK_UI_MODE` | `operator` | `operator` — chat transcript + performance dashboard (existing behaviour), served on port 7860. `customer` — single-view kiosk screen with a queue-aware menu, live cart, and a voice-only "Ask" button, intended for the physical kiosk touchscreen. |

The value is written to `/usr/share/nginx/html/config.js` by
`docker-entrypoint.sh` (installed as an nginx `docker-entrypoint.d`
script) and read by the SPA before the React bundle loads. In
`docker-compose.yml` the two screens are separate containers
(`kiosk-ui` and `kiosk-ui-customer`) built from the *same* image/context,
published on different host ports (`7860` and `7861` respectively) so
they can be shown on two separate monitors during a demo.

## Compose Defaults

When running with the top-level [docker-compose.yml](https://github.com/intel-retail/voice-enabled-interactions/blob/main/smart-kiosk-assistant/docker-compose.yml), the defaults are wired to the internal Compose network:

- `KIOSK_CORE_ANALYZER_URL=http://audio-analyzer:8010/v1/audio/transcriptions`
- `KIOSK_CORE_RAG_URL=http://rag-service:8020/api/v1/query`
- `KIOSK_CORE_TTS_URL=http://text-to-speech:8011/v1/audio/speech`
- `KIOSK_CORE_UI_BASE_URL=http://kiosk-core:8012`

Most deployments should leave these values unchanged. Override them only when `kiosk-core` or `kiosk-ui` must call services outside the local Compose stack.

## Session Parameters

Session parameters (chunk duration, silence threshold, etc.) can also be provided per-request in the POST body for `/api/v1/sessions/start` and `/api/v1/sessions/start-file`. Per-request values take precedence over the environment variable defaults.

---

## NPU Deployment Workflow

This section provides a complete step-by-step workflow to run the Smart Kiosk Assistant with Intel NPU acceleration where currently supported.

> **Which services support NPU?**
> `queue-service` (`QUEUE_DEVICE=NPU`) supports NPU — see
> [Queue Service Device](#queue-service-device-queue_device) above.
> `audio-analyzer` ASR (`provider: openvino, device: NPU`) does **not** —
> `WhisperPipeline` fails to compile on NPU (`Missing upper bound for one
> or more nodes`) for both the OpenVINO GenAI and plain OpenVINO backends —
> see [ASR Support Matrix](#asr-support-matrix) above for the exact error.
> `audio-analyzer` diarization does **not** either (see
> [Audio Analyzer Diarization Device](#audio-analyzer-diarization-device-configyaml)).
> `identity-service` has NPU device passthrough and its face detection/
> re-identification models compile and run on NPU; its voice model
> (ECAPA-TDNN) does **not** — see
> [Identity Service Device](#identity-service-device-identity_device).
> `ovms-llm` has NPU device passthrough and its model compiles on NPU, but
> live inference has been observed to fail at runtime — see
> [OVMS-LLM Device](#ovms-llm-device-target_device) for the exact errors
> observed; validate end-to-end before relying on it in production.
> `rag-service`'s embedding/reranker models do **not** support NPU (dynamic
> shapes rejected by the NPU compiler) and are configured independently of
> `TARGET_DEVICE` — see
> [RAG Service Embedding/Reranker Device](#rag-service-embeddingreranker-device-rag_embedding_device-rag_reranker_device).
> `text-to-speech` does not support NPU at all. Do not set NPU on the
> unsupported services/components — they will either fail to start or
> silently disable the affected feature.
>
> | Component | CPU | GPU | NPU |
> |---|---|---|---|
> | Queue Service (`QUEUE_DEVICE`) | Yes | Yes | Yes |
> | Identity Service — face/re-id (`IDENTITY_DEVICE`) | Yes | Yes | Yes |
> | Identity Service — voice/ECAPA-TDNN (`IDENTITY_DEVICE`) | Yes | Yes | No — dynamic STFT reshape rejected by NPU compiler |
> | OVMS-LLM (`TARGET_DEVICE`) | Yes | Yes | Compiles, but runtime inference failures observed — validate before production use |
> | RAG Service embedding/reranker (`RAG_EMBEDDING_DEVICE` / `RAG_RERANKER_DEVICE`) | Yes | Yes | No — dynamic shapes rejected by NPU compiler |
> | Text-to-Speech (`models.tts.device`) | Yes | Yes | No |
> | Audio Analyzer ASR (`models.asr.device`) | Yes | Yes | No — `Missing upper bound for one or more nodes` at compile time (see [ASR Support Matrix](#asr-support-matrix)) |
> | Audio Analyzer Diarization (`models.diarization.device`) | Yes | No — currently deployed configuration only supports CPU | No — currently deployed configuration only supports CPU |
>
> As things currently stand, `queue-service` and `identity-service`
> face/re-id are the only components confirmed to run inference correctly
> on NPU in this stack. The remaining steps below configure NPU for
> `queue-service`; adapt the device variable if testing another component.

### 1 — System requirements

| Requirement | Details |
|---|---|
| Hardware | Intel Core Ultra (Meteor Lake or later) with integrated NPU |
| Host driver | Intel NPU driver (`intel-npu-driver`) installed and loaded |
| User-space runtime | `intel-level-zero-npu` package |
| Host device | `/dev/accel/accel0` (or similar) present and accessible |
| OpenVINO | Container image already bundles the correct runtime |

Verify the NPU device node is present before proceeding:
```bash
ls /dev/accel/
# Expected: accel0   accelmon0
```

### 2 — Install the Intel NPU driver (if not already installed)

Refer to the Intel NPU driver repository: <https://github.com/intel/linux-npu-driver/releases>. Installation varies by distribution. After installation:

```bash
# Verify kernel driver is loaded
lsmod | grep intel_vpu
# Verify device node exists
ls -la /dev/accel/accel0
```

### 3 — Set NPU device for queue-service

> [!NOTE]
> Earlier revisions of this guide walked through setting
> `models.asr.device=NPU` for Whisper ASR here. That configuration does
> **not work** — see [ASR Support Matrix](#asr-support-matrix) above. This
> workflow now uses `queue-service`, the component confirmed to run
> correctly on NPU in this stack.

Set `QUEUE_DEVICE=NPU` in `.env`:

```bash
# .env
QUEUE_DEVICE=NPU
```

### 4 — Start the stack

The recommended path is `make up`, which auto-detects the NPU device node and validates OpenVINO visibility before starting:

```bash
cd smart-kiosk-assistant
make check-env
make up
```

`make` automatically:
- Detects `/dev/accel/accel*` on the host
- Sets `ACCEL_MOUNT_PATH` to the detected device node
- Passes `ACCEL_MOUNT_PATH` into the Compose invocation

If you use `docker compose` directly, set `ACCEL_MOUNT_PATH` yourself:

```bash
ACCEL_MOUNT_PATH=/dev/accel/accel0 docker compose up -d
```

### 5 — Verify NPU is active

```bash
# Check queue-service started healthy
docker ps --filter "name=queue-service" --format "{{.Names}}\t{{.Status}}"

# Confirm NPU device is visible to OpenVINO inside the container
docker exec queue-service python3 -c "import openvino as ov; print(ov.Core().available_devices)"
# Expected output includes: NPU

# Check the gvainference pipeline is targeting device=NPU
docker logs queue-service 2>&1 | grep -i "device=NPU\|npu"
```

Optionally, verify NPU device passthrough for `identity-service`
(face/re-id only — voice will remain disabled, see
[Identity Service Device](#identity-service-device-identity_device)):

```bash
IDENTITY_DEVICE=NPU make up IDENTITY=true
docker logs identity-service 2>&1 | grep -i "face\|voice\|inference_ready"
```

### 6 — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Container unhealthy, `NPU not in available_devices` | NPU driver not loaded or `/dev/accel/accel0` not mapped | Verify host driver and set `ACCEL_MOUNT_PATH` |
| `libopenvino_intel_npu_compiler_loader.so` missing | NPU compiler not in image | Rebuild the affected image with NPU user-space packages |
| Slow first inference (20–60 s) | NPU compiler cache is empty (cold start) | Normal on first run; subsequent requests will be fast |
| `audio-analyzer` crash-loops with `Missing upper bound for one or more nodes` after setting `models.asr.device=NPU` | Whisper's OpenVINO IR has dynamic/unbounded shapes the NPU compiler rejects — this is not fixable via config | Set `models.asr.device` to `CPU` or `GPU` instead |
| Non-NPU containers unhealthy after NPU config change | NPU-unrelated services picking up wrong env | Only modify the specific component's config (e.g. `QUEUE_DEVICE`, `IDENTITY_DEVICE`); do not set `models.asr.device=NPU` |

> **Cold-start note:** The OpenVINO NPU compiler caches compiled kernels inside the container under `/tmp/ov_cache/`. The first inference after a container restart takes significantly longer (20–60 s) while the cache warms up. This is expected behavior.


