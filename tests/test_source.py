from memoir_reader.source import CanonicalBookSource, SourceError

MANIFEST = """# Publication Formatting Manifest
- Governing manuscript base commit: `abcdef1234567890`

| Order | Title | Source | Pages | DOCX text | PDF text | Raster preflight | Visual QA | Concern |
|---:|---|---|---:|---|---|---|---|---|
| 01 | APPROVED | `chapters/01.md` | 3 | PASS | PASS | PASS; font=PASS | PASS_100_PERCENT | |
| 02 | BLOCKED | `chapters/02.md` | 4 | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | blocked |
| 03 | APPROVED TWO | `chapters/03.md` | 2 | PASS | PASS | PASS; font=PASS | PASS_100_PERCENT | |
"""


def test_approved_rows_only_include_qa_passed_publication_files():
    files = ["01_APPROVED.pdf", "02_BLOCKED.pdf", "03_APPROVED_TWO.pdf"]
    chapters = CanonicalBookSource._approved_rows(MANIFEST, files)
    assert [chapter.order for chapter in chapters] == ["01", "03"]
    assert sum(chapter.pages for chapter in chapters) == 5


def test_manifest_base_commit_is_captured():
    assert CanonicalBookSource._extract_manifest_base_commit(MANIFEST) == "abcdef1234567890"


def test_missing_pdf_for_approved_row_is_hard_failure():
    try:
        CanonicalBookSource._approved_rows(MANIFEST, ["01_APPROVED.pdf"])
    except SourceError as exc:
        assert "order 03" in str(exc)
    else:
        raise AssertionError("expected SourceError")


def test_snapshot_at_rejects_non_commit_ref_without_network_call():
    source = CanonicalBookSource("owner/repo")
    try:
        source.snapshot_at("main")
    except SourceError as exc:
        assert "commit identity" in str(exc)
    else:
        raise AssertionError("expected SourceError")


def test_pdf_bytes_is_bound_to_requested_verified_commit(monkeypatch):
    source = CanonicalBookSource("owner/repo")
    commit = "a" * 40
    snapshot = __import__("memoir_reader.source", fromlist=["BookSnapshot", "ApprovedChapter"])
    chapter = snapshot.ApprovedChapter("01", "ONE", "chapters/01.md", 1, "01_ONE.pdf")
    source._snapshots_by_commit[commit] = snapshot.BookSnapshot(
        "owner/repo", "main", commit, None, 1, (chapter,), 0
    )

    class Response:
        status_code = 200
        content = b"%PDF-1.7 verified"

    monkeypatch.setattr(source._session, "get", lambda *args, **kwargs: Response())
    assert source.pdf_bytes("01_ONE.pdf", commit).startswith(b"%PDF")
    assert source.pdf_bytes("01_ONE.pdf", commit).startswith(b"%PDF")
