"""Outbound autonomy-event delivery to the Central QSR Agent.

Pushes kiosk observations to the agent's ``POST /autonomy/events`` inbox using
the same envelope as the QSR weather service and Order Accuracy
(intel-retail/order-accuracy#214)::

    {"event_id", "event_type", "store_id", "occurred_at", "data"}

This is the inverse direction of the MCP read tools in ``mcp_service.py``: the
agent *pulls* state over MCP at :8014, while this module *pushes* events so
Hermes can select a skill and propose an action without polling us.

Two kiosk observations are forwarded:

* ``queue_depth_sample`` -> ``queue_count_changed`` — the event type the
  agent's ``event-menu-decisions`` skill consumes. Its policy validates
  ``data.queue_count`` as a non-negative, non-boolean ``int``.
* ``board_mode_changed`` — forwarded under its own name; the agent's event
  agent accepts unregistered event names through its wildcard policy and will
  return a no-action explanation if no skill matches.

The agent's service-owner guide states that "the event producer owns change
detection and delivery", so ``AutonomyEventSink`` decides which queue samples
are worth an agent decision — see ``accepts``. A live camera count jitters by
one or two people from frame to frame; every forwarded sample costs the agent a
model run and the operator a review, so only a lasting change of the queue depth
(the median of recent polls) is sent, plus one confirmation after each change.
"""
from __future__ import annotations

import http.client
import json
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from kiosk_core.qsr_mcp.event_log import EventEnvelope

logger = logging.getLogger(__name__)

# Returns the HTTP status code; raises OSError subclasses on transport failure.
PostJson = Callable[[str, bytes, dict[str, str], float], int]


def _post_json(url: str, body: bytes, headers: dict[str, str], timeout: float) -> int:
    """POST ``body`` and return the HTTP status code.

    Redirects are deliberately not followed: a 3xx would otherwise silently
    re-POST the payload — including the bearer token — to another host.
    """
    import urllib.error
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


class PermanentDeliveryError(Exception):
    """Delivery failed and retrying the same request cannot help."""


