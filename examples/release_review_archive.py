"""Create and inspect a portable exact-candidate review-rehearsal archive.

This local transport control preserves one already validated rehearsal.  It does
not upload an artifact, query GitHub, grant a phase decision, merge, tag, release,
or deploy.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import io
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import struct
import sys
import tempfile
import zipfile

from examples import release_candidate_packet, release_review_rehearsal


ROOT = release_review_rehearsal.ROOT
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
REGULAR_MODE = 0o100644
MAX_ARCHIVE_BYTES = 40_000_000
MAX_ARCHIVE_CONTENT_BYTES = (
    release_review_rehearsal.MAX_CONTENT_BYTES
    + release_review_rehearsal.MAX_RECEIPT_BYTES
)
MAX_ARCHIVE_MEMBERS = release_review_rehearsal.MAX_FILES + 1
MAX_CENTRAL_DIRECTORY_BYTES = MAX_ARCHIVE_MEMBERS * 8_192
EOCD_SIZE = 22


class ReviewArchiveError(RuntimeError):
    """A review-rehearsal archive could not be handled safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewArchiveError(message)


def _has_symlink_ancestor(path: Path) -> bool:
    return any(item.is_symlink() for item in (path, *path.parents))


def _safe_name(value: object, label: str) -> str:
    _require(type(value) is str, f"{label} must be text")
    _require(
        0 < len(value) <= 1_024
        and "\\" not in value
        and "\x00" not in value,
        f"{label} is unsafe",
    )
    path = PurePosixPath(value)
    _require(
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in ("", ".", "..") for part in path.parts)
        and len(path.parts) <= release_review_rehearsal.MAX_DEPTH,
        f"{label} is unsafe",
    )
    return value


def _read_regular(path: Path, label: str, maximum: int) -> bytes:
    requested = Path(path)
    _require(
        requested.name not in ("", ".", ".."),
        f"{label} must be a regular file without symbolic-link ancestry",
    )
    parent, parent_descriptor = _open_directory_path(requested.parent)
    try:
        descriptor = os.open(
            requested.name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_descriptor,
        )
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            _require(
                stat.S_ISREG(metadata.st_mode),
                f"{label} must be a regular file without symbolic-link ancestry",
            )
            identity = _file_identity(metadata)
            content = stream.read(maximum + 1)
        parent_identity = _file_identity(os.fstat(parent_descriptor))
        _require(
            _live_entry_matches(
                parent,
                parent_identity,
                requested.name,
                identity,
            ),
            f"{label} path changed while it was read",
        )
    except ReviewArchiveError:
        raise
    except OSError as exc:
        raise ReviewArchiveError(f"{label} cannot be read") from exc
    finally:
        os.close(parent_descriptor)
    _require(len(content) <= maximum, f"{label} exceeds its size bound")
    return content


def _expected_names(receipt: dict) -> list[str]:
    artifacts = receipt.get("artifacts")
    _require(
        type(artifacts) is list
        and len(artifacts) <= release_review_rehearsal.MAX_FILES,
        "review archive receipt artifact inventory is invalid",
    )
    names = [release_review_rehearsal.RECEIPT_NAME]
    for index, artifact in enumerate(artifacts):
        _require(
            type(artifact) is dict
            and set(artifact) == {"byte_count", "path", "sha256"},
            f"review archive receipt artifact {index} is invalid",
        )
        name = _safe_name(
            artifact["path"], f"review archive receipt artifact {index}.path"
        )
        _require(
            name != release_review_rehearsal.RECEIPT_NAME,
            "review archive receipt cannot index itself",
        )
        names.append(name)
    _require(
        len(names) == len(set(names)) and names[1:] == sorted(names[1:]),
        "review archive receipt artifact paths are duplicate or unsorted",
    )
    return sorted(names)


