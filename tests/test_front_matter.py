import json
from pathlib import Path

import pytest

from memoir_reader.assembly import PublicationAssemblyError
from memoir_reader.front_matter import REQUIRED_SEQUENCE, load_front_matter_authority


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


def test_missing_approved_cover_keeps_front_matter_fail_closed():
    authority = load_front_matter_authority(AUTHORITY_PATH)
    assert authority.ready is False
    assert authority.cover is None
    with pytest.raises(PublicationAssemblyError, match="BLOCKED_MISSING_APPROVED_ASSET"):
        authority.require_ready()


def test_canonical_repository_mismatch_is_rejected(tmp_path):
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    payload["canonical_repository"] = "other/repo"
    target = tmp_path / "front-matter-authority.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PublicationAssemblyError, match="canonical repository"):
        load_front_matter_authority(target)


def test_approved_cover_requires_complete_provenance(tmp_path):
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    payload["cover"]["approval_status"] = "AUTHOR_APPROVED"
    target = tmp_path / "front-matter-authority.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PublicationAssemblyError, match="Cover approval provenance"):
        load_front_matter_authority(target)
