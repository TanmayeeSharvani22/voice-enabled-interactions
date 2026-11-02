#!/usr/bin/env sh
#
# Resolve the HuggingFace offline mode to start the stack with, and refuse to
# start a run that is guaranteed to stall.
#
# Background (ITEP-97604)
# -----------------------
# setup_models.sh does NOT pre-fetch the ASR/TTS/RAG models; they are pulled
# in-container on the first online run. On a host with no egress and no proxy,
# audio-analyzer and text-to-speech therefore raise httpx.ConnectError during
# FastAPI lifespan, their healthcheck never passes, and every service gated on
# `depends_on: service_healthy` aborts after the full 600s timeout. `make up`
# previously started anyway and simply stalled.
#
# Decision table (when HF_HUB_OFFLINE is not already 1):
#
#   egress reachable                 -> 0  (online, unchanged)
#   no egress + all caches populated -> 1  (auto offline; the stack can run)
#   no egress + caches cold          -> exit 3 (fail fast with remediation)
#
# HF_HUB_OFFLINE=1 is always honoured untouched: forcing offline is a
# deliberate choice and this script never overrides it.
#
# Set HF_AUTO_OFFLINE=false to disable both the auto-switch and the fail-fast
# and restore the previous warn-and-continue behaviour.
#
# Writes the resolved value ("0" or "1") to stdout. All diagnostics go to
# stderr so the caller can safely do VALUE=$(resolve-hf-offline.sh).
#
# Exit codes: 0 resolved, 3 blocked (no egress, cold cache).

set -u

say() { printf '%s\n' "$*" >&2; }

HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-0}"
HF_AUTO_OFFLINE="${HF_AUTO_OFFLINE:-true}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-smart-kiosk-assistant}"

# An explicit offline request always wins; check-env already reports whether
# the caches can actually satisfy it.
if [ "$HF_HUB_OFFLINE" = "1" ]; then
    printf '1\n'
    exit 0
fi

if [ "$HF_AUTO_OFFLINE" = "false" ] || [ "$HF_AUTO_OFFLINE" = "FALSE" ]; then
    printf '%s\n' "$HF_HUB_OFFLINE"
    exit 0
fi

# Probe from inside a container, not the host: the host may have egress (or a
# proxy in the shell) that the containers do not. Fall back to the host only
# when no small local image is available.
# Any local image with a shell works. Prefer a tiny one, but fall back to the
# stack's own images rather than giving up: without a probe image we can
# neither test egress the way a container sees it nor inspect the caches.
PROBE_IMG=""
for I in alpine:latest busybox:latest alpine busybox \
         "${REGISTRY_REPO:-intel}/kiosk-core:${RELEASE_TAG:-latest}" \
         "${REGISTRY_REPO:-intel}/rag-service:${RELEASE_TAG:-latest}" \
         "${REGISTRY_REPO:-intel}/audio-analyzer:${RELEASE_TAG:-latest}"; do
    if docker image inspect "$I" >/dev/null 2>&1; then PROBE_IMG="$I"; break; fi
done

net_ok=""
probe_reason=""
probe_inconclusive=""
if [ -n "$PROBE_IMG" ]; then
    # Pass the proxy through exactly as docker-compose.yml does, so the probe
    # tests the same path the services will take.
    if probe_out=$(docker run --rm \
        ${HTTP_PROXY:+-e HTTP_PROXY="$HTTP_PROXY"} \
        ${http_proxy:+-e http_proxy="$http_proxy"} \
        ${HTTPS_PROXY:+-e HTTPS_PROXY="$HTTPS_PROXY"} \
        ${https_proxy:+-e https_proxy="$https_proxy"} \
        "$PROBE_IMG" \
        sh -c 'wget -q -T 6 --spider https://huggingface.co 2>&1' 2>&1); then
        net_ok=1
    else
        probe_reason=$(printf '%s' "$probe_out" | tr '\n' ' ' | sed 's/  */ /g')
        case "$probe_reason" in
            *40[37]*|*"Forbidden"*|*"Proxy Authentication"*)
                probe_reason="the proxy refused the request (${probe_reason}) -- huggingface.co is blocked by your proxy, not merely unroutable" ;;
            "") probe_reason="no response (connection timed out or DNS failed)" ;;
        esac
    fi
elif curl -fsS --connect-timeout 3 --max-time 6 -o /dev/null https://huggingface.co 2>/dev/null; then
    # --fail: without it curl exits 0 on an HTTP 403 from a filtering proxy,
    # which would select online mode for a Hub we cannot actually read.
    net_ok=1
    probe_inconclusive=1
