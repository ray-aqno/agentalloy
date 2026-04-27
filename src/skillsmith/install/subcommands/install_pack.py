# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""``install-pack`` subcommand — pull a published skill pack into the corpus.

Operator-tier. The skill-pack registry shape is **TBD for v1**; we ship a
minimal mechanism that:

  1. Resolves a pack name to a manifest URL using a hardcoded pattern.
  2. Downloads + parses the manifest (JSON: ``{tarball_url, sha256, ...}``).
  3. Downloads the tarball, validates its sha256 against the manifest.
  4. Extracts YAML draft files into ``skill-source/pending-review/``.
  5. Calls the existing ``skillsmith.ingest`` pipeline on each YAML.
  6. Records the pack name and ingested skill IDs in install state.

A real registry (org-scoped, signed manifests, dependency resolution) is
deferred — flagged in the install spec's open questions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from skillsmith.install import state as install_state

SCHEMA_VERSION = 1
STEP_NAME = "install-pack"

# Hardcoded URL pattern. The placeholder org is ``navistone``; this lands
# in the manifest URL ``…/skill-pack-{name}/releases/latest/download/manifest.json``.
# When a real registry exists, this becomes a registry lookup instead.
_DEFAULT_MANIFEST_URL_PATTERN = (
    "https://github.com/navistone/skill-pack-{name}/releases/latest/download/manifest.json"
)

# Allowed URL schemes for both manifest and tarball. Refusing file:// / ftp://
# blocks SSRF + local-file disclosure via a malicious manifest.
_ALLOWED_SCHEMES = frozenset({"https", "http"})

# Pack name pattern — letters, digits, hyphens, underscores. Disallows path
# traversal (`..`, `/`) or scheme injection in the URL substitution.
_PACK_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

# Per-fetch size caps. Manifest is small JSON; tarball can be larger.
_MAX_MANIFEST_BYTES = 1 << 20  # 1 MiB
_MAX_TARBALL_BYTES = 100 << 20  # 100 MiB


