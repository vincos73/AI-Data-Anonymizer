from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import csv
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import sys
from typing import Literal

from privacy_guardian.models import AnonymizationMode, Finding
from privacy_guardian.persistence import append_private_line, atomic_write_text
from privacy_guardian.reporting import finding_counts, mode_label


ActivityAction = Literal["analysis", "anonymization", "save"]
SourceKind = Literal["document", "pasted_text"]

ACTION_LABELS: dict[ActivityAction, str] = {
    "analysis": "Analisi",
    "anonymization": "Anonimizzazione",
    "save": "Salvataggio",
}
SOURCE_LABELS: dict[SourceKind, str] = {
    "document": "Documento",
    "pasted_text": "Testo incollato",
}
LOG_FILENAME = "activity-log.jsonl"
SETTINGS_FILENAME = "activity-settings.json"
DEFAULT_RETENTION_ENTRIES = 1000


@dataclass(frozen=True)
class ActivityLogEntry:
    schema_version: int
    timestamp: str
    action: ActivityAction
    action_label: str
    source_kind: SourceKind
    source_label: str
    mode: AnonymizationMode
    mode_label: str
    total_findings: int
    finding_counts: dict[str, int]
    source_extension: str | None = None
    source_size_bytes: int | None = None
    source_sha256: str | None = None
    output_extension: str | None = None
    output_size_bytes: int | None = None
    output_sha256: str | None = None
    app_version: str | None = None


@dataclass(frozen=True)
class ActivityLogSettings:
    enabled: bool = True
    retention_entries: int = DEFAULT_RETENTION_ENTRIES


def default_activity_log_path() -> Path:
    override = os.environ.get("OMISSIS_ACTIVITY_LOG_PATH")
    if override:
        return Path(override).expanduser()

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "OMISSIS"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "OMISSIS"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "omissis"

    return base / LOG_FILENAME


