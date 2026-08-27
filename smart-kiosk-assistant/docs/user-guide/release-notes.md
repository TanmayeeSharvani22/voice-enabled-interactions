# Release Notes: Smart Kiosk Assistant

## 2026.2.0

This release delivers a unified Smart Kiosk Assistant stack with dual
React-based UIs, OpenVINO-powered AI inference, agentic tool-calling
ordering, queue-aware recommendations, enhanced voice interaction,
optional multimodal identity, and streamlined deployment. This update
includes the following changes:

- The kiosk front end has been rebuilt as a React (Vite + TypeScript)
  single-page application, replacing the previous Gradio interface for a
  faster and more customizable web experience.
- A single `kiosk-ui` image now serves two runtime modes selected by
  `KIOSK_UI_MODE`: an operator screen on port `7860` and a
  customer-facing kiosk screen on port `7861`.
- The operator screen provides voice and text chat, a live queue feed,
  knowledge-base ingestion, audio device settings, and a performance
  dashboard with executive KPIs, model KPIs, hardware charts, and
  pipeline flow visualization.
- The customer screen provides a queue-aware menu grid with a category
  rail, a live cart panel with running order total and upsell prompts, a
  queue-status bar, and a voice "Ask" bar.
- The ordering agent now drives the cart through an MCP tool server
  hosted by `kiosk-core`, with tools for catalogue browsing, cart
  lifecycle management, order confirmation, and upsell suggestions.
  Built-in guardrails resolve ambiguous item references and reject
  implausible quantities.
- A rule-based upsell engine produces contextual add-on suggestions that
  are surfaced in both the cart and the spoken response.
- The ordering agent runs its Qwen3-4B language model through OpenVINO
  Model Server (OVMS) instead of an in-process OpenVINO model, providing
  a dedicated, OpenAI-compatible inference endpoint for tool calling.
- A queue analytics capability adds a person-counting service and an
  RTSP streamer, using YOLO detection with OpenVINO to track queue length
  from a video feed, expose a live MJPEG overlay stream, and surface a
  dynamic peak-hour menu.
- The audio-analyzer service adds OpenAI-compatible streaming
  transcription over Server-Sent Events, a realtime WebSocket
  transcription endpoint, Video Summarization Service (VSS) response
  compatibility, and more accurate multi-speaker segment splitting with
  persisted enrolment.
- Speaker diarization has been enabled across the audio-analyzer and
  kiosk-core pipeline, improving turn attribution during multi-speaker
  interactions.
- The text-to-speech service now supports named voices and produces
  faster, more natural-sounding prosody.
- An optional multimodal identity service adds Face ID and voiceprint
  authentication, combining OpenVINO face and ECAPA voice inference with
  a FAISS index and SQLite loyalty profiles, with login, registration,
  and enrolment screens in the UI, enabled through a dedicated
  deployment profile.
- Inference devices are configurable per service (`CPU`, `GPU`, `NPU`),
  including NPU passthrough for `identity-service`, `ovms-llm`, and
  audio-analyzer ASR, with independent device settings for the RAG
  embedding and reranker models.
- All kiosk services and container images have been rebuilt and aligned
  to `2026.2.0`: `kiosk-core`, `kiosk-ui`, `queue-service`,
  `identity-service`, `rag-service`, `rtsp-streamer`, `audio-analyzer`,
  `text-to-speech`, and `metrics-collector`.
- A Makefile-based workflow simplifies setup and operations with targets
  for environment initialization, configuration validation, model and
  sample-video download, image build, service startup, per-service health
  checks, log tailing, single-service rebuilds, and cleanup.
- Sample-video tooling downloads and provisions the RTSP feed clips used
  by the queue analytics pipeline, configurable through the environment
  file.

## 2026.1.0

The initial release of Smart Kiosk Assistant marks the launch of a voice-enabled
interactive application for retail, QSR, Airlines and other customer-facing
environments. The application has the following features:

- Designed as a conversational AI experience, it enables users to engage
  naturally through speech and receive intelligent, spoken responses
  in real time.
- The platform brings together speech recognition, retrieval-augmented
  generation, and text-to-speech in a seamless, end-to-end voice
  interaction flow.
- With browser-based voice capture and natural audio playback, the experience
  feels intuitive, responsive, and ready for real-world engagement.
- Smart Kiosk Assistant grounds every response in an ingestible local knowledge
  base, helping deliver more relevant, context-aware, and business-specific
  answers.
- Its integrated AI stack combines kiosk UI, orchestration, speech-to-text,
  retrieval, and speech synthesis into a unified deployment-ready application.
- The experience is further enhanced by built-in visibility into model KPIs and
  live performance data, including runtime model details and latency metrics.
- Optimized for local and edge deployment, the application leverages OpenVINO
  acceleration on Intel hardware for efficient AI inference.
- Docker Compose packaging and flexible configuration make the solution easy to
  deploy, adapt, and scale across enterprise environments.
- This launch establishes Smart Kiosk Assistant as a strong foundation for
  immersive, intelligent, and voice-first digital engagement experiences.