def _directory_members(root: Path, receipt: dict) -> dict[str, bytes]:
    expected = _expected_names(receipt)
    paths = release_review_rehearsal._regular_files(root)
    actual = [path.relative_to(root).as_posix() for path in paths]
    _require(actual == expected, "review archive directory inventory changed")
    members: dict[str, bytes] = {}
    total = 0
    for path, name in zip(paths, actual):
        maximum = (
            release_review_rehearsal.MAX_RECEIPT_BYTES
            if name == release_review_rehearsal.RECEIPT_NAME
            else release_review_rehearsal.MAX_CONTENT_BYTES
        )
        content = _read_regular(path, f"review archive member {name}", maximum)
        total += len(content)
        _require(
            total <= MAX_ARCHIVE_CONTENT_BYTES,
            "review archive content exceeds its total-size bound",
        )
        members[name] = content
    return members


def _archive_bytes(members: dict[str, bytes]) -> bytes:
    destination = io.BytesIO()
    try:
        with zipfile.ZipFile(
            destination, "w", compression=zipfile.ZIP_STORED
        ) as archive:
            for name in sorted(members):
                info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = REGULAR_MODE << 16
                archive.writestr(info, members[name])
    except (OSError, RuntimeError, zipfile.LargeZipFile) as exc:
        raise ReviewArchiveError("review archive cannot be assembled") from exc
    content = destination.getvalue()
    _require(
        0 < len(content) <= MAX_ARCHIVE_BYTES,
        "review archive exceeds its file-size bound",
    )
    return content


def _preflight_zip(content: bytes) -> int:
    _require(
        len(content) >= EOCD_SIZE
        and content[-EOCD_SIZE:-EOCD_SIZE + 4] == b"PK\x05\x06",
        "review archive lacks a canonical end-of-directory record",
    )
    try:
        (
            _signature,
            disk_number,
            directory_disk,
            disk_entries,
            total_entries,
            directory_size,
            directory_offset,
            comment_size,
        ) = struct.unpack("<4s4H2LH", content[-EOCD_SIZE:])
    except struct.error as exc:
        raise ReviewArchiveError(
            "review archive end-of-directory record is invalid"
        ) from exc
    _require(
        disk_number == 0
        and directory_disk == 0
        and disk_entries == total_entries
        and comment_size == 0,
        "review archive end-of-directory bounds are invalid",
    )
    _require(
        0 < total_entries <= MAX_ARCHIVE_MEMBERS,
        "review archive member count is outside the supported bound",
    )
    _require(
        0 < directory_size <= MAX_CENTRAL_DIRECTORY_BYTES
        and directory_offset + directory_size == len(content) - EOCD_SIZE,
        "review archive central directory is outside its bound",
    )
    return total_entries


