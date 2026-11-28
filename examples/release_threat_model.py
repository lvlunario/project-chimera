"""Assess the bounded P7 local-prototype threat model at an exact commit.

This control checks model structure, candidate binding, and evidence references. It
does not prove that Chimera is secure, run a penetration test, or accept residual risk.
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
MODEL_PATH = ROOT / "docs" / "threat-model-v1.json"
MODEL_REPOSITORY_PATH = "docs/threat-model-v1.json"
MODEL_ID = "p7-local-prototype-threat-model-v1"

_COMMIT = re.compile(r"[0-9a-f]{40}")
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9]*-[0-9]{3}")
_REQUIREMENT = re.compile(r"\b[A-Z][A-Z0-9]*-[0-9]{3}\b")
_CATEGORIES = {
    "denial_of_service", "elevation_of_privilege", "information_disclosure",
    "repudiation", "spoofing", "supply_chain", "tampering",
}
_DISPOSITIONS = {"tracked_for_m4", "must_fix_before_m4"}
_LIKELIHOODS = {"low", "medium", "high"}
_IMPACTS = {"low", "medium", "high", "critical"}
_PROPERTIES = {"availability", "confidentiality", "integrity"}
_TRUST = {"external_dependency", "trusted", "untrusted_data", "untrusted_local"}
_DEPLOYMENT = (
    "One authorized operator on one trusted local host using local files, loopback HTTP "
    "and synthetic or separately authorized data"
)
_INCLUDED = (
    "Strict workflow, telemetry and fault-plan input boundaries",
    "Durable execution, completed evidence, reports, handoff and read-only dashboard",
    "Repository-level acceptance, performance and release evidence controls",
)
_EXCLUDED = (
    "Remote hosting, accounts, multi-user isolation, TLS and production service operation",
    "Sandboxing arbitrary Python callbacks, general exactly-once external effects and hostile-host filesystem defense",
    "Digital signatures, trusted time, build attestation, measurement authenticity, live hardware and certification",
    "Handoff transport, receiver-host security and authenticity across an untrusted channel",
)
_ASSUMPTIONS = (
    "The operator controls and protects the local host, checkout and output directories",
    "Typed product inputs are untrusted data, while Python callbacks and operation identities are trusted declarations",
    "Inputs contain no secrets or personal data unless a separately authorized confidentiality design is added",
    "Synthetic fixtures establish software behavior and never establish physical-radio performance",
)


class ThreatModelError(RuntimeError):
    """The threat-model assessment could not be produced safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ThreatModelError(message)


def _canonical(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False,
    ) + "\n").encode("utf-8")


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ThreatModelError(f"duplicate JSON field: {key}")
        document[key] = value
    return document


def _load_canonical_json(path: Path, maximum_bytes: int) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ThreatModelError("JSON document must be a regular file")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ThreatModelError("JSON document is unavailable") from exc
    _require(0 < len(content) <= maximum_bytes,
             "JSON document size is outside the supported bound")
    try:
        document = json.loads(
            content.decode("utf-8"), object_pairs_hook=_reject_duplicate_fields,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ThreatModelError(f"non-finite JSON value: {value}")
            ),
        )
        canonical = _canonical(document)
    except ThreatModelError:
        raise
    except (RecursionError, UnicodeError, ValueError) as exc:
        raise ThreatModelError("document is not strict UTF-8 JSON") from exc
    _require(type(document) is dict, "JSON document must be an object")
    _require(content == canonical,
             "JSON document must use canonical formatting")
    return document, content


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *arguments], cwd=ROOT, capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ThreatModelError("Git checkout identity is unavailable") from exc


def _validate_candidate_checkout(candidate_commit: str) -> None:
    if type(candidate_commit) is not str or _COMMIT.fullmatch(candidate_commit) is None:
        raise ThreatModelError(
            "candidate commit must be a full lowercase 40-character Git SHA"
        )
    head = _git("rev-parse", "HEAD")
    actual = head.stdout.strip()
    if (head.returncode != 0 or _COMMIT.fullmatch(actual) is None
            or actual != candidate_commit):
        raise ThreatModelError(
            "candidate commit must equal the exact checked-out Git HEAD"
        )
    status = _git("status", "--porcelain", "--untracked-files=normal")
    if status.returncode != 0:
        raise ThreatModelError("Git checkout status is unavailable")
    if status.stdout:
        raise ThreatModelError("threat-model assessment requires a clean checkout")


