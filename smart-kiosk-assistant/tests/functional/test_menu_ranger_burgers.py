"""
Tier 1 — Ranger Burgers opt-in menu consistency
================================================
The Ranger Burgers menu in configs/menus/ranger-burgers/ is selected with
KIOSK_MENU_DIR. These checks keep its files consistent with each other and
with the default config folder. No Docker, no ML models.

Run:
    pytest tests/functional/test_menu_ranger_burgers.py -m tier1 -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

_KIOSK_ROOT = Path(__file__).resolve().parents[2]
_MENU = _KIOSK_ROOT / "configs" / "menus" / "ranger-burgers"
_PRODUCTS = _MENU / "ordering" / "products.yaml"
_UPSELL = _MENU / "ordering" / "upsell_rules.yaml"
_KB = _KIOSK_ROOT / "knowledge-base-samples" / "RangerBurgers-QSR-menu.md"
_INTENTS = _KIOSK_ROOT / "Sample_data" / "ranger-burgers" / "na_intents.jsonl"

# Every file rag-service reads from its domain-config mount must exist in the
# menu folder too, because KIOSK_MENU_DIR replaces the whole mount.
_RAG_FILES = (
    "agent_profile.yaml",
    "intent_rules.yaml",
    "reply_templates.yaml",
    "guard_rules.json",
)


def _products() -> list[dict]:
    return yaml.safe_load(_PRODUCTS.read_text(encoding="utf-8"))["products"]


@pytest.mark.tier1
def test_menu_folder_has_every_mounted_file():
    for name in ("products.yaml", "upsell_rules.yaml"):
        assert (_MENU / "ordering" / name).is_file(), f"missing ordering/{name}"
    for name in _RAG_FILES:
        assert (_MENU / "rag-service" / name).is_file(), f"missing rag-service/{name}"
    default_rag = {p.name for p in (_KIOSK_ROOT / "configs" / "rag-service").iterdir()}
    assert default_rag <= set(_RAG_FILES), (
        f"configs/rag-service has files the menu folder lacks: {default_rag - set(_RAG_FILES)}"
    )


@pytest.mark.tier1
def test_guard_rules_match_default():
    """guard_rules.json has no menu content; the copy must not drift."""
    default = json.loads((_KIOSK_ROOT / "configs" / "rag-service" / "guard_rules.json").read_text())
    menu = json.loads((_MENU / "rag-service" / "guard_rules.json").read_text())
    assert menu == default


@pytest.mark.tier1
def test_products_unique_and_priced():
    products = _products()
    ids = [p["product_id"] for p in products]
    names = [p["name"] for p in products]
    assert len(ids) == len(set(ids)), "duplicate product_id"
    assert len(names) == len(set(names)), "duplicate product name"
    assert all(float(p["price"]) > 0 for p in products)


@pytest.mark.tier1
def test_upsell_ids_exist():
    ids = {p["product_id"] for p in _products()}
    categories = {p["category"] for p in _products()}
    rules = yaml.safe_load(_UPSELL.read_text(encoding="utf-8"))["rules"]
    for i, rule in enumerate(rules):
        for pid in (rule.get("trigger_product_ids") or []) + rule["suggest_product_ids"]:
            assert pid in ids, f"rule #{i}: unknown product_id {pid}"
        for cat in rule.get("trigger_categories") or []:
            assert cat in categories, f"rule #{i}: unknown category {cat}"


@pytest.mark.tier1
def test_every_product_is_in_knowledge_base():
    kb = _KB.read_text(encoding="utf-8")
    missing = [p["name"] for p in _products() if f"**{p['name']}**" not in kb]
    assert not missing, f"products missing from {_KB.name}: {missing}"


@pytest.mark.tier1
def test_intent_cart_names_exist_in_products():
    names = {p["name"] for p in _products()}
    bad = []
    for line in _INTENTS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for field in ("seed", "expect_cart"):
            bad += [(row["id"], n) for n in row.get(field, {}) if n not in names]
    assert not bad, f"cart names not in products.yaml: {bad[:10]}"
