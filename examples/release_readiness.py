"""Assemble exact-candidate inputs for Chimera's bounded M4 review.

This control proves that the repository's requirement inventory, dated defect
snapshot, and required guide headings are complete and candidate-bound.  It does
not declare a release candidate, close a phase, or grant human acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "release-readiness-v1.json"
MANIFEST_REPOSITORY_PATH = "docs/release-readiness-v1.json"
MANIFEST_ID = "p7-local-prototype-release-readiness-v1"

_COMMIT = re.compile(r"[0-9a-f]{40}")
_GROUP = re.compile(r"GROUP-[0-9]{3}")
_REQUIREMENT = re.compile(
    r"^\|\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[0-9]{3})\s*\|",
    re.MULTILINE,
)
_DISPOSITIONS = {"fixed_verified_pending_pr_integration", "unresolved"}
_SEVERITIES = {"blocker", "major", "minor"}
_EXPECTED_OPEN_DEFECTS = {
    4: "Defect: mutable dependency list can bypass failure blocking",
    14: "Defect: ambient Decimal exponent case changes deterministic evidence identity",
}
_EXPECTED_GUIDE_PATHS = (
    "README.md",
    "docs/MANUAL.md",
    "docs/APPROVALS.md",
    "docs/QUALITY.md",
    "docs/THREAT_MODEL.md",
    "docs/reviews/2026-10-24-p345-operator-acceptance.md",
)
_PURPOSE = (
    "Prepare exact-candidate requirement, defect and guide inputs for M4 review "
    "without declaring release readiness or human acceptance"
)
_INCLUDED = (
    "Every requirement identifier declared as a table row in docs/REQUIREMENTS.md",
    "Open GitHub defect issues observed through the connected repository integration",
    "Required headings in the operator, acceptance, quality and threat-model guides",
)
_LIMITATIONS = (
    "The defect inventory is a dated snapshot and must be refreshed before M4 disposition",
    "Tracked file identity and heading presence do not prove that a test passed or a guide is usable",
    "Manual-device, screen-reader, operator and PM observations remain separate human evidence",
    "This control does not tag, merge, publish, deploy or approve the prototype",
)
_PENDING_HUMAN_EVIDENCE = (
    "D-004 through D-006 interface decisions",
    "Leo operator walkthrough",
    "M4 entry-to-acceptance decision",
    "M5 final product acceptance",
    "Manual physical-device observations",
    "Screen-reader and WCAG observations",
    "Separate P3, P4 and P5 dispositions",
)


class ReleaseReadinessError(RuntimeError):
    """The release-readiness assessment could not be produced safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseReadinessError(message)


def _canonical(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False,
    ) + "\n").encode("utf-8")


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ReleaseReadinessError(f"duplicate JSON field: {key}")
        document[key] = value
    return document


def _load_canonical_json(path: Path, maximum_bytes: int) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ReleaseReadinessError("JSON document must be a regular file")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ReleaseReadinessError("JSON document is unavailable") from exc
    _require(0 < len(content) <= maximum_bytes,
             "JSON document size is outside the supported bound")
    try:
        document = json.loads(
            content.decode("utf-8"), object_pairs_hook=_reject_duplicate_fields,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ReleaseReadinessError(f"non-finite JSON value: {value}")
            ),
        )
        canonical = _canonical(document)
    except ReleaseReadinessError:
        raise
    except (RecursionError, UnicodeError, ValueError) as exc:
        raise ReleaseReadinessError("document is not strict UTF-8 JSON") from exc
    _require(type(document) is dict, "JSON document must be an object")
    _require(content == canonical, "JSON document must use canonical formatting")
    return document, content


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *arguments], cwd=ROOT, capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseReadinessError("Git checkout identity is unavailable") from exc


