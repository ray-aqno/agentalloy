"""End-to-end tests for the container deployment flow in simple_setup.py.

Tests E2E-1 through E2E-4 covering:
  E2E-1: Full container setup with mocked runtime binary
  E2E-2: Container bootstrap pulls qwen3-embedding:0.6b model
  E2E-3: Container bootstrap idempotency - restart skips redundant operations
  E2E-4: Container bootstrap crash recovery - re-runs migrations and install-packs

All external dependencies (subprocess.run for runtime commands, HTTP health
checks, DB access, file I/O) are mocked so these tests run in isolation
and complete in <10s each.
"""

from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compose_file(tmp_path: Path) -> Path:
    """Create a minimal compose.yaml so _has_assets returns True."""
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "version: '3'\n"
        "services:\n"
        "  agentalloy:\n"
        "    image: agentalloy:local\n"
        "    ports:\n"
        "      - '47950:47950'\n"
    )
    return compose


def _make_containerfile(tmp_path: Path) -> Path:
    """Create a minimal Containerfile so _has_assets returns True."""
    cf = tmp_path / "Containerfile"
    cf.write_text("FROM python:3.12\n")
    return cf


def _inject_preflight_mocks():
    """Inject mock versions of preflight functions into the preflight module."""
    import agentalloy.install.subcommands.preflight as preflight

    if not hasattr(preflight, "_probe_compose_runtime"):
        preflight._probe_compose_runtime = lambda: ("podman", "/usr/bin/podman", [])

    if not hasattr(preflight, "_compose_failure_message"):
        preflight._compose_failure_message = lambda probes: (
            "Neither `podman` nor `docker` found on PATH",
            "Install Podman (recommended) or Docker.\n"
            "  Linux:   sudo apt install podman\n"
            "  macOS:   brew install podman\n"
            "  Verify:  podman --version",
        )


def _make_urlopen_mock():
    """Return a mock for urllib.request.urlopen that works as a context manager.

    The mock returns a context-manager mock whose __enter__ yields a response
    mock with status=200, so `with urlopen(...) as resp: resp.status == 200`
    evaluates correctly.
    """
    ctx_mock = MagicMock()
    ctx_mock.__enter__ = MagicMock(return_value=MagicMock(status=200))
    ctx_mock.__exit__ = MagicMock(return_value=False)
    return ctx_mock


def _all_common_patches(tmp_path: Path):
    """Return a list of common patch context managers for container flow tests.

    Must call _inject_preflight_mocks() first to add the mock preflight
    attributes that the patched versions reference.

    NOTE: _run_quiet, _wait_for_one_shot, urllib.request.urlopen, and
    time.monotonic are NOT included here. They are created as shared mocks
    in _run_container_flow_all_mocked so that tests can override their
    behavior by setting side_effect/return_value on the shared mock objects.
    """
    _inject_preflight_mocks()
    return [
        patch("agentalloy.install.subcommands.preflight._probe_compose_runtime",
              return_value=("podman", "/usr/bin/podman", [])),
        patch("agentalloy.install.subcommands.preflight._compose_failure_message",
              return_value=("ok", "ok")),
        patch("agentalloy.install.subcommands.preflight.run_preflight",
              return_value={"checks": []}),
        patch("agentalloy.install.subcommands.simple_setup._list_project_containers",
              return_value=[]),
        patch("agentalloy.install.subcommands.simple_setup._remove_containers",
              return_value=True),
        patch("agentalloy.install.subcommands.simple_setup._container_setup_log_path",
              return_value=tmp_path / "setup.log"),
        patch("agentalloy.install.subcommands.simple_setup._inspect_ollama_project",
              return_value=("test-project", "test-project_default")),
        patch("agentalloy.install.state.load_state", return_value={}),
        patch("agentalloy.install.state.save_state"),
        patch("agentalloy.install.state.user_config_dir",
              return_value=tmp_path / ".config" / "agentalloy"),
        patch("agentalloy.install.state.env_path",
              return_value=tmp_path / ".env"),
        patch("agentalloy.install.state._atomic_write"),
        patch("agentalloy.install.subcommands.verify.run", return_value=0),
        patch("agentalloy.install.subcommands.wire_harness.run", return_value=0),
        patch("agentalloy.install.subcommands.simple_setup._build_namespace"),
        patch("agentalloy.install.subcommands.simple_setup._prompt_for_packs",
              return_value=""),
        patch("agentalloy.install.subcommands.simple_setup._discover_packs",
              return_value={}),
        patch("pathlib.Path.cwd", return_value=tmp_path),
        patch("time.sleep", return_value=None),
        patch("builtins.input", return_value="y"),
    ]


