"""QSR agent contract for the kiosk.

The Central QSR Agent's built-in ``kiosk`` capability reads
``get_kiosk_context`` and, after an operator approves a proposal, calls
``change_menu_items`` or ``update_kiosk_settings``. These tools map that
contract onto this kiosk's real state:

* menu: the ordering catalogue (``products`` table), via ``menu.update_item``
  and the same policy gate as ``update_menu_item``;
* queue: queue-service, with an estimated wait from the active kiosks;
* settings: express mode is the simplified menu board; ``upsell_enabled``
  switches the ordering upsell engine; ``active_kiosks`` is recorded for the
  store's kiosk count.
"""
from __future__ import annotations

import logging
import math
import os
import sqlite3
from datetime import datetime, timezone
from types import ModuleType
from typing import Annotated, Any, Literal, Optional, TypedDict

from pydantic import Field

from kiosk_core import config as cfg
from kiosk_core.qsr_mcp import board_state, menu

logger = logging.getLogger(__name__)

KIOSK_MODES = {"standard": "full", "express": "simplified"}
SETTINGS_TOOL = "update_kiosk_settings"


class MenuChange(TypedDict):
    item_id: Annotated[str, Field(min_length=1, description="product_id from get_kiosk_context menu.items[].id")]
    available: bool
    reason: Annotated[str, Field(min_length=1)]


def settings() -> dict[str, Any]:
    """Current kiosk operating settings, with configured defaults."""
    state = board_state.get()
    return {
        "kiosk_mode": "express" if state.get("mode") == "simplified" else "standard",
        "active_kiosks": state.get("active_kiosks", cfg.QSR_ACTIVE_KIOSKS),
        "upsell_enabled": state.get("upsell_enabled", True),
    }


def upsell_enabled() -> bool:
    return bool(board_state.get().get("upsell_enabled", True))


def estimated_wait_minutes(queue_count: Any) -> Optional[int]:
    if isinstance(queue_count, bool) or not isinstance(queue_count, int) or queue_count < 0:
        return None
    active = max(1, int(settings()["active_kiosks"]))
    return math.ceil(queue_count * cfg.QSR_MINUTES_PER_ORDER / active)


