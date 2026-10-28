"""Access reconciliation: give every corpus file its access key. Nothing is inferred or corrected."""
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from common.access import doc_acl_key, deny_key, eligible_users, validate_groups
from common.config import load_config


@dataclass
class FileRecord:
    path: Path
    content_hash: str
    size_bytes: int
    acl_key: str
    flags: list[str] = field(default_factory=list)


def reconcile() -> list[FileRecord]:
    validate_groups()
    records = []
    for path in sorted(p for p in load_config()["paths"]["corpus_dir"].rglob("*") if p.is_file()):
        if path.name.startswith("."):
            continue  # OS metadata files such as .DS_Store
        data = path.read_bytes()
        key = doc_acl_key(path)
        record = FileRecord(path, hashlib.sha256(data).hexdigest(), len(data), key)
        if key == deny_key():
            record.flags.append("no_permission_entry")
        elif not eligible_users(key):
            record.flags.append("no_current_eligible_user")
        records.append(record)
    return records
