"""Bind one exact Chimera M4 engineering candidate to reviewed evidence.

The offline command consumes a published review rehearsal and a canonical snapshot
of connected GitHub Actions inspection.  It validates and binds those inputs; it
does not query GitHub, authenticate the snapshot, grant M4, or record human review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys

from examples import release_review_rehearsal


ROOT = Path(__file__).resolve().parents[1]
NOMINATION_ID = "p7-m4-engineering-nomination-v1"
REPOSITORY = "lvlunario/project-chimera"
DEVELOPMENT_BRANCH = "magnum-opus/development"
MAX_JSON_BYTES = 262_144
MAX_PACKET_BYTES = 32_000_000
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RUN_URL = re.compile(
    r"https://github\.com/lvlunario/project-chimera/actions/runs/([1-9][0-9]*)"
)
_REQUIRED_JOBS = (
    "Chromium dashboard journey",
    "Python 3.11",
    "Python 3.12",
)
_CI_FIELDS = {
    "branch",
    "candidate_commit_sha",
    "inspected_at_utc",
    "record_type",
    "repository",
    "runs",
    "schema_version",
}
_RUN_FIELDS = {
    "conclusion",
    "event",
    "jobs",
    "run_id",
    "run_url",
    "source_candidate_commit_sha",
    "tested_commit_sha",
    "workflow_name",
}
_JOB_FIELDS = {"conclusion", "name"}
_NOMINATION_FIELDS = {
    "candidate_change_policy",
    "candidate_commit_sha",
    "defect_snapshot",
    "engineering_state",
    "generated_at_utc",
    "hosted_ci",
    "human_acceptance",
    "m4_decision",
    "m5_decision",
    "nomination_id",
    "phase_dispositions",
    "record_type",
    "rehearsal",
    "schema_version",
    "scope",
}
_REHEARSAL_FIELDS = {
    "component_statuses",
    "generated_at_utc",
    "packet",
    "packet_status",
    "receipt",
    "release_blockers",
}
_IDENTITY_FIELDS = {"byte_count", "sha256"}
_DEFECT_FIELDS = {
    "open_count",
    "open_release_blockers",
    "snapshot_age_at_nomination_seconds",
    "snapshot_at_utc",
}
_HOSTED_FIELDS = _CI_FIELDS | {
    "evidence_sha256",
    "verification_boundary",
}
_PHASE_FIELDS = {"p3", "p4", "p5"}
SCOPE = (
    "exact-SHA engineering nomination for M4 review only; not live GitHub "
    "verification, a human walkthrough, phase disposition, M4/M5 decision, "
    "release, merge, tag or deployment"
)
CI_BOUNDARY = (
    "caller-supplied connected GitHub inspection snapshot; validated and "
    "content-bound offline, not queried or authenticated by this command"
)
CANDIDATE_CHANGE_POLICY = (
    "retain this exact commit until an explicit later nomination record "
    "supersedes it"
)


class CandidateNominationError(RuntimeError):
    """An M4 engineering candidate could not be nominated safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateNominationError(message)


def _canonical(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CandidateNominationError(
            "candidate nomination is not canonical JSON"
        ) from exc
    return (rendered + "\n").encode("utf-8")


def _no_duplicates(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise CandidateNominationError(
                f"candidate nomination JSON has duplicate field: {key}"
            )
        document[key] = value
    return document


def _read_bounded(path: Path, limit: int, label: str) -> bytes:
    _require(
        not path.is_symlink() and path.is_file(),
        f"{label} must be a regular file",
    )
    try:
        with path.open("rb") as stream:
            content = stream.read(limit + 1)
    except OSError as exc:
        raise CandidateNominationError(f"{label} cannot be read") from exc
    _require(0 < len(content) <= limit, f"{label} exceeds its size bound")
    return content


def _load_canonical(path: Path, limit: int, label: str) -> tuple[dict, bytes]:
    content = _read_bounded(path, limit, label)
    return _decode_canonical(content, label)


def _decode_canonical(content: bytes, label: str) -> tuple[dict, bytes]:
    try:
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_no_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CandidateNominationError(
                    f"{label} contains non-finite value: {value}"
                )
            ),
        )
    except CandidateNominationError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CandidateNominationError(f"{label} is invalid JSON") from exc
    _require(type(document) is dict, f"{label} must be a JSON object")
    _require(_canonical(document) == content, f"{label} is not canonical JSON")
    return document, content


