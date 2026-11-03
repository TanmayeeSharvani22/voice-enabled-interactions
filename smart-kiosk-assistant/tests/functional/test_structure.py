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
import re
import subprocess

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


class TestTargetDeviceDrivesEveryService:
    """`TARGET_DEVICE` must switch the whole stack, not just ovms-llm.

    ITEP-97604: on a host whose GPU is not usable by OpenVINO, a user set
    ``TARGET_DEVICE=CPU`` (the remedy `check-env` itself printed) and
    audio-analyzer still crash-looped with "[GPU] Context was not initialized
    for 0 device". ``TARGET_DEVICE`` only fed setup_models.sh and the ovms-llm
    container; every other service read its own ``*_DEVICE`` variable, and
    .env.example hard-coded four of them to GPU, so the documented CPU switch
    could not take effect.
    """

    _COMPOSE = (_KIOSK_ROOT / "docker-compose.yml").read_text()
    _ENV_EXAMPLE = (_KIOSK_ROOT / ".env.example").read_text()

    # Per-service inference devices that must follow TARGET_DEVICE when the
    # user has not pinned them. TTS/diarization/queue are deliberately CPU.
    _CHAINED = (
        "AUDIO_ANALYZER__MODELS__ASR__DEVICE",
        "AUDIO_ANALYZER__MODELS__ASR__PREVIEW__DEVICE",
        "SMART_KIOSK_RAG__MODELS__EMBEDDING__DEVICE",
        "SMART_KIOSK_RAG__RETRIEVAL__RERANKER__DEVICE",
        "IDENTITY_DEVICE",
    )

    @pytest.mark.tier1
    @pytest.mark.parametrize("key", _CHAINED)
    def test_device_falls_back_to_target_device(self, key):
        """Each service device must chain through TARGET_DEVICE."""
        line = next(
            (ln for ln in self._COMPOSE.splitlines()
             if ln.strip().startswith(f"{key}:")),
            None,
        )
        assert line is not None, f"{key} missing from docker-compose.yml"
        assert "${TARGET_DEVICE:-GPU}" in line, (
            f"{key} must fall back to ${{TARGET_DEVICE:-GPU}} so a CPU-only "
            f"host needs one switch; got: {line.strip()}"
        )

    @pytest.mark.tier1
    @pytest.mark.parametrize(
        "var",
        ("ASR_DEVICE", "RAG_EMBEDDING_DEVICE",
         "RAG_RERANKER_DEVICE", "IDENTITY_DEVICE"),
    )
    def test_env_example_does_not_pin_gpu(self, var):
        """An uncommented *_DEVICE=GPU in .env.example defeats TARGET_DEVICE.

        Compose resolves ``${ASR_DEVICE:-${TARGET_DEVICE:-GPU}}`` against the
        value .env supplies, so shipping ``ASR_DEVICE=GPU`` makes the fallback
        unreachable for every user created by `make init-env`.
        """
        for raw in self._ENV_EXAMPLE.splitlines():
            stripped = raw.strip()
            if stripped.startswith("#"):
                continue
            assert not stripped.startswith(f"{var}="), (
                f"{var} must stay commented out in .env.example so it "
                f"inherits TARGET_DEVICE; found: {stripped}"
            )

    @pytest.mark.tier1
    def test_target_device_is_exported_to_compose(self):
        """COMPOSE_BASE must pass TARGET_DEVICE explicitly.

        Relying on `.env` alone breaks `make up TARGET_DEVICE=CPU`, where the
        command-line value never reaches the compose interpolation.
        """
        makefile = (_KIOSK_ROOT / "Makefile").read_text()
        base = next(
            (ln for ln in makefile.splitlines()
             if ln.startswith("COMPOSE_BASE")),
            "",
        )
        assert "TARGET_DEVICE=$(TARGET_DEVICE)" in base, (
            "COMPOSE_BASE must export TARGET_DEVICE so command-line "
            f"overrides reach docker compose; got: {base.strip()}"
        )


