"""Versioned requirement-to-task binding artifacts."""
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json


class BindingError(ValueError):
    """A requirement-binding artifact is malformed or unsupported."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BindingError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _validate_id(value: object, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise BindingError(f"{label} must be a nonempty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise BindingError(f"{label} must be valid UTF-8 text") from exc
    return value


def _canonical(document: dict) -> str:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class RequirementBindings:
    """Immutable canonical schema-v1 mapping used to reproduce an assessment."""

    _json: str

    def __post_init__(self) -> None:
        if type(self._json) is not str:
            raise BindingError("Binding input must be JSON text")
        try:
            document = json.loads(self._json, object_pairs_hook=_unique_object)
        except BindingError:
            raise
        except (ValueError, TypeError, RecursionError) as exc:
            raise BindingError(str(exc)) from exc
        if type(document) is not dict or set(document) != {"schema_version", "bindings"}:
            raise BindingError("Expected exactly schema_version and bindings")
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise BindingError("Unsupported binding schema_version; expected integer 1")
        if type(document["bindings"]) is not list:
            raise BindingError("bindings must be a list")
        normalized = []
        seen = set()
        for item in document["bindings"]:
            if type(item) is not dict or set(item) != {"requirement_id", "task_id"}:
                raise BindingError("Each binding requires exactly requirement_id and task_id")
            requirement_id = _validate_id(item["requirement_id"], "requirement_id")
            task_id = _validate_id(item["task_id"], "task_id")
            if requirement_id in seen:
                raise BindingError(f"Duplicate requirement_id: {requirement_id}")
            seen.add(requirement_id)
            normalized.append({"requirement_id": requirement_id, "task_id": task_id})
        normalized.sort(key=lambda item: item["requirement_id"])
        object.__setattr__(self, "_json", _canonical({
            "schema_version": 1,
            "bindings": normalized,
        }))

    @classmethod
    def from_json(cls, text: str) -> "RequirementBindings":
        return cls(text)

    @classmethod
    def from_mapping(cls, bindings: Mapping[str, str]) -> "RequirementBindings":
        if not isinstance(bindings, Mapping):
            raise TypeError("bindings must map requirement IDs to task IDs")
        document = {
            "schema_version": 1,
            "bindings": [
                {"requirement_id": requirement_id, "task_id": task_id}
                for requirement_id, task_id in bindings.items()
            ],
        }
        try:
            return cls(_canonical(document))
        except BindingError:
            raise
        except (TypeError, ValueError) as exc:
            raise BindingError("Binding identifiers must be JSON strings") from exc

    def to_json(self) -> str:
        return self._json

    def to_mapping(self) -> dict[str, str]:
        document = json.loads(self._json)
        return {item["requirement_id"]: item["task_id"] for item in document["bindings"]}

    @property
    def sha256(self) -> str:
        """Content identity, not a signature or authenticity guarantee."""
        return sha256(self._json.encode("utf-8")).hexdigest()
