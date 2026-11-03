"""Tests for the QSR agent contract tools (kiosk_core/qsr_mcp/agent_tools.py).

The Central QSR Agent reads ``get_kiosk_context`` and calls
``change_menu_items`` / ``update_kiosk_settings`` after an operator approves.
These run over the real MCP surface so the input schemas the agent validates
against are exercised too.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import time
from datetime import datetime, timezone

import pytest

from kiosk_core.ordering.models import Product, UpsellRequest


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def kiosk(monkeypatch, tmp_path):
    monkeypatch.setenv("KIOSK_CORE_QSR_MCP_ENABLED", "true")
    monkeypatch.setenv("KIOSK_CORE_QSR_MCP_LOG_BACKEND", "memory")
    monkeypatch.setenv("KIOSK_CORE_QUEUE_SERVICE_ENABLED", "false")
    monkeypatch.setenv("KIOSK_CORE_DB_PATH", str(tmp_path / "kiosk.db"))
    monkeypatch.setenv("KIOSK_CORE_QSR_MENU_REQUESTS_PATH", str(tmp_path / "menu_requests.json"))
    monkeypatch.setenv("KIOSK_CORE_QSR_MCP_BOARD_STATE_PATH", str(tmp_path / "board.json"))
    monkeypatch.setenv("KIOSK_CORE_QSR_AUTONOMY_EVENTS_URL", "")

    import kiosk_core.config as cfg_module
    importlib.reload(cfg_module)
    import kiosk_core.ordering.db as db_module
    importlib.reload(db_module)
    import kiosk_core.qsr_mcp.menu as menu_module
    importlib.reload(menu_module)
    import kiosk_core.qsr_mcp.menu_requests as requests_module
    importlib.reload(requests_module)
    import kiosk_core.qsr_mcp.board_state as board_module
    importlib.reload(board_module)
    import kiosk_core.qsr_mcp.mcp_service as mcp_service
    importlib.reload(mcp_service)
    mcp_service.init(force=True)

    from kiosk_core.ordering.repository import SqliteProductRepository

    async def setup():
        await db_module.init_db()
        async with db_module.get_db() as db:
            repo = SqliteProductRepository(db)
            await repo.seed_upsert(Product(product_id="P1", name="Veg Burger", category="burgers", price=100.0))
            await repo.seed_upsert(Product(product_id="P2", name="Cola", category="beverages", price=50.0))
            await repo.seed_upsert(Product(product_id="P3", name="Fries", category="sides", price=60.0))
            await db.commit()

    _run(setup())
    yield mcp_service
    mcp_service.init(force=True)


def call(service, name, arguments=None):
    from fastmcp import Client

    async def go():
        async with Client(service.mcp) as client:
            return await client.call_tool(name, arguments or {}, raise_on_error=False)

    result = _run(go())
    if result.is_error:
        raise ValueError(result.content[0].text)
    return result.data if result.data is not None else json.loads(result.content[0].text)


def test_context_has_the_shape_the_agent_validates(kiosk):
    context = call(kiosk, "get_kiosk_context")
    assert context["restaurant"]["id"] == "qsr-001"
    assert datetime.fromisoformat(context["observed_at"]).tzinfo is not None
    assert {item["id"]: item["available"] for item in context["menu"]["items"]} == {
        "P1": True, "P2": True, "P3": True}
    operations = context["operations"]
    assert (operations["kiosk_mode"], operations["active_kiosks"], operations["max_kiosks"],
            operations["upsell_enabled"]) == ("standard", 3, 4, True)
    assert operations["queue_available"] is False and operations["queue_count"] is None
    assert context["recent_activity"] == {"orders_last_15_minutes": 0, "top_item": None}


def test_change_menu_items_applies_a_bundle_and_rejects_bad_ones(kiosk):
    result = call(kiosk, "change_menu_items", {
        "changes": [{"item_id": "P2", "available": False, "reason": "out of cola"},
                    {"item_id": "P3", "available": False, "reason": "fryer down"}],
        "reason": "stock-out"})
    assert result["executed"] is True
    items = {item["id"]: item["available"] for item in call(kiosk, "get_kiosk_context")["menu"]["items"]}
    assert items == {"P1": True, "P2": False, "P3": False}
    for bad in (
        {"changes": [{"item_id": "P2", "available": False, "reason": "again"}], "reason": "x"},  # no-op
        {"changes": [{"item_id": "NOPE", "available": True, "reason": "x"}], "reason": "x"},
        {"changes": [], "reason": "x"},  # schema: 1..3 items
        {"changes": [{"item_id": "P1", "available": False}], "reason": "x"},  # schema: reason required
    ):
        with pytest.raises(ValueError):
            call(kiosk, "change_menu_items", bad)
    items = {item["id"]: item["available"] for item in call(kiosk, "get_kiosk_context")["menu"]["items"]}
    assert items == {"P1": True, "P2": False, "P3": False}


def test_update_kiosk_settings_switches_board_upsell_and_wait(kiosk):
    from kiosk_core.ordering.service import OrderingService
    from kiosk_core.qsr_mcp import agent_tools, board_state

    ordering = OrderingService("configs/ordering/upsell_rules.yaml")
    result = call(kiosk, "update_kiosk_settings",
                  {"mode": "express", "active_kiosks": 4, "upsell_enabled": False, "reason": "lunch rush"})
    assert result["executed"] is True
    assert result["settings"] == {"kiosk_mode": "express", "active_kiosks": 4, "upsell_enabled": False}
    assert board_state.get()["mode"] == "simplified"
    assert _run(ordering.get_upsell_suggestions(UpsellRequest(product_ids=["P1"]))) == []
    assert agent_tools.estimated_wait_minutes(10) == 5  # 10 people x 2 min / 4 kiosks
    operations = call(kiosk, "get_kiosk_context")["operations"]
    assert (operations["kiosk_mode"], operations["active_kiosks"], operations["upsell_enabled"]) == (
        "express", 4, False)

    call(kiosk, "update_kiosk_settings", {"mode": "standard", "upsell_enabled": True, "reason": "quiet"})
    assert board_state.get()["mode"] == "full" and agent_tools.upsell_enabled() is True
    for bad in ({"reason": "nothing to change"}, {"mode": "turbo", "reason": "x"},
                {"active_kiosks": 9, "reason": "x"}):
        with pytest.raises(ValueError):
            call(kiosk, "update_kiosk_settings", bad)
    changed = [e for e in kiosk._log.read(limit=100) if e.event_type == "kiosk_settings_changed"]
    assert len(changed) == 2


def test_queue_events_carry_service_previous_count_and_wait():
    from kiosk_core.qsr_mcp.autonomy import AutonomyEventSink
    from kiosk_core.qsr_mcp.event_log import new_event

    sent = []
    sink = AutonomyEventSink("http://agent/autonomy/events", store_id="qsr-001",
                             post_json=lambda url, body, headers, timeout: sent.append(json.loads(body)) or 202)
    for count in (3, 8):
        event = new_event("queue_depth_sample", "smart_kiosk", "store-001",
                          {"count": count, "nearby": 0, "status": "LOW", "estimated_wait_minutes": count})
        assert sink.accepts(event)
        sink.push(event)
    assert [body["service"] for body in sent] == ["kiosk", "kiosk"]
    assert "previous_queue_count" not in sent[0]["data"]
    assert (sent[1]["data"]["queue_count"], sent[1]["data"]["previous_queue_count"],
            sent[1]["data"]["estimated_wait_minutes"]) == (8, 3, 8)
    assert datetime.fromisoformat(sent[1]["occurred_at"]).tzinfo == timezone.utc


def test_bundle_at_the_rate_limit_boundary_applies_nothing(kiosk):
    spec = kiosk._policy._actions["update_menu_item"]
    spec.max_calls = 3
    spec._calls.extend([time.monotonic()] * 2)  # one call left, bundle needs two
    result = call(kiosk, "change_menu_items", {
        "changes": [{"item_id": "P2", "available": False, "reason": "out of cola"},
                    {"item_id": "P3", "available": False, "reason": "fryer down"}],
        "reason": "stock-out"})
    assert result["executed"] is False and result["reason"] == "rate limit exceeded"
    items = {item["id"]: item["available"] for item in call(kiosk, "get_kiosk_context")["menu"]["items"]}
    assert items == {"P1": True, "P2": True, "P3": True}
    spec._calls.clear()  # the same bundle goes through once there is room
    assert call(kiosk, "change_menu_items", {
        "changes": [{"item_id": "P2", "available": False, "reason": "out of cola"},
                    {"item_id": "P3", "available": False, "reason": "fryer down"}],
        "reason": "stock-out"})["executed"] is True


def test_upsell_setting_written_by_another_process_is_picked_up(kiosk, tmp_path):
    from kiosk_core.qsr_mcp import agent_tools, board_state

    path = tmp_path / "board.json"
    assert agent_tools.upsell_enabled() is True
    state = json.loads(path.read_text()) if path.exists() else {"mode": "full"}
    state["upsell_enabled"] = False
    path.write_text(json.dumps(state))  # written by the standalone MCP process
    os.utime(path, ns=(time.time_ns() + 10**9,) * 2)
    assert agent_tools.upsell_enabled() is False
    assert board_state.get()["upsell_enabled"] is False
