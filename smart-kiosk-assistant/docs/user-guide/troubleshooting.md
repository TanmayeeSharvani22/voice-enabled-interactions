# Troubleshooting

## Stack Will Not Start

- Confirm the published host ports are free:

  ```bash
  ss -ltnp | grep -E "7860|8010|8011|8012|8020"
  ```

- Confirm Docker Compose can build:

  ```bash
  docker compose config
  docker compose build
  ```

- Tail individual services to find the first failure:

  ```bash
  docker compose logs -f audio-analyzer
  docker compose logs -f text-to-speech
  docker compose logs -f rag-service
  docker compose logs -f kiosk-core
  docker compose logs -f kiosk-ui
  ```

## First Startup Is Slow

This is expected. On first run each model-hosting service downloads or
exports model assets to its `models/` directory and Hugging Face cache.
Subsequent starts reuse the cached artifacts. The default
`audio-analyzer` healthcheck allows up to ~240 seconds for warmup; the
RAG LLM compile on GPU can also take a few minutes the first time.

## A `health` Endpoint Fails

- Run `docker compose ps` and check the `STATUS` column for `unhealthy`.
- If you are behind a corporate proxy, pass `--noproxy '*'` to `curl`
  when hitting `127.0.0.1`.
- Confirm the service container actually started:

  ```bash
  docker compose logs <service-name>
  ```

## Selected Device Is Not Used

