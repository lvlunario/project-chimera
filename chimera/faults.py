"""Deterministic synthetic sample replacement; never changes source files."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .telemetry import (LinkTelemetry, _decimal, _decimal_text, _unique_object,
                        parse_link_csv)

MAX_PLAN_BYTES = 65_536
MAX_REPLACEMENTS = 1_000


class FaultError(ValueError):
    """A synthetic fault plan is invalid or cannot apply to the given input."""


@dataclass(frozen=True)
class FaultPlan:
    """Strict canonical v1 plan; indices are one-based source sample positions."""

    _json: str

    def __post_init__(self) -> None:
        try:
            if type(self._json) is not str or len(self._json.encode("utf-8")) > MAX_PLAN_BYTES:
                raise FaultError("Fault plan must be UTF-8 JSON within 65536 bytes")
            document = json.loads(self._json, object_pairs_hook=_unique_object)
            if type(document) is not dict or set(document) != {
                "schema_version", "model", "replacements"
            }:
                raise FaultError("Invalid fault plan fields")
            if type(document["schema_version"]) is not int or document["schema_version"] != 1:
                raise FaultError("Unsupported fault plan schema_version")
            if document["model"] != "sample-replacement-v1":
                raise FaultError("Unsupported fault model")
            replacements = document["replacements"]
            if type(replacements) is not list or len(replacements) > MAX_REPLACEMENTS:
                raise FaultError("Fault plan exceeds replacement bound or is not a list")
            seen = set()
            for item in replacements:
                if type(item) is not dict or set(item) != {"sample_index", "link_margin_db"}:
                    raise FaultError("Invalid replacement fields")
                index = item["sample_index"]
                if type(index) is not int or not 1 <= index <= 10_000 or index in seen:
                    raise FaultError("Replacement indices must be unique integers in 1..10000")
                value = item["link_margin_db"]
                if type(value) is not str or len(value) > 128:
                    raise FaultError("Replacement margin must be decimal text of at most 128 characters")
                _decimal(value, "link_margin_db")
                seen.add(index)
            replacements.sort(key=lambda item: item["sample_index"])
            canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
            if len(canonical.encode("utf-8")) > MAX_PLAN_BYTES:
                raise FaultError("Canonical fault plan exceeds byte bound")
            object.__setattr__(self, "_json", canonical)
        except (ValueError, TypeError, RecursionError) as exc:
            raise FaultError(f"Invalid fault plan: {exc}") from exc

    @classmethod
    def from_json(cls, text: str) -> "FaultPlan":
        return cls(text)

    def to_json(self) -> str:
        return self._json

    def to_dict(self) -> dict:
        return json.loads(self._json)

    @property
    def sha256(self) -> str:
        return sha256(self._json.encode("utf-8")).hexdigest()


def inject_link_csv(data: bytes, plan: FaultPlan, *,
                    expected_sha256: str | None = None) -> bytes:
    """Return canonical synthetic CSV bytes; validate all input before transforming.

    Replacements are literal decimal values, not rounded arithmetic. No random state,
    clock, I/O, or physical channel model is involved. Empty plans are controls but
    still canonicalize CSV formatting. Input/plan identity must accompany derived data.
    """
    if type(plan) is not FaultPlan:
        raise FaultError("plan must be a validated FaultPlan")
    telemetry = parse_link_csv(data, expected_sha256=expected_sha256)
    replacements = {item["sample_index"]: item["link_margin_db"]
                    for item in plan.to_dict()["replacements"]}
    if replacements and max(replacements) > len(telemetry.samples):
        raise FaultError("Replacement index exceeds source sample count")
    rows = ["timestamp_utc,link_margin_db\n"]
    for index, sample in enumerate(telemetry.samples, start=1):
        margin = replacements.get(index, _decimal_text(sample.link_margin_db))
        rows.append(f"{sample.timestamp_utc},{margin}\n")
    result = "".join(rows).encode("utf-8")
    # Reuse the ingestion contract, including the output byte bound.
    parse_link_csv(result)
    return result


def fault_manifest(data: bytes, plan: FaultPlan, *,
                   expected_sha256: str | None = None) -> dict:
    """Recompute a detached provenance record; not an authenticity guarantee."""
    output = inject_link_csv(data, plan, expected_sha256=expected_sha256)
    source: LinkTelemetry = parse_link_csv(data, expected_sha256=expected_sha256)
    derived = parse_link_csv(output)
    return {
        "schema_version": 1,
        "synthetic": True,
        "procedure": "chimera.synthetic.sample-replacement-v1",
        "source": source.manifest(),
        "fault_plan": plan.to_dict(),
        "fault_plan_sha256": plan.sha256,
        "derived": derived.manifest(),
    }