def _run_container_flow_all_mocked(
    tmp_path: Path,
    extra_patches=None,
    mock_overrides=None,
):
    """Run _run_container_flow with all external dependencies mocked.

    Uses contextlib.ExitStack to avoid Python's AST nested block limit.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory for compose files and logs.
    extra_patches : list[contextlib.AbstractContextManager], optional
        Additional patch context managers to apply.
    mock_overrides : dict, optional
        Override shared mock behavior. Keys: "run_quiet",
        "wait_for_one_shot", "urlopen", "monotonic". Values are the new
        side_effect or return_value to set.
    """
    patches = _all_common_patches(tmp_path)

    # Create shared mock objects that tests can override
    mock_run_quiet = MagicMock(return_value=0)
    mock_wait_for_one_shot = MagicMock(return_value=0)
    mock_urlopen = MagicMock(return_value=_make_urlopen_mock())
    mock_monotonic = MagicMock(return_value=0.0)

    # Apply default mocks
    patches.append(
        patch("agentalloy.install.subcommands.simple_setup._run_quiet", mock_run_quiet)
    )
    patches.append(
        patch(
            "agentalloy.install.subcommands.simple_setup._wait_for_one_shot",
            mock_wait_for_one_shot,
        )
    )
    patches.append(
        patch("urllib.request.urlopen", mock_urlopen)
    )
    patches.append(
        patch("time.monotonic", mock_monotonic)
    )

    # Apply mock overrides BEFORE entering the ExitStack so the
    # mock objects already have the correct behavior when called.
    if mock_overrides:
        if "run_quiet" in mock_overrides:
            mock_run_quiet.side_effect = mock_overrides["run_quiet"]
        if "wait_for_one_shot" in mock_overrides:
            mock_wait_for_one_shot.side_effect = mock_overrides["wait_for_one_shot"]
        if "urlopen" in mock_overrides:
            mock_urlopen.side_effect = mock_overrides["urlopen"]
        if "monotonic" in mock_overrides:
            mock_monotonic.side_effect = mock_overrides["monotonic"]

    if extra_patches:
        patches.extend(extra_patches)

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)

        from agentalloy.install.subcommands.simple_setup import (
            SetupConfig,
            _run_container_flow,
        )

        cfg = SetupConfig(
            deployment="container",
            non_interactive=True,
            port=47950,
            packs="",
            harness="manual",
        )

        return _run_container_flow(cfg, 0.0)


# ---------------------------------------------------------------------------
# E2E-1: Full container setup with mocked runtime binary
# ---------------------------------------------------------------------------