def _validate_candidate_checkout(candidate_commit: str) -> None:
    if type(candidate_commit) is not str or _COMMIT.fullmatch(candidate_commit) is None:
        raise ReleaseReadinessError(
            "candidate commit must be a full lowercase 40-character Git SHA"
        )
    head = _git("rev-parse", "HEAD")
    actual = head.stdout.strip()
    if (head.returncode != 0 or _COMMIT.fullmatch(actual) is None
            or actual != candidate_commit):
        raise ReleaseReadinessError(
            "candidate commit must equal the exact checked-out Git HEAD"
        )
    status = _git("status", "--porcelain", "--untracked-files=normal")
    if status.returncode != 0:
        raise ReleaseReadinessError("Git checkout status is unavailable")
    if status.stdout:
        raise ReleaseReadinessError(
            "release-readiness assessment requires a clean checkout"
        )


def _timestamp_text(value: object, location: str) -> str:
    if type(value) is not str:
        raise ReleaseReadinessError(f"{location} must be UTC timestamp text")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReleaseReadinessError(
            f"{location} must be canonical UTC timestamp text"
        ) from exc
    if (parsed.tzinfo != timezone.utc
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise ReleaseReadinessError(
            f"{location} must be canonical UTC timestamp text"
        )
    return value


def _generated_timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    return _timestamp_text(value, "generated_at_utc")


def _object(value: object, keys: set[str], location: str) -> dict:
    _require(type(value) is dict, f"{location} must be an object")
    _require(set(value) == keys,
             f"{location} fields changed: expected {sorted(keys)}, got {sorted(value)}")
    return value


def _text(value: object, location: str, maximum: int = 2_000) -> str:
    _require(type(value) is str, f"{location} must be text")
    _require(value == value.strip() and 0 < len(value) <= maximum and "\x00" not in value,
             f"{location} must be nonempty trimmed text")
    return value


def _text_list(value: object, location: str, minimum: int = 1) -> list[str]:
    _require(type(value) is list and len(value) >= minimum,
             f"{location} must contain at least {minimum} item(s)")
    result = [_text(item, f"{location}[{index}]")
              for index, item in enumerate(value)]
    _require(len(set(result)) == len(result), f"{location} contains duplicates")
    return result


def _tracked_repository_paths() -> set[str]:
    result = _git("ls-tree", "-r", "--name-only", "-z", "HEAD")
    if result.returncode != 0:
        raise ReleaseReadinessError("candidate repository paths are unavailable")
    return {item for item in result.stdout.split("\x00") if item}


def _declared_requirement_ids() -> list[str]:
    path = ROOT / "docs" / "REQUIREMENTS.md"
    if path.is_symlink() or not path.is_file():
        raise ReleaseReadinessError("requirements traceability document is unavailable")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReleaseReadinessError(
            "requirements traceability document is unavailable"
        ) from exc
    identifiers = _REQUIREMENT.findall(content)
    _require(bool(identifiers), "requirements traceability document has no table rows")
    _require(len(identifiers) == len(set(identifiers)),
             "requirements traceability document has duplicate identifiers")
    return sorted(identifiers)


def _repository_file(value: object, location: str,
                     tracked: set[str]) -> tuple[str, bytes, dict]:
    text = _text(value, location, 240)
    _require("\\" not in text and "://" not in text,
             f"{location} must use repository POSIX syntax")
    path = PurePosixPath(text)
    _require(not path.is_absolute() and bool(path.parts)
             and all(part not in ("", ".", "..") for part in path.parts),
             f"{location} must not traverse the repository")
    _require(text in tracked, f"{location} is not tracked in the candidate")
    candidate = ROOT.joinpath(*path.parts)
    _require(not candidate.is_symlink() and candidate.is_file(),
             f"{location} must name a tracked regular file")
    try:
        candidate.resolve(strict=True).relative_to(ROOT.resolve(strict=True))
        content = candidate.read_bytes()
    except (OSError, ValueError) as exc:
        raise ReleaseReadinessError(f"{location} escapes or is unavailable") from exc
    return text, content, {
        "byte_count": len(content),
        "path": text,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _validate_manifest(
    document: dict,
    *,
    tracked_paths: set[str] | None = None,
    requirement_ids: list[str] | None = None,
) -> dict:
    tracked = _tracked_repository_paths() if tracked_paths is None else tracked_paths
    declared = (_declared_requirement_ids()
                if requirement_ids is None else sorted(requirement_ids))
    _require(MANIFEST_REPOSITORY_PATH in tracked,
             "fixed release-readiness manifest is not tracked in the candidate")
    root = _object(document, {
        "defect_snapshot", "guide_checks", "manifest_id", "record_type",
        "release_review", "requirement_groups", "schema_version", "scope",
    }, "release-readiness manifest")
    _require(type(root["schema_version"]) is int and root["schema_version"] == 1,
             "release-readiness schema version must be integer 1")
    _require(root["record_type"] == "chimera.local-prototype-release-readiness",
             "release-readiness record type changed")
    _require(root["manifest_id"] == MANIFEST_ID,
             "release-readiness manifest identity changed")

    scope = _object(root["scope"], {"included", "limitations", "purpose"}, "scope")
    _require(scope["purpose"] == _PURPOSE,
             "scope.purpose changed without a new manifest version")
    for field, expected in (("included", _INCLUDED), ("limitations", _LIMITATIONS)):
        _text_list(scope[field], f"scope.{field}", len(expected))
        _require(scope[field] == list(expected),
                 f"scope.{field} changed without a new manifest version")

    evidence_files: dict[str, dict] = {}
    groups = root["requirement_groups"]
    _require(type(groups) is list and 1 <= len(groups) <= 64,
             "requirement_groups must contain 1..64 items")
    group_ids: list[str] = []
    covered: list[str] = []
    for index, item in enumerate(groups):
        location = f"requirement_groups[{index}]"
        group = _object(item, {
            "evidence_paths", "group_id", "requirement_ids",
        }, location)
        group_id = _text(group["group_id"], location + ".group_id", 16)
        _require(_GROUP.fullmatch(group_id) is not None,
                 f"{location}.group_id is invalid")
        group_ids.append(group_id)
        ids = group["requirement_ids"]
        _require(type(ids) is list and bool(ids),
                 f"{location}.requirement_ids must be nonempty")
        local_ids = []
        for requirement_index, requirement in enumerate(ids):
            identifier = _text(
                requirement,
                f"{location}.requirement_ids[{requirement_index}]",
                32,
            )
            _require(_REQUIREMENT.fullmatch(f"| {identifier} |") is not None,
                     f"{location} has an invalid requirement identifier")
            local_ids.append(identifier)
        _require(local_ids == sorted(set(local_ids)),
                 f"{location}.requirement_ids must be sorted and unique")
        covered.extend(local_ids)
        paths = group["evidence_paths"]
        _require(type(paths) is list and 1 <= len(paths) <= 24,
                 f"{location}.evidence_paths must contain 1..24 items")
        local_paths = []
        for path_index, path in enumerate(paths):
            evidence_path, _, identity = _repository_file(
                path, f"{location}.evidence_paths[{path_index}]", tracked
            )
            local_paths.append(evidence_path)
            evidence_files[evidence_path] = identity
        _require(local_paths == sorted(set(local_paths)),
                 f"{location}.evidence_paths must be sorted and unique")
    _require(group_ids == sorted(set(group_ids)),
             "requirement_groups must be ordered and unique by group_id")
    _require(len(covered) == len(set(covered)),
             "a requirement is assigned to more than one group")
    missing = sorted(set(declared) - set(covered))
    extra = sorted(set(covered) - set(declared))
    _require(not missing and not extra,
             f"requirement coverage mismatch: missing={missing}, extra={extra}")

    snapshot = _object(root["defect_snapshot"], {
        "github_repository", "observed_at_utc", "open_defects", "source",
    }, "defect_snapshot")
    _require(snapshot["github_repository"] == "lvlunario/project-chimera",
             "defect snapshot repository changed")
    _timestamp_text(snapshot["observed_at_utc"], "defect_snapshot.observed_at_utc")
    _require(snapshot["source"] == "connected GitHub issue search",
             "defect snapshot source changed")
    defects = snapshot["open_defects"]
    _require(type(defects) is list, "defect_snapshot.open_defects must be a list")
    defect_numbers: list[int] = []
    blocker_numbers: list[int] = []
    for index, item in enumerate(defects):
        location = f"defect_snapshot.open_defects[{index}]"
        defect = _object(item, {
            "engineering_disposition", "evidence_paths", "github_state",
            "issue_number", "release_blocker", "severity", "title",
        }, location)
        number = defect["issue_number"]
        _require(type(number) is int and 1 <= number <= 1_000_000,
                 f"{location}.issue_number is invalid")
        defect_numbers.append(number)
        title = _text(defect["title"], location + ".title", 200)
        _require(title.startswith("Defect: "),
                 f"{location}.title is not a defect issue")
        _require(_EXPECTED_OPEN_DEFECTS.get(number) == title,
                 f"{location} is not part of the fixed v1 defect snapshot")
        _require(defect["github_state"] == "open",
                 f"{location}.github_state must remain open in this snapshot")
        severity = _text(defect["severity"], location + ".severity", 16)
        _require(severity in _SEVERITIES, f"{location}.severity is invalid")
        disposition = _text(
            defect["engineering_disposition"],
            location + ".engineering_disposition",
            64,
        )
        _require(disposition in _DISPOSITIONS,
                 f"{location}.engineering_disposition is invalid")
        blocker = defect["release_blocker"]
        _require(type(blocker) is bool,
                 f"{location}.release_blocker must be Boolean")
        _require(
            blocker == (disposition == "unresolved"),
            f"{location} blocker status conflicts with engineering disposition",
        )
        if blocker:
            blocker_numbers.append(number)
        paths = defect["evidence_paths"]
        _require(type(paths) is list and bool(paths),
                 f"{location}.evidence_paths must be nonempty")
        local_paths = []
        for path_index, path in enumerate(paths):
            evidence_path, _, identity = _repository_file(
                path, f"{location}.evidence_paths[{path_index}]", tracked
            )
            local_paths.append(evidence_path)
            evidence_files[evidence_path] = identity
        _require(local_paths == sorted(set(local_paths)),
                 f"{location}.evidence_paths must be sorted and unique")
    _require(defect_numbers == sorted(set(defect_numbers)),
             "open defects must be ordered and unique by issue number")
    _require(defect_numbers == sorted(_EXPECTED_OPEN_DEFECTS),
             "fixed v1 open-defect snapshot is incomplete")

    guides = root["guide_checks"]
    _require(type(guides) is list and bool(guides),
             "guide_checks must be nonempty")
    guide_ids: list[str] = []
    guide_paths: list[str] = []
    heading_count = 0
    guide_summaries = []
    for index, item in enumerate(guides):
        location = f"guide_checks[{index}]"
        guide = _object(item, {
            "guide_id", "path", "required_headings",
        }, location)
        guide_id = _text(guide["guide_id"], location + ".guide_id", 16)
        _require(re.fullmatch(r"GUIDE-[0-9]{3}", guide_id) is not None,
                 f"{location}.guide_id is invalid")
        guide_ids.append(guide_id)
        path, content, identity = _repository_file(
            guide["path"], location + ".path", tracked
        )
        guide_paths.append(path)
        evidence_files[path] = identity
        try:
            lines = content.decode("utf-8").splitlines()
        except UnicodeError as exc:
            raise ReleaseReadinessError(f"{location}.path is not UTF-8 text") from exc
        headings = _text_list(
            guide["required_headings"], location + ".required_headings"
        )
        position = -1
        for heading_index, heading in enumerate(headings):
            _require(heading.startswith("#") and " " in heading,
                     f"{location}.required_headings[{heading_index}] is invalid")
            try:
                position = lines.index(heading, position + 1)
            except ValueError as exc:
                raise ReleaseReadinessError(
                    f"{path} is missing required heading: {heading}"
                ) from exc
        heading_count += len(headings)
        guide_summaries.append({
            "guide_id": guide_id,
            "heading_count": len(headings),
            "path": path,
        })
    _require(guide_ids == sorted(set(guide_ids)),
             "guide_checks must be ordered and unique by guide_id")
    _require(guide_paths == list(_EXPECTED_GUIDE_PATHS),
             "fixed v1 guide inventory is incomplete or reordered")

    review = _object(root["release_review"], {
        "human_acceptance", "m4_decision", "m5_decision",
        "open_release_blockers", "pending_human_evidence",
    }, "release_review")
    _require(review["human_acceptance"] == "not_granted",
             "human acceptance must not be inferred")
    _require(review["m4_decision"] == "pending",
             "M4 decision must remain pending")
    _require(review["m5_decision"] == "pending",
             "M5 decision must remain pending")
    pending = _text_list(
        review["pending_human_evidence"],
        "release_review.pending_human_evidence",
        len(_PENDING_HUMAN_EVIDENCE),
    )
    _require(pending == list(_PENDING_HUMAN_EVIDENCE),
             "pending human evidence changed without a new manifest version")
    blockers = review["open_release_blockers"]
    _require(type(blockers) is list
             and all(type(item) is int for item in blockers),
             "release_review.open_release_blockers must be an integer list")
    _require(blockers == sorted(set(blockers)),
             "release_review.open_release_blockers must be sorted and unique")
    _require(blockers == blocker_numbers,
             "release blocker list does not match defect dispositions")

    return {
        "defect_count": len(defect_numbers),
        "defect_snapshot_at_utc": snapshot["observed_at_utc"],
        "evidence_files": [evidence_files[path] for path in sorted(evidence_files)],
        "guide_count": len(guide_ids),
        "guide_heading_count": heading_count,
        "guide_summaries": guide_summaries,
        "open_release_blockers": blockers,
        "pending_human_evidence": pending,
        "requirement_count": len(declared),
        "requirement_group_count": len(group_ids),
    }


def _has_symlink_ancestor(path: Path) -> bool:
    current = path
    while True:
        if current.is_symlink():
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _write_record(target: Path, record: dict) -> None:
    content = _canonical(record)
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    except FileExistsError as exc:
        raise ReleaseReadinessError(
            "release-readiness assessment output already exists or is a symbolic link"
        ) from exc
    except OSError as exc:
        raise ReleaseReadinessError(
            "cannot publish release-readiness assessment output"
        ) from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except (FileNotFoundError, OSError):
                pass
    reopened, saved = _load_canonical_json(target, 1_048_576)
    _require(reopened == record and saved == content,
             "release-readiness assessment output did not reopen canonically")


def _build_assessment(
    *, candidate_commit: str, generated_at_utc: str,
    manifest_content: bytes, summary: dict,
) -> dict:
    snapshot_at = datetime.fromisoformat(summary["defect_snapshot_at_utc"])
    generated_at = datetime.fromisoformat(generated_at_utc)
    _require(snapshot_at <= generated_at,
             "defect snapshot cannot be later than assessment generation")
    blocked = bool(summary["open_release_blockers"])
    return {
        "candidate_checks": {
            "before_assessment": "matched_clean_head",
            "before_publication": "matched_clean_head",
        },
        "candidate_commit_sha": candidate_commit,
        "checks": [
            {
                "description": "every declared requirement is covered exactly once",
                "id": "READINESS-001",
                "status": "passed",
            },
            {
                "description": "the dated open-defect inventory and blocker dispositions agree",
                "id": "READINESS-002",
                "status": "blocked" if blocked else "passed",
            },
            {
                "description": "required operator and release guide headings are present",
                "id": "READINESS-003",
                "status": "passed",
            },
            {
                "description": "manifest and evidence identities are bound to the exact clean candidate",
                "id": "READINESS-004",
                "status": "passed",
            },
            {
                "description": "human observations and M4/M5 decisions remain explicitly pending",
                "id": "READINESS-005",
                "status": "passed",
            },
        ],
        "defects": {
            "open_count": summary["defect_count"],
            "open_release_blockers": summary["open_release_blockers"],
            "snapshot_at_utc": summary["defect_snapshot_at_utc"],
        },
        "evidence_files": summary["evidence_files"],
        "generated_at_utc": generated_at_utc,
        "guides": {
            "guide_count": summary["guide_count"],
            "required_heading_count": summary["guide_heading_count"],
            "summaries": summary["guide_summaries"],
        },
        "human_acceptance": "not_granted",
        "m4_decision": "pending",
        "m5_decision": "pending",
        "manifest": {
            "byte_count": len(manifest_content),
            "id": MANIFEST_ID,
            "path": MANIFEST_REPOSITORY_PATH,
            "sha256": hashlib.sha256(manifest_content).hexdigest(),
        },
        "pending_human_evidence": summary["pending_human_evidence"],
        "record_type": "chimera.release-readiness-assessment",
        "requirements": {
            "covered_count": summary["requirement_count"],
            "declared_count": summary["requirement_count"],
            "group_count": summary["requirement_group_count"],
        },
        "schema_version": 1,
        "scope": (
            "candidate-bound M4 review inputs only; not a live GitHub query, test-result "
            "claim, release declaration, phase closure, tag, deployment or human acceptance"
        ),
        "status": "release_blockers_present" if blocked else "review_inputs_complete",
    }


def assess_release_readiness(
    output: str | Path, *, candidate_commit: str,
    generated_at_utc: str | None = None,
) -> dict:
    """Validate the fixed manifest and publish an exact-candidate assessment."""
    _validate_candidate_checkout(candidate_commit)
    target = Path(output)
    if target.is_symlink() or target.exists():
        raise ReleaseReadinessError(
            "release-readiness assessment output already exists or is a symbolic link"
        )
    if _has_symlink_ancestor(target.parent) or not target.parent.is_dir():
        raise ReleaseReadinessError(
            "release-readiness assessment output parent is unavailable"
        )
    resolved = target.resolve(strict=False)
    checkout = ROOT.resolve()
    if resolved == checkout or checkout in resolved.parents:
        raise ReleaseReadinessError(
            "release-readiness assessment output must be outside the source checkout"
        )
    document, manifest_content = _load_canonical_json(MANIFEST_PATH, 262_144)
    summary = _validate_manifest(document)
    record = _build_assessment(
        candidate_commit=candidate_commit,
        generated_at_utc=_generated_timestamp(generated_at_utc),
        manifest_content=manifest_content,
        summary=summary,
    )
    _validate_candidate_checkout(candidate_commit)
    _write_record(resolved, record)
    return record


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="assemble exact-candidate inputs for bounded M4 review"
    )
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        record = assess_release_readiness(
            args.output, candidate_commit=args.candidate_commit
        )
    except ReleaseReadinessError as exc:
        print(f"chimera release readiness: {exc}", file=sys.stderr)
        return 2
    for check in record["checks"]:
        label = "PASS" if check["status"] == "passed" else check["status"].upper()
        print(f"{label} {check['id']}: {check['description']}")
    print(f"candidate-commit: {args.candidate_commit}")
    print(f"manifest-sha256: {record['manifest']['sha256']}")
    print(f"release-readiness-assessment: {args.output.resolve(strict=False)}")
    print("M4 review inputs only; M4/M5 decisions and human acceptance remain pending")
    return 0 if record["status"] == "review_inputs_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
