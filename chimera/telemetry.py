"""Strict, deterministic ingestion for the communications-link CSV prototype."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
import io
import json
from pathlib import Path
import re


MAX_INPUT_BYTES = 1_048_576
MAX_SAMPLES = 10_000
_HEADER = ("timestamp_utc", "link_margin_db")
_NUMBER = re.compile(r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?\Z")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z"
)


class TelemetryError(ValueError):
    """Communications telemetry is unavailable or violates the input contract."""


def _decimal_text(value: Decimal) -> str:
    """Render exact decimal digits with stable exponent case, without arithmetic."""
    with localcontext() as context:
        context.capitals = 1
        return str(value)


@dataclass(frozen=True)
class InputIdentity:
    """Identity of exact source bytes, independent of pathname."""

    sha256: str
    byte_length: int

    def __post_init__(self) -> None:
        if not _valid_digest(self.sha256):
            raise TelemetryError("sha256 must be a lowercase SHA-256 hex digest")
        if (type(self.byte_length) is not int or self.byte_length < 0
                or self.byte_length > MAX_INPUT_BYTES):
            raise TelemetryError("byte_length is outside the input bound")


@dataclass(frozen=True)
class LinkSample:
    timestamp_utc: str
    link_margin_db: Decimal

    def __post_init__(self) -> None:
        _utc_timestamp(self.timestamp_utc, 0)
        if type(self.link_margin_db) is not Decimal or not self.link_margin_db.is_finite():
            raise TelemetryError("link_margin_db must be a finite Decimal")


@dataclass(frozen=True)
class LinkTelemetry:
    """Validated immutable samples plus the exact source-byte identity."""

    input_sha256: str
    input_bytes: int
    samples: tuple[LinkSample, ...]

    def __post_init__(self) -> None:
        InputIdentity(self.input_sha256, self.input_bytes)
        if type(self.samples) is not tuple or not self.samples:
            raise TelemetryError("samples must be a nonempty tuple")
        if len(self.samples) > MAX_SAMPLES:
            raise TelemetryError("samples exceed the telemetry row bound")
        previous: datetime | None = None
        for sample in self.samples:
            if type(sample) is not LinkSample:
                raise TelemetryError("samples must contain LinkSample values")
            parsed = _utc_timestamp(sample.timestamp_utc, 0)
            if previous is not None and parsed <= previous:
                raise TelemetryError("sample timestamps must be strictly increasing")
            previous = parsed

    @property
    def minimum_link_margin_db(self) -> Decimal:
        return min(sample.link_margin_db for sample in self.samples)

    def manifest(self) -> dict:
        """Return a detached, JSON-safe ingestion summary for run evidence."""
        return {
            "schema_version": 1,
            "media_type": "text/csv",
            "input_sha256": self.input_sha256,
            "input_bytes": self.input_bytes,
            "sample_count": len(self.samples),
            "timestamp_start_utc": self.samples[0].timestamp_utc,
            "timestamp_end_utc": self.samples[-1].timestamp_utc,
            "link_margin_unit": "dB",
            "minimum_link_margin_db": _decimal_text(self.minimum_link_margin_db),
        }


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise TelemetryError(f"Duplicate report field: {key}")
        result[key] = value
    return result


def _decimal(value: object, field: str) -> Decimal:
    if type(value) is not str or not value or _NUMBER.fullmatch(value) is None:
        raise TelemetryError(f"{field} must be a finite ASCII-decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise TelemetryError(f"{field} must be a finite ASCII-decimal string") from exc
    if not result.is_finite():
        raise TelemetryError(f"{field} must be a finite ASCII-decimal string")
    return result


def _threshold(value: object) -> Decimal:
    if type(value) not in (int, float, Decimal):
        raise TelemetryError("threshold_db must be a finite number")
    try:
        result = (Decimal(value) if type(value) is int
                  else value if type(value) is Decimal
                  else Decimal(str(value)))
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise TelemetryError("threshold_db must be a finite number") from exc
    if not result.is_finite():
        raise TelemetryError("threshold_db must be a finite number")
    return result


@dataclass(frozen=True)
class LinkMarginReport:
    """Versioned canonical report for one validated minimum-margin evaluation."""

    _json: str

    def __post_init__(self) -> None:
        if type(self._json) is not str:
            raise TelemetryError("Link-margin report input must be JSON text")
        try:
            document = json.loads(self._json, object_pairs_hook=_unique_object)
        except (ValueError, TypeError, RecursionError) as exc:
            raise TelemetryError(f"Invalid link-margin report JSON: {exc}") from exc
        fields = {
            "schema_version", "requirement_id", "rule", "unit", "input_sha256",
            "input_bytes", "threshold_db", "sample_count", "minimum_link_margin_db",
            "passed", "failure_count", "failing_samples",
        }
        if type(document) is not dict or set(document) != fields:
            raise TelemetryError("Invalid link-margin report fields")
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise TelemetryError("Unsupported link-margin report schema_version")
        if document["requirement_id"] != "COM-LINK-001":
            raise TelemetryError("Invalid link-margin report requirement_id")
        if document["rule"] != "minimum_link_margin_gte" or document["unit"] != "dB":
            raise TelemetryError("Invalid link-margin report rule or unit")
        InputIdentity(document["input_sha256"], document["input_bytes"])
        if (type(document["sample_count"]) is not int
                or not 1 <= document["sample_count"] <= MAX_SAMPLES):
            raise TelemetryError("Invalid link-margin report sample_count")
        threshold = _decimal(document["threshold_db"], "threshold_db")
        minimum = _decimal(
            document["minimum_link_margin_db"], "minimum_link_margin_db"
        )
        if type(document["passed"]) is not bool:
            raise TelemetryError("Invalid link-margin report passed value")
        if (type(document["failure_count"]) is not int
                or document["failure_count"] < 0
                or document["failure_count"] > document["sample_count"]):
            raise TelemetryError("Invalid link-margin report failure_count")
        findings = document["failing_samples"]
        if type(findings) is not list or len(findings) != document["failure_count"]:
            raise TelemetryError("Invalid link-margin report failing_samples")
        prior_index = 0
        prior_time: datetime | None = None
        finding_margins: list[Decimal] = []
        for finding in findings:
            if (type(finding) is not dict
                    or set(finding) != {"sample_index", "timestamp_utc", "link_margin_db"}):
                raise TelemetryError("Invalid failing-sample fields")
            index = finding["sample_index"]
            if (type(index) is not int or index <= prior_index
                    or index > document["sample_count"]):
                raise TelemetryError("Invalid failing-sample index")
            parsed_time = _utc_timestamp(finding["timestamp_utc"], index + 1)
            if prior_time is not None and parsed_time <= prior_time:
                raise TelemetryError("Failing-sample timestamps must be increasing")
            margin = _decimal(finding["link_margin_db"], "link_margin_db")
            if margin >= threshold:
                raise TelemetryError("Failing sample does not violate the threshold")
            prior_index, prior_time = index, parsed_time
            finding_margins.append(margin)
        if document["passed"] != (document["failure_count"] == 0):
            raise TelemetryError("Report verdict conflicts with failing samples")
        if document["passed"] != (minimum >= threshold):
            raise TelemetryError("Report verdict conflicts with minimum margin")
        if finding_margins and min(finding_margins) != minimum:
            raise TelemetryError("Report minimum is absent from failing samples")
        object.__setattr__(
            self, "_json",
            json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False),
        )

    @classmethod
    def from_json(cls, text: str) -> "LinkMarginReport":
        """Reopen a report without reading telemetry or executing checks."""
        return cls(text)

    @classmethod
    def from_telemetry(cls, telemetry: LinkTelemetry,
                       threshold_db: int | float | Decimal) -> "LinkMarginReport":
        if not isinstance(telemetry, LinkTelemetry):
            raise TypeError("telemetry must be validated LinkTelemetry")
        threshold = _threshold(threshold_db)
        failing = [
            {
                "sample_index": index,
                "timestamp_utc": sample.timestamp_utc,
                "link_margin_db": _decimal_text(sample.link_margin_db),
            }
            for index, sample in enumerate(telemetry.samples, start=1)
            if sample.link_margin_db < threshold
        ]
        document = {
            "schema_version": 1,
            "requirement_id": "COM-LINK-001",
            "rule": "minimum_link_margin_gte",
            "unit": "dB",
            "input_sha256": telemetry.input_sha256,
            "input_bytes": telemetry.input_bytes,
            "threshold_db": _decimal_text(threshold),
            "sample_count": len(telemetry.samples),
            "minimum_link_margin_db": _decimal_text(telemetry.minimum_link_margin_db),
            "passed": not failing,
            "failure_count": len(failing),
            "failing_samples": failing,
        }
        return cls(json.dumps(document, allow_nan=False))

    @property
    def passed(self) -> bool:
        return json.loads(self._json)["passed"]

    def to_json(self) -> str:
        return self._json

    def to_dict(self) -> dict:
        return json.loads(self._json)


def _valid_digest(value: object) -> bool:
    return (type(value) is str and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


def _read_bounded(path: str | Path) -> bytes:
    try:
        with Path(path).open("rb") as source:
            data = source.read(MAX_INPUT_BYTES + 1)
    except (OSError, TypeError, ValueError) as exc:
        raise TelemetryError("Telemetry input is unavailable") from exc
    if len(data) > MAX_INPUT_BYTES:
        raise TelemetryError(f"Telemetry input exceeds {MAX_INPUT_BYTES} bytes")
    return data


def identify_link_csv(path: str | Path) -> InputIdentity:
    """Hash bounded source bytes without claiming that their contents are valid."""
    data = _read_bounded(path)
    return InputIdentity(sha256(data).hexdigest(), len(data))


def _utc_timestamp(value: str, row_number: int) -> datetime:
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        raise TelemetryError(f"Row {row_number}: invalid UTC timestamp grammar")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TelemetryError(f"Row {row_number}: invalid timestamp_utc") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise TelemetryError(f"Row {row_number}: timestamp_utc must use UTC")
    return parsed


def _margin(value: str, row_number: int) -> Decimal:
    if not value or value != value.strip():
        raise TelemetryError(f"Row {row_number}: link_margin_db is empty or padded")
    if _NUMBER.fullmatch(value) is None:
        raise TelemetryError(f"Row {row_number}: invalid link_margin_db")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise TelemetryError(f"Row {row_number}: invalid link_margin_db") from exc
    if not result.is_finite():
        raise TelemetryError(f"Row {row_number}: link_margin_db must be finite")
    return result


def load_link_csv(path: str | Path, *, expected_sha256: str | None = None) -> LinkTelemetry:
    """Load the exact two-column UTF-8 CSV contract and reject ambiguous input."""
    return parse_link_csv(_read_bounded(path), expected_sha256=expected_sha256)


def parse_link_csv(data: bytes, *, expected_sha256: str | None = None) -> LinkTelemetry:
    """Validate bounded CSV bytes without filesystem effects."""
    if expected_sha256 is not None and not _valid_digest(expected_sha256):
        raise TelemetryError("expected_sha256 must be a lowercase SHA-256 hex digest")
    if type(data) is not bytes or len(data) > MAX_INPUT_BYTES:
        raise TelemetryError("Telemetry input must be bytes within the input bound")
    digest = sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise TelemetryError("Telemetry input identity changed")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TelemetryError("Telemetry input must be UTF-8") from exc
    if text.startswith("\ufeff"):
        raise TelemetryError("Telemetry input must not contain a UTF-8 BOM")
    try:
        rows = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(rows)
    except (csv.Error, StopIteration) as exc:
        raise TelemetryError("Telemetry CSV header is missing or malformed") from exc
    if tuple(header) != _HEADER:
        raise TelemetryError(
            "Telemetry CSV header must be exactly timestamp_utc,link_margin_db"
        )

    samples: list[LinkSample] = []
    previous: datetime | None = None
    try:
        for row_number, row in enumerate(rows, start=2):
            if len(samples) == MAX_SAMPLES:
                raise TelemetryError(f"Telemetry CSV exceeds {MAX_SAMPLES} samples")
            if len(row) != 2:
                raise TelemetryError(f"Row {row_number}: expected exactly two fields")
            parsed_time = _utc_timestamp(row[0], row_number)
            if previous is not None and parsed_time <= previous:
                raise TelemetryError(
                    f"Row {row_number}: timestamps must be strictly increasing"
                )
            samples.append(LinkSample(row[0], _margin(row[1], row_number)))
            previous = parsed_time
    except csv.Error as exc:
        raise TelemetryError("Telemetry CSV row is malformed") from exc
    if not samples:
        raise TelemetryError("Telemetry CSV must contain at least one sample")
    return LinkTelemetry(digest, len(data), tuple(samples))


def link_margin_passes(telemetry: LinkTelemetry,
                       threshold_db: int | float | Decimal) -> bool:
    """Return an exact boolean verdict; invalid thresholds are never failures."""
    return LinkMarginReport.from_telemetry(telemetry, threshold_db).passed


def evaluate_link_margin(telemetry: LinkTelemetry,
                         threshold_db: int | float | Decimal) -> LinkMarginReport:
    """Evaluate all samples and return the canonical investigation report."""
    return LinkMarginReport.from_telemetry(telemetry, threshold_db)
