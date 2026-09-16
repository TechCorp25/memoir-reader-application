from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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
APPROVED = "AUTHOR_APPROVED"
APPROVED_NOT_MATERIALIZED = "AUTHOR_APPROVED_ASSET_NOT_MATERIALIZED"
ACTIVATION_POLICY = "FAIL_CLOSED_UNTIL_FRONT_COVER_MATERIALIZED"


@dataclass(frozen=True)
class FrontMatterAuthority:
    canonical_repository: str
    book_title: str
    dedication: ApprovedDedication
    cover_status: str
    cover: ApprovedCover | None
    back_cover_status: str
    back_cover: ApprovedCover | None
    sequence: tuple[str, ...]
    activation: str

    @property
    def ready(self) -> bool:
        return self.cover is not None and self.cover.approved

    @property
    def back_cover_ready(self) -> bool:
        return self.back_cover is not None and self.back_cover.approved

    @property
    def all_covers_ready(self) -> bool:
        return self.ready and self.back_cover_ready

    def require_ready(self) -> None:
        if not self.ready:
            raise PublicationAssemblyError(f"Front matter is not publication-ready: {self.cover_status}")

    def approved_asset(self, asset_id: str) -> ApprovedCover:
        for asset in (self.cover, self.back_cover):
            if asset is not None and asset.approved and asset.asset_id == asset_id:
                return asset

        dedication = self.dedication
        if (
            dedication.approved
            and dedication.presentation == "image"
            and dedication.asset_id == asset_id
            and dedication.asset_path
            and dedication.mime_type
            and dedication.sha256
        ):
            return ApprovedCover(
                asset_id=dedication.asset_id,
                source=f"{dedication.source}:{dedication.asset_path}",
                sha256=dedication.sha256,
                mime_type=dedication.mime_type,
                approved=True,
                asset_path=dedication.asset_path,
            )

        raise PublicationAssemblyError("Requested front-matter asset is not publication-approved and materialized")


def _required_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise PublicationAssemblyError(f"Front-matter authority is missing {key}")
    return value


def _safe_asset_path(asset_root: Path, relative_path: str, label: str) -> Path:
    posix = PurePosixPath(relative_path)
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        raise PublicationAssemblyError(f"{label} asset path is invalid")
    resolved_root = asset_root.resolve()
    resolved_asset = (asset_root / Path(*posix.parts)).resolve()
    if resolved_asset != resolved_root and resolved_root not in resolved_asset.parents:
        raise PublicationAssemblyError(f"{label} asset path escapes the application root")
    return resolved_asset


def resolve_approved_asset_path(
    asset: ApprovedCover,
    authority_path: Path | str = FRONT_MATTER_AUTHORITY_PATH,
) -> Path:
    if not asset.approved or not asset.asset_path:
        raise PublicationAssemblyError("Approved asset path is unavailable")
    root = Path(authority_path).resolve().parent.parent
    return _safe_asset_path(root, asset.asset_path, "Front-matter asset")


def _validate_image_bytes(payload: bytes, mime_type: str, label: str) -> None:
    signatures = {
        "image/jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
        "image/png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": lambda value: len(value) >= 12 and value[:4] == b"RIFF" and value[8:12] == b"WEBP",
    }
    check = signatures.get(mime_type)
    if check is None or not check(payload):
        raise PublicationAssemblyError(f"{label} bytes do not match the approved image type")


def _git_blob_sha(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _load_cover(
    data: dict[str, Any],
    *,
    label: str,
    asset_root: Path,
    allow_unmaterialized: bool = False,
) -> tuple[str, ApprovedCover | None]:
    status = str(data.get("approval_status") or "")
    if status == APPROVED:
        asset_id = str(data.get("asset_id") or "")
        asset_path = str(data.get("asset_path") or "")
        sha256 = str(data.get("sha256") or "")
        mime_type = str(data.get("mime_type") or "")
        authority = str(data.get("authority") or "")
        if not all((asset_id, asset_path, sha256, mime_type, authority)):
            raise PublicationAssemblyError(f"{label} approval provenance is incomplete")
        if len(sha256) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in sha256):
            raise PublicationAssemblyError(f"{label} SHA-256 is invalid")
        if not mime_type.startswith("image/"):
            raise PublicationAssemblyError(f"{label} must be an image asset")

        file_path = _safe_asset_path(asset_root, asset_path, label)
        try:
            payload = file_path.read_bytes()
        except OSError as exc:
            raise PublicationAssemblyError(f"{label} approved asset could not be read") from exc
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256.lower() != sha256.lower():
            raise PublicationAssemblyError(f"{label} approved asset SHA-256 does not match authority")
        _validate_image_bytes(payload, mime_type, label)

        return status, ApprovedCover(
            asset_id=asset_id,
            source=f"{authority}:{asset_path}",
            sha256=sha256.lower(),
            mime_type=mime_type,
            approved=True,
            asset_path=asset_path,
        )
    if allow_unmaterialized and status == APPROVED_NOT_MATERIALIZED:
        if not str(data.get("authority") or ""):
            raise PublicationAssemblyError(f"{label} author approval provenance is incomplete")
        return status, None
    raise PublicationAssemblyError(f"{label} approval status is invalid")