def default_activity_settings_path() -> Path:
    override = os.environ.get("OMISSIS_ACTIVITY_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    return default_activity_log_path().with_name(SETTINGS_FILENAME)


def load_activity_settings(path: str | Path | None = None) -> ActivityLogSettings:
    settings_path = Path(path) if path else default_activity_settings_path()
    if not settings_path.exists():
        return ActivityLogSettings()
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        enabled = bool(payload.get("enabled", True))
        retention = int(payload.get("retention_entries", DEFAULT_RETENTION_ENTRIES))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return ActivityLogSettings()
    return ActivityLogSettings(
        enabled=enabled,
        retention_entries=max(50, min(10_000, retention)),
    )


def save_activity_settings(
    settings: ActivityLogSettings,
    path: str | Path | None = None,
) -> Path:
    settings_path = Path(path) if path else default_activity_settings_path()
    payload = json.dumps(asdict(settings), ensure_ascii=False, indent=2, sort_keys=True)
    return atomic_write_text(settings_path, payload)


def set_activity_logging_enabled(enabled: bool, path: str | Path | None = None) -> ActivityLogSettings:
    current = load_activity_settings(path)
    updated = ActivityLogSettings(enabled=enabled, retention_entries=current.retention_entries)
    save_activity_settings(updated, path)
    return updated


def set_activity_retention(retention_entries: int, path: str | Path | None = None) -> ActivityLogSettings:
    current = load_activity_settings(path)
    updated = ActivityLogSettings(
        enabled=current.enabled,
        retention_entries=max(50, min(10_000, retention_entries)),
    )
    save_activity_settings(updated, path)
    trim_activity_log(max_entries=updated.retention_entries)
    return updated


def build_activity_entry(
    *,
    action: ActivityAction,
    source_kind: SourceKind,
    mode: AnonymizationMode,
    findings: list[Finding],
    source_path: str | Path | None = None,
    output_path: str | Path | None = None,
    output_data: bytes | None = None,
    app_version: str | None = None,
) -> ActivityLogEntry:
    source_extension = None
    source_size_bytes = None
    source_sha256 = None
    if source_path:
        source = Path(source_path)
        source_extension = source.suffix.lower() or None
        try:
            source_size_bytes = source.stat().st_size
            source_sha256 = file_sha256(source)
        except OSError:
            source_size_bytes = None
            source_sha256 = None

    output_extension = None
    output_size_bytes = None
    output_sha256 = None
    if output_path:
        output = Path(output_path)
        output_extension = output.suffix.lower() or None
        try:
            output_size_bytes = output.stat().st_size
            output_sha256 = file_sha256(output)
        except OSError:
            output_size_bytes = None
            output_sha256 = None
    elif output_data is not None:
        output_size_bytes = len(output_data)
        output_sha256 = hashlib.sha256(output_data).hexdigest()

    return ActivityLogEntry(
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        action=action,
        action_label=ACTION_LABELS[action],
        source_kind=source_kind,
        source_label=SOURCE_LABELS[source_kind],
        mode=mode,
        mode_label=mode_label(mode),
        total_findings=len(findings),
        finding_counts=finding_counts(findings),
        source_extension=source_extension,
        source_size_bytes=source_size_bytes,
        source_sha256=source_sha256,
        output_extension=output_extension,
        output_size_bytes=output_size_bytes,
        output_sha256=output_sha256,
        app_version=app_version,
    )


def record_activity(entry: ActivityLogEntry, path: str | Path | None = None) -> Path:
    log_path = Path(path) if path else default_activity_log_path()
    settings_path = log_path.with_name(SETTINGS_FILENAME) if path else None
    settings = load_activity_settings(settings_path)
    if not settings.enabled:
        return log_path
    append_private_line(log_path, json.dumps(asdict(entry), ensure_ascii=False, sort_keys=True))
    trim_activity_log(log_path, max_entries=settings.retention_entries)
    return log_path


def load_activity_entries(path: str | Path | None = None, limit: int | None = None) -> list[dict[str, object]]:
    log_path = Path(path) if path else default_activity_log_path()
    if not log_path.exists():
        return []

    entries: list[dict[str, object]] = []
    try:
        with log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    entries.append(payload)
    except OSError:
        return []

    if limit is not None:
        return entries[-limit:]
    return entries


def export_activity_log_csv(destination: str | Path, path: str | Path | None = None) -> Path:
    entries = load_activity_entries(path)
    destination_path = Path(destination)
    fieldnames = [
        "timestamp",
        "action_label",
        "source_label",
        "mode_label",
        "total_findings",
        "finding_counts",
        "source_extension",
        "source_size_bytes",
        "source_sha256",
        "output_extension",
        "output_size_bytes",
        "output_sha256",
        "app_version",
    ]
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for entry in entries:
        row = {field: entry.get(field) for field in fieldnames}
        row["finding_counts"] = json.dumps(row["finding_counts"] or {}, ensure_ascii=False, sort_keys=True)
        writer.writerow(row)
    return atomic_write_text(destination_path, buffer.getvalue())


def clear_activity_log(path: str | Path | None = None) -> Path:
    log_path = Path(path) if path else default_activity_log_path()
    return atomic_write_text(log_path, "")


def trim_activity_log(
    path: str | Path | None = None,
    *,
    max_entries: int | None = None,
) -> Path:
    log_path = Path(path) if path else default_activity_log_path()
    if not log_path.exists():
        return log_path
    if max_entries is None:
        settings_path = log_path.with_name(SETTINGS_FILENAME) if path else None
        max_entries = load_activity_settings(settings_path).retention_entries
    max_entries = max(1, max_entries)
    entries = load_activity_entries(log_path)
    if len(entries) <= max_entries:
        return log_path
    payload = "\n".join(
        json.dumps(entry, ensure_ascii=False, sort_keys=True)
        for entry in entries[-max_entries:]
    )
    return atomic_write_text(log_path, payload + "\n")


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
