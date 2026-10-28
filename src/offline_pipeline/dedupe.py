"""Deduplication by content hash. Same content + same access key -> keep one."""
from dataclasses import dataclass

from offline_pipeline.reconcile import FileRecord


@dataclass
class Duplicate:
    record: FileRecord
    duplicate_of: FileRecord


def dedupe(records: list[FileRecord]) -> tuple[list[FileRecord], list[Duplicate]]:
    """Return (kept, dropped). The first file by path is kept, so the result is deterministic."""
    kept: dict[tuple[str, str], FileRecord] = {}
    dropped = []
    for record in sorted(records, key=lambda r: r.path.as_posix()):
        group = (record.content_hash, record.acl_key)
        if group in kept:
            dropped.append(Duplicate(record, kept[group]))
        else:
            kept[group] = record
    return list(kept.values()), dropped
