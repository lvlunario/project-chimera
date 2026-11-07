"""Prepare one exact-candidate Chimera review directory and M4 packet.

This command composes existing engineering controls.  It does not perform a human
walkthrough, grant a phase decision, upload an artifact, merge, tag, or deploy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

from examples import (
    operator_acceptance_prep,
    release_candidate_packet,
    release_performance,
    release_readiness,
    release_threat_model,
)


ROOT = Path(__file__).resolve().parents[1]
REHEARSAL_ID = "p7-m4-review-rehearsal-v1"
RECEIPT_NAME = "review-rehearsal.json"
PACKET_NAME = "chimera-m4-evidence.zip"
MAX_FILES = 128
MAX_ENTRIES = 512
MAX_DEPTH = 16
MAX_CONTENT_BYTES = 32_000_000
MAX_RECEIPT_BYTES = 262_144
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RECEIPT_FIELDS = {
    "artifacts",
    "candidate_checks",
    "candidate_commit_sha",
    "component_statuses",
    "generated_at_utc",
    "human_acceptance",
    "m4_decision",
    "m5_decision",
    "packet_status",
    "rehearsal_id",
    "record_type",
    "release_blockers",
    "schema_version",
    "scope",
    "status",
}
_COMPONENT_FIELDS = {
    "operator_acceptance",
    "performance",
    "release_readiness",
    "threat_model",
}
SCOPE = (
    "one-command exact-candidate review preparation only; not a CI result, "
    "human walkthrough, phase decision, release, upload, merge, tag or deployment"
)


class ReviewRehearsalError(RuntimeError):
    """An exact-candidate review rehearsal could not be prepared safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewRehearsalError(message)


def _canonical(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ReviewRehearsalError(
            "review rehearsal receipt is not canonical JSON"
        ) from exc
    return (rendered + "\n").encode("utf-8")


def _timestamp_text(value: str | None) -> str:
    if value is None:
        value = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReviewRehearsalError(
            "generated_at_utc must be canonical UTC timestamp text"
        ) from exc
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    if parsed.tzinfo != timezone.utc or value != canonical:
        raise ReviewRehearsalError(
            "generated_at_utc must be canonical UTC timestamp text"
        )
    return value


def _no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ReviewRehearsalError(
                f"review rehearsal JSON has duplicate field: {key}"
            )
        value[key] = item
    return value


def _decode_json(content: bytes, label: str) -> dict:
    try:
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_no_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ReviewRehearsalError(
                    f"{label} contains non-finite value: {value}"
                )
            ),
        )
    except ReviewRehearsalError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ReviewRehearsalError(f"{label} is invalid JSON") from exc
    _require(type(document) is dict, f"{label} must be a JSON object")
    return document


def _has_symlink_ancestor(path: Path) -> bool:
    return any(item.is_symlink() for item in (path, *path.parents))


def _read_bounded(path: Path, limit: int, label: str) -> bytes:
    try:
        with path.open("rb") as stream:
            content = stream.read(limit + 1)
    except OSError as exc:
        raise ReviewRehearsalError(f"{label} cannot be read") from exc
    _require(len(content) <= limit, f"{label} exceeds its size bound")
    return content


def _regular_files(root: Path) -> list[Path]:
    """Enumerate a bounded, non-symlinked tree without an unbounded listing."""
    pending = [root]
    files = []
    entries = 0
    try:
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as scanned:
                for entry in scanned:
                    entries += 1
                    _require(
                        entries <= MAX_ENTRIES,
                        "review rehearsal output has too many entries",
                    )
                    path = Path(entry.path)
                    relative = path.relative_to(root)
                    _require(
                        len(relative.parts) <= MAX_DEPTH,
                        "review rehearsal output exceeds the depth bound",
                    )
                    if entry.is_symlink():
                        raise ReviewRehearsalError(
                            "review rehearsal output contains a symbolic link"
                        )
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        files.append(path)
                    else:
                        raise ReviewRehearsalError(
                            "review rehearsal output is not regular"
                        )
    except ReviewRehearsalError:
        raise
    except OSError as exc:
        raise ReviewRehearsalError(
            "review rehearsal output cannot be enumerated"
        ) from exc
    return sorted(files, key=lambda item: item.as_posix())