def _catalogue() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Menu items and the last 15 minutes of confirmed orders."""
    if not os.path.exists(cfg.KIOSK_DB_PATH):
        return [], {"orders_last_15_minutes": 0, "top_item": None}
    conn = sqlite3.connect(cfg.KIOSK_DB_PATH, timeout=5.0)
    try:
        conn.row_factory = sqlite3.Row
        items = [
            {"id": row["product_id"], "name": row["name"], "category": row["category"],
             "price": row["price"], "available": bool(row["is_available"])}
            for row in conn.execute(
                "SELECT product_id, name, category, price, is_available FROM products "
                "ORDER BY category, name")
        ]
        recent = "o.status = 'confirmed' AND o.created_at >= datetime('now', '-15 minutes')"
        orders = conn.execute(f"SELECT COUNT(*) FROM orders o WHERE {recent}").fetchone()[0]
        top = conn.execute(
            "SELECT COALESCE(p.name, oi.product_id) FROM order_items oi "
            "JOIN orders o ON o.order_id = oi.order_id "
            "LEFT JOIN products p ON p.product_id = oi.product_id "
            f"WHERE {recent} GROUP BY oi.product_id ORDER BY SUM(oi.quantity) DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    return items, {"orders_last_15_minutes": orders, "top_item": top[0] if top else None}


def kiosk_context(service: ModuleType) -> dict[str, Any]:
    client = service.get_queue_client()
    snapshot = client.get_queue_snapshot() if client is not None else None
    count = snapshot.get("count") if snapshot else None
    items, activity = _catalogue()
    current = settings()
    return {
        "schema_version": "1.0",
        "source": service.SERVICE_NAME,
        "restaurant": {"id": cfg.QSR_AUTONOMY_STORE_ID,
                       **({"name": cfg.QSR_RESTAURANT_NAME} if cfg.QSR_RESTAURANT_NAME else {})},
        "operations": {
            "status": "open",
            "queue_available": snapshot is not None,
            "queue_count": count,
            "queue_status": snapshot.get("status") if snapshot else None,
            "people_nearby": snapshot.get("nearby") if snapshot else None,
            "estimated_wait_minutes": estimated_wait_minutes(count),
            "max_kiosks": cfg.QSR_MAX_KIOSKS,
            **current,
            "baseline_settings": {"kiosk_mode": "standard", "active_kiosks": cfg.QSR_ACTIVE_KIOSKS,
                                  "upsell_enabled": True},
        },
        "menu": {"items": items},
        "recent_activity": activity,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def register(service: ModuleType) -> None:
    """Add the agent contract tools to ``service.mcp`` (the QSR MCP surface)."""
    mcp = service.mcp
    service._READ_TOOLS["get_kiosk_context"] = {
        "description": "QSR agent context: restaurant, menu, queue, wait, kiosk settings, recent orders",
        "schema": {},
    }
    service._ACT_TOOLS["change_menu_items"] = {
        "description": "Apply up to three menu availability changes",
        "schema": {"changes": "list[{item_id, available, reason}]", "reason": "str"},
        "gate": "same as update_menu_item",
    }
    service._ACT_TOOLS[SETTINGS_TOOL] = {
        "description": "Change kiosk mode (standard|express), active kiosks, upsell prompts",
        "schema": {"reason": "str", "mode": "str|None", "active_kiosks": "int|None", "upsell_enabled": "bool|None"},
        "gate": "automatic",
    }

    @mcp.tool(
        name="get_kiosk_context",
        description=(
            "Snapshot for the QSR agent: restaurant identity, menu items with availability, queue "
            "depth and estimated wait, kiosk settings (mode, active kiosks, upsell), and orders in "
            "the last 15 minutes."
        ),
    )
    def get_kiosk_context() -> dict[str, Any]:
        service._ensure_init()
        return kiosk_context(service)

    @mcp.tool(
        name="change_menu_items",
        description=(
            "Apply one approved bundle of up to three menu availability changes. item_id is the "
            "product id from get_kiosk_context. Uses the same policy gate as update_menu_item."
        ),
    )
    def change_menu_items(
        changes: Annotated[list[MenuChange], Field(min_length=1, max_length=3)],
        reason: Annotated[str, Field(min_length=1)],
    ) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("reason is required")
        seen: set[str] = set()
        for change in changes:
            item = menu.get_item(change["item_id"])
            if item is None:
                raise ValueError(f"unknown menu item: {change['item_id']}")
            if change["item_id"] in seen:
                raise ValueError(f"duplicate menu item: {change['item_id']}")
            if item["is_available"] == change["available"]:
                raise ValueError(f"{change['item_id']} already has the requested availability")
            if not change["reason"].strip():
                raise ValueError("each menu change needs a reason")
            seen.add(change["item_id"])
        results = [
            service._gated_menu_call(
                "update_menu_item", {"product_id": change["item_id"], "is_available": change["available"]},
                f"{change['reason'].strip()} ({reason.strip()})", service._update_menu_item_impl)
            for change in changes
        ]
        return {"executed": all(result.get("executed") for result in results),
                "changes": changes, "reason": reason.strip(), "results": results}

    @mcp.tool(
        name=SETTINGS_TOOL,
        description=(
            "Apply one approved bundle of kiosk operating settings: mode (standard, or express = "
            "simplified menu board), number of active kiosks, and upsell prompts. Only the supplied "
            "fields change."
        ),
    )
    def update_kiosk_settings(
        reason: Annotated[str, Field(min_length=1)],
        mode: Optional[Literal["standard", "express"]] = None,
        active_kiosks: Optional[Annotated[int, Field(ge=1, le=cfg.QSR_MAX_KIOSKS)]] = None,
        upsell_enabled: Optional[bool] = None,
    ) -> dict[str, Any]:
        reason = reason.strip()
        if not reason:
            raise ValueError("reason is required")
        requested = {key: value for key, value in (
            ("kiosk_mode", mode), ("active_kiosks", active_kiosks), ("upsell_enabled", upsell_enabled))
            if value is not None}
        if not requested:
            raise ValueError("at least one of mode, active_kiosks or upsell_enabled is required")
        service._ensure_init()
        decision = service._policy.evaluate(SETTINGS_TOOL, {**requested, "reason": reason})
        if not decision.allowed:
            return {"executed": False, "level": decision.level.value, "reason": decision.reason}
        if mode is not None and mode != settings()["kiosk_mode"]:
            service._set_board_mode_impl(KIOSK_MODES[mode], reason)
        stored = {key: value for key, value in requested.items() if key != "kiosk_mode"}
        if stored:
            board_state.update_settings(reason, **stored)
        if service.MCP_SERVICE_ENABLED:
            try:
                service.emit("kiosk_settings_changed", {"changes": requested, "reason": reason})
            except Exception:
                logger.exception("[QSR-MCP] Failed to emit kiosk_settings_changed")
        return {"executed": True, "level": decision.level.value, "changes": requested,
                "reason": reason, "settings": settings()}