class AutonomyEventSink:
    """POSTs kiosk events to the QSR Agent's ``/autonomy/events`` webhook.

    Args:
        url: Full agent inbox URL, e.g. ``http://qsr-agent:8600/autonomy/events``.
        store_id: Must equal the agent's ``QSR_RESTAURANT_ID``.
        token: Optional bearer token sent as an ``Authorization`` header.
        event_types: Internal event types eligible for forwarding.
        queue_min_delta: Minimum change of the smoothed queue depth before a
            new ``queue_count_changed`` event is sent.
        queue_smoothing_samples: Polls whose median is the queue depth, so a
            miscounted frame or a person walking past does not count as a
            change. The forwarded sample is the latest one at the median.
        queue_min_interval_s: Minimum seconds between two queue events.
        queue_confirm_s: After a change, resend the queue depth once after
            this many seconds without another event, so the agent sees
            whether the change lasted (a long queue that persists, or a
            recovery that holds). ``0`` disables confirmations.
        timeout_s: Per-attempt HTTP timeout in seconds.
        post_json: Injected HTTP poster; overridden in tests.
    """

    name = "autonomy"

    # Internal event name -> the name the QSR agent's skills document.
    EVENT_TYPE_MAP = {
        "queue_depth_sample": "queue_count_changed",
        "board_mode_changed": "board_mode_changed",
    }

    def __init__(
        self,
        url: str,
        store_id: str,
        token: str | None = None,
        event_types: tuple[str, ...] = ("queue_depth_sample", "board_mode_changed"),
        queue_min_delta: int = 1,
        queue_smoothing_samples: int = 1,
        queue_min_interval_s: float = 0.0,
        queue_confirm_s: float = 0.0,
        timeout_s: float = 5.0,
        post_json: PostJson = _post_json,
    ) -> None:
        self._url = url
        self._store_id = store_id
        self._token = token
        self._event_types = frozenset(event_types)
        self._queue_min_delta = max(1, queue_min_delta)
        self._queue_window: deque[tuple[int, dict[str, Any]]] = deque(maxlen=max(1, queue_smoothing_samples))
        self._queue_min_interval_ms = max(0.0, queue_min_interval_s) * 1000
        self._queue_confirm_ms = max(0.0, queue_confirm_s) * 1000
        self._timeout_s = timeout_s
        self._post_json = post_json
        self._lock = threading.Lock()
        self._last_queue_count: int | None = None
        self._last_queue_sent_ms = 0
        self._confirm_pending = False
        # Per accepted sample, by ref_id (retries rebuild the event): the
        # count sent before it, and the window sample forwarded in its place.
        self._previous_counts: dict[str, int | None] = {}
        self._forwarded: dict[str, dict[str, Any]] = {}

    def restore_queue_state(self, count: Any, ts_ms: int) -> None:
        """Resume from the last logged sample after a restart.

        Without this, the first sample after every restart is sent as a new
        event with no ``previous_queue_count``.
        """
        count = _coerce_queue_count(count)
        if count is None:
            return
        with self._lock:
            self._last_queue_count = count
            self._last_queue_sent_ms = ts_ms

    # -- eligibility --------------------------------------------------------

    def accepts(self, event: EventEnvelope) -> bool:
        """Decide whether this event should reach the agent.

        Applies the configured event-type filter and, for queue samples, the
        producer-side change detection the agent's contract requires: the
        poller samples on a fixed interval, but ``queue_count_changed`` must
        only fire when the depth moved in a way worth a decision. Time is
        taken from the samples, not the wall clock.
        """
        if event.event_type not in self._event_types:
            return False
        if event.event_type != "queue_depth_sample":
            return True

        count = _coerce_queue_count(event.payload.get("count"))
        if count is None:
            # queue-service returned no usable count; nothing to assert.
            return False
        with self._lock:
            window = self._queue_window
            window.append((count, event.payload))
            if len(window) < window.maxlen:
                return False
            median = sorted(c for c, _ in window)[(len(window) - 1) // 2]
            if not self._queue_sample_is_due(median, event.ts_ms):
                return False
            self._previous_counts[event.ref_id] = self._last_queue_count
            self._forwarded[event.ref_id] = next(p for c, p in reversed(window) if c == median)
            self._last_queue_count = median
            self._last_queue_sent_ms = event.ts_ms
            for kept in (self._previous_counts, self._forwarded):
                while len(kept) > 256:
                    kept.pop(next(iter(kept)))
        return True

    def _queue_sample_is_due(self, count: int, now: int) -> bool:
        """Whether the smoothed depth is sent now. Caller holds ``self._lock``."""
        previous = self._last_queue_count
        if previous is None:
            return True
        elapsed = now - self._last_queue_sent_ms
        if elapsed < self._queue_min_interval_ms:
            return False
        if abs(count - previous) >= self._queue_min_delta:
            self._confirm_pending = bool(self._queue_confirm_ms)
            return True
        if self._confirm_pending and elapsed >= self._queue_confirm_ms:
            self._confirm_pending = False
            return True
        return False

    # -- envelope -----------------------------------------------------------

    def build_event(self, event: EventEnvelope) -> dict[str, Any]:
        """Translate an internal envelope into the agent's event contract."""
        with self._lock:
            forwarded = self._forwarded.get(event.ref_id, event.payload)
            previous = self._previous_counts.get(event.ref_id)
        payload = dict(forwarded)
        occurred_at = datetime.fromtimestamp(
            event.ts_ms / 1000, tz=timezone.utc
        ).isoformat(timespec="milliseconds")
        data: dict[str, Any] = {
            **payload,
            "source": event.service,
            "source_event_type": event.event_type,
            "ref_id": event.ref_id,
        }
        if event.event_type == "queue_depth_sample":
            # The agent's HermesEventMenuPolicy rejects anything that is not a
            # non-negative, non-boolean int.
            data["queue_count"] = _coerce_queue_count(payload.get("count"))
            if previous is not None:
                data["previous_queue_count"] = previous
        return {
            # Stable across retries so the agent deduplicates redeliveries;
            # ref_id is unique per emitted event.
            "event_id": f"{event.service}-{event.event_type}-{event.ref_id}",
            "event_type": self.EVENT_TYPE_MAP.get(event.event_type, event.event_type),
            # The agent journals and learns per service; its kiosk capability is `kiosk`.
            "service": "kiosk",
            "store_id": self._store_id,
            "occurred_at": occurred_at,
            "data": data,
        }

    # -- delivery -----------------------------------------------------------

    def push(self, event: EventEnvelope) -> bool:
        """Deliver one event. Returns ``True`` when it need not be retried.

        Eligibility is **not** re-checked here — ``Delivery`` calls
        ``accepts`` once per event before its retry loop. Re-checking per
        attempt would make the stateful queue-change detection treat a retry
        of the same sample as "unchanged" and silently drop it.

        Raises:
            PermanentDeliveryError: The agent rejected the event with a 4xx
                other than 429, so retrying the identical body cannot help.
        """
        autonomy_event = self.build_event(event)
        body = json.dumps(autonomy_event).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            status = self._post_json(self._url, body, headers, self._timeout_s)
        except (OSError, http.client.HTTPException) as error:
            logger.warning(
                "[QSR-AUTONOMY] event %s delivery failed: %s",
                autonomy_event["event_id"],
                error,
            )
            return False
        if 200 <= status < 300:
            logger.info(
                "[QSR-AUTONOMY] event %s (%s) delivered: HTTP %s",
                autonomy_event["event_id"],
                autonomy_event["event_type"],
                status,
            )
            return True
        logger.warning(
            "[QSR-AUTONOMY] event %s rejected: HTTP %s",
            autonomy_event["event_id"],
            status,
        )
        if 400 <= status < 500 and status != 429:
            raise PermanentDeliveryError(
                f"autonomy webhook rejected event: HTTP {status}"
            )
        return False


def _coerce_queue_count(value: Any) -> int | None:
    """Return ``value`` as a non-negative int, or ``None`` if unusable.

    ``bool`` is excluded explicitly: it is an ``int`` subclass in Python but
    the agent's policy rejects it.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None
