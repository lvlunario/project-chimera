"""Deterministic, self-verifying handoff bundles for completed link runs."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
from zipfile import BadZipFile, ZIP_STORED, ZipFile, ZipInfo

from .api import CompletedLinkRun, OperatorAPIError


ARTIFACT_NAMES = (
    "request.json", "evidence.json", "bindings.json", "report.json", "report.html"
)
MANIFEST_NAME = "manifest.json"
MAX_BUNDLE_BYTES = 16_777_216
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class HandoffError(ValueError):
    """A completed-run handoff cannot be created or trusted."""


def _canonical(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ) + "\n").encode("utf-8")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise HandoffError(f"Duplicate manifest field: {key}")
        result[key] = value
    return result


def _artifacts(run: CompletedLinkRun) -> dict[str, bytes]:
    return {
        "request.json": _canonical(dict(run.request)),
        "evidence.json": (run.evidence.to_json() + "\n").encode("utf-8"),
        "bindings.json": (run.bindings.to_json() + "\n").encode("utf-8"),
        "report.json": (run.report.to_json() + "\n").encode("utf-8"),
        "report.html": run.report.to_html().encode("utf-8"),
    }


def _manifest(run: CompletedLinkRun, artifacts: dict[str, bytes]) -> dict:
    report = run.report.to_dict()
    return {
        "schema_version": 1,
        "bundle_type": "chimera.completed-link-run",
        "run_id": str(run.request["run_id"]),
        "workflow": str(run.request["workflow"]),
        "requirement_id": str(report["requirement"]["requirement_id"]),
        "verdict": str(report["requirement"]["verdict"]),
        "artifacts": [
            {
                "path": name,
                "bytes": len(artifacts[name]),
                "sha256": sha256(artifacts[name]).hexdigest(),
            }
            for name in ARTIFACT_NAMES
        ],
    }


def _zip_entry(name: str) -> ZipInfo:
    info = ZipInfo(name, _FIXED_ZIP_TIME)
    info.compress_type = ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def create_handoff_bundle(run_directory: str | Path,
                          destination: str | Path) -> dict:
    """Validate one completed run and publish a deterministic ZIP bundle once."""
    try:
        run = CompletedLinkRun.open(run_directory)
    except OperatorAPIError as exc:
        raise HandoffError(f"Completed run is invalid: {exc}") from exc
    artifacts = _artifacts(run)
    manifest = _manifest(run, artifacts)
    payload = BytesIO()
    with ZipFile(payload, "w", compression=ZIP_STORED, allowZip64=False) as archive:
        archive.writestr(_zip_entry(MANIFEST_NAME), _canonical(manifest))
        for name in ARTIFACT_NAMES:
            archive.writestr(_zip_entry(name), artifacts[name])
    content = payload.getvalue()
    if len(content) > MAX_BUNDLE_BYTES:  # Defensive; source artifact limits are smaller.
        raise HandoffError("Handoff bundle exceeds the supported size")

    target = Path(destination)
    if target.is_symlink() or target.exists():
        raise HandoffError("Handoff output already exists or is a symbolic link")
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and refuses to replace a raced destination.
        os.link(temporary, target)
    except FileExistsError as exc:
        raise HandoffError("Handoff output already exists or is a symbolic link") from exc
    except OSError as exc:
        raise HandoffError("Cannot publish handoff bundle") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                pass
    return manifest


def _read_bundle(path: str | Path) -> bytes:
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise HandoffError("Handoff bundle must be a regular file")
    try:
        with target.open("rb") as stream:
            content = stream.read(MAX_BUNDLE_BYTES + 1)
    except OSError as exc:
        raise HandoffError("Handoff bundle is unavailable") from exc
    if len(content) > MAX_BUNDLE_BYTES:
        raise HandoffError("Handoff bundle exceeds the supported size")
    return content


def inspect_handoff_bundle(path: str | Path) -> dict:
    """Fail closed unless a bundle manifest and every completed artifact agree."""
    try:
        with ZipFile(BytesIO(_read_bundle(path)), "r") as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            expected = [MANIFEST_NAME, *ARTIFACT_NAMES]
            if names != expected or len(set(names)) != len(names):
                raise HandoffError("Handoff bundle has unexpected or duplicate entries")
            if any(member.compress_type != ZIP_STORED or member.flag_bits & 1
                   for member in members):
                raise HandoffError("Handoff entries must be unencrypted and stored")
            documents = {name: archive.read(name) for name in expected}
    except HandoffError:
        raise
    except (BadZipFile, KeyError, OSError, RuntimeError) as exc:
        raise HandoffError("Handoff bundle is not a readable ZIP archive") from exc

    try:
        manifest = json.loads(
            documents[MANIFEST_NAME].decode("utf-8"), object_pairs_hook=_unique_object
        )
    except HandoffError:
        raise
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError) as exc:
        raise HandoffError("Invalid handoff manifest") from exc
    expected_fields = {
        "schema_version", "bundle_type", "run_id", "workflow",
        "requirement_id", "verdict", "artifacts",
    }
    if type(manifest) is not dict or set(manifest) != expected_fields:
        raise HandoffError("Invalid handoff manifest fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise HandoffError("Unsupported handoff schema_version")
    if manifest["bundle_type"] != "chimera.completed-link-run":
        raise HandoffError("Unsupported handoff bundle_type")
    entries = manifest["artifacts"]
    if type(entries) is not list or len(entries) != len(ARTIFACT_NAMES):
        raise HandoffError("Invalid handoff artifact manifest")
    for name, entry in zip(ARTIFACT_NAMES, entries):
        data = documents[name]
        if (type(entry) is not dict
                or set(entry) != {"path", "bytes", "sha256"}
                or entry["path"] != name
                or type(entry["bytes"]) is not int
                or entry["bytes"] != len(data)
                or entry["sha256"] != sha256(data).hexdigest()):
            raise HandoffError(f"Handoff artifact identity mismatch: {name}")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name in ARTIFACT_NAMES:
            (root / name).write_bytes(documents[name])
        try:
            run = CompletedLinkRun.open(root)
        except OperatorAPIError as exc:
            raise HandoffError(f"Bundled run is invalid: {exc}") from exc
    expected_manifest = _manifest(run, _artifacts(run))
    if manifest != expected_manifest or documents[MANIFEST_NAME] != _canonical(manifest):
        raise HandoffError("Handoff manifest conflicts with completed run")
    return manifest
