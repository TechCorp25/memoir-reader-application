import hashlib
import json
from pathlib import Path

import pytest

from memoir_reader.assembly import PublicationAssemblyError
from memoir_reader.front_matter import REQUIRED_SEQUENCE, load_front_matter_authority

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = REPO_ROOT / "publication" / "front-matter-authority.json"
FRONT_COVER_PATH = REPO_ROOT / "publication" / "assets" / "33669713-CC6F-48A1-A36D-E6D04200014A.png"
FRONT_COVER_SHA256 = "adedcf87e5b38be7c3e15048967a3dc70a8a1521ad4f5d35f6bb1939dd7cb34c"
DEDICATION_PATH = REPO_ROOT / "publication" / "assets" / "49BD8356-7D82-4923-981F-FF0BB45EB283.png"
DEDICATION_GIT_BLOB_SHA = "3b4f1f878606c20bc0ac4afdf65ca8ad0aee631c"
BACK_COVER_PATH = REPO_ROOT / "publication" / "assets" / "back-cover.jpeg"
BACK_COVER_SHA256 = "6b59c5d29bf561660210cfda6890e590a1bf48a34a37983a32135c876122cfb1"


def git_blob_sha(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def test_controlled_authority_records_exact_required_sequence_and_approved_dedication():
    authority = load_front_matter_authority(AUTHORITY_PATH)
    assert authority.sequence == REQUIRED_SEQUENCE
    assert authority.book_title == "The Long Road To Nowhere"
    assert authority.dedication.content == (
        "For anyone who's ever felt lost, questioned the path being travelled or wondered if it's to late to start again"
    )
    assert authority.dedication.presentation == "image"
    assert authority.dedication.asset_id == "dedication-approved"
    assert authority.dedication.asset_path == "publication/assets/49BD8356-7D82-4923-981F-FF0BB45EB283.png"
    assert authority.dedication.mime_type == "image/png"
    assert authority.dedication.git_blob_sha == DEDICATION_GIT_BLOB_SHA
    dedication_bytes = DEDICATION_PATH.read_bytes()
    assert git_blob_sha(dedication_bytes) == DEDICATION_GIT_BLOB_SHA
    assert authority.dedication.sha256 == hashlib.sha256(dedication_bytes).hexdigest()


def test_front_cover_is_author_approved_materialized_and_exactly_sha_bound():
    authority = load_front_matter_authority(AUTHORITY_PATH)
    assert authority.cover_status == "AUTHOR_APPROVED"
    assert authority.cover is not None
    assert authority.ready is True
    assert authority.cover.asset_path == "publication/assets/33669713-CC6F-48A1-A36D-E6D04200014A.png"
    assert authority.cover.mime_type == "image/png"
    assert authority.cover.sha256 == FRONT_COVER_SHA256
    assert hashlib.sha256(FRONT_COVER_PATH.read_bytes()).hexdigest() == FRONT_COVER_SHA256
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    assert payload["cover"]["pixel_width"] == 1024
    assert payload["cover"]["pixel_height"] == 1536
    assert payload["cover"]["source_filename"] == "33669713-CC6F-48A1-A36D-E6D04200014A.png"
    authority.require_ready()


def test_back_cover_is_author_approved_materialized_and_exactly_sha_bound():
    authority = load_front_matter_authority(AUTHORITY_PATH)
    assert authority.back_cover_status == "AUTHOR_APPROVED"
    assert authority.back_cover is not None
    assert authority.back_cover_ready is True
    assert authority.back_cover.asset_path == "publication/assets/back-cover.jpeg"
    assert authority.back_cover.sha256 == BACK_COVER_SHA256
    assert hashlib.sha256(BACK_COVER_PATH.read_bytes()).hexdigest() == BACK_COVER_SHA256
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    assert payload["back_cover"]["source_file_id"] == "file_0000000041ec820b896edee6effd01cd"


def test_canonical_repository_mismatch_is_rejected(tmp_path):
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    payload["canonical_repository"] = "other/repo"
    target = tmp_path / "publication" / "front-matter-authority.json"
    target.parent.mkdir()
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PublicationAssemblyError, match="canonical repository"):
        load_front_matter_authority(target)


def _copy_required_front_matter_assets(assets_dir: Path) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / DEDICATION_PATH.name).write_bytes(DEDICATION_PATH.read_bytes())
    (assets_dir / "back-cover.jpeg").write_bytes(BACK_COVER_PATH.read_bytes())


def _materialized_authority(tmp_path: Path, image_bytes: bytes, sha256: str) -> Path:
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    payload["cover"] = {
        "approval_status": "AUTHOR_APPROVED",
        "asset_id": "front-cover-approved",
        "asset_path": "publication/assets/front-cover.jpeg",
        "sha256": sha256,
        "mime_type": "image/jpeg",
        "authority": "author:test",
    }
    authority_path = tmp_path / "publication" / "front-matter-authority.json"
    assets_dir = tmp_path / "publication" / "assets"
    _copy_required_front_matter_assets(assets_dir)
    (assets_dir / "front-cover.jpeg").write_bytes(image_bytes)
    authority_path.write_text(json.dumps(payload), encoding="utf-8")
    return authority_path


def test_materialized_front_cover_is_verified_by_exact_sha256(tmp_path):
    image_bytes = b"\xff\xd8\xff\xe0approved-test-image"
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    target = _materialized_authority(tmp_path, image_bytes, sha256)
    authority = load_front_matter_authority(target)
    assert authority.ready is True
    assert authority.cover is not None
    assert authority.cover.sha256 == sha256
    assert authority.back_cover_ready is True


def test_materialized_front_cover_hash_mismatch_is_rejected(tmp_path):
    image_bytes = b"\xff\xd8\xff\xe0approved-test-image"
    target = _materialized_authority(tmp_path, image_bytes, "0" * 64)
    with pytest.raises(PublicationAssemblyError, match="SHA-256 does not match"):
        load_front_matter_authority(target)


def test_materialized_front_cover_with_wrong_image_signature_is_rejected(tmp_path):
    image_bytes = b"not-a-jpeg"
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    target = _materialized_authority(tmp_path, image_bytes, sha256)
    with pytest.raises(PublicationAssemblyError, match="do not match the approved image type"):
        load_front_matter_authority(target)


def test_materialized_front_cover_path_traversal_is_rejected(tmp_path):
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    payload["cover"] = {
        "approval_status": "AUTHOR_APPROVED",
        "asset_id": "front-cover-approved",
        "asset_path": "../outside.jpeg",
        "sha256": "0" * 64,
        "mime_type": "image/jpeg",
        "authority": "author:test",
    }
    target = tmp_path / "publication" / "front-matter-authority.json"
    _copy_required_front_matter_assets(tmp_path / "publication" / "assets")
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PublicationAssemblyError, match="asset path is invalid"):
        load_front_matter_authority(target)


def test_dedication_asset_git_blob_mismatch_is_rejected(tmp_path):
    payload = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    payload["dedication"]["git_blob_sha"] = "0" * 40
    target = tmp_path / "publication" / "front-matter-authority.json"
    assets_dir = tmp_path / "publication" / "assets"
    _copy_required_front_matter_assets(assets_dir)
    (assets_dir / FRONT_COVER_PATH.name).write_bytes(FRONT_COVER_PATH.read_bytes())
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PublicationAssemblyError, match="Git blob SHA does not match"):
        load_front_matter_authority(target)