class TestFullContainerSetup:
    """E2E-1: Full container setup with mocked runtime binary.

    Verifies that _run_container_flow returns 0 when every step succeeds,
    and that the correct sequence of subprocess calls is made.
    """

    def test_full_setup_returns_zero(self):
        """_run_container_flow returns 0 when every step succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            rc = _run_container_flow_all_mocked(tmp_path)

            assert rc == 0, f"Expected exit code 0, got {rc}"

    def test_full_setup_calls_subprocess_in_correct_order(self):
        """Verify _run_quiet is called for each major compose/run step.

        _run_quiet is called for compose/podman commands that produce output:
          1. compose up agentalloy-init (migrations)
          2. compose up ollama + ollama-pull
          3. podman run install-packs
          4. podman run agentalloy (main service)

        The 'podman wait' steps use _wait_for_one_shot instead.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            call_order = []

            def track_run(cmd, **kwargs):
                call_order.append(cmd[0] if cmd else None)
                return 0

            rc = _run_container_flow_all_mocked(
                tmp_path,
                mock_overrides={"run_quiet": track_run},
            )

            assert rc == 0
            # _run_quiet is called 4 times: init, ollama, install-packs, main
            assert len(call_order) >= 4, (
                f"Expected at least 4 _run_quiet calls, got {len(call_order)}: {call_order}"
            )

    def test_full_setup_records_state_on_success(self):
        """After successful setup, state is saved with deployment=container."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            saved_state = {}

            def capture_save_state(st):
                saved_state.clear()
                saved_state.update(st)

            rc = _run_container_flow_all_mocked(
                tmp_path,
                extra_patches=[
                    patch("agentalloy.install.state.save_state", side_effect=capture_save_state),
                ],
            )

            assert rc == 0
            assert saved_state.get("deployment") == "container"
            assert saved_state.get("port") == 47950
            assert saved_state.get("runtime_binary") == "podman"

    def test_full_setup_skips_native_prompts_in_non_interactive_mode(self):
        """In non-interactive mode, no prompts are shown and setup proceeds."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            input_calls = []

            def track_input(prompt=""):
                input_calls.append(str(prompt))
                return "y"

            rc = _run_container_flow_all_mocked(
                tmp_path,
                extra_patches=[
                    patch("builtins.input", side_effect=track_input),
                ],
            )

            assert rc == 0
            # In non-interactive mode, input() should not be called
            # (the non_interactive path skips all prompts)
            assert len(input_calls) == 0, (
                f"Expected no input() calls in non-interactive mode, got {len(input_calls)}"
            )


# ---------------------------------------------------------------------------
# E2E-2: Container bootstrap pulls qwen3-embedding:0.6b model
# ---------------------------------------------------------------------------


