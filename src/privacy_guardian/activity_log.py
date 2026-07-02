from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Literal

from privacy_guardian.models import AnonymizationMode, Finding
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
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(entry), ensure_ascii=False, sort_keys=True))
        handle.write("\n")
    return log_path


def load_activity_entries(path: str | Path | None = None, limit: int | None = None) -> list[dict[str, object]]:
    log_path = Path(path) if path else default_activity_log_path()
    if not log_path.exists():
        return []

    entries: list[dict[str, object]] = []
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

    if limit is not None:
        return entries[-limit:]
    return entries


def export_activity_log_csv(destination: str | Path, path: str | Path | None = None) -> Path:
    entries = load_activity_entries(path)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
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
    with destination_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            row = {field: entry.get(field) for field in fieldnames}
            row["finding_counts"] = json.dumps(row["finding_counts"] or {}, ensure_ascii=False, sort_keys=True)
            writer.writerow(row)
    return destination_path


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
