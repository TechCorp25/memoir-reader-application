from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .assembly import ApprovedCover, ApprovedDedication, PublicationAssemblyError


FRONT_MATTER_AUTHORITY_PATH = Path(__file__).resolve().parents[1] / "publication" / "front-matter-authority.json"
REQUIRED_SEQUENCE = (
    "cover",
    "blank",
    "title",
    "blank",
    "dedication",
    "blank",
    "index",
    "blank",
    "manuscript",
)


@dataclass(frozen=True)
class FrontMatterAuthority:
    canonical_repository: str
    book_title: str
    dedication: ApprovedDedication
    cover_status: str
    cover: ApprovedCover | None
    sequence: tuple[str, ...]
    activation: str

    @property
    def ready(self) -> bool:
        return self.cover is not None and self.cover.approved

    def require_ready(self) -> None:
        if not self.ready:
            raise PublicationAssemblyError(f"Front matter is not publication-ready: {self.cover_status}")


def _required_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise PublicationAssemblyError(f"Front-matter authority is missing {key}")
    return value


def load_front_matter_authority(
    path: Path | str = FRONT_MATTER_AUTHORITY_PATH,
    *,
    expected_canonical_repository: str = "techcorp-DevApps/memoir",
) -> FrontMatterAuthority:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationAssemblyError("Front-matter authority could not be loaded") from exc

    if payload.get("schema_version") != 1:
        raise PublicationAssemblyError("Front-matter authority schema is unsupported")
    if payload.get("canonical_repository") != expected_canonical_repository:
        raise PublicationAssemblyError("Front-matter authority does not match the canonical repository")
    if payload.get("canonical_precedence") is not True:
        raise PublicationAssemblyError("Canonical front-matter precedence is not asserted")

    sequence = tuple(payload.get("sequence") or ())
    if sequence != REQUIRED_SEQUENCE:
        raise PublicationAssemblyError("Front-matter physical sequence is invalid")

    title = _required_mapping(payload, "book_title")
    if title.get("approval_status") != "AUTHOR_APPROVED" or not str(title.get("value") or "").strip():
        raise PublicationAssemblyError("Book-title authority is incomplete")

    dedication_data = _required_mapping(payload, "dedication")
    if dedication_data.get("approval_status") != "AUTHOR_APPROVED":
        raise PublicationAssemblyError("Dedication is not publication-approved")
    dedication_value = str(dedication_data.get("value") or "")
    dedication_authority = str(dedication_data.get("authority") or "")
    if not dedication_value or not dedication_authority:
        raise PublicationAssemblyError("Dedication approval provenance is incomplete")
    dedication = ApprovedDedication(
        content=dedication_value,
        source=dedication_authority,
        approved=True,
        presentation=str(dedication_data.get("presentation") or "script"),
    )

    cover_data = _required_mapping(payload, "cover")
    cover_status = str(cover_data.get("approval_status") or "")
    cover: ApprovedCover | None = None
    if cover_status == "AUTHOR_APPROVED":
        asset_id = str(cover_data.get("asset_id") or "")
        asset_path = str(cover_data.get("asset_path") or "")
        sha256 = str(cover_data.get("sha256") or "")
        mime_type = str(cover_data.get("mime_type") or "")
        authority = str(cover_data.get("authority") or "")
        if not all((asset_id, asset_path, sha256, mime_type, authority)):
            raise PublicationAssemblyError("Cover approval provenance is incomplete")
        cover = ApprovedCover(
            asset_id=asset_id,
            source=f"{authority}:{asset_path}",
            sha256=sha256,
            mime_type=mime_type,
            approved=True,
        )
    elif cover_status != "BLOCKED_MISSING_APPROVED_ASSET":
        raise PublicationAssemblyError("Cover approval status is invalid")

    activation = str(payload.get("activation") or "")
    if activation != "FAIL_CLOSED_UNTIL_COVER_APPROVED":
        raise PublicationAssemblyError("Front-matter activation policy is invalid")

    return FrontMatterAuthority(
        canonical_repository=expected_canonical_repository,
        book_title=str(title["value"]),
        dedication=dedication,
        cover_status=cover_status,
        cover=cover,
        sequence=sequence,
        activation=activation,
    )
