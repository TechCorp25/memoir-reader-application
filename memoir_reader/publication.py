from __future__ import annotations

from typing import Any, Protocol

from .assembly import ApprovedCover, PhysicalPage, build_index, assemble_publication
from .front_matter import FrontMatterAuthority


class SnapshotLike(Protocol):
    repository: str
    commit_sha: str
    total_pages: int
    chapters: tuple[Any, ...]


FRONT_MATTER_PAGE_COUNT = 8


def _asset_payload(asset: ApprovedCover) -> dict[str, str]:
    return {
        "asset_id": asset.asset_id,
        "url": f"/api/front-matter-asset/{asset.asset_id}",
        "mime_type": asset.mime_type,
        "sha256": asset.sha256,
    }


def build_publication_payload(snapshot: SnapshotLike, authority: FrontMatterAuthority) -> dict[str, Any]:
    """Build a commit-pinned physical-book payload from verified authorities.

    This function is deliberately fail-closed. It cannot assemble a physical book
    until the exact approved front-cover bytes have been materialised and validated
    by the front-matter authority loader.
    """

    authority.require_ready()
    if authority.cover is None:
        raise AssertionError("front-matter authority reported ready without a cover")

    pages: tuple[PhysicalPage, ...] = assemble_publication(
        snapshot.chapters,
        cover=authority.cover,
        book_title=authority.book_title,
        dedication=authority.dedication,
    )
    if len(pages) != FRONT_MATTER_PAGE_COUNT + snapshot.total_pages:
        raise ValueError("Physical publication page count failed integrity validation")

    assets = {authority.cover.asset_id: _asset_payload(authority.cover)}
    dedication_asset_id = authority.dedication.asset_id
    if authority.dedication.presentation == "image" and dedication_asset_id:
        dedication_asset = authority.approved_asset(dedication_asset_id)
        assets[dedication_asset.asset_id] = _asset_payload(dedication_asset)
    if authority.back_cover_ready and authority.back_cover is not None:
        assets[authority.back_cover.asset_id] = _asset_payload(authority.back_cover)

    return {
        "repository": snapshot.repository,
        "commit_sha": snapshot.commit_sha,
        "book_title": authority.book_title,
        "dedication_presentation": authority.dedication.presentation,
        "dedication_asset_id": dedication_asset_id,
        "manuscript_total_pages": snapshot.total_pages,
        "front_matter_pages": FRONT_MATTER_PAGE_COUNT,
        "physical_total_pages": len(pages),
        "index": [entry.as_dict() for entry in build_index(snapshot.chapters)],
        "pages": [page.as_dict() for page in pages],
        "assets": assets,
        "cover_asset_id": authority.cover.asset_id,
        "back_cover": {
            "approval_status": authority.back_cover_status,
            "materialized": authority.back_cover_ready,
            "asset_id": authority.back_cover.asset_id if authority.back_cover else None,
        },
    }