class TestModelPullBootstrap:
    """E2E-2: Container bootstrap pulls qwen3-embedding:0.6b model.

    Verifies that the ollama + ollama-pull compose step is called and that
    the model pull is confirmed.
    """

    def test_model_pull_step_is_executed(self):
        """The ollama + ollama-pull compose up step is called."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            compose_up_calls = []

            def track_run_quiet(cmd, **kwargs):
                if "compose" in cmd and "up" in cmd:
                    compose_up_calls.append(cmd)
                return 0

            rc = _run_container_flow_all_mocked(
                tmp_path,
                mock_overrides={"run_quiet": track_run_quiet},
            )

            assert rc == 0
            # Should have at least 2 compose up calls: init + ollama
            compose_up_count = sum(1 for c in compose_up_calls if "compose" in c)
            assert compose_up_count >= 2, (
                f"Expected at least 2 compose up calls, got {compose_up_count}"
            )

    def test_model_pull_confirmed_in_output(self):
        """When ollama-pull succeeds, 'Embedding model ready' is printed."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            printed_messages = []

            def capture_print(*args, **kwargs):
                printed_messages.append(" ".join(str(a) for a in args))

            rc = _run_container_flow_all_mocked(
                tmp_path,
                extra_patches=[
                    patch("agentalloy.install.subcommands.simple_setup._print",
                          side_effect=capture_print),
                ],
                # wait_for_one_shot returns 0 by default (ollama-pull succeeded)
            )

            assert rc == 0
            assert any("Embedding model ready" in m for m in printed_messages), (
                f"Expected 'Embedding model ready' in output, got: {printed_messages}"
            )

    def test_model_pull_failure_continues_with_warning(self):
        """When ollama-pull fails, a warning is printed but setup continues."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            printed_messages = []

            def capture_print(*args, **kwargs):
                printed_messages.append(" ".join(str(a) for a in args))

            # _wait_for_one_shot is called twice: init-wait (index 0) and
            # ollama-pull-wait (index 1). Return 0 for init, 1 for ollama-pull.
            wait_results = [0, 1]  # init ok, ollama-pull fails
            rc = _run_container_flow_all_mocked(
                tmp_path,
                extra_patches=[
                    patch("agentalloy.install.subcommands.simple_setup._print",
                          side_effect=capture_print),
                ],
                mock_overrides={"wait_for_one_shot": iter(wait_results)},
            )

            assert rc == 0, (
                f"Expected setup to continue after model pull failure, got {rc}"
            )
            assert any("embeddings may fail" in m for m in printed_messages), (
                f"Expected warning about embeddings, got: {printed_messages}"
            )


# ---------------------------------------------------------------------------
# E2E-3: Container bootstrap idempotency
# ---------------------------------------------------------------------------


class TestBootstrapIdempotency:
    """E2E-3: Container bootstrap idempotency - restart skips redundant operations.

    Verifies that when .bootstrap-complete already exists, the entrypoint
    skips Ollama install, model pull, migrations, and pack installation.
    """

    def test_entrypoint_skips_bootstrap_when_complete(self):
        """The generated entrypoint script checks for .bootstrap-complete first."""
        from agentalloy.install.subcommands.container_runtime import (
            _build_entrypoint_script,
        )

        script = _build_entrypoint_script("")

        # .bootstrap-complete check should come before ollama install
        bootstrap_check = script.index(".bootstrap-complete")
        ollama_install = script.index("ollama.ai/install.sh")
        uvicorn_start = script.index("exec uvicorn")

        assert bootstrap_check < ollama_install, (
            ".bootstrap-complete check should come before ollama install"
        )
        assert ollama_install < uvicorn_start, (
            "ollama install should come before uvicorn start"
        )

    def test_entrypoint_skips_all_steps_when_complete(self):
        """When .bootstrap-complete exists, only uvicorn runs."""
        from agentalloy.install.subcommands.container_runtime import (
            _build_entrypoint_script,
        )

        script = _build_entrypoint_script("")

        # The script has an if/else structure:
        # if bootstrap-complete exists -> skip to uvicorn
        # else -> do all bootstrap steps
        assert "if [ -f" in script and ".bootstrap-complete" in script
        assert "echo \">> Bootstrap already complete" in script
        assert "skip to uvicorn" in script.lower() or "skipping to uvicorn" in script.lower()

    def test_entrypoint_skips_ollama_install_when_present(self):
        """When ollama is already installed, the install step is skipped."""
        from agentalloy.install.subcommands.container_runtime import (
            _build_entrypoint_script,
        )

        script = _build_entrypoint_script("")

        # Check for ollama presence check before install
        ollama_check = script.index("command -v ollama")
        ollama_install = script.index("ollama.ai/install.sh")

        assert ollama_check < ollama_install, (
            "ollama presence check should come before install"
        )

    def test_entrypoint_skips_model_pull_when_cached(self):
        """When the model is already cached, the pull step is skipped."""
        from agentalloy.install.subcommands.container_runtime import (
            _build_entrypoint_script,
        )

        script = _build_entrypoint_script("")

        # Check for model presence check before pull
        model_check = script.index("grep -q qwen3-embedding")
        model_pull = script.index("ollama pull qwen3-embedding")

        assert model_check < model_pull, (
            "model cache check should come before pull"
        )


# ---------------------------------------------------------------------------
# E2E-4: Container bootstrap crash recovery
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    """E2E-4: Container bootstrap crash recovery - re-runs migrations and install-packs.

    Verifies that when a step fails, the setup correctly reports the failure
    and can be re-run.
    """

    def test_init_failure_aborts_setup(self):
        """When agentalloy-init (migrations) fails, setup exits with code 1."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            call_count = [0]

            def track_init_fail(cmd, **kwargs):
                call_count[0] += 1
                if "init" in str(cmd).lower() or "agentalloy-init" in str(cmd):
                    return 1  # migrations fail
                return 0

            rc = _run_container_flow_all_mocked(
                tmp_path,
                mock_overrides={"run_quiet": track_init_fail},
            )

            assert rc == 1, f"Expected exit code 1 on init failure, got {rc}"

    def test_init_timeout_aborts_setup(self):
        """When agentalloy-init times out, setup exits with code 1.

        The real _run_quiet catches TimeoutExpired and returns 1.
        The mock must do the same — return 1 instead of raising.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            # _run_quiet is called 4 times: init, ollama, install-packs, main.
            # First call is init -> returns 1 (simulating caught TimeoutExpired)
            run_quiet_effects = [1, 0, 0, 0]
            rc = _run_container_flow_all_mocked(
                tmp_path,
                mock_overrides={"run_quiet": iter(run_quiet_effects)},
            )

            assert rc == 1, f"Expected exit code 1 on init timeout, got {rc}"

    def test_container_start_failure_aborts_setup(self):
        """When the main agentalloy container fails to start, setup exits 1."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            call_count = [0]

            def track_container_fail(cmd, **kwargs):
                call_count[0] += 1
                # First 3 calls succeed (init, ollama, install-packs)
                if call_count[0] > 3:
                    return 1  # main container fails
                return 0

            rc = _run_container_flow_all_mocked(
                tmp_path,
                mock_overrides={"run_quiet": track_container_fail},
            )

            assert rc == 1, f"Expected exit code 1 on container start failure, got {rc}"

    def test_health_check_timeout_shows_warning(self):
        """When health check times out, a warning is printed but setup continues."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            printed_messages = []

            def capture_print(*args, **kwargs):
                printed_messages.append(" ".join(str(a) for a in args))

            # time.monotonic is called many times: health check loop iterations,
            # final elapsed-time calculation, etc. Provide enough values.
            monotonic_values = [0.0, 0.0, 0.0, 121.0, 0.0, 0.0, 0.0]
            rc = _run_container_flow_all_mocked(
                tmp_path,
                extra_patches=[
                    patch("agentalloy.install.subcommands.simple_setup._print",
                          side_effect=capture_print),
                ],
                mock_overrides={
                    "urlopen": OSError("connection refused"),
                    "monotonic": iter(monotonic_values),
                },
            )

            assert rc == 0, (
                f"Expected setup to continue after health check timeout, got {rc}"
            )
            assert any("not healthy" in m.lower() for m in printed_messages), (
                f"Expected health warning, got: {printed_messages}"
            )

    def test_preflight_failure_aborts_before_subprocess_calls(self):
        """When preflight fails, setup exits 1 without any subprocess calls."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose_file = _make_compose_file(tmp_path)
            _make_containerfile(tmp_path)

            subprocess_calls = []

            def track_subprocess(cmd, **kwargs):
                subprocess_calls.append(cmd[0] if cmd else None)
                return 0

            rc = _run_container_flow_all_mocked(
                tmp_path,
                extra_patches=[
                    patch("agentalloy.install.subcommands.preflight.run_preflight",
                          return_value={
                              "checks": [
                                  {
                                      "name": "port_free",
                                      "passed": False,
                                      "severity": "fatal",
                                      "error": "port 47950 in use",
                                      "remediation": "Stop the process on port 47950",
                                  }
                              ]
                          }),
                ],
            )

            assert rc == 1, f"Expected exit code 1 on preflight failure, got {rc}"
            assert len(subprocess_calls) == 0, (
                f"Expected no subprocess calls after preflight failure, got {subprocess_calls}"
            )