The device field lives in the per-service pinned config (see
[Configuration](./get-started/configuration.md#inference-device)). If the device
does not appear in the logs:

- Check the value is supported for that model (e.g. `audio-analyzer`
  ASR supports `CPU` for `provider: openai`, and `CPU|GPU|NPU` for
  `provider: openvino` — `NPU` only works with `whisper-tiny`/`whisper-base`,
  see [ASR Support Matrix](./get-started/configuration.md#asr-support-matrix)).
- For `GPU`: confirm `/dev/dri` exists and the Intel OpenVINO GPU
  runtime is installed.
- Restart the affected service after the change:

  ```bash
  docker compose up -d --build --force-recreate <service-name>
  ```

- Confirm OpenVINO picked the device:

  ```bash
  docker compose logs <service-name> | grep -i -E "device|compiling|GPU|CPU"
  ```

For `audio-analyzer` specifically, check the effective provider/device
selection from `configs/audio-analyzer/config.yaml`:

```bash
grep -nE "provider:|device:" configs/audio-analyzer/config.yaml
```

and verify startup behavior:

```bash
docker logs audio-analyzer
```

`docker-compose.yml` is the single Compose file and should not override
ASR provider/device. The ASR selection is read only from
`configs/audio-analyzer/config.yaml`.

> [!IMPORTANT]
> `audio-analyzer` ASR on NPU works only for `whisper-tiny`/`whisper-base`;
> `whisper-small`+ fails to compile. `make check-env` does not check model
> name, so a `whisper-small`+ NPU config passes `check-env` but crash-loops
> at container startup. See
> [ASR Support Matrix](./get-started/configuration.md#asr-support-matrix).

NPU-capable services (`queue-service`, `identity-service` face/re-id,
`audio-analyzer` ASR with `whisper-tiny`/`whisper-base`) get the host NPU
device via `ACCEL_MOUNT_PATH` (defaults to `/dev/null` so CPU/GPU-only
hosts are unaffected). `make up` auto-detects and sets this automatically;
for direct `docker compose up`, set `ACCEL_MOUNT_PATH` yourself.

Before startup, run:

```bash
make check-env
```

### Error: OpenVINO does not report an NPU device

```bash
ls -l /dev/accel/
make check-env
```

For direct Compose runs, set the mapping explicitly:

```bash
ACCEL_MOUNT_PATH=/dev/accel/accel0 docker compose up -d queue-service
```

### `models.asr.device=NPU` Fails to Compile for `audio-analyzer`

| Provider + Device | Model | Result |
|---|---|---|
| `openvino` + `NPU` | `whisper-tiny`/`whisper-base` | ✅ Works |
| `openvino` + `NPU` | `whisper-small`+ | ❌ `Check '!self_attn_nodes.empty()' failed` |
| `openvino` + `GPU`/`CPU` | any | ✅ Works |
| `openai` + `GPU`/`NPU` | any | ❌ Not supported (CPU only) |

Fix: use `whisper-tiny`/`whisper-base` on NPU, or switch to `GPU`/`CPU` for larger models, then recreate:

```bash
docker compose up -d --force-recreate audio-analyzer
docker logs audio-analyzer
curl http://localhost:8010/health
```

### `TARGET_DEVICE=NPU` Causes OVMS/RAG to Restart-Loop

`ovms-llm` compiles on NPU but chat-completion requests fail at runtime
(`Input length exceeds the maximum allowed length`). `rag-service`
embedding/reranker (`RAG_EMBEDDING_DEVICE`/`RAG_RERANKER_DEVICE`, independent
of `TARGET_DEVICE`) fails to compile on NPU entirely — don't set either to `NPU`.

```bash
# .env: TARGET_DEVICE=CPU or GPU
docker compose up -d --force-recreate ovms-llm
```

### `IDENTITY_DEVICE=NPU` — Face/Re-ID Works, Voice Does Not

Face/re-id models run on NPU. The voice model (ECAPA-TDNN) fails to
compile (`Upper bounds are not specified for node ... compute_STFT`), so
voice auth stays disabled (`inference_ready=false`) — this is expected.
See [Identity Service Device](./get-started/configuration.md#identity-service-device-identity_device).

## Permission Errors on Mounted Folders

Every container runs as UID/GID `1000:1000` (baked into each image).
Model files and caches for `audio-analyzer` and `text-to-speech` live
in Docker named volumes (`audio_analyzer_models`,
`audio_analyzer_cache`, `text_to_speech_models`, etc.) initialized with
that ownership, so the usual host-side ownership errors do not apply.
If you still see:

```
PermissionError: [Errno 13] Permission denied: '...'
```

on a path inside the container, a named volume was likely created
earlier with the wrong ownership (for example by an older root-only
run). Reset it:

```bash
docker compose down
docker volume rm \
  smart-kiosk-assistant_audio_analyzer_models \
  smart-kiosk-assistant_audio_analyzer_cache \
  smart-kiosk-assistant_text_to_speech_models \
  smart-kiosk-assistant_text_to_speech_cache
docker compose up -d
```
Replace `smart-kiosk-assistant_` with whatever Compose project prefix
`docker volume ls` shows on your host. Resetting a volume forces the
services to re-download model assets on next startup.

## Browser UI Is Not Accessible Or Loads Blank (Remote Host)

If the kiosk stack runs on a remote/headless machine and
`http://<remote-ip>:7860` won't load or renders a blank page, the browser
is refusing the page because it's not a secure origin. Try either fix:

- **SSH port forwarding (recommended)** — tunnel the UI port to
  `localhost` so the browser treats it as a secure origin:

  ```bash
  ssh -L 7860:localhost:7860 intel@10.223.23.34
  ```

  Replace `intel@10.223.23.34` with your actual username/host, then open
  `http://127.0.0.1:7860` on your local machine.
- **Chrome insecure-origin flag** — allow the remote URL as a secure
  origin: open `chrome://flags/#unsafely-treat-insecure-origin-as-secure`,
  add `http://<remote-ip>:7860`, enable the flag, and relaunch Chrome.

## Browser UI Does Not Capture Audio

- Confirm the browser granted microphone permission for
  `http://127.0.0.1:7860`. Reset the permission and reload if needed.
- Modern browsers restrict microphone access on insecure origins. Use
  `http://127.0.0.1` (loopback) or serve the UI behind HTTPS.
- Check the `kiosk-ui` logs for upload errors:

  ```bash
  docker compose logs -f kiosk-ui
  ```

## Answer Is Empty or Off-Topic

- Confirm the knowledge base was ingested. The Gradio UI exposes an
  ingestion panel; see also
  [rag-service/README.md](https://github.com/intel-retail/voice-enabled-interactions/blob/main/smart-kiosk-assistant/rag-service/README.md).
- Check `rag-service` logs for retrieval scores and reranker output.
- Try the same question from the API to rule out the UI:

  ```bash
  curl --noproxy '*' -X POST http://127.0.0.1:8020/api/v1/query \
    -H 'Content-Type: application/json' \
    -d '{"query":"What are the store hours?"}'
  ```

## TTS Plays No Audio in the Browser

- Confirm the session snapshot has non-empty `tts_audio_segments` and
  no `tts_errors`. See [API Reference](./api-reference.md).
- The `kiosk-core` container and the `kiosk-ui` container share the
  `generated_audio` Docker volume. If you removed the volume, recreate
  the stack:

  ```bash
  docker compose down
  docker compose up -d --build
  ```

## kiosk-core Cannot Reach a Downstream Service

The compose defaults wire `kiosk-core` and `kiosk-ui` to the internal
service names (`audio-analyzer`, `text-to-speech`, `rag-service`). If
you override these URLs for a host-run setup, confirm:

- The downstream service is reachable from `kiosk-core` (try `curl`
  against the override URL from inside the `kiosk-core` container or
  from the host).
- For host-run downstreams reached from a container, use
  `host.docker.internal` (see the alternative compose snippets in
  [Run With Docker Compose](./get-started/run-container.md)).

## See Also

- [Configuration](./get-started/configuration.md)
- [Get Started](./get-started.md)
- [Run On The Host](./get-started/run-standalone.md)
