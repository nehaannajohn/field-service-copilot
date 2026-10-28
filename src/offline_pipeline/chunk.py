"""Turn one file's parsed units into chunks: thread grouping, splitting, context header, stable IDs."""
import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache

import tiktoken

from common.access import documents
from common.config import load_config
from offline_pipeline.reconcile import FileRecord


@dataclass
class Chunk:
    chunk_id: str
    doc_path: str
    doc_title: str
    doc_type: str
    revision: str
    effective_date: str
    locator: dict
    header: str
    text_original: str
    text_en: str
    lang: str
    transformations_applied: list[str]
    acl_key: str
    flags: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def encoder():
    return tiktoken.encoding_for_model(load_config()["models"]["embedding"])


def tokens(text: str) -> int:
    return len(encoder().encode(text))


def build_chunks(record: FileRecord, results: list[dict]) -> list[Chunk]:
    """results: the checked model output for each part of the file, in part order."""
    rel_path = record.path.relative_to(load_config()["paths"]["data_dir"]).as_posix()
    info = documents().get(rel_path, {})
    meta = results[0]["metadata"]
    doc_title = info.get("title") or record.path.name
    doc_type = meta["doc_type"] if meta["doc_type"] != "unknown" else info.get("source_system", "unknown")
    transformations = sorted({t for r in results for t in r["transformations_applied"]})
    units = merge_sections([u for r in results for u in r["units"]])

    chunks = []
    for group_index, group in enumerate(group_threads(units)):
        for piece_index, (pieces, locator) in enumerate(split_group(group)):
            text_original, text_en = pieces
            label = " › ".join(locator["section_path"]) or locator.get("record_id") or ""
            header = " | ".join(x for x in [doc_title, meta["revision"], label] if x and x != "unknown")
            chunk_key = f"{rel_path}|{group_index}|{json.dumps(locator, sort_keys=True)}|{piece_index}"
            chunks.append(Chunk(
                chunk_id=hashlib.sha256(chunk_key.encode()).hexdigest()[:16],
                doc_path=rel_path, doc_title=doc_title, doc_type=doc_type,
                revision=meta["revision"], effective_date=meta["effective_date"],
                locator=locator, header=header, text_original=text_original, text_en=text_en,
                lang=group[0]["lang"], transformations_applied=transformations, acl_key=record.acl_key,
            ))
    return chunks


def merge_sections(units: list[dict]) -> list[dict]:
    """Drop empty units; merge consecutive plain units of the same section, up to the token limit."""
    limit = load_config()["chunking"]["max_tokens"]
    merged = []
    for unit in units:
        if not unit["text_original"].strip():
            continue
        prev = merged[-1] if merged else None
        plain = lambda u: not u["parent_id"] and u["unit_type"] == "section"
        if (prev and plain(prev) and plain(unit)
                and prev["locator"]["section_path"] == unit["locator"]["section_path"]
                and tokens(prev["text_en"] + "\n\n" + unit["text_en"]) <= limit):
            prev["text_original"] += "\n\n" + unit["text_original"]
            prev["text_en"] += "\n\n" + unit["text_en"]
        else:
            merged.append(dict(unit))
    return merged


def group_threads(units: list[dict]) -> list[list[dict]]:
    """Units that reply to another unit's record_id are grouped under their root, in original order."""
    by_id = {u["locator"]["record_id"]: u for u in units if u["locator"]["record_id"]}

    def root_id(unit):
        seen = set()
        while unit["parent_id"] in by_id and unit["parent_id"] not in seen:
            seen.add(unit["parent_id"])
            unit = by_id[unit["parent_id"]]
        return unit["locator"]["record_id"] or id(unit)

    groups: dict = {}
    for unit in units:
        groups.setdefault(root_id(unit), []).append(unit)
    return list(groups.values())


def split_group(group: list[dict]) -> list[tuple[tuple[str, str], dict]]:
    """Return ((text_original, text_en), locator) pieces, each within the token limit where possible."""
    limit = load_config()["chunking"]["max_tokens"]
    locator = dict(group[0]["locator"])
    if len(group) > 1:   # a thread: root plus replies
        locator["thread_record_ids"] = [u["locator"]["record_id"] for u in group]
        windows = thread_windows(group, limit)
    else:
        windows = [group]
    pieces = []
    for window in windows:
        original = "\n\n".join(u["text_original"] for u in window)
        english = "\n\n".join(u["text_en"] for u in window)
        pieces.extend(split_text_pair(original, english, limit))
    total = len(pieces)
    return [((o, e), {**locator, "part": i, "of": total} if total > 1 else locator)
            for i, (o, e) in enumerate(pieces, 1)]


def thread_windows(group: list[dict], limit: int) -> list[list[dict]]:
    """Consecutive replies, each window starting with the root message."""
    root, replies = group[0], group[1:]
    windows, current = [], [root]
    for reply in replies:
        if len(current) > 1 and tokens("\n\n".join(u["text_en"] for u in current + [reply])) > limit:
            windows.append(current)
            current = [root]
        current.append(reply)
    windows.append(current)
    return windows


def split_text_pair(original: str, english: str, limit: int) -> list[tuple[str, str]]:
    """Split at paragraph boundaries with one paragraph of overlap. The original and English texts are
    split at the same boundaries; if their paragraph counts differ, the text is kept whole."""
    if tokens(english) <= limit:
        return [(original, english)]
    paras_en, paras_orig = english.split("\n\n"), original.split("\n\n")
    if len(paras_en) != len(paras_orig):
        return [(original, english)]
    pieces, start = [], 0
    while start < len(paras_en):
        end = start + 1
        while end < len(paras_en) and tokens("\n\n".join(paras_en[start:end + 1])) <= limit:
            end += 1
        pieces.append(("\n\n".join(paras_orig[start:end]), "\n\n".join(paras_en[start:end])))
        if end >= len(paras_en):
            break
        start = max(end - 1, start + 1)   # one paragraph of overlap
    return pieces
