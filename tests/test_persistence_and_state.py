from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from privacy_guardian.activity_log import (
    ActivityLogEntry,
    ActivityLogSettings,
    clear_activity_log,
    load_activity_entries,
    record_activity,
    save_activity_settings,
)
from privacy_guardian.models import Finding
from privacy_guardian.persistence import atomic_write_bytes
from privacy_guardian.reversible import (
    ReversibleMapEntry,
    read_encrypted_mapping,
    write_encrypted_mapping,
)
from privacy_guardian.workflow_state import selection_fingerprint, source_fingerprint


class AtomicPersistenceTests(unittest.TestCase):
    def test_failed_replace_keeps_previous_file_and_removes_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.txt"
            target.write_bytes(b"previous")

            with mock.patch("privacy_guardian.persistence.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    atomic_write_bytes(target, b"new")

            self.assertEqual(target.read_bytes(), b"previous")
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])

    def test_reversible_map_is_atomic_private_and_readable(self) -> None:
        mapping = (ReversibleMapEntry("<PERSONA_1>", "PERSON", "Mario Rossi"),)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "session.omissis-map"
            write_encrypted_mapping(target, mapping, "password locale")

            self.assertEqual(read_encrypted_mapping(target, "password locale"), mapping)
            if os.name != "nt":
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)


class ActivityLogControlTests(unittest.TestCase):
    def _entry(self, timestamp: str = "2026-07-28T10:00:00+00:00") -> ActivityLogEntry:
        return ActivityLogEntry(
            schema_version=1,
            timestamp=timestamp,
            action="analysis",
            action_label="Analisi",
            source_kind="pasted_text",
            source_label="Testo incollato",
            mode="maximum",
            mode_label="Massima protezione",
            total_findings=1,
            finding_counts={"PERSON": 1},
        )

    def test_disabled_log_does_not_create_activity_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "activity-log.jsonl"
            settings_path = log_path.with_name("activity-settings.json")
            save_activity_settings(ActivityLogSettings(enabled=False), settings_path)

            record_activity(self._entry(), log_path)

            self.assertFalse(log_path.exists())

    def test_retention_and_clear_are_applied_locally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "activity-log.jsonl"
            settings_path = log_path.with_name("activity-settings.json")
            save_activity_settings(
                ActivityLogSettings(enabled=True, retention_entries=50),
                settings_path,
            )

            for index in range(55):
                record_activity(
                    replace(self._entry(), timestamp=f"2026-07-28T10:{index:02d}:00+00:00"),
                    log_path,
                )

            entries = load_activity_entries(log_path)
            self.assertEqual(len(entries), 50)
            self.assertEqual(entries[0]["timestamp"], "2026-07-28T10:05:00+00:00")
            clear_activity_log(log_path)
            self.assertEqual(load_activity_entries(log_path), [])


class WorkflowIdentityTests(unittest.TestCase):
    def test_source_and_selection_fingerprints_change_only_with_relevant_state(self) -> None:
        findings = [Finding("PERSON", 0, 11, 0.95)]

        self.assertEqual(source_fingerprint("Mario Rossi"), source_fingerprint("Mario Rossi"))
        self.assertNotEqual(source_fingerprint("Mario Rossi"), source_fingerprint("Mario Bianchi"))
        self.assertNotEqual(
            selection_fingerprint(findings, [True]),
            selection_fingerprint(findings, [False]),
        )


if __name__ == "__main__":
    unittest.main()
