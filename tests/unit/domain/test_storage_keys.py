"""Acceptance tests for S07 — storage keys (specs/S07-object-storage.md, D-014)."""

import importlib
import re
from types import ModuleType

import pytest
from hypothesis import given
from hypothesis import strategies as st


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.storage_keys")


TENANT = st.from_regex(r"[a-z0-9][a-z0-9-]{0,30}", fullmatch=True)
UPLOAD_ID = st.uuids().map(str)
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")  # the layout rule, restated for the test


@given(tenant=TENANT, upload_id=UPLOAD_ID)
def test_keys_prefixed_by_tenant(tenant: str, upload_id: str) -> None:
    """AC-4: the tenant is the second path segment of every key (D-014)."""
    m = _mod()
    assert m.incoming_key(tenant, upload_id).split("/")[:2] == ["incoming", tenant]
    assert m.work_key(tenant, upload_id, "chunk-0001.wav").split("/")[:2] == ["work", tenant]


@given(tenant=st.text(min_size=1, max_size=20).filter(lambda s: not ID_PATTERN.fullmatch(s)))
def test_rejects_unsafe_tenant_ids(tenant: str) -> None:
    with pytest.raises(ValueError, match="tenant"):
        _mod().incoming_key(tenant, "00000000-0000-0000-0000-000000000000")


@pytest.mark.parametrize("name", ["../escape.wav", "a/b.wav", ""])
def test_rejects_unsafe_work_names(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        _mod().work_key("tenant-a", "job-1", name)


def test_check_incoming_key_accepts_only_the_incoming_layout() -> None:
    m = _mod()
    m.check_incoming_key("incoming/tenant-a/upload-1")
    for bad in ("work/tenant-a/upload-1", "incoming/tenant-a", "incoming/a/b/c", "incoming/../x"):
        with pytest.raises(ValueError, match=r"incoming|invalid"):
            m.check_incoming_key(bad)


def test_check_prefix_requires_a_whole_segment() -> None:
    m = _mod()
    assert m.check_prefix("work/tenant-a/job-1/") == "work/tenant-a/job-1/"
    for bad in ("", "work/tenant-a/job-1"):
        with pytest.raises(ValueError, match="prefix"):
            m.check_prefix(bad)
