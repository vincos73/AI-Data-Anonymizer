from __future__ import annotations

import base64
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
from typing import Iterable

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from privacy_guardian import __version__
from privacy_guardian.models import Finding
from privacy_guardian.reporting import ENTITY_PLACEHOLDERS


MAP_SCHEMA_VERSION = 1
MAP_EXTENSION = ".omissis-map"
KDF_ITERATIONS = 390_000
PLACEHOLDER_PATTERN = re.compile(r"<([A-Z_]+)_(\d+)>")
_BASE_TO_ENTITY = {base: entity for entity, base in ENTITY_PLACEHOLDERS.items()}


@dataclass(frozen=True)
class ReversibleMapEntry:
    placeholder: str
    entity_type: str
    value: str


@dataclass(frozen=True)
class ReversibleAnonymizationResult:
    text: str
    mapping: tuple[ReversibleMapEntry, ...]


class ReversibleMapError(ValueError):
    """Raised when a reversible map cannot be read or decrypted."""


class ReversibleAnonymizer:
    def __init__(self, entries: Iterable[ReversibleMapEntry] | None = None) -> None:
        self._entries: list[ReversibleMapEntry] = []
        self._seen: dict[tuple[str, str], str] = {}
        self._counts: Counter[str] = Counter()

        for entry in entries or ():
            self._entries.append(entry)
            self._seen[(entry.entity_type, entry.value)] = entry.placeholder
            self._counts[entry.entity_type] = max(self._counts[entry.entity_type], _placeholder_index(entry.placeholder))

    @property
    def mapping(self) -> tuple[ReversibleMapEntry, ...]:
        return tuple(self._entries)

    def reserve_placeholders(self, text: str) -> None:
        """Skip placeholder indexes already present verbatim in the text, so restore stays unambiguous."""
        for match in PLACEHOLDER_PATTERN.finditer(text):
            entity_type = _BASE_TO_ENTITY.get(match.group(1), match.group(1))
            index = int(match.group(2))
            if index > self._counts[entity_type]:
                self._counts[entity_type] = index

    def anonymize(self, text: str, findings: Iterable[Finding]) -> str:
        self.reserve_placeholders(text)
        chunks: list[str] = []
        cursor = 0

        for finding in sorted(findings, key=lambda item: item.start):
            if finding.start < cursor:
                continue
            value = text[finding.start : finding.end]
            chunks.append(text[cursor : finding.start])
            chunks.append(self.placeholder_for(finding.entity_type, value))
            cursor = finding.end

        chunks.append(text[cursor:])
        return "".join(chunks)

    def placeholder_for(self, entity_type: str, value: str) -> str:
        key = (entity_type, value)
        existing = self._seen.get(key)
        if existing:
            return existing

        self._counts[entity_type] += 1
        placeholder = numbered_placeholder(entity_type, self._counts[entity_type])
        self._seen[key] = placeholder
        self._entries.append(ReversibleMapEntry(placeholder=placeholder, entity_type=entity_type, value=value))
        return placeholder


def reversible_anonymize(
    text: str,
    findings: Iterable[Finding],
    entries: Iterable[ReversibleMapEntry] | None = None,
) -> ReversibleAnonymizationResult:
    anonymizer = ReversibleAnonymizer(entries)
    anonymized_text = anonymizer.anonymize(text, findings)
    return ReversibleAnonymizationResult(text=anonymized_text, mapping=anonymizer.mapping)


def numbered_placeholder(entity_type: str, index: int) -> str:
    base = ENTITY_PLACEHOLDERS.get(entity_type, entity_type)
    return f"<{base}_{index}>"


def restore_text(text: str, mapping: Iterable[ReversibleMapEntry]) -> str:
    restored = text
    for entry in sorted(mapping, key=lambda item: len(item.placeholder), reverse=True):
        restored = restored.replace(entry.placeholder, entry.value)
    return restored


def encrypt_mapping(mapping: Iterable[ReversibleMapEntry], passphrase: str) -> bytes:
    passphrase = passphrase.strip()
    if not passphrase:
        raise ReversibleMapError("Serve una password per cifrare la mappa reversibile.")

    salt = secrets.token_bytes(16)
    key = _derive_key(passphrase, salt)
    token = Fernet(key).encrypt(_mapping_payload(mapping))
    envelope = {
        "schema_version": MAP_SCHEMA_VERSION,
        "format": "omissis-reversible-map",
        "kdf": "PBKDF2HMAC-SHA256",
        "iterations": KDF_ITERATIONS,
        "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
        "token": token.decode("ascii"),
    }
    return json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")


def decrypt_mapping(data: bytes | str, passphrase: str) -> tuple[ReversibleMapEntry, ...]:
    passphrase = passphrase.strip()
    if not passphrase:
        raise ReversibleMapError("Serve la password usata per cifrare la mappa.")

    try:
        envelope = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        salt = base64.urlsafe_b64decode(envelope["salt"])
        token = envelope["token"].encode("ascii")
        if envelope.get("schema_version") != MAP_SCHEMA_VERSION:
            raise ReversibleMapError("Versione della mappa reversibile non supportata.")
    except (KeyError, TypeError, ValueError) as exc:
        raise ReversibleMapError("File mappa reversibile non valido.") from exc

    try:
        payload = Fernet(_derive_key(passphrase, salt)).decrypt(token)
        decoded = json.loads(payload.decode("utf-8"))
        entries = decoded.get("entries", [])
        return tuple(
            ReversibleMapEntry(
                placeholder=str(entry["placeholder"]),
                entity_type=str(entry["entity_type"]),
                value=str(entry["value"]),
            )
            for entry in entries
        )
    except (InvalidToken, KeyError, TypeError, ValueError) as exc:
        raise ReversibleMapError("Password errata o mappa reversibile danneggiata.") from exc


def write_encrypted_mapping(path: str | Path, mapping: Iterable[ReversibleMapEntry], passphrase: str) -> None:
    target = Path(path)
    target.write_bytes(encrypt_mapping(mapping, passphrase))


def read_encrypted_mapping(path: str | Path, passphrase: str) -> tuple[ReversibleMapEntry, ...]:
    return decrypt_mapping(Path(path).read_bytes(), passphrase)


def _mapping_payload(mapping: Iterable[ReversibleMapEntry]) -> bytes:
    payload = {
        "schema_version": MAP_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "app": "OMISSIS",
        "app_version": __version__,
        "entries": [asdict(entry) for entry in mapping],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _placeholder_index(placeholder: str) -> int:
    try:
        return int(placeholder.rsplit("_", 1)[1].rstrip(">"))
    except (IndexError, ValueError):
        return 0
