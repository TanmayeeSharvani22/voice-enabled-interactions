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
    def test_locally_built_services_pass_proxy_as_build_args(self):
        """apt-get/pip/npm run in the builder, not the final container.

        The service-level ``environment`` block does not apply at build time,
        so without ``build.args`` a proxied host gets an apt-get timeout during
        ``make build REGISTRY=false``. HTTP_PROXY/HTTPS_PROXY are predefined
        build args, so no ARG declaration is needed in the Dockerfile and they
        are not baked into the image.
        """
        compose = self._load_compose()

        missing = []
        for name, service in compose.get("services", {}).items():
            build = service.get("build")
            if not isinstance(build, dict):
                continue
            args = build.get("args") or {}
            for key in self._PROXY_KEYS:
                if key not in args:
                    missing.append(f"{name}.build.args.{key}")
                elif args[key] is not None:
                    missing.append(
                        f"{name}.build.args.{key}={args[key]!r} (must be value-less)"
                    )

        assert not missing, (
            "Every locally built service must pass the proxy through as build "
            f"args, declared value-less. Missing/invalid: {missing}"
        )

    @pytest.mark.tier1
    def test_hf_offline_resolver_exists_and_is_executable(self):
        """`make up` depends on this script to avoid a 600s stall with no egress."""
        import os

        path = _KIOSK_ROOT / "scripts" / "resolve-hf-offline.sh"
        assert path.is_file(), "scripts/resolve-hf-offline.sh not found"
        assert os.access(path, os.X_OK), (
            "scripts/resolve-hf-offline.sh must be executable; `make up` runs it directly"
        )

        makefile = (_KIOSK_ROOT / "Makefile").read_text()
        up_body = makefile.split("\nup:", 1)[1].split("\ndown:", 1)[0]
        assert "resolve-hf-offline.sh" in up_body, (
            "the `up` target must resolve HF offline mode before starting the stack"
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

    @pytest.mark.tier1
    def test_legacy_kiosk_proxy_variables_are_translated_not_ignored(self):
        """Deployments still using the removed file's variable names must work.

        ``docker-compose.proxy.yml`` read ``KIOSK_HTTP_PROXY`` /
        ``KIOSK_HTTPS_PROXY``. A .env carrying only those would otherwise lose
        egress silently once the file was deleted, and stall on the first
        model download - the exact failure this change exists to prevent.
        """
        makefile = (_KIOSK_ROOT / "Makefile").read_text()

        assert "KIOSK_HTTP_PROXY" in makefile and "KIOSK_HTTPS_PROXY" in makefile, (
            "the Makefile must still recognise the legacy KIOSK_HTTP_PROXY / "
            "KIOSK_HTTPS_PROXY names rather than silently ignoring them"
        )
        assert "deprecated" in makefile, (
            "translating the legacy names must emit a deprecation warning so "
            "they can eventually be removed"
        )

    @pytest.mark.tier1
    def test_check_env_detects_exported_and_commented_empty_proxy_lines(self):
        """`HTTP_PROXY=` in .env reintroduces ITEP-97604; all forms must be caught.

        Compose accepts ``export HTTP_PROXY=`` as an empty value, and does NOT
        strip a trailing comment - ``HTTP_PROXY= # optional`` becomes the
        literal string ``# optional``. Both are broken configurations that the
        original regex, anchored directly after ``=``, let through.
        """
        import re
        import subprocess

        makefile = (_KIOSK_ROOT / "Makefile").read_text()
        match = re.search(
            r"grep -qE '(\^\[\[:space:\]\]\*\(export.*?)' \.env", makefile
        )
        assert match, "check-env must grep .env for unusable proxy assignments"
        pattern = match.group(1).replace("$$", "$")

        flagged = ("HTTP_PROXY=", "export HTTPS_PROXY=", "  http_proxy=  ",
                   "HTTP_PROXY= # optional", "export https_proxy=  # note")
        allowed = ("#HTTP_PROXY=", "# HTTP_PROXY=http://p:912",
                   "HTTP_PROXY=http://p:912")

        for line in flagged + allowed:
            hit = subprocess.run(
                ["grep", "-qE", pattern], input=line, text=True
            ).returncode == 0
            assert hit is (line in flagged), (
                f"check-env proxy regex misclassified {line!r} "
                f"(expected {'flagged' if line in flagged else 'allowed'})"
            )

    @pytest.mark.tier1
    def test_resolver_never_blocks_on_an_unverified_verdict(self):
        """Refusing to start is only justified when the verdict is established.

        With no local image to probe with, neither container egress nor the
        caches can be inspected: a host ``curl`` says nothing about what a
        container reaches through Docker's ``proxies.default``. Blocking there
        would break startups that would have worked.
        """
        resolver = (_KIOSK_ROOT / "scripts" / "resolve-hf-offline.sh").read_text()

        assert "probe_inconclusive" in resolver, (
            "the resolver must track whether its verdict was actually "
            "established before it is allowed to block startup"
        )
        assert "curl -fsS" in resolver, (
            "the host fallback must use curl --fail; without it an HTTP 403 "
            "from a filtering proxy exits 0 and is misread as working egress"
        )
        assert "nc -z" not in resolver, (
            "a raw TCP connect to :443 is not proof of Hub access and must "
            "not count as a successful probe"
        )
        assert "-size +1024k" in resolver and "*.incomplete" in resolver, (
            "the cache check must require real weight files, so an empty "
            "models--*/ directory or an interrupted download is not counted "
            "as a warm cache"
        )

    @pytest.mark.tier1
    def test_resolver_probes_with_curl_not_busybox_wget(self):
        """A busybox `wget` 403 from the Hub's edge must not mean "no egress".

        Observed on a working host: busybox ``wget`` gets ``403 Forbidden``
        from huggingface.co while ``curl`` gets ``200`` over the same network,
        with and without the proxy. Trusting wget there forces
        ``HF_HUB_OFFLINE=1`` on an online host, which breaks startup outright:
        ``optimum-cli export openvino`` must reach the Hub API to infer a
        model's task, so the first-run IR export dies and audio-analyzer
        crash-loops.
        """
        resolver = (_KIOSK_ROOT / "scripts" / "resolve-hf-offline.sh").read_text()

        assert "PROBE_TOOL" in resolver, (
            "the probe image must be chosen by whether it actually has curl "
            "or wget - some service images ship neither, and probing with "
            "them fails with 'wget: not found', which looks like no egress"
        )
        assert "exit 42" in resolver, (
            "a wget-only 403 must be reported as inconclusive, not as an "
            "unreachable Hub"
        )
        assert "/api/models/" in resolver, (
            "probe the API endpoint huggingface_hub itself calls, so a proxy "
            "that serves the landing page but blocks the API is caught"
        )

        # The inconclusive bail-out must precede the cache decision, otherwise
        # an unverified probe still silently selects offline mode. Anchored on
        # the *call* to count_warm_caches, not its definition.
        assert "\ncount_warm_caches\n" in resolver, (
            "the cache scan must be invoked as a named step so its position "
            "relative to the inconclusive gate is checkable"
        )
        assert resolver.index("probe_inconclusive\" ] || [ -z \"$PROBE_IMG") < \
            resolver.index("\ncount_warm_caches\n"), (
            "the inconclusive check must come BEFORE the cache evaluation; "
            "an unestablished verdict must drive no decision at all"
        )

    @pytest.mark.tier1
    def test_resolver_checks_the_converted_model_cache(self):
        """Cached source weights alone do not make an offline start safe.

        audio-analyzer converts the model to OpenVINO IR on first run via
        ``optimum-cli``, which needs the Hub API to infer the task. Offline
        mode is only viable once that IR already exists, so the IR volume -
        not just the Hugging Face source cache - must be what is inspected.
        """
        resolver = (_KIOSK_ROOT / "scripts" / "resolve-hf-offline.sh").read_text()

        assert "audio_analyzer_models" in resolver, (
            "the resolver must verify the exported OpenVINO IR volume; the "
            "Hugging Face source cache being populated does not mean the "
            "service can start offline"
        )


class TestOvmsModelsBindMount:
    """Guards the fresh-clone bring-up path for ovms-llm (ITEP-96305)."""

    @staticmethod
    def _load_compose() -> dict:
        import yaml

        with open(_KIOSK_ROOT / "docker-compose.yml") as fh:
            return yaml.safe_load(fh)

    @pytest.mark.tier1
    def test_models_bind_mount_is_made_writable_before_ovms_starts(self):
        """``docker compose up -d`` must work on a clone with no ``models/``.

        ``smart-kiosk-assistant/models/`` is gitignored, so it does not exist
        on a fresh clone and Docker creates the bind target as ``root:root
        0755``. ovms-llm runs as uid 5000 and then dies with::

            Libgit2 clone error: 2 ... failed to make directory
            '/models/OpenVINO': Permission denied

        taking every dependent service down with it. ``make up`` masks this
        via its own ``mkdir -p models``; the documented Quick Start
        (``docker compose pull && docker compose up -d``) has no such step.
        """
        compose = self._load_compose()
        init = compose["services"]["ovms-cache-init"]

        mounts = [str(v) for v in init.get("volumes", [])]
        assert any(m.startswith("./models:") for m in mounts), (
            "ovms-cache-init must mount ./models so it can fix the "
            "permissions Docker gives a freshly created bind target"
        )
        assert "/models" in str(init.get("command", "")), (
            "ovms-cache-init must make /models writable by uid 5000 before "
            "ovms-llm starts"
        )

        # Ownership must be left alone: models/identity is written by
        # identity-service and by the host, so a recursive chown would break
        # it. Only the mode of the top-level directory may change.
        command = str(init["command"])
        assert "chown -R 5000:5000 /models" not in command, (
            "do not recursively chown /models - models/identity is written "
            "by identity-service and by the host user"
        )

    @pytest.mark.tier1
    def test_ovms_llm_waits_for_the_permission_fix(self):
        """The fix is useless if ovms-llm can start before it completes."""
        compose = self._load_compose()
        depends = compose["services"]["ovms-llm"].get("depends_on", {})

        assert "ovms-cache-init" in depends, (
            "ovms-llm must depend on ovms-cache-init, otherwise it can start "
            "before /models is writable"
        )
        assert depends["ovms-cache-init"]["condition"] == "service_completed_successfully", (
            "ovms-llm must wait for ovms-cache-init to finish, not merely start"
        )


class TestSingleHuggingFaceProbe:
    """The HF egress/cache probe must exist in exactly one place.

    `check-env` used to carry its own inline copy of this logic. The two
    drifted: the Makefile copy probed with ``wget --spider || nc -z`` (which
    huggingface.co rejects with 403 regardless of reachability, and which
    cannot traverse a proxy) and inspected ``audio_analyzer_cache``, while
    the resolver used curl and inspected ``audio_analyzer_models``. They
    contradicted each other and reported "unreachable" on hosts that
    demonstrably had container egress (ITEP-97604).
    """

    _RESOLVER = _KIOSK_ROOT / "scripts" / "resolve-hf-offline.sh"

    @pytest.mark.tier1
    def test_check_env_delegates_to_the_resolver(self):
        """check-env must call the resolver rather than reimplement it."""
        makefile = (_KIOSK_ROOT / "Makefile").read_text()

        assert "HF_RESOLVE_DRY_RUN=true" in makefile, (
            "check-env must invoke scripts/resolve-hf-offline.sh in dry-run "
            "mode instead of carrying its own egress probe"
        )
        assert "--spider" not in makefile, (
            "the Makefile must not probe huggingface.co with wget --spider: "
            "the Hub returns 403 to busybox wget even when reachable"
        )

    @pytest.mark.tier1
    def test_resolver_supports_a_non_blocking_dry_run(self):
        """check-env reports; only `make up` may refuse to start."""
        resolver = self._RESOLVER.read_text()

        assert "HF_RESOLVE_DRY_RUN" in resolver, "resolver must support dry-run mode"
        assert "dry_run()" in resolver, "dry-run must be a single shared predicate"

    @pytest.mark.tier1
    def test_cache_volume_list_is_defined_once(self):
        """One list of cache volumes, so the two callers cannot disagree."""
        resolver = self._RESOLVER.read_text()

        assert "CACHE_VOLUMES=" in resolver, (
            "the cache volume list must be a single named constant"
        )
        assert resolver.count("audio_analyzer_models text_to_speech_cache") == 1, (
            "the cache volume list must not be duplicated"
        )

    @pytest.mark.tier1
    def test_both_callers_pass_the_same_effective_registry(self):
        """`check-env` and `up` must probe the same images.

        The resolver picks its probe image from
        ``$REGISTRY_REPO/<service>:$RELEASE_TAG``. If only one caller passes
        the effective registry, ``make up REGISTRY=private.example/team``
        makes check-env probe the custom images while `up` falls back to
        whatever REGISTRY_REPO happens to be in .env -- so the two can reach
        opposite conclusions about the very same host.
        """
        makefile = (_KIOSK_ROOT / "Makefile").read_text()

        invocations = [
            block
            for block in makefile.split("./scripts/resolve-hf-offline.sh")[:-1]
        ]
        assert len(invocations) == 2, (
            "expected exactly two resolver invocations (check-env and up), "
            f"found {len(invocations)}"
        )

        for block in invocations:
            # Only the environment assignments immediately preceding the call.
            env = block[-400:]
            for var in ("REGISTRY_REPO=", "RELEASE_TAG="):
                assert var in env, (
                    f"every resolve-hf-offline.sh invocation must pass {var} "
                    "so check-env and up select the same probe image"
                )
