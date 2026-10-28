"""Access keys: who may see which document, used as-is from users.json and permissions.json."""
import json
from functools import lru_cache
from pathlib import Path

from common.config import load_config

PUBLIC_KEY = ""          # empty required_groups: every user may see it
SEPARATOR = "|"


def deny_key() -> str:
    return load_config()["access"]["deny_key"]


@lru_cache(maxsize=1)
def users() -> dict[str, set[str]]:
    """user_id -> set of groups."""
    data = json.loads(load_config()["paths"]["users"].read_text())
    return {u["id"]: set(u["groups"]) for u in data["users"]}


@lru_cache(maxsize=1)
def permissions() -> dict[str, list[str]]:
    """doc path relative to data/ (e.g. 'corpus/manuals/x.pdf') -> required_groups."""
    data = json.loads(load_config()["paths"]["permissions"].read_text())
    return {path: doc["required_groups"] for path, doc in data["documents"].items()}


def validate_groups() -> None:
    """Fail if the deny key is used as a real group name anywhere."""
    groups = set().union(*users().values(), *permissions().values())
    if deny_key() in groups:
        raise ValueError(f"Group name {deny_key()!r} is reserved for documents without a permissions entry")


def acl_key(required_groups: list[str] | None) -> str:
    """None = no permissions entry -> deny key. [] -> public. Otherwise the sorted groups joined."""
    if required_groups is None:
        return deny_key()
    return SEPARATOR.join(sorted(required_groups))


def doc_acl_key(doc_path: Path) -> str:
    """Access key for a corpus file, looked up by its path relative to data/."""
    relative = doc_path.relative_to(load_config()["paths"]["data_dir"]).as_posix()
    return acl_key(permissions().get(relative))


def key_groups(key: str) -> set[str]:
    return set(key.split(SEPARATOR)) if key else set()


def permitted_keys(user_id: str, all_keys: set[str]) -> set[str]:
    """Keys whose groups the user holds in full. The deny key is never permitted.

    all_keys: every distinct acl_key that exists. At query time this is
    `SELECT DISTINCT acl_key FROM chunks` on the index; in tests it is built
    from permissions.json plus the deny key.
    """
    groups = users()[user_id]
    return {k for k in all_keys if k != deny_key() and key_groups(k) <= groups}


def eligible_users(key: str) -> list[str]:
    """Users who may see documents with this key (empty for the deny key)."""
    return [uid for uid in users() if key in permitted_keys(uid, {key})]


@lru_cache(maxsize=1)
def documents() -> dict[str, dict]:
    """doc path relative to data/ -> its full permissions.json entry (title, source_system, required_groups)."""
    return json.loads(load_config()["paths"]["permissions"].read_text())["documents"]


@lru_cache(maxsize=1)
def group_descriptions() -> dict[str, str]:
    """group -> what it means, from users.json."""
    return json.loads(load_config()["paths"]["users"].read_text())["groups"]


def certifications(user_id: str) -> dict[str, str]:
    """The user's certification groups (by the configured prefix) with their descriptions."""
    prefix = load_config()["access"]["certification_prefix"]
    return {g: group_descriptions().get(g, "") for g in sorted(users()[user_id]) if g.startswith(prefix)}
