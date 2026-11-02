"""
Tier 1 — Repository & Project Structure Tests
==============================================
Covers:
  NEX-T24243  Verify repository clone
  NEX-T24244  Verify project structure

These tests assert that all expected files, directories, and configuration
artefacts are present in the checked-out repository.  They require no
running services, no Docker daemon, and no ML models.

Run:
    pytest tests/functional/test_structure.py -m tier1 -v
"""
from pathlib import Path

import pytest

# Resolve to smart-kiosk-assistant/ (two levels up from tests/functional/)
_KIOSK_ROOT = Path(__file__).resolve().parents[2]


class TestRepositoryClone:
    """NEX-T24243 — Verify repository clone."""

    @pytest.mark.tier1
    def test_readme_present(self):
        """README.md must exist at the project root."""
        assert (_KIOSK_ROOT / "README.md").is_file(), "README.md not found"

    @pytest.mark.tier1
    def test_dockerfile_present(self):
        """Dockerfile for kiosk-core must be present."""
        assert (_KIOSK_ROOT / "Dockerfile").is_file(), "Dockerfile not found"

    @pytest.mark.tier1
    def test_docker_compose_present(self):
        """docker-compose.yml must be present."""
        assert (_KIOSK_ROOT / "docker-compose.yml").is_file(), "docker-compose.yml not found"

    @pytest.mark.tier1
    def test_requirements_present(self):
        """requirements.txt must be present and non-empty."""
        req = _KIOSK_ROOT / "requirements.txt"
        assert req.is_file(), "requirements.txt not found"
        assert req.stat().st_size > 0, "requirements.txt is empty"

    @pytest.mark.tier1
    def test_main_entrypoint_present(self):
        """main.py (kiosk-core FastAPI entrypoint) must exist."""
        assert (_KIOSK_ROOT / "main.py").is_file(), "main.py not found"


class TestProjectStructure:
    """NEX-T24244 — Verify project structure."""

    @pytest.mark.tier1
    def test_kiosk_core_package_present(self):
        """kiosk_core/ Python package must exist."""
        assert (_KIOSK_ROOT / "kiosk_core").is_dir(), "kiosk_core/ directory not found"

    @pytest.mark.tier1
    def test_docs_directory_present(self):
        """docs/ directory must exist."""
        assert (_KIOSK_ROOT / "docs").is_dir(), "docs/ directory not found"

    @pytest.mark.tier1
    def test_rag_service_present(self):
        """rag-service/ directory must exist."""
        assert (_KIOSK_ROOT / "rag-service").is_dir(), "rag-service/ directory not found"

    @pytest.mark.tier1
    def test_configs_directory_present(self):
        """configs/ directory with per-service YAML overrides must exist."""
        assert (_KIOSK_ROOT / "configs").is_dir(), "configs/ directory not found"

    @pytest.mark.tier1
    def test_metrics_collector_not_vendored_locally(self):
        """kiosk_core/metrics-collector/ must NOT exist.

        The metrics-collector source moved to the edge-ai-suites repo
        (health-and-life-sciences-ai-suite/multi_modal_patient_monitoring/
        services/metrics-collector), shared with the multi-modal patient
        monitoring suite. kiosk-core now pulls the published
        intel/hl-ai-metrics-collector image (see docker-compose.yml) instead
        of vendoring/building the source locally.
        """
        assert not (_KIOSK_ROOT / "kiosk_core" / "metrics-collector").exists(), (
            "kiosk_core/metrics-collector/ should have been removed — "
            "metrics-collector is now pulled from the intel/hl-ai-metrics-collector "
            "image built from the edge-ai-suites repo, not built locally."
        )

    @pytest.mark.tier1
    def test_kiosk_core_service_module_present(self):
        """kiosk_core/service.py — core session orchestration — must exist."""
        assert (_KIOSK_ROOT / "kiosk_core" / "service.py").is_file(), (
            "kiosk_core/service.py not found"
        )

    @pytest.mark.tier1
    def test_kiosk_core_models_module_present(self):
        """kiosk_core/models.py — Pydantic request/response models — must exist."""
        assert (_KIOSK_ROOT / "kiosk_core" / "models.py").is_file(), (
            "kiosk_core/models.py not found"
        )

    @pytest.mark.tier1
    def test_kiosk_core_config_module_present(self):
        """kiosk_core/config.py — environment-driven configuration — must exist."""
        assert (_KIOSK_ROOT / "kiosk_core" / "config.py").is_file(), (
            "kiosk_core/config.py not found"
        )

    @pytest.mark.tier1
    def test_docker_compose_references_kiosk_core_service(self):
        """docker-compose.yml must declare a kiosk-core service."""
        import yaml  # pyyaml is in requirements.txt

        with open(_KIOSK_ROOT / "docker-compose.yml") as fh:
            compose = yaml.safe_load(fh)

        services = compose.get("services", {})
        assert "kiosk-core" in services, (
            f"kiosk-core service not found in docker-compose.yml; found: {list(services)}"
        )

    @pytest.mark.tier1
    def test_docker_compose_kiosk_core_exposes_port_8012(self):
        """kiosk-core service must expose port 8012 (the documented API port)."""
        import yaml

        with open(_KIOSK_ROOT / "docker-compose.yml") as fh:
            compose = yaml.safe_load(fh)

        ports = compose["services"]["kiosk-core"].get("ports", [])
        port_strings = [str(p) for p in ports]
        assert any("8012" in p for p in port_strings), (
            f"Port 8012 not exposed by kiosk-core in docker-compose.yml; ports: {port_strings}"
        )