class TestRtspStreamerSurfacesMediamtxFailure:
    """rtsp-streamer must explain why mediamtx refused to start.

    ITEP-97604: mediamtx's output is redirected to /tmp/mediamtx.log inside the
    container, so a start failure produced only a generic "RTSP server failed
    to start" line every ~12s forever. The real cause died with the container.
    """

    _START_SH = (_KIOSK_ROOT / "rtsp-streamer" / "start.sh").read_text()

    @pytest.mark.tier1
    def test_failure_path_dumps_the_mediamtx_log(self):
        assert "dump_mediamtx_log" in self._START_SH, (
            "start.sh must dump /tmp/mediamtx.log when mediamtx fails to "
            "bind the RTSP port, or the cause is unrecoverable"
        )
        assert "tail -n 50 /tmp/mediamtx.log" in self._START_SH

    @pytest.mark.tier1
    def test_dead_mediamtx_is_detected_immediately(self):
        """Don't burn the full 10s timeout on a process that already exited."""
        assert 'kill -0 "$mediamtx_pid"' in self._START_SH, (
            "the readiness loop must notice mediamtx has exited instead of "
            "polling a dead process until the retry budget runs out"
        )


class TestSetupModelsNeutralisesStaleGpuPins:
    """setup_models.sh must reconcile stale per-service GPU pins in .env.

    ITEP-97604: a per-service *_DEVICE value takes precedence over
    TARGET_DEVICE in docker-compose, and .env is not a shell -- a variable can
    only inherit TARGET_DEVICE by being absent. Older .env.example revisions
    shipped ASR_DEVICE/RAG_*_DEVICE/IDENTITY_DEVICE pinned to GPU, so a user
    switching an existing install to CPU got TARGET_DEVICE=CPU while every
    service still requested GPU and crash-looped. Fixing .env.example cannot
    help them, because their .env already exists.
    """

    _SETUP_SH = (_KIOSK_ROOT / "setup_models.sh").read_text()

    @pytest.mark.tier1
    def test_stale_gpu_pins_are_commented_out(self):
        """Switching to a non-GPU device must neutralise leftover GPU pins."""
        assert "auto-disabled by setup_models.sh" in self._SETUP_SH, (
            "update_env must comment out per-service *_DEVICE variables still "
            "pinned to GPU; otherwise TARGET_DEVICE=CPU is silently ignored "
            "and every pinned service crash-loops on a GPU-less host"
        )

    @pytest.mark.tier1
    def test_every_gpu_capable_service_var_is_covered(self):
        """All five chained vars must be reconciled, not just ASR."""
        block = self._SETUP_SH.split("Stale per-service GPU pins")[1]
        loop = block.split("RENDER_GID")[0]
        for var in (
            "ASR_DEVICE",
            "RAG_EMBEDDING_DEVICE",
            "RAG_RERANKER_DEVICE",
            "RAG_LLM_DEVICE",
            "IDENTITY_DEVICE",
        ):
            assert var in loop, (
                f"{var} chains to TARGET_DEVICE in docker-compose, so a stale "
                f"GPU pin for it must be reconciled too"
            )

    @pytest.mark.tier1
    def test_cpu_only_services_are_never_rewritten(self):
        """TTS/diarization/queue are deliberately CPU — never auto-flip them."""
        block = self._SETUP_SH.split("Stale per-service GPU pins")[1]
        loop = block.split("RENDER_GID")[0]
        # Inspect executable lines only: the rationale comment above the loop
        # names these variables precisely to explain why they are excluded.
        code = "\n".join(
            line for line in loop.splitlines() if not line.lstrip().startswith("#")
        )
        for var in ("TTS_DEVICE", "DIARIZATION_DEVICE", "QUEUE_DEVICE"):
            assert var not in code, (
                f"{var} is intentionally CPU-only (GPU TTS is known-bad: int4 "
                f"on iGPU produces noise and GPU+int8 measured 281s on the "
                f"first call); it must not be rewritten in either direction"
            )

    @pytest.mark.tier1
    def test_only_gpu_pins_are_neutralised(self):
        """A deliberate ASR_DEVICE=NPU override must survive."""
        block = self._SETUP_SH.split("Stale per-service GPU pins")[1]
        loop = block.split("RENDER_GID")[0]
        assert "=GPU" in loop, (
            "only pins whose value is GPU may be neutralised -- matching any "
            "value that merely differs from TARGET_DEVICE would clobber a "
            "deliberate heterogeneous override such as ASR_DEVICE=NPU"
        )

    @pytest.mark.tier1
    def test_not_applied_when_target_device_is_gpu(self):
        """On a GPU target the pins agree with TARGET_DEVICE — leave them."""
        block = self._SETUP_SH.split("Stale per-service GPU pins")[1]
        guard = block.split("for _var")[0]
        assert '"${TARGET_DEVICE}" != "GPU"' in guard, (
            "the reconciliation must be guarded on a non-GPU target so a "
            "normal GPU install is left byte-identical"
        )

    @pytest.mark.tier1
    def test_previous_value_is_preserved_in_the_comment(self):
        """Comment the line out rather than deleting it, so it is reversible."""
        block = self._SETUP_SH.split("Stale per-service GPU pins")[1]
        loop = block.split("RENDER_GID")[0]
        assert "# \\1" in loop, (
            "the original assignment must be preserved inside the comment so "
            "the edit is visible and reversible by hand"
        )

    @pytest.mark.tier1
    def test_check_env_blocks_startup_when_gpu_is_unusable(self):
        """A GPU pin on a GPU-less host must fail check-env, not just warn.

        check-env is a prerequisite of `up`, so a warning alone lets `make up`
        proceed and every pinned service crash-loops. The escalation is scoped
        to hosts with no render node: pinning one service to GPU while the
        rest run on CPU is legitimate on a GPU-capable machine.
        """
        makefile = (_KIOSK_ROOT / "Makefile").read_text()
        block = makefile.split("_GPU_PINS=\"\"")[1].split("effective inference devices")[0]
        assert "renderD" in block, (
            "the GPU-pin check must consult the render node before deciding "
            "between a hard error and a warning, so a deliberate mixed "
            "GPU/CPU setup on a GPU-capable host is not rejected"
        )
        assert "ERRORS+1" in block, (
            "on a host with no render node a leftover GPU pin must increment "
            "ERRORS so check-env exits non-zero and `up` is blocked"
        )