def _timestamp_text(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ThreatModelError(
            "generated_at_utc must be canonical UTC timestamp text"
        ) from exc
    if (parsed.tzinfo != timezone.utc
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise ThreatModelError(
            "generated_at_utc must be canonical UTC timestamp text"
        )
    return value


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


def _identifier(value: object, prefix: str, location: str) -> str:
    text = _text(value, location, 32)
    _require(_IDENTIFIER.fullmatch(text) is not None
             and text.startswith(prefix + "-"),
             f"{location} must be a canonical {prefix} identifier")
    return text


def _text_list(value: object, location: str, minimum: int = 1) -> list[str]:
    _require(type(value) is list and len(value) >= minimum,
             f"{location} must contain at least {minimum} item(s)")
    result = [_text(item, f"{location}[{index}]")
              for index, item in enumerate(value)]
    _require(len(set(result)) == len(result), f"{location} contains duplicates")
    return result


def _id_list(value: object, prefix: str, location: str) -> list[str]:
    _require(type(value) is list and bool(value), f"{location} must be nonempty")
    result = [_identifier(item, prefix, f"{location}[{index}]")
              for index, item in enumerate(value)]
    _require(result == sorted(set(result)),
             f"{location} must be sorted and unique")
    return result


def _requirement_list(value: object, location: str,
                      declared: set[str]) -> list[str]:
    _require(type(value) is list and bool(value), f"{location} must be nonempty")
    result = []
    for index, item in enumerate(value):
        text = _text(item, f"{location}[{index}]", 32)
        _require(_IDENTIFIER.fullmatch(text) is not None,
                 f"{location}[{index}] is not a requirement identifier")
        result.append(text)
    _require(result == sorted(set(result)),
             f"{location} must be sorted and unique")
    _require(set(result) <= declared,
             f"{location} references an undeclared requirement")
    return result


def _tracked_repository_paths() -> set[str]:
    result = _git("ls-tree", "-r", "--name-only", "-z", "HEAD")
    if result.returncode != 0:
        raise ThreatModelError("candidate repository paths are unavailable")
    return {item for item in result.stdout.split("\x00") if item}


def _declared_requirement_ids() -> set[str]:
    path = ROOT / "docs" / "REQUIREMENTS.md"
    if path.is_symlink() or not path.is_file():
        raise ThreatModelError("requirements traceability document is unavailable")
    try:
        return set(_REQUIREMENT.findall(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError) as exc:
        raise ThreatModelError("requirements traceability document is unavailable") from exc


def _evidence_file(value: object, location: str,
                   tracked: set[str]) -> tuple[str, dict]:
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
        raise ThreatModelError(f"{location} escapes or is unavailable") from exc
    return text, {
        "path": text,
        "byte_count": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _validate_model(
    document: dict,
    *,
    tracked_paths: set[str] | None = None,
    requirement_ids: set[str] | None = None,
) -> dict:
    tracked = _tracked_repository_paths() if tracked_paths is None else tracked_paths
    declared = _declared_requirement_ids() if requirement_ids is None else requirement_ids
    _require(MODEL_REPOSITORY_PATH in tracked,
             "fixed threat-model document is not tracked in the candidate")
    root = _object(document, {
        "actors", "assets", "model_id", "record_type", "release_review",
        "schema_version", "scope", "threats", "trust_boundaries",
    }, "threat model")
    _require(type(root["schema_version"]) is int and root["schema_version"] == 1,
             "threat-model schema version must be integer 1")
    _require(root["record_type"] == "chimera.local-prototype-threat-model",
             "threat-model record type changed")
    _require(root["model_id"] == MODEL_ID, "threat-model identity changed")

    scope = _object(root["scope"], {
        "assumptions", "deployment", "excluded", "included",
    }, "scope")
    _require(scope["deployment"] == _DEPLOYMENT,
             "scope.deployment changed without a new model version")
    for field, expected in (
        ("included", _INCLUDED),
        ("excluded", _EXCLUDED),
        ("assumptions", _ASSUMPTIONS),
    ):
        _text_list(scope[field], f"scope.{field}", len(expected))
        _require(scope[field] == list(expected),
                 f"scope.{field} changed without a new model version")

    assets = root["assets"]
    _require(type(assets) is list and bool(assets), "assets must be nonempty")
    asset_ids: set[str] = set()
    for index, item in enumerate(assets):
        asset = _object(item, {
            "description", "id", "name", "security_properties",
        }, f"assets[{index}]")
        identifier = _identifier(asset["id"], "ASSET", f"assets[{index}].id")
        _require(identifier not in asset_ids, f"duplicate asset: {identifier}")
        asset_ids.add(identifier)
        _text(asset["name"], f"assets[{index}].name")
        _text(asset["description"], f"assets[{index}].description")
        properties = _text_list(
            asset["security_properties"], f"assets[{index}].security_properties"
        )
        _require(properties == sorted(properties) and set(properties) <= _PROPERTIES,
                 f"assets[{index}].security_properties are invalid")
    _require([item["id"] for item in assets] == sorted(asset_ids),
             "assets must be ordered by identifier")

    actors = root["actors"]
    _require(type(actors) is list and bool(actors), "actors must be nonempty")
    actor_ids: set[str] = set()
    for index, item in enumerate(actors):
        actor = _object(item, {
            "description", "id", "name", "trust",
        }, f"actors[{index}]")
        identifier = _identifier(actor["id"], "ACTOR", f"actors[{index}].id")
        _require(identifier not in actor_ids, f"duplicate actor: {identifier}")
        actor_ids.add(identifier)
        _text(actor["name"], f"actors[{index}].name")
        _text(actor["description"], f"actors[{index}].description")
        trust = _text(actor["trust"], f"actors[{index}].trust", 32)
        _require(trust in _TRUST, f"actors[{index}].trust is invalid")
    _require([item["id"] for item in actors] == sorted(actor_ids),
             "actors must be ordered by identifier")

    boundaries = root["trust_boundaries"]
    _require(type(boundaries) is list and bool(boundaries),
             "trust_boundaries must be nonempty")
    boundary_ids: set[str] = set()
    referenced_actors: set[str] = set()
    for index, item in enumerate(boundaries):
        boundary = _object(item, {
            "actor_ids", "asset_ids", "description", "id", "name",
        }, f"trust_boundaries[{index}]")
        identifier = _identifier(
            boundary["id"], "BOUNDARY", f"trust_boundaries[{index}].id"
        )
        _require(identifier not in boundary_ids,
                 f"duplicate trust boundary: {identifier}")
        boundary_ids.add(identifier)
        _text(boundary["name"], f"trust_boundaries[{index}].name")
        _text(boundary["description"], f"trust_boundaries[{index}].description")
        boundary_actors = _id_list(
            boundary["actor_ids"], "ACTOR", f"trust_boundaries[{index}].actor_ids"
        )
        boundary_assets = _id_list(
            boundary["asset_ids"], "ASSET", f"trust_boundaries[{index}].asset_ids"
        )
        _require(set(boundary_actors) <= actor_ids,
                 f"trust_boundaries[{index}] references an unknown actor")
        _require(set(boundary_assets) <= asset_ids,
                 f"trust_boundaries[{index}] references an unknown asset")
        referenced_actors.update(boundary_actors)
    _require([item["id"] for item in boundaries] == sorted(boundary_ids),
             "trust boundaries must be ordered by identifier")
    _require(referenced_actors == actor_ids,
             "every actor must participate in a trust boundary")

    threats = root["threats"]
    _require(type(threats) is list and 1 <= len(threats) <= 64,
             "threats must contain 1..64 items")
    threat_ids: set[str] = set()
    control_ids: set[str] = set()
    referenced_assets: set[str] = set()
    referenced_boundaries: set[str] = set()
    evidence_files: dict[str, dict] = {}
    dispositions = {name: 0 for name in sorted(_DISPOSITIONS)}
    for index, item in enumerate(threats):
        threat = _object(item, {
            "asset_ids", "boundary_ids", "category", "controls",
            "engineering_disposition", "id", "impact", "impact_severity",
            "likelihood", "preconditions", "residual_risk", "title",
        }, f"threats[{index}]")
        identifier = _identifier(threat["id"], "RISK", f"threats[{index}].id")
        _require(identifier not in threat_ids, f"duplicate threat: {identifier}")
        threat_ids.add(identifier)
        _text(threat["title"], f"threats[{index}].title")
        category = _text(threat["category"], f"threats[{index}].category", 32)
        likelihood = _text(threat["likelihood"], f"threats[{index}].likelihood", 16)
        impact_severity = _text(
            threat["impact_severity"], f"threats[{index}].impact_severity", 16
        )
        _require(category in _CATEGORIES,
                 f"threats[{index}].category is invalid")
        _require(likelihood in _LIKELIHOODS,
                 f"threats[{index}].likelihood is invalid")
        _require(impact_severity in _IMPACTS,
                 f"threats[{index}].impact_severity is invalid")
        _text(threat["preconditions"], f"threats[{index}].preconditions")
        _text(threat["impact"], f"threats[{index}].impact")
        _text(threat["residual_risk"], f"threats[{index}].residual_risk")
        threat_assets = _id_list(
            threat["asset_ids"], "ASSET", f"threats[{index}].asset_ids"
        )
        threat_boundaries = _id_list(
            threat["boundary_ids"], "BOUNDARY", f"threats[{index}].boundary_ids"
        )
        _require(set(threat_assets) <= asset_ids,
                 f"threats[{index}] references an unknown asset")
        _require(set(threat_boundaries) <= boundary_ids,
                 f"threats[{index}] references an unknown boundary")
        referenced_assets.update(threat_assets)
        referenced_boundaries.update(threat_boundaries)
        disposition = _text(
            threat["engineering_disposition"],
            f"threats[{index}].engineering_disposition",
            32,
        )
        _require(disposition in _DISPOSITIONS,
                 f"threats[{index}].engineering_disposition is invalid")
        dispositions[disposition] += 1

        controls = threat["controls"]
        _require(type(controls) is list and 1 <= len(controls) <= 16,
                 f"threats[{index}].controls must contain 1..16 items")
        local_control_ids = []
        for control_index, item in enumerate(controls):
            location = f"threats[{index}].controls[{control_index}]"
            control = _object(item, {
                "description", "evidence_paths", "id", "requirement_ids",
            }, location)
            control_id = _identifier(control["id"], "CONTROL", location + ".id")
            _require(control_id not in control_ids,
                     f"duplicate control: {control_id}")
            control_ids.add(control_id)
            local_control_ids.append(control_id)
            _text(control["description"], location + ".description")
            _requirement_list(
                control["requirement_ids"], location + ".requirement_ids", declared
            )
            paths = control["evidence_paths"]
            _require(type(paths) is list and 1 <= len(paths) <= 16,
                     f"{location}.evidence_paths must contain 1..16 items")
            local_paths = []
            for path_index, path in enumerate(paths):
                evidence_path, identity = _evidence_file(
                    path, f"{location}.evidence_paths[{path_index}]", tracked
                )
                local_paths.append(evidence_path)
                evidence_files[evidence_path] = identity
            _require(local_paths == sorted(set(local_paths)),
                     f"{location}.evidence_paths must be sorted and unique")
        _require(local_control_ids == sorted(local_control_ids),
                 f"threats[{index}].controls must be ordered by identifier")
    _require([item["id"] for item in threats] == sorted(threat_ids),
             "threats must be ordered by identifier")
    _require(referenced_assets == asset_ids,
             "every asset must be covered by a threat")
    _require(referenced_boundaries == boundary_ids,
             "every trust boundary must be covered by a threat")
    _require(dispositions["tracked_for_m4"] > 0,
             "the model must preserve tracked residual risks")

    review = _object(root["release_review"], {
        "decision_status", "human_acceptance", "must_fix_before_m4", "notes",
    }, "release_review")
    _require(review["decision_status"] == "pending_m4_review",
             "M4 release decision must remain pending")
    _require(review["human_acceptance"] == "not_granted",
             "human acceptance must not be inferred")
    _text_list(review["notes"], "release_review.notes", 2)
    blockers = review["must_fix_before_m4"]
    _require(type(blockers) is list, "release_review.must_fix_before_m4 must be a list")
    blocker_ids = [_identifier(item, "RISK", f"release_review.must_fix_before_m4[{i}]")
                   for i, item in enumerate(blockers)]
    _require(blocker_ids == sorted(set(blocker_ids)),
             "release_review.must_fix_before_m4 must be sorted and unique")
    expected = sorted(item["id"] for item in threats
                      if item["engineering_disposition"] == "must_fix_before_m4")
    _require(blocker_ids == expected,
             "M4 blocker list does not match threat dispositions")
    return {
        "asset_count": len(asset_ids),
        "actor_count": len(actor_ids),
        "trust_boundary_count": len(boundary_ids),
        "threat_count": len(threat_ids),
        "control_count": len(control_ids),
        "evidence_files": [evidence_files[path] for path in sorted(evidence_files)],
        "must_fix_before_m4": blocker_ids,
        "disposition_counts": dispositions,
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
        raise ThreatModelError(
            "threat-model assessment output already exists or is a symbolic link"
        ) from exc
    except OSError as exc:
        raise ThreatModelError("cannot publish threat-model assessment output") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except (FileNotFoundError, OSError):
                pass
    reopened, saved = _load_canonical_json(target, 1_048_576)
    _require(reopened == record and saved == content,
             "threat-model assessment output did not reopen canonically")


def _build_assessment(
    *, candidate_commit: str, generated_at_utc: str,
    model_content: bytes, summary: dict,
) -> dict:
    status = ("blocked_by_open_release_threat"
              if summary["must_fix_before_m4"] else "model_complete")
    reference_status = "blocked" if summary["must_fix_before_m4"] else "passed"
    return {
        "schema_version": 1,
        "record_type": "chimera.release-threat-model-assessment",
        "model_id": MODEL_ID,
        "candidate_commit_sha": candidate_commit,
        "candidate_checks": {
            "before_assessment": "matched_clean_head",
            "before_publication": "matched_clean_head",
        },
        "generated_at_utc": generated_at_utc,
        "model": {
            "path": MODEL_REPOSITORY_PATH,
            "byte_count": len(model_content),
            "sha256": hashlib.sha256(model_content).hexdigest(),
            "asset_count": summary["asset_count"],
            "actor_count": summary["actor_count"],
            "trust_boundary_count": summary["trust_boundary_count"],
            "threat_count": summary["threat_count"],
            "control_count": summary["control_count"],
            "evidence_file_count": len(summary["evidence_files"]),
            "disposition_counts": summary["disposition_counts"],
        },
        "evidence_files": summary["evidence_files"],
        "checks": [
            {"id": "THREAT-001", "status": "passed",
             "description": "versioned scope, assets, actors and trust boundaries are complete"},
            {"id": "THREAT-002", "status": "passed",
             "description": "each threat has likelihood, impact, controls and residual risk"},
            {"id": "THREAT-003", "status": "passed",
             "description": "control requirements and evidence are tracked in the exact candidate"},
            {"id": "THREAT-004", "status": "passed",
             "description": "scope exclusions and pending human M4 acceptance remain explicit"},
            {"id": "THREAT-005", "status": reference_status,
             "description": "M4 blocker dispositions are explicit and machine checked"},
        ],
        "must_fix_before_m4": summary["must_fix_before_m4"],
        "status": status,
        "release_decision": "pending_m4_review",
        "human_acceptance": "not_granted",
        "scope": (
            "model structure, candidate binding and reference validity only; not a "
            "penetration test, vulnerability scan, control-effectiveness proof, "
            "security certification, residual-risk acceptance or phase approval"
        ),
    }


def assess_threat_model(
    output: str | Path, *, candidate_commit: str,
    generated_at_utc: str | None = None,
) -> dict:
    """Validate the fixed model and publish an exact-candidate assessment."""
    _validate_candidate_checkout(candidate_commit)
    target = Path(output)
    if target.is_symlink() or target.exists():
        raise ThreatModelError(
            "threat-model assessment output already exists or is a symbolic link"
        )
    if (_has_symlink_ancestor(target.parent)
            or not target.parent.is_dir()):
        raise ThreatModelError("threat-model assessment output parent is unavailable")
    resolved = target.resolve(strict=False)
    checkout = ROOT.resolve()
    if resolved == checkout or checkout in resolved.parents:
        raise ThreatModelError(
            "threat-model assessment output must be outside the source checkout"
        )
    document, model_content = _load_canonical_json(MODEL_PATH, 262_144)
    summary = _validate_model(document)
    record = _build_assessment(
        candidate_commit=candidate_commit,
        generated_at_utc=_timestamp_text(generated_at_utc),
        model_content=model_content,
        summary=summary,
    )
    _validate_candidate_checkout(candidate_commit)
    _write_record(resolved, record)
    return record


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="assess the fixed P7 local-prototype threat model"
    )
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        record = assess_threat_model(
            args.output, candidate_commit=args.candidate_commit
        )
    except ThreatModelError as exc:
        print(f"chimera threat model: {exc}", file=sys.stderr)
        return 2
    for check in record["checks"]:
        label = "PASS" if check["status"] == "passed" else check["status"].upper()
        print(f"{label} {check['id']}: {check['description']}")
    print(f"candidate-commit: {args.candidate_commit}")
    print(f"model-sha256: {record['model']['sha256']}")
    print(f"threat-model-assessment: {args.output.resolve(strict=False)}")
    print("Model/reference validation only; M4 review and security acceptance remain pending")
    return 0 if record["status"] == "model_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