else
    probe_reason="probed from the host, not a container (no local image to probe with)"
    probe_inconclusive=1
fi

if [ -n "$net_ok" ]; then
    printf '0\n'
    exit 0
fi

# No egress confirmed. Decide between auto-offline and fail-fast on cache
# contents -- but only if we were able to look properly.
#
# `find -L` follows the snapshot symlinks into blobs/, so an interrupted
# download (a dangling symlink, or a *.incomplete blob) is skipped rather than
# counted. The size floor rejects an empty models--*/ directory and truncated
# files: a real ASR/TTS/LLM weight file is tens of MB at minimum, so 1 MiB is
# far below any true positive while excluding configs and tokenizer JSON.
cache_warm=0
cache_checked=0
if [ -n "$PROBE_IMG" ]; then
    for V in audio_analyzer_cache text_to_speech_cache rag_service_hf_cache; do
        VOL="${COMPOSE_PROJECT}_${V}"
        docker volume inspect "$VOL" >/dev/null 2>&1 || continue
        cache_checked=$((cache_checked + 1))
        if docker run --rm -v "$VOL":/c:ro "$PROBE_IMG" \
            sh -c 'find -L /c -maxdepth 8 -type f \
                     \( -name "*.safetensors" -o -name "*.bin" -o -name "*.onnx" \
                        -o -name "*.pt" -o -name "*.pth" -o -name "*.ckpt" \) \
                     ! -name "*.incomplete" -size +1024k -print -quit 2>/dev/null | grep -q .' \
            >/dev/null 2>&1; then
            cache_warm=$((cache_warm + 1))
        fi
    done
fi

if [ "$cache_warm" -ge 3 ]; then
    say ""
    say "[hf] huggingface.co is unreachable from a container:"
    say "[hf]   ${probe_reason}"
    say "[hf] All 3 model caches hold real weight files, so starting with"
    say "[hf] HF_HUB_OFFLINE=1 -- the services load from cache instead of"
    say "[hf] stalling on a live Hub call."
    say "[hf] Set HF_AUTO_OFFLINE=false to disable this."
    say ""
    printf '1\n'
    exit 0
fi

# Never block on a verdict we could not actually establish. Without a probe
# image we can inspect neither egress-as-a-container-sees-it nor the caches,
# and a host-only curl says nothing about what the containers can reach
# through Docker's proxies.default. Warn and let the run proceed.
if [ -n "$probe_inconclusive" ] || [ -z "$PROBE_IMG" ]; then
    say ""
    say "[hf] Could not verify Hub reachability or the model caches:"
    say "[hf]   ${probe_reason:-no container image available to probe with}"
    say "[hf] Continuing with HF_HUB_OFFLINE=${HF_HUB_OFFLINE} rather than"
    say "[hf] blocking on an unverified verdict. If startup then hangs, this"
    say "[hf] is why -- see docs/user-guide/troubleshooting.md."
    say ""
    printf '%s\n' "$HF_HUB_OFFLINE"
    exit 0
fi

say ""
say "✗ Cannot start: huggingface.co is unreachable from a container and the"
if [ "$cache_checked" -eq 0 ]; then
    say "  model caches do not exist yet (nothing has been downloaded on this host)."
else
    say "  model caches are not usable: only ${cache_warm} of ${cache_checked} hold real weight files."
fi
say ""
say "  Probe result: ${probe_reason}"
say ""
say "  audio-analyzer and text-to-speech download their models in-container on"
say "  first run. Without egress they raise httpx.ConnectError during startup,"
say "  never become healthy, and every dependent service aborts after the full"
say "  600s timeout. Refusing to start rather than stall (ITEP-97604)."
say ""
say "  Fix one of these, then re-run:"
say ""
say "    1. Proxy -- export it (both cases are mirrored for you by make):"
say "         export HTTP_PROXY=http://proxy.example.com:3128"
say "         export HTTPS_PROXY=http://proxy.example.com:3128"
say "       or put HTTP_PROXY/HTTPS_PROXY in .env, or configure"
say "       proxies.default in ~/.docker/config.json."
say "       Use an address routable from inside a container -- not 127.0.0.1."
say ""
say "    2. Warm the cache on a connected host, copy the volumes over, then"
say "       set HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 in .env."
say ""
say "    3. Override deliberately (it will likely stall):"
say "         make up HF_AUTO_OFFLINE=false"
say ""
exit 3