class TestDevicePinDetectionMatchesWhatComposeHonours:
    """The pin detector, the un-pinner and the device tools must agree.

    Three consumers resolve the same per-service `*_DEVICE` variables:
    docker-compose, `make check-env` and `scripts/validate_device_profile.py`.
    If any of them disagrees about which assignments are live -- or about what
    an unset variable falls back to -- `make setup-models TARGET_DEVICE=CPU`
    reports success while check-env still blocks startup, or a benchmark run
    records a device the container never received.
    """

    _MAKEFILE = (_KIOSK_ROOT / "Makefile").read_text()
    _SETUP = (_KIOSK_ROOT / "setup_models.sh").read_text()
    _VALIDATE = (_KIOSK_ROOT / "scripts" / "validate_device_profile.py").read_text()
    _MANIFEST = (_KIOSK_ROOT / "scripts" / "write_run_manifest.py").read_text()

    @pytest.mark.tier1
    @pytest.mark.parametrize(
        "line",
        (
            "export ASR_DEVICE=GPU",
            "ASR_DEVICE = GPU",
            "  ASR_DEVICE=GPU",
            "ASR_DEVICE=GPU  # pinned for a bench run",
        ),
    )
    def test_unpinner_matches_every_live_assignment_form(self, line, tmp_path):
        """Forms Compose and make honour must all be neutralised.

        Compose's dotenv parser and make's `include .env` both accept an
        `export` prefix and whitespace around the `=`. A pattern anchored on
        '^VAR=GPU' leaves those pins in place, so the documented recovery
        command silently fails and check-env keeps failing.
        """
        pattern = re.search(
            r'_pat="(\^[^"]+)"', self._SETUP
        )
        assert pattern, "expected a _pat= regex in setup_models.sh"
        rx = pattern.group(1).replace("${_var}", "ASR_DEVICE")
        env = tmp_path / ".env"
        env.write_text(line + "\n")
        out = subprocess.run(
            ["grep", "-qE", rx, str(env)], check=False
        )
        assert out.returncode == 0, (
            f"setup_models.sh would not neutralise a live pin written as "
            f"{line!r}; Compose and make both resolve it to GPU"
        )

    @pytest.mark.tier1
    @pytest.mark.parametrize("var", ("MY_ASR_DEVICE=GPU", "ASR_DEVICE_EXTRA=GPU"))
    def test_unpinner_does_not_match_unrelated_variables(self, var, tmp_path):
        """A loose pattern must not rewrite similarly-named variables."""
        pattern = re.search(r'_pat="(\^[^"]+)"', self._SETUP)
        rx = pattern.group(1).replace("${_var}", "ASR_DEVICE")
        env = tmp_path / ".env"
        env.write_text(var + "\n")
        out = subprocess.run(["grep", "-qE", rx, str(env)], check=False)
        assert out.returncode != 0, f"{var} must not be treated as an ASR_DEVICE pin"

    @pytest.mark.tier1
    @pytest.mark.parametrize("var", ("IDENTITY_DEVICE", "QUEUE_DEVICE"))
    def test_disabled_services_do_not_block_startup(self, var):
        """A pin on a service whose profile is off must not fail check-env.

        identity-service and queue-service only start under their Compose
        profiles. Failing check-env for a container that will never be created
        blocks an otherwise valid CPU-only stack.
        """
        flag = "_IDENTITY_ON" if var == "IDENTITY_DEVICE" else "_QUEUE_ON"
        block = self._MAKEFILE.split("_GPU_PINS=\"\"")[1].split("effective inference devices")[0]
        assert f"$(if $({flag}),{var}:" in block, (
            f"{var} must only join the GPU-pin check when {flag} is set, "
            f"so a disabled service cannot block a CPU-only bring-up"
        )

    @pytest.mark.tier1
    def test_remediation_only_offers_setup_models_for_vars_it_rewrites(self):
        """check-env must not point at a command that cannot fix the pin.

        setup_models.sh rewrites only the ASR/RAG/identity pins. TTS,
        diarization and queue are deliberately CPU-only and never auto-
        rewritten, so telling the user to run `make setup-models` for those
        is a dead end.
        """
        unpinned = self._SETUP.split("for _var in", 1)[1].split("; do", 1)[0]
        for var in ("ASR_DEVICE", "RAG_EMBEDDING_DEVICE", "RAG_RERANKER_DEVICE",
                    "RAG_LLM_DEVICE", "IDENTITY_DEVICE"):
            assert var in unpinned, f"{var} should be auto-un-pinned"
        for var in ("TTS_DEVICE", "DIARIZATION_DEVICE", "QUEUE_DEVICE"):
            assert var not in unpinned, f"{var} is CPU-by-design, not auto-rewritten"

        block = self._MAKEFILE.split("_GPU_PINS=\"\"")[1].split("effective inference devices")[0]
        assert "_GPU_PINS_MANUAL" in block, (
            "check-env must separate pins `make setup-models` can clear from "
            "those needing a manual .env edit, or its 'Fix:' line is wrong"
        )

    @pytest.mark.tier1
    @pytest.mark.parametrize(
        "source", ("_VALIDATE", "_MANIFEST"),
    )
    def test_device_tools_inherit_target_device(self, source):
        """Benchmark tooling must resolve devices the way Compose does.

        A literal default here disagrees with Compose as soon as the
        per-service pin is unset -- which is now the shipped default -- so a
        CPU-only run gets rejected on a GPU-less host, or the manifest records
        a device the container never used.
        """
        text = getattr(self, source)
        for stale in ('"ASR_DEVICE", "CPU"',
                      '"RAG_EMBEDDING_DEVICE", "GPU"',
                      '"RAG_RERANKER_DEVICE", "GPU"'):
            assert stale not in text, (
                f"{stale} hard-codes a default that no longer matches "
                f"docker-compose's ${{TARGET_DEVICE:-GPU}} fallback"
            )
        assert "stack_dev" in text, "expected devices to chain through _stack_dev()"