def _read_members(content: bytes) -> dict[str, bytes]:
    _require(
        type(content) is bytes and 0 < len(content) <= MAX_ARCHIVE_BYTES,
        "review archive size is outside the supported bound",
    )
    members: dict[str, bytes] = {}
    total = 0
    names: list[str] = []
    expected_member_count = _preflight_zip(content)
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            _require(not archive.comment, "review archive has an archive comment")
            infos = archive.infolist()
            _require(
                len(infos) == expected_member_count,
                "review archive member count is outside the supported bound",
            )
            for info in infos:
                name = _safe_name(info.filename, "review archive member name")
                _require(
                    name not in members,
                    f"review archive contains a duplicate member: {name}",
                )
                _require(
                    not info.is_dir(),
                    "review archive cannot contain directory entries",
                )
                _require(
                    info.date_time == FIXED_ZIP_TIME,
                    f"review archive timestamp changed: {name}",
                )
                _require(
                    info.compress_type == zipfile.ZIP_STORED
                    and info.compress_size == info.file_size,
                    f"review archive member must be stored: {name}",
                )
                _require(
                    info.flag_bits == 0,
                    f"review archive member flags changed: {name}",
                )
                _require(
                    info.create_system == 3
                    and (info.external_attr >> 16) == REGULAR_MODE,
                    f"review archive member mode changed: {name}",
                )
                _require(
                    not info.extra and not info.comment,
                    f"review archive member metadata changed: {name}",
                )
                maximum = (
                    release_review_rehearsal.MAX_RECEIPT_BYTES
                    if name == release_review_rehearsal.RECEIPT_NAME
                    else release_review_rehearsal.MAX_CONTENT_BYTES
                )
                _require(
                    0 <= info.file_size <= maximum,
                    f"review archive member size is invalid: {name}",
                )
                data = archive.read(info)
                _require(
                    len(data) == info.file_size,
                    f"review archive member is truncated: {name}",
                )
                members[name] = data
                names.append(name)
                total += len(data)
                _require(
                    total <= MAX_ARCHIVE_CONTENT_BYTES,
                    "review archive content exceeds its total-size bound",
                )
    except ReviewArchiveError:
        raise
    except (
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
        OverflowError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ) as exc:
        raise ReviewArchiveError(
            "review archive is not a valid bounded ZIP"
        ) from exc
    _require(names == sorted(names), "review archive member order changed")
    name_set = set(names)
    for name in names:
        parent = PurePosixPath(name).parent
        while parent != PurePosixPath("."):
            _require(
                parent.as_posix() not in name_set,
                "review archive has a file/path-prefix collision",
            )
            parent = parent.parent
    receipt_content = members.get(release_review_rehearsal.RECEIPT_NAME)
    _require(
        type(receipt_content) is bytes and bool(receipt_content),
        "review archive lacks its receipt",
    )
    try:
        receipt = release_review_rehearsal._decode_json(
            receipt_content, "review archive receipt"
        )
        canonical_receipt = release_review_rehearsal._canonical(receipt)
    except (UnicodeError, ValueError, OverflowError, RecursionError) as exc:
        raise ReviewArchiveError(
            "review archive receipt is not canonical UTF-8 JSON"
        ) from exc
    _require(
        canonical_receipt == receipt_content,
        "review archive receipt is not canonical JSON",
    )
    _require(
        set(members) == set(_expected_names(receipt)),
        "review archive member inventory disagrees with its receipt",
    )
    return members


def _summary(content: bytes, members: dict[str, bytes], receipt: dict) -> dict:
    receipt_content = members[release_review_rehearsal.RECEIPT_NAME]
    packet_content = members[release_review_rehearsal.PACKET_NAME]
    return {
        "archive": {
            "byte_count": len(content),
            "sha256": sha256(content).hexdigest(),
        },
        "candidate_commit_sha": receipt["candidate_commit_sha"],
        "human_acceptance": receipt["human_acceptance"],
        "m4_decision": receipt["m4_decision"],
        "m5_decision": receipt["m5_decision"],
        "packet": {
            "byte_count": len(packet_content),
            "sha256": sha256(packet_content).hexdigest(),
        },
        "receipt": {
            "byte_count": len(receipt_content),
            "sha256": sha256(receipt_content).hexdigest(),
        },
        "release_blockers": receipt["release_blockers"],
        "status": receipt["status"],
    }


def _inspect_bytes(content: bytes) -> dict:
    members = _read_members(content)
    _require(
        _archive_bytes(members) == content,
        "review archive is not the canonical deterministic ZIP",
    )
    with tempfile.TemporaryDirectory(prefix="chimera-review-archive-") as directory:
        root = Path(directory)
        for name in sorted(members):
            destination = root.joinpath(*PurePosixPath(name).parts)
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                with destination.open("xb") as stream:
                    stream.write(members[name])
            except OSError as exc:
                raise ReviewArchiveError(
                    "review archive cannot be staged for inspection"
                ) from exc
        receipt = release_review_rehearsal.inspect_review_rehearsal(root)
    return _summary(content, members, receipt)


def inspect_review_archive(archive: str | Path) -> dict:
    """Portably inspect a rehearsal archive without Git or its source checkout."""
    content = _read_regular(
        Path(archive), "review archive", MAX_ARCHIVE_BYTES
    )
    return _inspect_bytes(content)


def _file_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _open_directory_path(path: Path) -> tuple[Path, int]:
    absolute = Path(os.path.abspath(os.fspath(path)))
    _require(
        absolute.is_absolute() and bool(absolute.anchor),
        "review archive output parent is unavailable",
    )
    try:
        current = os.open(absolute.anchor, _directory_flags())
        for part in absolute.parts[1:]:
            _require(
                part not in ("", ".", ".."),
                "review archive output parent is unavailable",
            )
            child = os.open(part, _directory_flags(), dir_fd=current)
            os.close(current)
            current = child
    except Exception as exc:
        try:
            os.close(current)
        except (UnboundLocalError, OSError):
            pass
        if isinstance(exc, ReviewArchiveError):
            raise
        raise ReviewArchiveError(
            "review archive output parent is unavailable"
        ) from exc
    return absolute, current