def _utc_timestamp(value: object, label: str) -> str:
    _require(type(value) is str, f"{label} must be canonical UTC timestamp text")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CandidateNominationError(
            f"{label} must be canonical UTC timestamp text"
        ) from exc
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    _require(
        parsed.tzinfo == timezone.utc and value == canonical,
        f"{label} must be canonical UTC timestamp text",
    )
    return value


def _generated_timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    return _utc_timestamp(value, "generated_at_utc")


def _object(value: object, keys: set[str], label: str) -> dict:
    _require(type(value) is dict, f"{label} must be an object")
    _require(set(value) == keys, f"{label} fields changed")
    return value


def _identity(path: Path, limit: int, label: str) -> dict:
    content = _read_bounded(path, limit, label)
    return {"byte_count": len(content), "sha256": sha256(content).hexdigest()}


def _validate_ci_document(document: dict, content: bytes | None = None) -> dict:
    _object(document, _CI_FIELDS, "hosted CI evidence")
    _require(
        type(document["schema_version"]) is int
        and document["schema_version"] == 1
        and document["record_type"]
        == "chimera.github-actions-candidate-evidence",
        "hosted CI evidence contract changed",
    )
    _require(
        document["repository"] == REPOSITORY
        and document["branch"] == DEVELOPMENT_BRANCH,
        "hosted CI evidence repository or branch changed",
    )
    candidate = document["candidate_commit_sha"]
    _require(
        type(candidate) is str and _COMMIT.fullmatch(candidate) is not None,
        "hosted CI evidence candidate is invalid",
    )
    _utc_timestamp(document["inspected_at_utc"], "hosted CI inspected_at_utc")
    runs = document["runs"]
    _require(type(runs) is list and len(runs) == 2, "hosted CI must contain two runs")
    _require(
        [item.get("event") if type(item) is dict else None for item in runs]
        == ["push", "pull_request"],
        "hosted CI must contain push then pull_request evidence",
    )
    observed_ids = []
    for index, run in enumerate(runs):
        event = ("push", "pull_request")[index]
        _object(run, _RUN_FIELDS, f"hosted CI {event} run")
        run_id = run["run_id"]
        _require(
            type(run_id) is int and run_id > 0,
            f"hosted CI {event} run ID is invalid",
        )
        observed_ids.append(run_id)
        url = run["run_url"]
        match = _RUN_URL.fullmatch(url) if type(url) is str else None
        _require(
            match is not None and match.group(1) == str(run_id),
            f"hosted CI {event} run URL is invalid",
        )
        _require(
            run["event"] == event
            and run["workflow_name"] == "test"
            and run["conclusion"] == "success",
            f"hosted CI {event} run did not complete successfully",
        )
        tested = run["tested_commit_sha"]
        source = run["source_candidate_commit_sha"]
        _require(
            type(tested) is str
            and _COMMIT.fullmatch(tested) is not None
            and source == candidate,
            f"hosted CI {event} commit identity is invalid",
        )
        if event == "push":
            _require(
                tested == candidate,
                "hosted CI push run did not test the candidate commit",
            )
        jobs = run["jobs"]
        _require(
            type(jobs) is list
            and [item.get("name") if type(item) is dict else None for item in jobs]
            == list(_REQUIRED_JOBS),
            f"hosted CI {event} required job inventory changed",
        )
        for job in jobs:
            _object(job, _JOB_FIELDS, f"hosted CI {event} job")
            _require(
                job["conclusion"] == "success",
                f"hosted CI {event} job did not succeed",
            )
    _require(len(set(observed_ids)) == 2, "hosted CI run IDs must be distinct")
    if content is not None:
        _require(_canonical(document) == content, "hosted CI evidence is not canonical")
    return document


