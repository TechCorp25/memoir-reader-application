from dataclasses import dataclass

import pytest

from memoir_reader.assembly import ApprovedCover, ApprovedDedication, PublicationAssemblyError
from memoir_reader.front_matter import FrontMatterAuthority, REQUIRED_SEQUENCE
from memoir_reader.publication import build_publication_payload


@dataclass(frozen=True)
class Chapter:
    order: str
    title: str
    source: str
    pages: int
    pdf_file: str


@dataclass(frozen=True)
class Snapshot:
    repository: str
    commit_sha: str
    total_pages: int
    chapters: tuple[Chapter, ...]


CHAPTERS = (
    Chapter("01", "ONE", "chapters/01.md", 3, "01_ONE.pdf"),
    Chapter("02", "TWO", "chapters/02.md", 2, "02_TWO.pdf"),
)
SNAPSHOT = Snapshot("techcorp-DevApps/memoir", "a" * 40, 5, CHAPTERS)
DEDICATION = ApprovedDedication(
    "Exact approved words",
    "author:test",
    True,
    "image",
    "dedication-approved",
    "publication/assets/dedication.png",
    "image/png",
    "d" * 64,
    "e" * 40,
)


def ready_authority() -> FrontMatterAuthority:
    cover = ApprovedCover(
        "front-cover-approved",
        "author:test:publication/assets/front-cover.jpeg",
        "b" * 64,
        "image/jpeg",
        True,
        "publication/assets/front-cover.jpeg",
    )
    back = ApprovedCover(
        "back-cover-approved",
        "author:test:publication/assets/back-cover.jpeg",
        "c" * 64,
        "image/jpeg",
        True,
        "publication/assets/back-cover.jpeg",
    )
    return FrontMatterAuthority(
        canonical_repository="techcorp-DevApps/memoir",
        book_title="The Long Road To Nowhere",
        dedication=DEDICATION,
        cover_status="AUTHOR_APPROVED",
        cover=cover,
        back_cover_status="AUTHOR_APPROVED",
        back_cover=back,
        sequence=REQUIRED_SEQUENCE,
        activation="FAIL_CLOSED_UNTIL_FRONT_COVER_MATERIALIZED",
    )


def test_payload_preserves_manuscript_pagination_inside_physical_sequence():
    payload = build_publication_payload(SNAPSHOT, ready_authority())
    assert payload["book_title"] == "The Long Road To Nowhere"
    assert payload["dedication_presentation"] == "image"
    assert payload["dedication_asset_id"] == "dedication-approved"
    assert payload["manuscript_total_pages"] == 5
    assert payload["front_matter_pages"] == 8
    assert payload["physical_total_pages"] == 13
    assert payload["pages"][4]["kind"] == "dedication"
    assert payload["pages"][4]["asset_id"] == "dedication-approved"
    assert payload["pages"][8]["kind"] == "manuscript"
    assert payload["pages"][8]["display_number"] == 1
    assert payload["pages"][8]["chapter_order"] == "01"
    assert payload["pages"][8]["side"] == "recto"


def test_payload_index_uses_logical_manuscript_folios():
    payload = build_publication_payload(SNAPSHOT, ready_authority())
    assert payload["index"] == [
        {"order": "01", "title": "ONE", "manuscript_page": 1},
        {"order": "02", "title": "TWO", "manuscript_page": 4},
    ]


def test_payload_exposes_only_verified_materialized_asset_urls():
    payload = build_publication_payload(SNAPSHOT, ready_authority())
    assert payload["assets"]["front-cover-approved"] == {
        "asset_id": "front-cover-approved",
        "url": "/api/front-matter-asset/front-cover-approved",
        "mime_type": "image/jpeg",
        "sha256": "b" * 64,
    }
    assert payload["assets"]["dedication-approved"] == {
        "asset_id": "dedication-approved",
        "url": "/api/front-matter-asset/dedication-approved",
        "mime_type": "image/png",
        "sha256": "d" * 64,
    }
    assert payload["assets"]["back-cover-approved"]["url"] == "/api/front-matter-asset/back-cover-approved"


def test_payload_is_fail_closed_while_front_cover_bytes_are_not_materialized():
    blocked = FrontMatterAuthority(
        canonical_repository="techcorp-DevApps/memoir",
        book_title="The Long Road To Nowhere",
        dedication=DEDICATION,
        cover_status="AUTHOR_APPROVED_ASSET_NOT_MATERIALIZED",
        cover=None,
        back_cover_status="AUTHOR_APPROVED_ASSET_NOT_MATERIALIZED",
        back_cover=None,
        sequence=REQUIRED_SEQUENCE,
        activation="FAIL_CLOSED_UNTIL_FRONT_COVER_MATERIALIZED",
    )
    with pytest.raises(PublicationAssemblyError, match="AUTHOR_APPROVED_ASSET_NOT_MATERIALIZED"):
        build_publication_payload(SNAPSHOT, blocked)
