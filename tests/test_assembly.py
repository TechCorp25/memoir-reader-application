from dataclasses import dataclass

import pytest

from memoir_reader.assembly import (
    ApprovedCover,
    ApprovedDedication,
    PublicationAssemblyError,
    assemble_publication,
    build_index,
    spread_indexes,
)


@dataclass(frozen=True)
class Chapter:
    order: str
    title: str
    source: str
    pages: int
    pdf_file: str


CHAPTERS = (
    Chapter("01", "ONE", "chapters/01.md", 3, "01_ONE.pdf"),
    Chapter("02", "TWO", "chapters/02.md", 2, "02_TWO.pdf"),
)
COVER = ApprovedCover(
    asset_id="approved-cover",
    source="controlled:test",
    sha256="a" * 64,
    mime_type="image/png",
    approved=True,
)
DEDICATION = ApprovedDedication("Exact approved words", "controlled:test", True)


def test_front_matter_order_is_exact_and_blank_pages_are_preserved():
    pages = assemble_publication(CHAPTERS, cover=COVER, book_title="BOOK", dedication=DEDICATION)
    assert [page.kind for page in pages[:9]] == [
        "cover", "blank", "title", "blank", "dedication", "blank", "index", "blank", "manuscript"
    ]


def test_chapter_one_begins_at_manuscript_page_one_after_eight_front_matter_surfaces():
    pages = assemble_publication(CHAPTERS, cover=COVER, book_title="BOOK", dedication=DEDICATION)
    first_manuscript = pages[8]
    assert first_manuscript.chapter_order == "01"
    assert first_manuscript.display_number == 1
    assert first_manuscript.physical_position == 9
    assert first_manuscript.side == "recto"


def test_index_uses_logical_manuscript_page_offsets_not_physical_positions():
    entries = build_index(CHAPTERS)
    assert [(entry.title, entry.manuscript_page) for entry in entries] == [("ONE", 1), ("TWO", 4)]


def test_recto_verso_front_matter_produces_blank_left_and_content_right_spreads():
    pages = assemble_publication(CHAPTERS, cover=COVER, book_title="BOOK", dedication=DEDICATION)
    assert [(pages[i].kind, pages[i].side) for i in (1, 2)] == [("blank", "verso"), ("title", "recto")]
    assert [(pages[i].kind, pages[i].side) for i in (3, 4)] == [("blank", "verso"), ("dedication", "recto")]
    assert [(pages[i].kind, pages[i].side) for i in (5, 6)] == [("blank", "verso"), ("index", "recto")]
    assert [(pages[i].kind, pages[i].side) for i in (7, 8)] == [("blank", "verso"), ("manuscript", "recto")]


def test_wide_view_cover_is_singleton_then_physical_spreads_are_2_3_4_5():
    assert spread_indexes(0, 13) == (0,)
    assert spread_indexes(1, 13) == (1, 2)
    assert spread_indexes(2, 13) == (1, 2)
    assert spread_indexes(3, 13) == (3, 4)


def test_unapproved_cover_is_rejected():
    cover = ApprovedCover("candidate", "unverified", "a" * 64, "image/png", False)
    with pytest.raises(PublicationAssemblyError, match="not publication-approved"):
        assemble_publication(CHAPTERS, cover=cover, book_title="BOOK", dedication=DEDICATION)


def test_cover_without_provenance_hash_is_rejected():
    cover = ApprovedCover("candidate", "unverified", "", "image/png", True)
    with pytest.raises(PublicationAssemblyError, match="provenance"):
        assemble_publication(CHAPTERS, cover=cover, book_title="BOOK", dedication=DEDICATION)


def test_unapproved_dedication_is_rejected():
    dedication = ApprovedDedication("candidate text", "unverified", False)
    with pytest.raises(PublicationAssemblyError, match="not publication-approved"):
        assemble_publication(CHAPTERS, cover=COVER, book_title="BOOK", dedication=dedication)


def test_manuscript_pages_are_continuous_across_chapter_boundaries():
    pages = assemble_publication(CHAPTERS, cover=COVER, book_title="BOOK", dedication=DEDICATION)
    manuscript = [page for page in pages if page.kind == "manuscript"]
    assert [page.display_number for page in manuscript] == [1, 2, 3, 4, 5]
    assert manuscript[3].chapter_order == "02"
    assert manuscript[3].local_pdf_page == 1
