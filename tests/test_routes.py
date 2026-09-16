from memoir_reader import create_app
from memoir_reader.assembly import ApprovedCover, ApprovedDedication
from memoir_reader.front_matter import FrontMatterAuthority, REQUIRED_SEQUENCE
from memoir_reader.source import ApprovedChapter, BookSnapshot, SourceError


COMMIT = "a" * 40
BACK_COVER_SHA256 = "6b59c5d29bf561660210cfda6890e590a1bf48a34a37983a32135c876122cfb1"
CHAPTERS = (
    ApprovedChapter("01", "ONE", "chapters/01.md", 3, "01_ONE.pdf"),
    ApprovedChapter("02", "TWO", "chapters/02.md", 2, "02_TWO.pdf"),
)
SNAPSHOT = BookSnapshot(
    repository="techcorp-DevApps/memoir",
    requested_ref="main",
    commit_sha=COMMIT,
    manifest_base_commit=None,
    total_pages=5,
    chapters=CHAPTERS,
    generated_at_unix=0,
)


class FakeSource:
    def __init__(self, snapshot=SNAPSHOT, error=None):
        self._snapshot = snapshot
        self._error = error

    def snapshot(self):
        if self._error:
            raise self._error
        return self._snapshot


def client_for(fake_source):
    app = create_app()
    app.config.update(TESTING=True)
    app.extensions["book_source"] = fake_source
    return app.test_client()


def ready_authority():
    front = ApprovedCover(
        asset_id="front-cover-approved",
        source="author:test:publication/assets/front-cover.jpeg",
        sha256="b" * 64,
        mime_type="image/jpeg",
        approved=True,
        asset_path="publication/assets/front-cover.jpeg",
    )
    back = ApprovedCover(
        asset_id="back-cover-approved",
        source="author:test:publication/assets/back-cover.jpeg",
        sha256="c" * 64,
        mime_type="image/jpeg",
        approved=True,
        asset_path="publication/assets/back-cover.jpeg",
    )
    return FrontMatterAuthority(
        canonical_repository="techcorp-DevApps/memoir",
        book_title="The Long Road To Nowhere",
        dedication=ApprovedDedication("Exact approved words", "author:test", True),
        cover_status="AUTHOR_APPROVED",
        cover=front,
        back_cover_status="AUTHOR_APPROVED",
        back_cover=back,
        sequence=REQUIRED_SEQUENCE,
        activation="FAIL_CLOSED_UNTIL_FRONT_COVER_MATERIALIZED",
    )


def test_health_keeps_canonical_reader_healthy_while_physical_assembly_is_blocked(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    response = client_for(FakeSource()).get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["canonical_source"] == "techcorp-DevApps/memoir"
    assert payload["commit_sha"] == COMMIT
    assert payload["application_commit"] is None
    assert payload["publication_assembly"]["status"] == "blocked"
    assert payload["publication_assembly"]["front_cover"] == "AUTHOR_APPROVED_ASSET_NOT_MATERIALIZED"
    assert payload["publication_assembly"]["front_cover_materialized"] is False
    assert payload["publication_assembly"]["back_cover"] == "AUTHOR_APPROVED"
    assert payload["publication_assembly"]["back_cover_materialized"] is True


def test_health_exposes_render_application_commit_for_deployment_verification(monkeypatch):
    application_commit = "d" * 40
    monkeypatch.setenv("RENDER_GIT_COMMIT", application_commit)
    response = client_for(FakeSource()).get("/health")
    assert response.status_code == 200
    assert response.get_json()["application_commit"] == application_commit


def test_publication_endpoint_fails_closed_until_exact_front_cover_is_materialized():
    response = client_for(FakeSource()).get("/api/publication")
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["error"] == "publication_assembly_unavailable"
    assert payload["commit_sha"] == COMMIT
    assert "AUTHOR_APPROVED_ASSET_NOT_MATERIALIZED" in payload["message"]


def test_publication_endpoint_returns_commit_pinned_physical_model_when_ready(monkeypatch):
    import memoir_reader.routes as routes

    monkeypatch.setattr(routes, "load_front_matter_authority", lambda **kwargs: ready_authority())
    response = client_for(FakeSource()).get("/api/publication")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["commit_sha"] == COMMIT
    assert payload["manuscript_total_pages"] == 5
    assert payload["front_matter_pages"] == 8
    assert payload["physical_total_pages"] == 13
    assert payload["pages"][0]["kind"] == "cover"
    assert payload["pages"][8]["kind"] == "manuscript"
    assert payload["pages"][8]["display_number"] == 1
    assert payload["assets"]["front-cover-approved"]["url"] == "/api/front-matter-asset/front-cover-approved"
    assert payload["assets"]["back-cover-approved"]["url"] == "/api/front-matter-asset/back-cover-approved"
    assert response.headers["X-Memoir-Commit"] == COMMIT
    assert response.headers["Cache-Control"] == "no-store"


def test_publication_endpoint_rejects_unverified_canonical_source():
    response = client_for(FakeSource(error=SourceError("canonical unavailable"))).get("/api/publication")
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["error"] == "canonical_source_unavailable"


def test_front_matter_asset_route_rejects_unmaterialized_front_cover():
    response = client_for(FakeSource()).get("/api/front-matter-asset/front-cover-approved")
    assert response.status_code == 404
    assert response.get_json()["error"] == "front_matter_asset_unavailable"


def test_materialized_back_cover_route_is_available_and_sha_bound():
    response = client_for(FakeSource()).get("/api/front-matter-asset/back-cover-approved")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.data.startswith(b"\xff\xd8\xff")
    assert response.headers["X-Asset-SHA256"] == BACK_COVER_SHA256
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_front_matter_asset_route_serves_only_verified_asset(monkeypatch, tmp_path):
    import memoir_reader.routes as routes

    payload = b"\xff\xd8\xff\xe0verified-cover"
    target = tmp_path / "front-cover.jpeg"
    target.write_bytes(payload)
    authority = ready_authority()
    monkeypatch.setattr(routes, "load_front_matter_authority", lambda **kwargs: authority)
    monkeypatch.setattr(routes, "resolve_approved_asset_path", lambda asset: target)

    response = client_for(FakeSource()).get("/api/front-matter-asset/front-cover-approved")
    assert response.status_code == 200
    assert response.data == payload
    assert response.mimetype == "image/jpeg"
    assert response.headers["X-Asset-SHA256"] == "b" * 64
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_front_matter_asset_route_rejects_unknown_asset(monkeypatch):
    import memoir_reader.routes as routes

    monkeypatch.setattr(routes, "load_front_matter_authority", lambda **kwargs: ready_authority())
    response = client_for(FakeSource()).get("/api/front-matter-asset/not-approved")
    assert response.status_code == 404
    assert response.get_json()["error"] == "front_matter_asset_unavailable"