def _artifact(path: Path, root: Path, *, remaining_bytes: int) -> dict:
    _require(
        not path.is_symlink() and path.is_file(),
        f"review rehearsal artifact is unavailable: {path.name}",
    )
    relative = path.relative_to(root)
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "review rehearsal artifact path is unsafe",
    )
    content = _read_bounded(
        path,
        remaining_bytes,
        "review rehearsal output",
    )
    return {
        "byte_count": len(content),
        "path": relative.as_posix(),
        "sha256": sha256(content).hexdigest(),
    }


def _artifact_inventory(root: Path) -> list[dict]:
    artifacts = []
    total = 0
    for path in _regular_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in {RECEIPT_NAME, ".PUBLISHING"}:
            continue
        _require(
            "\\" not in relative
            and not Path(relative).is_absolute()
            and ".." not in Path(relative).parts,
            "review rehearsal output path is unsafe",
        )
        _require(
            len(artifacts) < MAX_FILES,
            "review rehearsal output has too many files",
        )
        artifact = _artifact(
            path,
            root,
            remaining_bytes=MAX_CONTENT_BYTES - total,
        )
        total += artifact["byte_count"]
        artifacts.append(artifact)
    return artifacts


def _load_source(path: Path, label: str) -> dict:
    _require(
        not path.is_symlink() and path.is_file(),
        f"{label} is unavailable",
    )
    content = _read_bounded(path, 2_097_152, label)
    return _decode_json(content, label)