def _embedded_ci(hosted: dict) -> tuple[dict, str]:
    _object(hosted, _HOSTED_FIELDS, "candidate nomination hosted CI")
    _require(
        hosted["verification_boundary"] == CI_BOUNDARY,
        "candidate nomination hosted CI boundary changed",
    )
    evidence_sha = hosted["evidence_sha256"]
    _require(
        type(evidence_sha) is str and _SHA256.fullmatch(evidence_sha) is not None,
        "candidate nomination hosted CI identity is invalid",
    )
    document = {key: hosted[key] for key in _CI_FIELDS}
    content = _canonical(document)
    _require(
        sha256(content).hexdigest() == evidence_sha,
        "candidate nomination hosted CI evidence identity changed",
    )
    return _validate_ci_document(document, content), evidence_sha


def _has_symlink_ancestor(path: Path) -> bool:
    return any(item.is_symlink() for item in (path, *path.parents))


def _file_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _directory_has_ancestor(
    descriptor: int, ancestor_identities: set[tuple[int, int]]
) -> bool:
    current = os.dup(descriptor)
    try:
        for _ in range(1024):
            current_identity = _file_identity(os.fstat(current))
            if current_identity in ancestor_identities:
                return True
            parent = os.open("..", _directory_flags(), dir_fd=current)
            parent_identity = _file_identity(os.fstat(parent))
            if parent_identity == current_identity:
                os.close(parent)
                return False
            os.close(current)
            current = parent
    except OSError as exc:
        raise CandidateNominationError(
            "candidate nomination output ancestry cannot be verified"
        ) from exc
    finally:
        os.close(current)
    raise CandidateNominationError(
        "candidate nomination output ancestry exceeds its bound"
    )


def _live_parent_matches(
    parent: Path, expected_identity: tuple[int, int]
) -> bool:
    try:
        if _has_symlink_ancestor(parent):
            return False
        metadata = os.stat(parent, follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISDIR(metadata.st_mode)
        and _file_identity(metadata) == expected_identity
    )


def _validate_output(
    output: str | Path, rehearsal: Path
) -> tuple[Path, int, tuple[int, int]]:
    requested = Path(output)
    if requested.is_symlink() or requested.exists():
        raise CandidateNominationError(
            "candidate nomination output already exists or is a symbolic link"
        )
    if _has_symlink_ancestor(requested.parent) or not requested.parent.is_dir():
        raise CandidateNominationError(
            "candidate nomination output parent is unavailable"
        )
    target = requested.resolve(strict=False)
    checkout = ROOT.resolve()
    rehearsal_root = rehearsal.resolve(strict=True)
    if (
        target == checkout
        or checkout in target.parents
        or target == rehearsal_root
        or rehearsal_root in target.parents
    ):
        raise CandidateNominationError(
            "candidate nomination output must be outside the checkout and rehearsal"
        )
    try:
        parent_descriptor = os.open(target.parent, _directory_flags())
    except OSError as exc:
        raise CandidateNominationError(
            "candidate nomination output parent is unavailable"
        ) from exc
    try:
        parent_metadata = os.fstat(parent_descriptor)
        parent_identity = _file_identity(parent_metadata)
        _require(
            stat.S_ISDIR(parent_metadata.st_mode)
            and _live_parent_matches(target.parent, parent_identity),
            "candidate nomination output parent changed during validation",
        )
        protected = {
            _file_identity(os.stat(checkout, follow_symlinks=False)),
            _file_identity(os.stat(rehearsal_root, follow_symlinks=False)),
        }
        _require(
            not _directory_has_ancestor(parent_descriptor, protected),
            "candidate nomination output must be outside the checkout and rehearsal",
        )
        try:
            os.stat(
                target.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise CandidateNominationError(
                "candidate nomination output already exists or is a symbolic link"
            )
    except Exception:
        os.close(parent_descriptor)
        raise
    return target, parent_descriptor, parent_identity


def _unlink_if_identity(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int],
) -> None:
    try:
        metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if _file_identity(metadata) == expected_identity:
            os.unlink(name, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
    except OSError:
        pass


def _temporary_file(parent_descriptor: int, target_name: str) -> tuple[int, str]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
    )
    for _ in range(16):
        name = f".{target_name}.{secrets.token_hex(16)}.tmp"
        try:
            return os.open(name, flags, 0o600, dir_fd=parent_descriptor), name
        except FileExistsError:
            continue
    raise CandidateNominationError(
        "cannot allocate candidate nomination staging file"
    )


