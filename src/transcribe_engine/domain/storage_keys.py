"""Object-store key layout (S07, D-014). Pure functions, no I/O.

The tenant is always the second path segment: `incoming/{tenant}/...` and `work/{tenant}/...`.
Ids are server-generated; anything that could escape its segment is rejected.
"""

import re

__all__ = ["check_incoming_key", "check_prefix", "incoming_key", "work_key"]

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def _check_id(kind: str, value: str) -> str:
    if not _ID.fullmatch(value):
        raise ValueError(f"invalid {kind}: must be 1-64 letters, digits, '_' or '-'")
    return value


def incoming_key(tenant_id: str, upload_id: str) -> str:
    """Key for a raw upload: incoming/{tenant}/{upload_id}."""
    return f"incoming/{_check_id('tenant id', tenant_id)}/{_check_id('upload id', upload_id)}"


def work_key(tenant_id: str, job_id: str, name: str) -> str:
    """Key for a derived object of a job: work/{tenant}/{job}/{name}."""
    if not name or "/" in name or ".." in name or name.strip(".") == "":
        raise ValueError("invalid name: must be a plain file name")
    return f"work/{_check_id('tenant id', tenant_id)}/{_check_id('job id', job_id)}/{name}"


def check_incoming_key(key: str) -> None:
    """Raise ValueError unless `key` is an incoming key with valid ids (no segment escape)."""
    parts = key.split("/")
    if len(parts) != 3 or parts[0] != "incoming":
        raise ValueError("not an incoming key")
    incoming_key(parts[1], parts[2])


def check_prefix(prefix: str) -> str:
    """A listing or delete prefix must name a whole segment: non-empty and ending in '/' (D-015)."""
    if not prefix or not prefix.endswith("/"):
        raise ValueError("prefix must be non-empty and end with '/'")
    return prefix