def _require_packet_source_match(root: Path, packet_path: Path) -> None:
    try:
        expected = {
            release_candidate_packet.ASSESSMENT_NAMES["performance"]:
                (root / "sources/release-performance.json").read_bytes(),
            release_candidate_packet.ASSESSMENT_NAMES["threat_model"]:
                (root / "sources/release-threat-model.json").read_bytes(),
            release_candidate_packet.ASSESSMENT_NAMES["readiness"]:
                (root / "sources/release-readiness.json").read_bytes(),
        }
        acceptance_root = root / "sources/operator-acceptance"
        acceptance_files = {
            path.relative_to(acceptance_root).as_posix(): path
            for path in acceptance_root.rglob("*")
            if path.is_file()
        }
        _require(
            set(acceptance_files)
            == release_candidate_packet.ACCEPTANCE_WORKSPACE_NAMES,
            "operator acceptance source inventory disagrees with packet contract",
        )
        for relative, path in sorted(acceptance_files.items()):
            expected[f"operator-acceptance/{relative}"] = path.read_bytes()
        with zipfile.ZipFile(packet_path, "r") as archive:
            names = archive.namelist()
            for name, content in expected.items():
                _require(
                    names.count(name) == 1 and archive.read(name) == content,
                    f"packet source content disagrees with rehearsal output: {name}",
                )
    except ReviewRehearsalError:
        raise
    except (OSError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ReviewRehearsalError(
            "packet source content cannot be compared with rehearsal output"
        ) from exc


def _validate_rehearsal_directory(
    root: Path,
    *,
    allow_publication_marker: bool = False,
    expected_candidate: str | None = None,
) -> dict:
    _require(
        not root.is_symlink() and root.is_dir(),
        "review rehearsal directory is unavailable",
    )
    marker = root / ".PUBLISHING"
    if allow_publication_marker:
        _require(
            not marker.is_symlink() and marker.is_file(),
            "review rehearsal publication marker is invalid",
        )
    else:
        _require(
            not marker.exists() and not marker.is_symlink(),
            "review rehearsal publication is incomplete",
        )
    receipt_path = root / RECEIPT_NAME
    _require(
        not receipt_path.is_symlink() and receipt_path.is_file(),
        "review rehearsal receipt is unavailable",
    )
    receipt_content = _read_bounded(
        receipt_path,
        MAX_RECEIPT_BYTES,
        "review rehearsal receipt",
    )
    receipt = _decode_json(receipt_content, "review rehearsal receipt")
    _require(
        _canonical(receipt) == receipt_content,
        "review rehearsal receipt is not canonical JSON",
    )
    _require(
        set(receipt) == _RECEIPT_FIELDS,
        "review rehearsal receipt fields changed",
    )
    _require(
        type(receipt["schema_version"]) is int
        and receipt["schema_version"] == 1
        and receipt["record_type"] == "chimera.release-review-rehearsal"
        and receipt["rehearsal_id"] == REHEARSAL_ID,
        "review rehearsal receipt contract changed",
    )
    candidate = receipt["candidate_commit_sha"]
    _require(
        type(candidate) is str and _COMMIT.fullmatch(candidate) is not None,
        "review rehearsal receipt has an invalid candidate",
    )
    if expected_candidate is not None:
        _require(
            candidate == expected_candidate,
            "review rehearsal receipt candidate changed",
        )
    generated = _timestamp_text(receipt["generated_at_utc"])
    _require(
        receipt["candidate_checks"] == {
            "before_preparation": "matched_clean_head",
            "before_publication": "matched_clean_head",
        },
        "review rehearsal candidate checks changed",
    )
    _require(
        type(receipt["component_statuses"]) is dict
        and set(receipt["component_statuses"]) == _COMPONENT_FIELDS
        and all(
            type(value) is str
            for value in receipt["component_statuses"].values()
        ),
        "review rehearsal component status fields changed",
    )
    _require(
        receipt["m4_decision"] == "pending"
        and receipt["m5_decision"] == "pending"
        and receipt["human_acceptance"] == "not_granted",
        "review rehearsal cannot record acceptance",
    )
    _require(receipt["scope"] == SCOPE, "review rehearsal scope changed")
    _require(
        type(receipt["artifacts"]) is list
        and all(
            type(item) is dict
            and set(item) == {"byte_count", "path", "sha256"}
            and type(item["byte_count"]) is int
            and item["byte_count"] >= 0
            and type(item["path"]) is str
            and type(item["sha256"]) is str
            and _SHA256.fullmatch(item["sha256"]) is not None
            for item in receipt["artifacts"]
        )
        and receipt["artifacts"] == _artifact_inventory(root),
        "review rehearsal artifact inventory disagrees with output",
    )
    _require(
        type(receipt["release_blockers"]) is list
        and all(
            type(issue_number) is int and issue_number > 0
            for issue_number in receipt["release_blockers"]
        )
        and receipt["release_blockers"]
        == sorted(set(receipt["release_blockers"])),
        "review rehearsal release blockers are invalid",
    )

    acceptance = _load_source(
        root / "sources/operator-acceptance/acceptance-preparation.json",
        "operator acceptance record",
    )
    performance = _load_source(
        root / "sources/release-performance.json",
        "performance record",
    )
    threat = _load_source(
        root / "sources/release-threat-model.json",
        "threat-model record",
    )
    readiness = _load_source(
        root / "sources/release-readiness.json",
        "release-readiness record",
    )
    packet_path = root / PACKET_NAME
    packet = release_candidate_packet.inspect_packet(packet_path)
    _require_packet_source_match(root, packet_path)
    for label, document in (
        ("operator acceptance", acceptance),
        ("performance", performance),
        ("threat model", threat),
        ("release readiness", readiness),
        ("packet", packet),
    ):
        _require(
            document["candidate_commit_sha"] == candidate,
            f"{label} candidate disagrees with rehearsal receipt",
        )
        _require(
            document["generated_at_utc"] == generated,
            f"{label} timestamp disagrees with rehearsal receipt",
        )
    expected_statuses = {
        "operator_acceptance": acceptance["engineering_status"],
        "performance": performance["status"],
        "release_readiness": readiness["status"],
        "threat_model": threat["status"],
    }
    _require(
        receipt["component_statuses"] == expected_statuses,
        "review rehearsal component statuses disagree with source records",
    )
    _require(
        receipt["packet_status"] == packet["status"]
        and receipt["status"] == packet["status"]
        and receipt["release_blockers"] == packet["release_blockers"],
        "review rehearsal packet status disagrees with receipt",
    )
    return receipt


def inspect_review_rehearsal(output: str | Path) -> dict:
    """Reinspect a published rehearsal directory without its source checkout."""
    return _validate_rehearsal_directory(Path(output))


def _publish_staging(
    stage: Path,
    target: Path,
    *,
    candidate_commit: str,
) -> dict:
    if target.is_symlink() or target.exists():
        raise ReviewRehearsalError(
            "review rehearsal output already exists or is a symbolic link"
        )
    try:
        target.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ReviewRehearsalError(
            "review rehearsal output appeared during publication"
        ) from exc
    except OSError as exc:
        raise ReviewRehearsalError(
            "cannot publish review rehearsal output"
        ) from exc
    marker = target / ".PUBLISHING"
    try:
        with marker.open("x", encoding="utf-8") as stream:
            stream.write(
                "Publication is incomplete; do not use this directory as evidence.\n"
            )
    except OSError as exc:
        try:
            target.rmdir()
        except OSError:
            raise ReviewRehearsalError(
                "review publication initialization failed; reserved output remains"
            ) from exc
        raise ReviewRehearsalError(
            "cannot initialize review rehearsal publication"
        ) from exc
    try:
        items = sorted(
            stage.iterdir(),
            key=lambda path: (path.name == RECEIPT_NAME, path.name),
        )
        for item in items:
            os.rename(item, target / item.name)
        stage.rmdir()
    except OSError as exc:
        raise ReviewRehearsalError(
            "review rehearsal publication is incomplete; .PUBLISHING remains"
        ) from exc
    receipt = _validate_rehearsal_directory(
        target,
        allow_publication_marker=True,
        expected_candidate=candidate_commit,
    )
    try:
        marker.unlink()
    except OSError as exc:
        raise ReviewRehearsalError(
            "review rehearsal publication is incomplete; .PUBLISHING remains"
        ) from exc
    return _validate_rehearsal_directory(
        target,
        expected_candidate=candidate_commit,
    )


def _validate_target(output: str | Path) -> Path:
    requested = Path(output)
    if requested.is_symlink() or requested.exists():
        raise ReviewRehearsalError(
            "review rehearsal output already exists or is a symbolic link"
        )
    if (_has_symlink_ancestor(requested.parent)
            or not requested.parent.is_dir()):
        raise ReviewRehearsalError(
            "review rehearsal output parent is unavailable"
        )
    target = requested.resolve(strict=False)
    checkout = ROOT.resolve()
    if target == checkout or checkout in target.parents:
        raise ReviewRehearsalError(
            "review rehearsal output must be outside the source checkout"
        )
    if target.is_symlink() or target.exists():
        raise ReviewRehearsalError(
            "review rehearsal output already exists or is a symbolic link"
        )
    return target


def prepare_review_rehearsal(
    output: str | Path,
    *,
    candidate_commit: str,
    generated_at_utc: str | None = None,
) -> dict:
    """Prepare all existing M4 review inputs with fail-closed publication."""
    operator_acceptance_prep._validate_candidate_checkout(candidate_commit)
    target = _validate_target(output)
    generated = _timestamp_text(generated_at_utc)
    stage = Path(tempfile.mkdtemp(
        dir=target.parent,
        prefix=f".{target.name}.staging-",
    ))
    try:
        stage.chmod(0o700)
        sources = stage / "sources"
        sources.mkdir(mode=0o700)
        acceptance_path = sources / "operator-acceptance"
        performance_path = sources / "release-performance.json"
        threat_path = sources / "release-threat-model.json"
        readiness_path = sources / "release-readiness.json"
        packet_path = stage / PACKET_NAME

        acceptance = operator_acceptance_prep.prepare_acceptance(
            acceptance_path,
            candidate_commit=candidate_commit,
            generated_at_utc=generated,
        )
        performance = release_performance.measure_performance(
            performance_path,
            candidate_commit=candidate_commit,
            generated_at_utc=generated,
        )
        threat = release_threat_model.assess_threat_model(
            threat_path,
            candidate_commit=candidate_commit,
            generated_at_utc=generated,
        )
        readiness = release_readiness.assess_release_readiness(
            readiness_path,
            candidate_commit=candidate_commit,
            generated_at_utc=generated,
        )
        packet = release_candidate_packet.assemble_packet(
            packet_path,
            candidate_commit=candidate_commit,
            acceptance_workspace=acceptance_path,
            performance_record=performance_path,
            threat_record=threat_path,
            readiness_record=readiness_path,
            generated_at_utc=generated,
        )
        _require(
            release_candidate_packet.inspect_packet(packet_path) == packet,
            "portable packet inspection disagrees with the assembled packet",
        )

        receipt = {
            "artifacts": _artifact_inventory(stage),
            "candidate_checks": {
                "before_preparation": "matched_clean_head",
                "before_publication": "matched_clean_head",
            },
            "candidate_commit_sha": candidate_commit,
            "component_statuses": {
                "operator_acceptance": acceptance["engineering_status"],
                "performance": performance["status"],
                "release_readiness": readiness["status"],
                "threat_model": threat["status"],
            },
            "generated_at_utc": generated,
            "human_acceptance": "not_granted",
            "m4_decision": "pending",
            "m5_decision": "pending",
            "packet_status": packet["status"],
            "rehearsal_id": REHEARSAL_ID,
            "record_type": "chimera.release-review-rehearsal",
            "release_blockers": packet["release_blockers"],
            "schema_version": 1,
            "scope": SCOPE,
            "status": packet["status"],
        }
        receipt_content = _canonical(receipt)
        receipt_path = stage / RECEIPT_NAME
        receipt_path.write_bytes(receipt_content)
        reopened = _decode_json(
            receipt_path.read_bytes(), "review rehearsal receipt"
        )
        _require(
            reopened == receipt and _canonical(reopened) == receipt_content,
            "review rehearsal receipt did not reopen canonically",
        )

        operator_acceptance_prep._validate_candidate_checkout(candidate_commit)
        receipt = _publish_staging(
            stage,
            target,
            candidate_commit=candidate_commit,
        )
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "prepare or reinspect one exact-candidate Chimera review rehearsal"
        )
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("inspect",),
        help="use 'inspect DIRECTORY' to validate a published directory",
    )
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "inspect":
        if args.directory is None:
            parser.error("inspect requires DIRECTORY")
        if args.candidate_commit is not None or args.output is not None:
            parser.error(
                "inspect cannot be combined with "
                "--candidate-commit or --output"
            )
        review_root = args.directory
    else:
        if args.directory is not None:
            parser.error("unexpected rehearsal directory")
        if args.candidate_commit is None or args.output is None:
            parser.error(
                "preparation requires --candidate-commit and --output"
            )
        review_root = args.output
    try:
        if args.command == "inspect":
            receipt = inspect_review_rehearsal(review_root)
        else:
            receipt = prepare_review_rehearsal(
                review_root,
                candidate_commit=args.candidate_commit,
            )
        receipt_path = review_root / RECEIPT_NAME
        packet_path = review_root / PACKET_NAME
        receipt_digest = sha256(receipt_path.read_bytes()).hexdigest()
        packet_digest = sha256(packet_path.read_bytes()).hexdigest()
        receipt_location = receipt_path.resolve(strict=False)
        packet_location = packet_path.resolve(strict=False)
    except (
        ReviewRehearsalError,
        operator_acceptance_prep.AcceptancePreparationError,
        release_performance.PerformanceBaselineError,
        release_threat_model.ThreatModelError,
        release_readiness.ReleaseReadinessError,
        release_candidate_packet.ReleaseCandidatePacketError,
        OSError,
    ) as exc:
        print(f"chimera review rehearsal: {exc}", file=sys.stderr)
        return 2
    for component, status in receipt["component_statuses"].items():
        print(f"{component}: {status}")
    print(f"packet: {receipt['packet_status']}")
    print(f"candidate-commit: {receipt['candidate_commit_sha']}")
    print(f"review-receipt: {receipt_location}")
    print(f"review-packet: {packet_location}")
    print(f"receipt-sha256: {receipt_digest}")
    print(f"packet-sha256: {packet_digest}")
    action = "inspection" if args.command == "inspect" else "preparation"
    print(
        f"Review {action} only; M4/M5 decisions and human acceptance "
        "remain pending"
    )
    return 0 if receipt["status"] == "packet_complete_for_m4_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
