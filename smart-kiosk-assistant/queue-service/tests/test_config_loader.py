"""Unit tests for config_loader.py -- path precedence and env overrides.

Covers the Copilot review fix for ITEP-95364: an explicit ``path`` argument
(e.g. from ``QueuePipeline(conf_dir=...)``) must take precedence over
``QUEUE_SERVICE_CONFIG_PATH``, while the env var must still redirect the
*default* path when no explicit path is supplied.
"""
from __future__ import annotations

import importlib
import os
import sys
import textwrap
from pathlib import Path

import pytest

CONFIG_LOADER_MODULE = "config_loader"


@pytest.fixture()
def config_loader(monkeypatch):
    """Import a fresh config_loader module with no QUEUE_SERVICE_* env vars set.

    The module-level ``config = load_config()`` at import time means a
    stale module (imported by an earlier test with different env vars)
    would poison other tests, so each test gets a clean re-import.
    """
    for key in list(os.environ):
        if key.startswith("QUEUE_SERVICE"):
            monkeypatch.delenv(key, raising=False)

    sys.modules.pop(CONFIG_LOADER_MODULE, None)
    module = importlib.import_module(CONFIG_LOADER_MODULE)
    yield module
    sys.modules.pop(CONFIG_LOADER_MODULE, None)


def _write_config(path: Path, device: str) -> None:
    path.write_text(
        textwrap.dedent(
            f"""\
            model:
              device: "{device}"
            """
        )
    )


def test_default_path_honors_config_path_env(tmp_path, monkeypatch, config_loader):
    """No explicit path -> QUEUE_SERVICE_CONFIG_PATH should redirect the load."""
    custom_config = tmp_path / "custom-queue-config.yaml"
    _write_config(custom_config, device="GPU")
    monkeypatch.setenv(config_loader.CONFIG_PATH_ENV, str(custom_config))

    result = config_loader.load_config_dict()

    assert result["model"]["device"] == "GPU"


def test_explicit_path_overrides_config_path_env(tmp_path, monkeypatch, config_loader):
    """An explicit path (e.g. from QueuePipeline(conf_dir=...)) must win over
    QUEUE_SERVICE_CONFIG_PATH, matching the Copilot review requirement."""
    explicit_config = tmp_path / "explicit-queue-config.yaml"
    _write_config(explicit_config, device="CPU")

    other_config = tmp_path / "other-queue-config.yaml"
    _write_config(other_config, device="GPU")
    monkeypatch.setenv(config_loader.CONFIG_PATH_ENV, str(other_config))

    result = config_loader.load_config_dict(str(explicit_config))

    assert result["model"]["device"] == "CPU"


def test_explicit_path_used_by_load_config_namespace_form(tmp_path, monkeypatch, config_loader):
    """load_config() (SimpleNamespace form) must behave consistently with
    load_config_dict() for the same explicit-path precedence rule."""
    explicit_config = tmp_path / "explicit-queue-config.yaml"
    _write_config(explicit_config, device="CPU")

    other_config = tmp_path / "other-queue-config.yaml"
    _write_config(other_config, device="GPU")
    monkeypatch.setenv(config_loader.CONFIG_PATH_ENV, str(other_config))

    result = config_loader.load_config(str(explicit_config))

    assert result.model.device == "CPU"


def test_queue_service_model_device_override_applies(tmp_path, monkeypatch, config_loader):
    """Normal QUEUE_SERVICE__MODEL__DEVICE override (the QUEUE_DEVICE path)
    must still work regardless of path precedence changes."""
    explicit_config = tmp_path / "queue-config.yaml"
    _write_config(explicit_config, device="CPU")
    monkeypatch.setenv("QUEUE_SERVICE__MODEL__DEVICE", "NPU")

    result = config_loader.load_config_dict(str(explicit_config))

    assert result["model"]["device"] == "NPU"


def test_queue_service_model_device_override_with_default_path(
    tmp_path, monkeypatch, config_loader
):
    """QUEUE_SERVICE_CONFIG_PATH (default-path redirection) and
    QUEUE_SERVICE__MODEL__DEVICE (value override) must compose correctly
    when used together, with no explicit path supplied."""
    custom_config = tmp_path / "custom-queue-config.yaml"
    _write_config(custom_config, device="CPU")
    monkeypatch.setenv(config_loader.CONFIG_PATH_ENV, str(custom_config))
    monkeypatch.setenv("QUEUE_SERVICE__MODEL__DEVICE", "NPU")

    result = config_loader.load_config_dict()

    assert result["model"]["device"] == "NPU"
