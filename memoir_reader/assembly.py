from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol


class PublicationAssemblyError(RuntimeError):
    """Raised when physical-book assembly cannot be proven from approved inputs."""


class ChapterLike(Protocol):
    order: str
    title: str
    source: str
    pages: int
    pdf_file: str


@dataclass(frozen=True)
class ApprovedCover:
    asset_id: str
    source: str
    sha256: str
    mime_type: str
    approved: bool


@dataclass(frozen=True)
class ApprovedDedication:
    content: str
    source: str
    approved: bool
    presentation: str = "script"


@dataclass(frozen=True)
class IndexEntry:
    order: str
    title: str
    manuscript_page: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "title": self.title,
            "manuscript_page": self.manuscript_page,
        }


@dataclass(frozen=True)
class PhysicalPage:
    physical_position: int
    page_id: str
    kind: str
    side: str
    display_number: int | None = None
    chapter_order: str | None = None
    chapter_title: str | None = None
    local_pdf_page: int | None = None
    pdf_file: str | None = None
    content: str | None = None
    asset_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "physical_position": self.physical_position,
            "page_id": self.page_id,
            "kind": self.kind,
            "side": self.side,
            "display_number": self.display_number,
            "chapter_order": self.chapter_order,
            "chapter_title": self.chapter_title,
            "local_pdf_page": self.local_pdf_page,
            "pdf_file": self.pdf_file,
            "content": self.content,
            "asset_id": self.asset_id,
        }


def physical_side(physical_position: int) -> str:
    if physical_position < 1:
        raise ValueError("physical position is 1-based")
    return "recto" if physical_position % 2 == 1 else "verso"


def build_index(chapters: Iterable[ChapterLike]) -> tuple[IndexEntry, ...]:
    manuscript_page = 1
    entries: list[IndexEntry] = []
    for chapter in chapters:
        if chapter.pages < 1:
            raise PublicationAssemblyError(f"Chapter {chapter.order} has an invalid page count")
        entries.append(IndexEntry(chapter.order, chapter.title, manuscript_page))
        manuscript_page += chapter.pages
    if not entries:
        raise PublicationAssemblyError("No publication-approved chapters were supplied")
    return tuple(entries)


def _validate_cover(cover: ApprovedCover) -> None:
    if not cover.approved:
        raise PublicationAssemblyError("Cover asset is not publication-approved")
    if not cover.asset_id or not cover.source or not cover.sha256:
        raise PublicationAssemblyError("Cover approval provenance is incomplete")
    if len(cover.sha256) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in cover.sha256):
        raise PublicationAssemblyError("Cover SHA-256 is invalid")
    if not cover.mime_type.startswith("image/"):
        raise PublicationAssemblyError("Approved cover must be an image asset")


def _validate_dedication(dedication: ApprovedDedication) -> None:
    if not dedication.approved:
        raise PublicationAssemblyError("Dedication is not publication-approved")
    if not dedication.content or not dedication.source:
        raise PublicationAssemblyError("Dedication approval provenance is incomplete")


def assemble_publication(
    chapters: Iterable[ChapterLike],
    *,
    cover: ApprovedCover,
    book_title: str,
    dedication: ApprovedDedication,
) -> tuple[PhysicalPage, ...]:
    """Assemble the physical book without changing manuscript page numbering.

    The required front matter is eight physical surfaces before Chapter 1. The
    cover is a physical surface but is never manuscript page 1. Manuscript folios
    begin at one on the first approved PDF page.
    """

    _validate_cover(cover)
    _validate_dedication(dedication)
    if not book_title.strip():
        raise PublicationAssemblyError("Book title is missing")

    chapter_list = tuple(chapters)
    index_entries = build_index(chapter_list)
    index_text = "\n".join(f"{entry.title}\t{entry.manuscript_page}" for entry in index_entries)

    front_matter: list[tuple[str, str, str | None, str | None]] = [
        ("cover", "front-matter:cover", None, cover.asset_id),
        ("blank", "front-matter:blank-1", None, None),
        ("title", "front-matter:title", book_title, None),
        ("blank", "front-matter:blank-2", None, None),
        ("dedication", "front-matter:dedication", dedication.content, None),
        ("blank", "front-matter:blank-3", None, None),
        ("index", "front-matter:index", index_text, None),
        ("blank", "front-matter:blank-4", None, None),
    ]

    pages: list[PhysicalPage] = []
    for kind, page_id, content, asset_id in front_matter:
        position = len(pages) + 1
        pages.append(
            PhysicalPage(
                physical_position=position,
                page_id=page_id,
                kind=kind,
                side=physical_side(position),
                content=content,
                asset_id=asset_id,
            )
        )

    manuscript_page = 1
    for chapter in chapter_list:
        for local_pdf_page in range(1, chapter.pages + 1):
            position = len(pages) + 1
            pages.append(
                PhysicalPage(
                    physical_position=position,
                    page_id=f"chapter:{chapter.order}:page:{local_pdf_page}",
                    kind="manuscript",
                    side=physical_side(position),
                    display_number=manuscript_page,
                    chapter_order=chapter.order,
                    chapter_title=chapter.title,
                    local_pdf_page=local_pdf_page,
                    pdf_file=chapter.pdf_file,
                )
            )
            manuscript_page += 1

    return tuple(pages)


def spread_indexes(anchor: int, total_physical_pages: int) -> tuple[int, ...]:
    """Return zero-based physical page indexes for a wide-view book spread.

    The closed cover is a singleton. After opening it, spreads pair even physical
    positions on the left with the following odd physical position on the right:
    2-3, 4-5, 6-7, 8-9, ...
    """

    if total_physical_pages <= 0:
        return ()
    bounded = max(0, min(anchor, total_physical_pages - 1))
    if bounded == 0:
        return (0,)
    physical_position = bounded + 1
    spread_start_position = physical_position if physical_position % 2 == 0 else physical_position - 1
    start_index = spread_start_position - 1
    indexes = [start_index]
    if start_index + 1 < total_physical_pages:
        indexes.append(start_index + 1)
    return tuple(indexes)