def _load_dedication(data: dict[str, Any], *, asset_root: Path) -> ApprovedDedication:
    if data.get("approval_status") != APPROVED:
        raise PublicationAssemblyError("Dedication is not publication-approved")

    content = str(data.get("value") or "")
    authority = str(data.get("authority") or "")
    presentation = str(data.get("presentation") or "script")
    if not content or not authority:
        raise PublicationAssemblyError("Dedication approval provenance is incomplete")

    if presentation != "image":
        return ApprovedDedication(
            content=content,
            source=authority,
            approved=True,
            presentation=presentation,
        )

    asset_id = str(data.get("asset_id") or "")
    asset_path = str(data.get("asset_path") or "")
    git_blob_sha = str(data.get("git_blob_sha") or "").lower()
    mime_type = str(data.get("mime_type") or "")
    if not all((asset_id, asset_path, git_blob_sha, mime_type)):
        raise PublicationAssemblyError("Dedication image approval provenance is incomplete")
    if len(git_blob_sha) != 40 or any(ch not in "0123456789abcdef" for ch in git_blob_sha):
        raise PublicationAssemblyError("Dedication Git blob SHA is invalid")
    if not mime_type.startswith("image/"):
        raise PublicationAssemblyError("Dedication must be an image asset")

    file_path = _safe_asset_path(asset_root, asset_path, "Dedication")
    try:
        payload = file_path.read_bytes()
    except OSError as exc:
        raise PublicationAssemblyError("Dedication approved asset could not be read") from exc

    actual_git_blob_sha = _git_blob_sha(payload)
    if actual_git_blob_sha != git_blob_sha:
        raise PublicationAssemblyError("Dedication approved asset Git blob SHA does not match authority")
    _validate_image_bytes(payload, mime_type, "Dedication")

    return ApprovedDedication(
        content=content,
        source=authority,
        approved=True,
        presentation="image",
        asset_id=asset_id,
        asset_path=asset_path,
        mime_type=mime_type,
        sha256=hashlib.sha256(payload).hexdigest(),
        git_blob_sha=git_blob_sha,
    )


def load_front_matter_authority(
    path: Path | str = FRONT_MATTER_AUTHORITY_PATH,
    *,
    expected_canonical_repository: str = "techcorp-DevApps/memoir",
) -> FrontMatterAuthority:
    authority_path = Path(path)
    try:
        payload = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationAssemblyError("Front-matter authority could not be loaded") from exc

    if payload.get("schema_version") != 2:
        raise PublicationAssemblyError("Front-matter authority schema is unsupported")
    if payload.get("canonical_repository") != expected_canonical_repository:
        raise PublicationAssemblyError("Front-matter authority does not match the canonical repository")
    if payload.get("canonical_precedence") is not True:
        raise PublicationAssemblyError("Canonical front-matter precedence is not asserted")

    sequence = tuple(payload.get("sequence") or ())
    if sequence != REQUIRED_SEQUENCE:
        raise PublicationAssemblyError("Front-matter physical sequence is invalid")

    title = _required_mapping(payload, "book_title")
    if title.get("approval_status") != APPROVED or not str(title.get("value") or "").strip():
        raise PublicationAssemblyError("Book-title authority is incomplete")

    # The authority file lives under publication/. Approved asset paths are
    # application-root-relative and therefore resolve one directory above it.
    asset_root = authority_path.resolve().parent.parent
    dedication = _load_dedication(_required_mapping(payload, "dedication"), asset_root=asset_root)
    cover_status, cover = _load_cover(
        _required_mapping(payload, "cover"),
        label="Front cover",
        asset_root=asset_root,
        allow_unmaterialized=True,
    )
    back_cover_status, back_cover = _load_cover(
        _required_mapping(payload, "back_cover"),
        label="Back cover",
        asset_root=asset_root,
        allow_unmaterialized=True,
    )

    activation = str(payload.get("activation") or "")
    if activation != ACTIVATION_POLICY:
        raise PublicationAssemblyError("Front-matter activation policy is invalid")

    return FrontMatterAuthority(
        canonical_repository=expected_canonical_repository,
        book_title=str(title["value"]),
        dedication=dedication,
        cover_status=cover_status,
        cover=cover,
        back_cover_status=back_cover_status,
        back_cover=back_cover,
        sequence=sequence,
        activation=activation,
    )