def _write_record(
    parent_descriptor: int, target_name: str, record: dict
) -> tuple[int, int]:
    content = _canonical(record)
    temporary: str | None = None
    publication_identity: tuple[int, int] | None = None
    try:
        descriptor, temporary = _temporary_file(parent_descriptor, target_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        publication_identity = _file_identity(
            os.stat(
                temporary,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        )
        os.link(
            temporary,
            target_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        os.fsync(parent_descriptor)
        return publication_identity
    except FileExistsError as exc:
        raise CandidateNominationError(
            "candidate nomination output appeared during publication"
        ) from exc
    except OSError as exc:
        if publication_identity is not None:
            _unlink_if_identity(
                parent_descriptor, target_name, publication_identity
            )
        raise CandidateNominationError(
            "cannot publish candidate nomination output"
        ) from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except (FileNotFoundError, OSError):
                pass


def _load_canonical_at(
    parent_descriptor: int, name: str, limit: int, label: str
) -> tuple[dict, bytes]:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            _require(
                stat.S_ISREG(metadata.st_mode),
                f"{label} must be a regular file",
            )
            content = stream.read(limit + 1)
    except CandidateNominationError:
        raise
    except OSError as exc:
        raise CandidateNominationError(f"{label} cannot be read") from exc
    _require(0 < len(content) <= limit, f"{label} exceeds its size bound")
    return _decode_canonical(content, label)


def _readiness_snapshot(rehearsal: Path) -> dict:
    readiness, _ = _load_canonical(
        rehearsal / "sources/release-readiness.json",
        2_097_152,
        "release-readiness source record",
    )
    defects = readiness.get("defects")
    _require(type(defects) is dict, "release-readiness defect inventory changed")
    required = {
        "open_count",
        "open_release_blockers",
        "snapshot_age_at_assessment_seconds",
        "snapshot_at_utc",
    }
    _require(set(defects) == required, "release-readiness defect inventory changed")
    _require(
        type(defects["open_count"]) is int and defects["open_count"] >= 0,
        "release-readiness open defect count is invalid",
    )
    blockers = defects["open_release_blockers"]
    _require(
        type(blockers) is list
        and all(type(item) is int and item > 0 for item in blockers)
        and blockers == sorted(set(blockers)),
        "release-readiness blocker inventory is invalid",
    )
    snapshot_at = _utc_timestamp(
        defects["snapshot_at_utc"], "release-readiness snapshot_at_utc"
    )
    return {
        "open_count": defects["open_count"],
        "open_release_blockers": blockers,
        "snapshot_at_utc": snapshot_at,
    }


def _seconds_between(earlier: str, later: str, label: str) -> int:
    first = datetime.fromisoformat(_utc_timestamp(earlier, f"{label} start"))
    second = datetime.fromisoformat(_utc_timestamp(later, f"{label} end"))
    _require(first <= second, f"{label} chronology is invalid")
    delta = second - first
    return delta.days * 86_400 + delta.seconds


def _expected_rehearsal(rehearsal: Path, receipt: dict) -> dict:
    _require(
        receipt["status"] == "packet_complete_for_m4_review"
        and receipt["packet_status"] == "packet_complete_for_m4_review"
        and receipt["release_blockers"] == [],
        "blocked review rehearsal cannot be engineering-nominated",
    )
    receipt_path = rehearsal / release_review_rehearsal.RECEIPT_NAME
    packet_path = rehearsal / release_review_rehearsal.PACKET_NAME
    return {
        "component_statuses": receipt["component_statuses"],
        "generated_at_utc": receipt["generated_at_utc"],
        "packet": _identity(packet_path, MAX_PACKET_BYTES, "M4 review packet"),
        "packet_status": receipt["packet_status"],
        "receipt": _identity(receipt_path, MAX_JSON_BYTES, "review rehearsal receipt"),
        "release_blockers": [],
    }


def _validate_nomination(
    record: dict,
    *,
    rehearsal: Path,
    expected_content: bytes | None = None,
) -> dict:
    _object(record, _NOMINATION_FIELDS, "candidate nomination")
    _require(
        type(record["schema_version"]) is int
        and record["schema_version"] == 1
        and record["record_type"] == "chimera.m4-candidate-nomination"
        and record["nomination_id"] == NOMINATION_ID,
        "candidate nomination contract changed",
    )
    candidate = record["candidate_commit_sha"]
    _require(
        type(candidate) is str and _COMMIT.fullmatch(candidate) is not None,
        "candidate nomination commit is invalid",
    )
    generated = _utc_timestamp(record["generated_at_utc"], "nomination generated_at_utc")
    _require(
        record["engineering_state"] == "nominated_for_m4_review"
        and record["candidate_change_policy"] == CANDIDATE_CHANGE_POLICY,
        "candidate nomination engineering state changed",
    )
    _require(
        record["m4_decision"] == "pending"
        and record["m5_decision"] == "pending"
        and record["human_acceptance"] == "not_granted",
        "candidate nomination cannot record acceptance",
    )
    phases = _object(
        record["phase_dispositions"], _PHASE_FIELDS, "candidate nomination phases"
    )
    _require(
        all(value == "pending" for value in phases.values()),
        "candidate nomination cannot disposition P3/P4/P5",
    )
    _require(record["scope"] == SCOPE, "candidate nomination scope changed")

    ci, _ = _embedded_ci(record["hosted_ci"])
    _require(
        ci["candidate_commit_sha"] == candidate,
        "candidate nomination hosted CI candidate changed",
    )
    receipt = release_review_rehearsal.inspect_review_rehearsal(rehearsal)
    _require(
        receipt["candidate_commit_sha"] == candidate,
        "candidate nomination rehearsal candidate changed",
    )
    expected_rehearsal = _expected_rehearsal(rehearsal, receipt)
    _object(record["rehearsal"], _REHEARSAL_FIELDS, "candidate nomination rehearsal")
    for label in ("receipt", "packet"):
        identity = _object(
            record["rehearsal"][label],
            _IDENTITY_FIELDS,
            f"candidate nomination rehearsal {label}",
        )
        _require(
            type(identity["byte_count"]) is int
            and identity["byte_count"] > 0
            and type(identity["sha256"]) is str
            and _SHA256.fullmatch(identity["sha256"]) is not None,
            f"candidate nomination rehearsal {label} identity is invalid",
        )
    _require(
        record["rehearsal"] == expected_rehearsal,
        "candidate nomination rehearsal evidence changed",
    )

    snapshot = _readiness_snapshot(rehearsal)
    expected_snapshot = {
        **snapshot,
        "snapshot_age_at_nomination_seconds": _seconds_between(
            snapshot["snapshot_at_utc"], generated, "defect snapshot"
        ),
    }
    nomination_snapshot = _object(
        record["defect_snapshot"], _DEFECT_FIELDS, "candidate defect snapshot"
    )
    _require(
        type(nomination_snapshot["open_count"]) is int
        and nomination_snapshot["open_count"] >= 0,
        "candidate nomination open defect count is invalid",
    )
    nomination_blockers = nomination_snapshot["open_release_blockers"]
    _require(
        type(nomination_blockers) is list
        and all(type(item) is int and item > 0 for item in nomination_blockers)
        and nomination_blockers == sorted(set(nomination_blockers)),
        "candidate nomination blocker inventory is invalid",
    )
    _require(
        type(nomination_snapshot["snapshot_age_at_nomination_seconds"]) is int
        and nomination_snapshot["snapshot_age_at_nomination_seconds"] >= 0
        and nomination_snapshot == expected_snapshot,
        "candidate nomination defect snapshot changed",
    )
    _seconds_between(
        receipt["generated_at_utc"], generated, "rehearsal nomination"
    )
    _seconds_between(
        ci["inspected_at_utc"], generated, "hosted CI nomination"
    )
    if expected_content is not None:
        _require(
            _canonical(record) == expected_content,
            "candidate nomination is not canonical JSON",
        )
    return record


def nominate_candidate(
    output: str | Path,
    *,
    rehearsal_directory: str | Path,
    ci_evidence: str | Path,
    generated_at_utc: str | None = None,
) -> dict:
    """Publish an exact-SHA engineering nomination from reviewed inputs."""
    rehearsal = Path(rehearsal_directory)
    receipt = release_review_rehearsal.inspect_review_rehearsal(rehearsal)
    expected_rehearsal = _expected_rehearsal(rehearsal, receipt)
    ci_document, ci_content = _load_canonical(
        Path(ci_evidence), MAX_JSON_BYTES, "hosted CI evidence"
    )
    _validate_ci_document(ci_document, ci_content)
    candidate = receipt["candidate_commit_sha"]
    _require(
        ci_document["candidate_commit_sha"] == candidate,
        "hosted CI evidence does not match the rehearsal candidate",
    )
    generated = _generated_timestamp(generated_at_utc)
    _seconds_between(receipt["generated_at_utc"], generated, "rehearsal nomination")
    _seconds_between(ci_document["inspected_at_utc"], generated, "hosted CI nomination")
    snapshot = _readiness_snapshot(rehearsal)
    record = {
        "candidate_change_policy": CANDIDATE_CHANGE_POLICY,
        "candidate_commit_sha": candidate,
        "defect_snapshot": {
            **snapshot,
            "snapshot_age_at_nomination_seconds": _seconds_between(
                snapshot["snapshot_at_utc"], generated, "defect snapshot"
            ),
        },
        "engineering_state": "nominated_for_m4_review",
        "generated_at_utc": generated,
        "hosted_ci": {
            **ci_document,
            "evidence_sha256": sha256(ci_content).hexdigest(),
            "verification_boundary": CI_BOUNDARY,
        },
        "human_acceptance": "not_granted",
        "m4_decision": "pending",
        "m5_decision": "pending",
        "nomination_id": NOMINATION_ID,
        "phase_dispositions": {"p3": "pending", "p4": "pending", "p5": "pending"},
        "record_type": "chimera.m4-candidate-nomination",
        "rehearsal": expected_rehearsal,
        "schema_version": 1,
        "scope": SCOPE,
    }
    target, parent_descriptor, parent_identity = _validate_output(
        output, rehearsal
    )
    publication_identity: tuple[int, int] | None = None
    try:
        _validate_nomination(record, rehearsal=rehearsal)
        publication_identity = _write_record(
            parent_descriptor, target.name, record
        )
        reopened, saved = _load_canonical_at(
            parent_descriptor,
            target.name,
            MAX_JSON_BYTES,
            "candidate nomination",
        )
        validated = _validate_nomination(
            reopened, rehearsal=rehearsal, expected_content=saved
        )
        _require(
            _live_parent_matches(target.parent, parent_identity),
            "candidate nomination output parent changed during publication",
        )
        return validated
    except Exception:
        if publication_identity is not None:
            _unlink_if_identity(
                parent_descriptor, target.name, publication_identity
            )
        raise
    finally:
        os.close(parent_descriptor)


def inspect_candidate_nomination(
    nomination: str | Path, *, rehearsal_directory: str | Path
) -> dict:
    """Reinspect a nomination and its rehearsal without changing either."""
    record, content = _load_canonical(
        Path(nomination), MAX_JSON_BYTES, "candidate nomination"
    )
    return _validate_nomination(
        record,
        rehearsal=Path(rehearsal_directory),
        expected_content=content,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="build or inspect an exact-SHA M4 engineering nomination"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--rehearsal", required=True, type=Path)
    build.add_argument("--ci-evidence", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("nomination", type=Path)
    inspect.add_argument("--rehearsal", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            record = nominate_candidate(
                args.output,
                rehearsal_directory=args.rehearsal,
                ci_evidence=args.ci_evidence,
            )
            nomination_path = args.output
        else:
            record = inspect_candidate_nomination(
                args.nomination,
                rehearsal_directory=args.rehearsal,
            )
            nomination_path = args.nomination
        saved = _canonical(record)
    except (
        CandidateNominationError,
        release_review_rehearsal.ReviewRehearsalError,
        OSError,
    ) as exc:
        print(f"chimera candidate nomination: {exc}", file=sys.stderr)
        return 2
    print(f"engineering-state: {record['engineering_state']}")
    print(f"candidate-commit: {record['candidate_commit_sha']}")
    print(f"nomination-record: {nomination_path.resolve(strict=False)}")
    print(f"nomination-sha256: {sha256(saved).hexdigest()}")
    print(f"receipt-sha256: {record['rehearsal']['receipt']['sha256']}")
    print(f"packet-sha256: {record['rehearsal']['packet']['sha256']}")
    print(
        "Engineering nomination only; P3/P4/P5, M4/M5 and human acceptance "
        "remain pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
