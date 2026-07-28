from __future__ import annotations

import os
from pathlib import Path
import tempfile


PRIVATE_FILE_MODE = 0o600


def atomic_write_bytes(
    path: str | Path,
    data: bytes,
    *,
    mode: int = PRIVATE_FILE_MODE,
) -> Path:
    """Replace a file only after its complete contents are safely written."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
        _sync_directory(target.parent)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    return target


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
    mode: int = PRIVATE_FILE_MODE,
) -> Path:
    return atomic_write_bytes(path, text.encode(encoding), mode=mode)


def append_private_line(path: str | Path, line: str) -> Path:
    """Append one complete UTF-8 line while keeping the local file owner-only."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (line.rstrip("\n") + "\n").encode("utf-8")
    descriptor = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY, PRIVATE_FILE_MODE)
    try:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("Scrittura del file locale incompleta.")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(target, PRIVATE_FILE_MODE)
    return target


def _sync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