class TestProxyConfiguration:
    """Guards against drift in the shared NO_PROXY configuration."""

    #: Services expected to use the shared ``x-no-proxy`` anchor verbatim.
    _ANCHORED_SERVICES = (
        "audio-analyzer",
        "text-to-speech",
        "rag-service",
    )

    @staticmethod
    def _load_compose() -> dict:
        import yaml

        with open(_KIOSK_ROOT / "docker-compose.yml") as fh:
            return yaml.safe_load(fh)

    @pytest.mark.tier1
    def test_anchored_services_share_the_no_proxy_list(self):
        """Services using the anchor must all resolve to the same NO_PROXY value."""
        compose = self._load_compose()
        anchor = compose["x-no-proxy"]

        for service in self._ANCHORED_SERVICES:
            env = compose["services"][service]["environment"]
            for key in ("NO_PROXY", "no_proxy"):
                assert env[key] == anchor, (
                    f"{service}.{key} does not match the x-no-proxy anchor. "
                    f"Expected {anchor!r}, got {env[key]!r}"
                )

    @pytest.mark.tier1
    def test_kiosk_core_no_proxy_prefix_matches_anchor(self):
        """kiosk-core keeps its own literal (it appends a runtime suffix).

        YAML anchors cannot be concatenated, so kiosk-core cannot reuse
        ``x-no-proxy`` directly. Assert its prefix still matches the anchor so
        a host added to the anchor but forgotten here fails CI instead of
        silently diverging.
        """
        compose = self._load_compose()
        anchor_hosts = [h for h in compose["x-no-proxy"].split(",") if h]

        env = compose["services"]["kiosk-core"]["environment"]
        for key in ("NO_PROXY", "no_proxy"):
            value = env[key]
            # Drop the ${KIOSK_CORE_QSR_EXTRA_NO_PROXY:+,...} suffix.
            literal = value.split("${", 1)[0]
            hosts = [h for h in literal.split(",") if h]

            missing = [h for h in anchor_hosts if h not in hosts]
            assert not missing, (
                f"kiosk-core.{key} is missing entries present in the x-no-proxy "
                f"anchor: {missing}. Keep the two in sync."
            )

    #: Proxy variables that must be passed through, in both letter cases.
    _PROXY_KEYS = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy")

    @pytest.mark.tier1
    def test_downloading_services_pass_proxy_through_without_a_default(self):
        """Proxy keys must be declared value-less, never with an empty default.

        ``HTTP_PROXY: ${HTTP_PROXY:-}`` injects an EMPTY value when the
        variable is unset, which overrides the proxy Docker would otherwise
        inject from ``~/.docker/config.json`` (``proxies.default``) and breaks
        the first-run model download on exactly the proxied hosts it was meant
        to help (ITEP-97604).

        A value-less key is resolved from the shell or .env when set, and
        omitted from the container entirely when unset.
        """
        compose = self._load_compose()

        for service in self._ANCHORED_SERVICES:
            env = compose["services"][service]["environment"]
            for key in self._PROXY_KEYS:
                assert key in env, (
                    f"{service} must declare {key} so a host proxy reaches the "
                    f"container; Python reads the lower-case names and curl "
                    f"reads either."
                )
                assert env[key] is None, (
                    f"{service}.{key} must be declared with NO value "
                    f"(got {env[key]!r}). A ${{...:-}} default injects an empty "
                    f"string and clobbers ~/.docker/config.json."
                )

    @pytest.mark.tier1
    def test_no_service_declares_an_empty_proxy_default(self):
        """No service anywhere may give a proxy variable an empty default."""
        compose = self._load_compose()

        offenders = []
        for name, service in compose.get("services", {}).items():
            env = service.get("environment") or {}
            if not isinstance(env, dict):
                continue
            for key in self._PROXY_KEYS:
                value = env.get(key)
                if value is not None and "${" in str(value):
                    offenders.append(f"{name}.{key}={value!r}")

        assert not offenders, (
            "Proxy variables must be declared value-less so an unset proxy is "
            "omitted rather than injected as an empty string. Found: "
            f"{offenders}"
        )

    @pytest.mark.tier1
    def test_proxy_override_file_is_gone(self):
        """The opt-in override file was folded back into docker-compose.yml.

        Keeping a second compose file solely for proxy settings meant proxied
        hosts had to discover and pass an extra flag; the value-less keys make
        it unnecessary.
        """
        assert not (_KIOSK_ROOT / "docker-compose.proxy.yml").exists(), (
            "docker-compose.proxy.yml should no longer exist - proxy "
            "passthrough is declared inline in docker-compose.yml"
        )