def _validate_url(url: str, kind: str) -> None:
    """Raise SystemExit(1) if ``url`` scheme is not in the allowlist."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        print(
            f"ERROR: {kind} URL has disallowed scheme '{parsed.scheme}': {url}",
            file=sys.stderr,
        )
        print(
            f"FIX:   Use one of: {', '.join(sorted(_ALLOWED_SCHEMES))}.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _download(url: str, dest: Path, max_bytes: int, timeout: int = 60) -> None:
    """Download a URL to a local file with a size cap.

    Raises on HTTP/network errors and on payloads exceeding ``max_bytes``
    (avoids tempdir DoS via attacker-controlled redirect targets).
    """
    _validate_url(url, "download")
    req = urllib.request.Request(url, headers={"User-Agent": "skillsmith-install/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — scheme allowlisted
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        bytes_read = 0
        chunk = 64 * 1024
        with dest.open("wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                bytes_read += len(buf)
                if bytes_read > max_bytes:
                    raise RuntimeError(f"Download exceeded {max_bytes} bytes from {url}; aborting")
                f.write(buf)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_manifest_url(pack_name: str, override: str | None) -> str:
    if override:
        _validate_url(override, "manifest")
        return override
    if not _PACK_NAME_RE.match(pack_name):
        print(
            f"ERROR: Pack name '{pack_name}' contains disallowed characters.",
            file=sys.stderr,
        )
        print(
            "FIX:   Pack names must match [a-zA-Z0-9][a-zA-Z0-9_-]{0,63} "
            "(no slashes, dots, or scheme prefixes).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return _DEFAULT_MANIFEST_URL_PATTERN.format(name=pack_name)


def _ingest_yaml(yaml_path: Path, repo_root: Path) -> dict[str, Any]:
    """Run the existing ingest pipeline on one YAML. Returns parsed result."""
    result = subprocess.run(  # noqa: S603 — fixed args, no shell
        [
            sys.executable,
            "-m",
            "skillsmith.ingest",
            str(yaml_path),
            "--yes",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {
        "yaml": yaml_path.name,
        "exit_code": result.returncode,
        "stdout_tail": result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "",
        "stderr_tail": result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "",
    }


def install_pack(
    name: str,
    manifest_url: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Install a skill pack by name. Returns contract-shaped result."""
    from skillsmith.install.state import _repo_root  # pyright: ignore[reportPrivateUsage]

    root = root or _repo_root()
    t0 = time.monotonic()
    url = _resolve_manifest_url(name, manifest_url)

    # 1. Fetch manifest
    with tempfile.TemporaryDirectory(prefix="skillsmith-pack-") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        manifest_path = tmpdir / "manifest.json"
        try:
            _download(url, manifest_path, max_bytes=_MAX_MANIFEST_BYTES)
        except urllib.error.URLError as exc:
            return {
                "schema_version": SCHEMA_VERSION,
                "action": "manifest_fetch_failed",
                "pack": name,
                "manifest_url": url,
                "error": str(exc.reason),
                "remediation": (
                    "Verify the pack name is correct and the manifest URL is reachable. "
                    "If the pack is hosted elsewhere, pass --manifest-url to override "
                    "the default pattern."
                ),
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        manifest = json.loads(manifest_path.read_text())
        tarball_url = manifest.get("tarball_url")
        expected_sha = (manifest.get("sha256") or "").lower()
        if not tarball_url or not expected_sha:
            return {
                "schema_version": SCHEMA_VERSION,
                "action": "manifest_invalid",
                "pack": name,
                "error": "Manifest is missing required fields tarball_url and/or sha256",
                "remediation": "Contact the pack author to publish a valid manifest.",
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        # 2. Download tarball + validate sha256
        tar_path = tmpdir / "pack.tar.gz"
        try:
            _download(tarball_url, tar_path, max_bytes=_MAX_TARBALL_BYTES)
        except urllib.error.URLError as exc:
            return {
                "schema_version": SCHEMA_VERSION,
                "action": "tarball_fetch_failed",
                "pack": name,
                "tarball_url": tarball_url,
                "error": str(exc.reason),
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        actual_sha = _sha256_file(tar_path)
        if actual_sha != expected_sha:
            return {
                "schema_version": SCHEMA_VERSION,
                "action": "sha256_mismatch",
                "pack": name,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "error": "Downloaded tarball sha256 does not match manifest",
                "remediation": "Pack may be tampered or manifest stale; abort and contact the author.",
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        # 3. Extract into a staging dir using the stdlib 'data' filter
        # (Python 3.12+). This filter rejects absolute paths, path traversal,
        # symlink/hardlink escapes, device/FIFO members, and stays inside the
        # destination root by design — much safer than the prior name-only
        # check which missed the link-traversal vector.
        extract_dir = tmpdir / "extracted"
        extract_dir.mkdir()
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(extract_dir, filter="data")
        except tarfile.TarError as exc:
            return {
                "schema_version": SCHEMA_VERSION,
                "action": "tarball_unsafe_path",
                "pack": name,
                "error": f"Tarball extraction rejected: {exc}",
                "remediation": "Pack is malformed or hostile; contact the author.",
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        yaml_files = sorted(extract_dir.glob("**/*.yaml")) + sorted(extract_dir.glob("**/*.yml"))
        if not yaml_files:
            return {
                "schema_version": SCHEMA_VERSION,
                "action": "no_yaml_in_pack",
                "pack": name,
                "error": "Pack tarball contained no YAML skill drafts",
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        pending_dir = root / "skill-source" / "pending-review"
        pending_dir.mkdir(parents=True, exist_ok=True)
        # Refuse to write through a symlink at pending_dir — a pre-planted
        # symlink there would otherwise redirect copies outside the repo.
        if not install_state.is_inside_root(pending_dir, root):
            return {
                "schema_version": SCHEMA_VERSION,
                "action": "pending_dir_outside_root",
                "pack": name,
                "error": (
                    f"skill-source/pending-review resolves outside repo root "
                    f"({pending_dir.resolve()}). A symlink may have been planted."
                ),
                "remediation": "Remove the symlink and re-run install-pack.",
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        # Two YAMLs at different paths within the tarball can share the
        # same basename (e.g. `engineering/foo.yaml` + `quality/foo.yaml`).
        # The tarfile-data filter doesn't dedupe by basename, so we keep
        # the on-disk names unique by flattening the relative path.
        copied: list[str] = []
        ingest_targets: list[Path] = []
        for yf in yaml_files:
            rel = yf.relative_to(extract_dir)
            safe_name = "_".join(rel.parts)
            target = pending_dir / safe_name
            if target.exists():
                # Defensive — shouldn't happen given the rel-path encoding,
                # but bail rather than silently overwrite.
                return {
                    "schema_version": SCHEMA_VERSION,
                    "action": "yaml_filename_collision",
                    "pack": name,
                    "error": f"Tarball produced colliding pending-review filename: {safe_name}",
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                }
            shutil.copyfile(yf, target)
            copied.append(safe_name)
            ingest_targets.append(target)

        # 4. Ingest each YAML via the existing pipeline
        ingest_results: list[dict[str, Any]] = []
        for target in ingest_targets:
            ingest_results.append(_ingest_yaml(target, root))

    failed = [r for r in ingest_results if r["exit_code"] != 0]

    # 5. Record in install state
    state = install_state.load_state(root)
    packs = state.get("installed_packs") or []
    packs.append(
        {
            "name": name,
            "manifest_url": url,
            "manifest_sha256": expected_sha,
            "yaml_files": copied,
            "ingest_failures": len(failed),
            "installed_at": int(time.time()),
        }
    )
    state["installed_packs"] = packs
    install_state.record_step(state, STEP_NAME, extra={"pack": name})
    install_state.save_state(state, root)

    duration_ms = int((time.monotonic() - t0) * 1000)
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "ingested" if not failed else "ingested_with_errors",
        "pack": name,
        "manifest_url": url,
        "manifest_sha256": expected_sha,
        "yaml_files": copied,
        "ingest_results": ingest_results,
        "ingest_failures": len(failed),
        "remediation": (
            "Some YAMLs failed to ingest; inspect ingest_results.stderr_tail and "
            "re-run `python -m skillsmith.ingest <yaml>` manually for each failure."
            if failed
            else None
        ),
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Subcommand interface
# ---------------------------------------------------------------------------


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],  # pyright: ignore[reportPrivateUsage]
) -> None:
    p: argparse.ArgumentParser = subparsers.add_parser(
        "install-pack",
        help="Pull a published skill pack into the corpus.",
    )
    p.add_argument("pack_name", help="Pack name (resolves to a known manifest URL).")
    p.add_argument(
        "--manifest-url",
        help=(
            "Override the default manifest URL pattern. "
            "Default: https://github.com/navistone/skill-pack-{name}/releases/latest/download/manifest.json"
        ),
    )
    p.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    result = install_pack(args.pack_name, manifest_url=args.manifest_url)
    print(json.dumps(result, indent=2))
    if result.get("ingest_failures", 0) > 0:
        return 2
    if result.get("action") not in ("ingested",):
        return 1
    return 0
