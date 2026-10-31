"""Local immutable completed evidence; not a journal or resumable runner."""
from hashlib import sha256
from pathlib import Path
import sqlite3

from .bindings import RequirementBindings
from .evidence import RunEvidence


class StorageError(ValueError):
    """Unsupported or inconsistent repository content."""


class StorageConflict(StorageError):
    """An existing identity has different content; nothing was overwritten."""


def _digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


_SCHEMA = {
    "runs": "CREATE TABLE runs (run_id TEXT PRIMARY KEY NOT NULL, document TEXT NOT NULL, digest TEXT NOT NULL)",
    "bindings": "CREATE TABLE bindings (digest TEXT PRIMARY KEY NOT NULL, document TEXT NOT NULL)",
    "associations": "CREATE TABLE associations (run_id TEXT NOT NULL REFERENCES runs(run_id), digest TEXT NOT NULL REFERENCES bindings(digest), PRIMARY KEY(run_id, digest))",
}


class EvidenceStore:
    """One local connection, atomic immutable run/binding associations.

    SQLite errors propagate. A failed COMMIT may have an unknown outcome: reopen
    and inspect before retrying. No callback execution or automatic retry occurs.
    """

    def __init__(self, path: str | Path):
        self._db = sqlite3.connect(path, timeout=5)
        try:
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.execute("PRAGMA synchronous = FULL")
            self._db.execute("PRAGMA busy_timeout = 5000")
            for setting, expected in (("foreign_keys", 1), ("synchronous", 2),
                                      ("busy_timeout", 5000)):
                if self._db.execute(f"PRAGMA {setting}").fetchone()[0] != expected:
                    raise StorageError(f"Required SQLite setting unavailable: {setting}")
            # The write lock also serializes two first-time initializers.
            self._db.execute("BEGIN IMMEDIATE")
            version = self._db.execute("PRAGMA user_version").fetchone()[0]
            tables = {row[0] for row in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if version == 0 and not tables:
                for statement in _SCHEMA.values():
                    self._db.execute(statement)
                self._db.execute("PRAGMA user_version = 1")
            elif version != 1 or tables != {"runs", "bindings", "associations"}:
                raise StorageError("Unsupported storage schema; expected version 1")
            self._db.commit()
            self._validate()
        except BaseException:
            self._db.close()
            raise

    def close(self) -> None:
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _validate(self) -> None:
        if self._db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise StorageError("Unsupported storage schema")
        definitions = dict(self._db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'"))
        if definitions != _SCHEMA:
            raise StorageError("Unexpected storage table definitions")
        if self._db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger', 'view')").fetchone():
            raise StorageError("Unexpected storage trigger/view")
        if self._db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise StorageError("SQLite integrity check failed")
        if self._db.execute("PRAGMA foreign_key_check").fetchall():
            raise StorageError("Invalid artifact relationship")
        try:
            for run_id, document, digest in self._db.execute("SELECT * FROM runs"):
                evidence = RunEvidence.from_json(document)
                if (evidence.to_dict()["run_id"] != run_id or
                        evidence.to_json() != document or _digest(document) != digest):
                    raise StorageError("Run identity/content mismatch")
            for digest, document in self._db.execute("SELECT * FROM bindings"):
                bindings = RequirementBindings.from_json(document)
                if bindings.to_json() != document or bindings.sha256 != digest:
                    raise StorageError("Binding identity/content mismatch")
        except (ValueError, TypeError, UnicodeError) as exc:
            raise StorageError(f"Invalid stored artifact: {exc}") from exc

    def save(self, evidence: RunEvidence, bindings: RequirementBindings) -> None:
        """Save both artifacts and their association, or roll back all changes."""
        if not isinstance(evidence, RunEvidence) or not isinstance(bindings, RequirementBindings):
            raise TypeError("Expected RunEvidence and RequirementBindings")
        run_id = evidence.to_dict()["run_id"]
        document = evidence.to_json()
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            self._validate()
            existing = self._db.execute(
                "SELECT document FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if existing is not None and existing[0] != document:
                raise StorageConflict("Run ID already has different evidence")
            if existing is None:
                self._db.execute("INSERT INTO runs VALUES (?, ?, ?)",
                                 (run_id, document, _digest(document)))
            existing = self._db.execute(
                "SELECT document FROM bindings WHERE digest = ?", (bindings.sha256,)).fetchone()
            if existing is not None and existing[0] != bindings.to_json():
                raise StorageConflict("Binding digest already has different content")
            if existing is None:
                self._db.execute("INSERT INTO bindings VALUES (?, ?)",
                                 (bindings.sha256, bindings.to_json()))
            if self._db.execute("SELECT 1 FROM associations WHERE run_id = ? AND digest = ?",
                                (run_id, bindings.sha256)).fetchone() is None:
                self._db.execute("INSERT INTO associations VALUES (?, ?)",
                                 (run_id, bindings.sha256))

    def load(self, run_id: str, bindings_sha256: str) -> tuple[RunEvidence, RequirementBindings]:
        """Read a selected pair in one snapshot; never invoke tasks."""
        with self._db:
            self._db.execute("BEGIN")
            self._validate()
            row = self._db.execute(
                "SELECT runs.document, bindings.document FROM associations "
                "JOIN runs ON runs.run_id = associations.run_id "
                "JOIN bindings ON bindings.digest = associations.digest "
                "WHERE associations.run_id = ? AND associations.digest = ?",
                (run_id, bindings_sha256)).fetchone()
            if row is None:
                raise KeyError((run_id, bindings_sha256))
            return RunEvidence.from_json(row[0]), RequirementBindings.from_json(row[1])
