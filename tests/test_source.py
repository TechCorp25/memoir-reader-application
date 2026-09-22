from memoir_reader.source import CanonicalBookSource, SourceError

MANIFEST = """# Publication Formatting Manifest
- Governing manuscript base commit: `abcdef1234567890`

| Order | Title | Source | Pages | DOCX text | PDF text | Raster preflight | Visual QA | Concern |
|---:|---|---|---:|---|---|---|---|---|
| 01 | APPROVED | `chapters/01.md` | 3 | PASS | PASS | PASS; font=PASS | PASS_100_PERCENT | |
| 02 | BLOCKED | `chapters/02.md` | 4 | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | blocked |
| 03 | APPROVED TWO | `chapters/03.md` | 2 | PASS | PASS | PASS; font=PASS | PASS_100_PERCENT | |
"""

CSV_MANIFEST = """order,title,source_path,source_blob_sha,approval_status,docx_output,pdf_output,page_count,docx_text_compare,pdf_text_compare,render_preflight,visual_qa,concern,sync_status
01,APPROVED,chapters/01.md,abc,CURRENT_REPOSITORY_SOURCE,publication/chapters/01_APPROVED.docx,publication/chapters/01_APPROVED.pdf,3,PASS,PASS,PASS; font=PASS,PASS_100_PERCENT,,branch-generated-verified
02,BLOCKED,chapters/02.md,def,BLOCKED_SOURCE_CONFLICT,,,,NOT_RUN,NOT_RUN,NOT_RUN,NOT_RUN,blocked,blocked
03,APPROVED TWO,chapters/03.md,ghi,CURRENT_REPOSITORY_SOURCE,publication/chapters/03_APPROVED_TWO.docx,publication/chapters/03_APPROVED_TWO.pdf,2,PASS,PASS,PASS; font=PASS,PASS_100_PERCENT,,branch-generated-verified
"""

AUTHOR_DIRECTED_SEQUENCE_MANIFEST = """order,title,source_path,source_blob_sha,approval_status,docx_output,pdf_output,page_count,docx_text_compare,pdf_text_compare,render_preflight,visual_qa,concern,sync_status
01,MAGIC TRICK,chapters/01_MagicTrick.md,aefd77356524bb78f37415e6f06d266ce4670af5,AUTHOR_DIRECTED_COMPLETE,,publication/chapters/01_MAGIC_TRICK.pdf,4,NOT_APPLICABLE,PASS,PASS; font=PASS,PASS_100_PERCENT,,canonical-sequence-2026-09-22
02,FOUR FLIGHTS,chapters/02_FourFlights.md,abc37bbe040899fa6e01d4d4dd64273dfc276c1d,AUTHOR_DIRECTED_COMPLETE,,publication/chapters/02_FOUR_FLIGHTS.pdf,12,NOT_APPLICABLE,PASS,PASS; font=PASS,PASS_100_PERCENT,,canonical-sequence-2026-09-22
03,STEPS TO FREEDOM,chapters/03_StepsToFreedom.md,1cfd0578151afc1374ed031f4061672f3cc430bd,AUTHOR_DIRECTED_COMPLETE,output/publication/03_STEPS_TO_FREEDOM_publication_master.docx,publication/chapters/03_STEPS_TO_FREEDOM.pdf,9,PASS,PASS,PASS; font=PASS,PASS_100_PERCENT,,canonical-sequence-2026-09-22
04,STARTING MONDAY,chapters/04_StartingMonday.md,99fdaf010c4a53f83cb8180d4b7b13a08e954f85,AUTHOR_DIRECTED_COMPLETE,,publication/chapters/04_STARTING_MONDAY.pdf,7,NOT_APPLICABLE,PASS,PASS; font=PASS,PASS_100_PERCENT,,canonical-sequence-2026-09-22
05,UNVERIFIED,chapters/05.md,bad,AUTHOR_DIRECTED_COMPLETE,,publication/chapters/05_UNVERIFIED.pdf,1,NOT_APPLICABLE,PASS,PASS; font=PASS,PASS_100_PERCENT,,branch-generated-verified
"""


def test_approved_rows_only_include_qa_passed_publication_files():
    files = ["01_APPROVED.pdf", "02_BLOCKED.pdf", "03_APPROVED_TWO.pdf"]
    chapters = CanonicalBookSource._approved_rows(MANIFEST, files)
    assert [chapter.order for chapter in chapters] == ["01", "03"]
    assert sum(chapter.pages for chapter in chapters) == 5


def test_csv_manifest_drives_approved_pdf_paths_without_directory_listing():
    chapters = CanonicalBookSource._approved_rows_csv(CSV_MANIFEST)
    assert [chapter.pdf_file for chapter in chapters] == ["01_APPROVED.pdf", "03_APPROVED_TWO.pdf"]
    assert sum(chapter.pages for chapter in chapters) == 5


def test_author_directed_opening_sequence_is_accepted_only_with_its_canonical_sync_state():
    chapters = CanonicalBookSource._approved_rows_csv(AUTHOR_DIRECTED_SEQUENCE_MANIFEST)
    assert [(chapter.order, chapter.title, chapter.pages) for chapter in chapters] == [
        ("01", "MAGIC TRICK", 4),
        ("02", "FOUR FLIGHTS", 12),
        ("03", "STEPS TO FREEDOM", 9),
        ("04", "STARTING MONDAY", 7),
    ]
    assert [chapter.pdf_file for chapter in chapters] == [
        "01_MAGIC_TRICK.pdf",
        "02_FOUR_FLIGHTS.pdf",
        "03_STEPS_TO_FREEDOM.pdf",
        "04_STARTING_MONDAY.pdf",
    ]


def test_formatted_opening_proofs_preserve_the_complete_approved_sequence():
    manifest = AUTHOR_DIRECTED_SEQUENCE_MANIFEST.replace(
        "publication/chapters/01_MAGIC_TRICK.pdf,4,NOT_APPLICABLE,PASS,PASS; font=PASS,PASS_100_PERCENT,,canonical-sequence-2026-09-22",
        "publication/chapters/01_MAGIC_TRICK.pdf,10,NOT_APPLICABLE,PASS,PASS; font=PASS,PASS_100_PERCENT,,canonical-sequence-2026-09-22-formatting",
    ).replace(
        "publication/chapters/04_STARTING_MONDAY.pdf,7,NOT_APPLICABLE,PASS,PASS; font=PASS,PASS_100_PERCENT,,canonical-sequence-2026-09-22",
        "publication/chapters/04_STARTING_MONDAY.pdf,7,NOT_APPLICABLE,PASS,PASS; font=PASS,PASS_100_PERCENT,,canonical-sequence-2026-09-22-formatting",
    )
    chapters = CanonicalBookSource._approved_rows_csv(manifest)
    assert [(chapter.order, chapter.pages) for chapter in chapters] == [
        ("01", 10), ("02", 12), ("03", 9), ("04", 7)
    ]
    assert sum(chapter.pages for chapter in chapters) == 38


def test_manifest_base_commit_is_captured():
    assert CanonicalBookSource._extract_manifest_base_commit(MANIFEST) == "abcdef1234567890"


def test_git_advertisement_resolves_requested_branch_sha():
    sha = "a" * 40
    payload = f"001e# service=git-upload-pack\n0000{sha} refs/heads/main\n".encode()
    assert CanonicalBookSource._commit_from_git_advertisement(payload, "main") == sha


def test_git_advertisement_rejects_missing_branch():
    try:
        CanonicalBookSource._commit_from_git_advertisement(b"0000", "main")
    except SourceError as exc:
        assert "commit identity" in str(exc)
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
