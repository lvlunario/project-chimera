"""Strict, deterministic ingestion for the communications-link CSV prototype."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
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
            "minimum_link_margin_db": str(self.minimum_link_margin_db),
        }


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
    if expected_sha256 is not None and not _valid_digest(expected_sha256):
        raise TelemetryError("expected_sha256 must be a lowercase SHA-256 hex digest")
    data = _read_bounded(path)
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
    if not isinstance(telemetry, LinkTelemetry):
        raise TypeError("telemetry must be validated LinkTelemetry")
    if type(threshold_db) not in (int, float, Decimal):
        raise TelemetryError("threshold_db must be a finite number")
    try:
        threshold = (Decimal(threshold_db) if type(threshold_db) is int
                     else threshold_db if type(threshold_db) is Decimal
                     else Decimal(str(threshold_db)))
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise TelemetryError("threshold_db must be a finite number") from exc
    if not threshold.is_finite():
        raise TelemetryError("threshold_db must be a finite number")
    return telemetry.minimum_link_margin_db >= threshold