def _directory_has_ancestor(
    descriptor: int, protected: set[tuple[int, int]]
) -> bool:
    current = os.dup(descriptor)
    try:
        for _ in range(1_024):
            current_identity = _file_identity(os.fstat(current))
            if current_identity in protected:
                return True
            parent = os.open("..", _directory_flags(), dir_fd=current)
            parent_identity = _file_identity(os.fstat(parent))
            if parent_identity == current_identity:
                os.close(parent)
                return False
            os.close(current)
            current = parent
    except OSError as exc:
        raise ReviewArchiveError(
            "review archive output ancestry cannot be verified"
        ) from exc
    finally:
        os.close(current)
    raise ReviewArchiveError(
        "review archive output ancestry exceeds its bound"
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
    _require(
        requested.name not in ("", ".", ".."),
        "review archive output is unavailable",
    )
    target_parent, parent_descriptor = _open_directory_path(requested.parent)
    target = target_parent / requested.name
    try:
        checkout = ROOT.resolve()
        rehearsal_root = rehearsal.resolve(strict=True)
        if (
            target == checkout
            or checkout in target.parents
            or target == rehearsal_root
            or rehearsal_root in target.parents
        ):
            raise ReviewArchiveError(
                "review archive output must be outside the checkout and rehearsal"
            )
        parent_metadata = os.fstat(parent_descriptor)
        parent_identity = _file_identity(parent_metadata)
        _require(
            stat.S_ISDIR(parent_metadata.st_mode)
            and _live_parent_matches(target.parent, parent_identity),
            "review archive output parent changed during validation",
        )
        protected = {
            _file_identity(os.stat(checkout, follow_symlinks=False)),
            _file_identity(os.stat(rehearsal_root, follow_symlinks=False)),
        }
        _require(
            not _directory_has_ancestor(parent_descriptor, protected),
            "review archive output must be outside the checkout and rehearsal",
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
            raise ReviewArchiveError(
                "review archive output already exists or is a symbolic link"
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
            return os.open(
                name, flags, 0o600, dir_fd=parent_descriptor
            ), name
        except FileExistsError:
            continue
    raise ReviewArchiveError("cannot allocate review archive staging file")


def _write_archive(
    parent_descriptor: int, target_name: str, content: bytes
) -> tuple[int, int]:
    temporary: str | None = None
    publication_identity: tuple[int, int] | None = None
    try:
        descriptor, temporary = _temporary_file(
            parent_descriptor, target_name
        )
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
        raise ReviewArchiveError(
            "review archive output appeared during publication"
        ) from exc
    except OSError as exc:
        if publication_identity is not None:
            _unlink_if_identity(
                parent_descriptor, target_name, publication_identity
            )
        raise ReviewArchiveError(
            "cannot publish review archive output"
        ) from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except (FileNotFoundError, OSError):
                pass


def _entry_matches_identity(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int],
) -> bool:
    try:
        metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        return False
    return (
        stat.S_ISREG(metadata.st_mode)
        and _file_identity(metadata) == expected_identity
    )


def _live_entry_matches(
    parent: Path,
    expected_parent_identity: tuple[int, int],
    name: str,
    expected_entry_identity: tuple[int, int],
) -> bool:
    try:
        _absolute, descriptor = _open_directory_path(parent)
    except ReviewArchiveError:
        return False
    try:
        return (
            _file_identity(os.fstat(descriptor))
            == expected_parent_identity
            and _entry_matches_identity(
                descriptor, name, expected_entry_identity
            )
        )
    except OSError:
        return False
    finally:
        os.close(descriptor)


def _read_at(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int],
) -> bytes:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_descriptor,
        )
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            _require(
                stat.S_ISREG(metadata.st_mode)
                and _file_identity(metadata) == expected_identity,
                "review archive output identity changed during publication",
            )
            content = stream.read(MAX_ARCHIVE_BYTES + 1)
            final_metadata = os.fstat(stream.fileno())
            _require(
                _file_identity(final_metadata) == expected_identity
                and final_metadata.st_size == metadata.st_size
                and final_metadata.st_mtime_ns == metadata.st_mtime_ns
                and final_metadata.st_ctime_ns == metadata.st_ctime_ns,
                "review archive output changed while it was reopened",
            )
    except ReviewArchiveError:
        raise
    except OSError as exc:
        raise ReviewArchiveError(
            "review archive output cannot be reopened"
        ) from exc
    _require(
        0 < len(content) <= MAX_ARCHIVE_BYTES,
        "review archive output exceeds its size bound",
    )
    return content


