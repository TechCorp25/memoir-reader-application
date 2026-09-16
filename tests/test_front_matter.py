import json
from pathlib import Path

import pytest

from memoir_reader.assembly import PublicationAssemblyError
from memoir_reader.front_matter import (
    APPROVED_NOT_MATERIALIZED,
    REQUIRED_SEQUENCE,
    load_front_matter_authority,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = REPO_ROOT / "publication" / "front-matter-authority.json"


def test_controlled_authority_records_exact_required_sequence_and_approved_dedication():
    authority = load_front_matter_authority(AUTHORITY_PATH)
    assert authority.sequence == REQUIRED_SEQUENCE
    assert authority.book_title == "The Long Road To Nowhere"
    assert authority.dedication.content == (
        "For anyone who's ever felt lost, questioned the path being travelled or wondered if it's to late to start again"
    )
    assert authority.dedication.presentation == "script"


def test_front_cover_authority_is_approved_but_remains_fail_closed_until_bytes_are_materialized():
    authority = load_front_matter_authority(AUTHORITY_PATH)
    assert authority.cover_status == APPROVED_NOT_MATERIALIZED
    assert authority.cover is None
    assert authority.ready is False
    with pytest.raises(PublicationAssemblyError, match="AUTHOR_APPROVED_ASSET_NOT_MATERIALIZED"):
        authority.require_ready()


def test_back_cover_authority_is_approved_and_sha_bound_but_not_yet_repository_materialized():
    authority = load_front_matter_authority(AUTHORITY_PATH)
    assert authority.back_cover_status == APPROVED_NOT_MATERIALIZED
    assert authority.back_cover is None
    assert authority.back_cover_ready is False
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    assert payload["back_cover"]["sha256"] == "6b59c5d29bf561660210cfda6890e590a1bf48a34a37983a32135c876122cfb1"
    assert payload["back_cover"]["source_file_id"] == "file_0000000041ec820b896edee6effd01cd"


def test_canonical_repository_mismatch_is_rejected(tmp_path):
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    payload["canonical_repository"] = "other/repo"
    target = tmp_path / "front-matter-authority.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PublicationAssemblyError, match="canonical repository"):
        load_front_matter_authority(target)


def test_materialized_front_cover_requires_complete_provenance(tmp_path):
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    payload["cover"]["approval_status"] = "AUTHOR_APPROVED"
    target = tmp_path / "front-matter-authority.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PublicationAssemblyError, match="Front cover approval provenance"):
        load_front_matter_authority(target)