def _live_entry_content_matches(
    parent: Path,
    expected_parent_identity: tuple[int, int],
    name: str,
    expected_entry_identity: tuple[int, int],
    expected_content: bytes,
) -> bool:
    try:
        _absolute, descriptor = _open_directory_path(parent)
    except ReviewArchiveError:
        return False
    try:
        if (
            _file_identity(os.fstat(descriptor))
            != expected_parent_identity
        ):
            return False
        content = _read_at(descriptor, name, expected_entry_identity)
        return (
            content == expected_content
            and _file_identity(os.fstat(descriptor))
            == expected_parent_identity
            and _entry_matches_identity(
                descriptor, name, expected_entry_identity
            )
        )
    except (OSError, ReviewArchiveError):
        return False
    finally:
        os.close(descriptor)


def create_review_archive(
    rehearsal: str | Path, output: str | Path
) -> dict:
    """Create a deterministic archive from one validated rehearsal directory."""
    rehearsal_root = Path(rehearsal)
    receipt = release_review_rehearsal.inspect_review_rehearsal(
        rehearsal_root
    )
    members = _directory_members(rehearsal_root, receipt)
    content = _archive_bytes(members)
    target, parent_descriptor, parent_identity = _validate_output(
        output, rehearsal_root
    )
    publication_identity: tuple[int, int] | None = None
    try:
        publication_identity = _write_archive(
            parent_descriptor, target.name, content
        )
        saved = _read_at(
            parent_descriptor, target.name, publication_identity
        )
        _require(saved == content, "review archive changed during publication")
        summary = _inspect_bytes(saved)
        _require(
            summary["candidate_commit_sha"]
            == receipt["candidate_commit_sha"],
            "review archive candidate changed during publication",
        )
        _require(
            _live_entry_content_matches(
                target.parent,
                parent_identity,
                target.name,
                publication_identity,
                content,
            ),
            "review archive output path or content changed during publication",
        )
        return summary
    except Exception:
        if publication_identity is not None:
            _unlink_if_identity(
                parent_descriptor, target.name, publication_identity
            )
        raise
    finally:
        os.close(parent_descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="build or inspect a portable Chimera review archive"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--rehearsal", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("archive", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            summary = create_review_archive(args.rehearsal, args.output)
            location = args.output.resolve(strict=False)
            action = "creation"
        else:
            summary = inspect_review_archive(args.archive)
            location = args.archive.resolve(strict=False)
            action = "inspection"
    except (
        ReviewArchiveError,
        release_review_rehearsal.ReviewRehearsalError,
        release_candidate_packet.ReleaseCandidatePacketError,
        OSError,
    ) as exc:
        print(f"chimera review archive: {exc}", file=sys.stderr)
        return 2
    print(f"status: {summary['status']}")
    print(f"candidate-commit: {summary['candidate_commit_sha']}")
    print(f"review-archive: {location}")
    print(f"archive-bytes: {summary['archive']['byte_count']}")
    print(f"archive-sha256: {summary['archive']['sha256']}")
    print(f"receipt-sha256: {summary['receipt']['sha256']}")
    print(f"packet-sha256: {summary['packet']['sha256']}")
    print(
        f"Review archive {action} only; P3/P4/P5, M4/M5 and human "
        "acceptance remain pending"
    )
    return 0 if summary["status"] == "packet_complete_for_m4_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
