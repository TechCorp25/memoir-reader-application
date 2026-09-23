from __future__ import annotations

import csv
import io
import re
import threading
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

import requests


MANIFEST_PATH = "publication/publication-formatting-manifest.md"
MANIFEST_CSV_PATH = "publication/publication-formatting-manifest.csv"
PUBLICATION_DIR = "publication/chapters"
APP_USER_AGENT = "memoir-reader-application/0.2"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

# Publication eligibility is established by the canonical repository's paired
# approval and synchronisation states. Keep the pairing explicit so that a new
# or partially-updated manifest state cannot become reader-visible merely by
# reusing one trusted value.
APPROVED_PUBLICATION_PROFILES = frozenset(
    {
        ("AUTHOR_DIRECTED_COMPLETE", "canonical-sequence-2026-09-22"),
        ("AUTHOR_DIRECTED_COMPLETE", "canonical-sequence-2026-09-22-formatting"),
        ("CURRENT_REPOSITORY_SOURCE", "branch-generated-verified"),
    }
)

# The author-approved 23 September proof uses a distinct sync and QA state.
# Recognize it only for Chapter 02; all other chapters retain their gate.
CHAPTER_02_REVISED_PROFILE = ("AUTHOR_DIRECTED_COMPLETE", "dialogue-and-prose-updated-2026-09-23")


class SourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApprovedChapter:
    order: str
    title: str
    source: str
    pages: int
    pdf_file: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "title": self.title,
            "source": self.source,
            "pages": self.pages,
            "pdf_file": self.pdf_file,
        }


@dataclass(frozen=True)
class BookSnapshot:
    repository: str
    requested_ref: str
    commit_sha: str
    manifest_base_commit: str | None
    total_pages: int
    chapters: tuple[ApprovedChapter, ...]
    generated_at_unix: float

    def as_dict(self) -> dict[str, Any]:
        offset = 0
        chapters: list[dict[str, Any]] = []
        for chapter in self.chapters:
            item = chapter.as_dict()
            item["first_page_index"] = offset
            item["last_page_index"] = offset + chapter.pages - 1
            chapters.append(item)
            offset += chapter.pages
        return {
            "repository": self.repository,
            "requested_ref": self.requested_ref,
            "commit_sha": self.commit_sha,
            "manifest_base_commit": self.manifest_base_commit,
            "total_pages": self.total_pages,
            "chapters": chapters,
        }


class CanonicalBookSource:
    """Resolve and serve only publication-approved assets from canonical GitHub."""

    def __init__(self, repo: str, ref: str = "main", ttl_seconds: int = 300):
        self.repo = repo
        self.ref = ref
        self.ttl_seconds = ttl_seconds
        self._snapshot: BookSnapshot | None = None
        self._snapshots_by_commit: dict[str, BookSnapshot] = {}
        self._pdf_cache: dict[tuple[str, str], bytes] = {}
        self._lock = threading.RLock()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": APP_USER_AGENT})

    @property
    def git_base(self) -> str:
        return f"https://github.com/{self.repo}.git"

    def _get_text(self, url: str) -> str:
        response = self._session.get(url, timeout=15)
        if response.status_code != 200:
            raise SourceError(f"Canonical source request failed ({response.status_code})")
        return response.text

    @staticmethod
    def _commit_from_git_advertisement(payload: bytes, ref: str) -> str:
        text = payload.decode("latin1", errors="ignore")
        ref_name = f"refs/heads/{ref}"
        match = re.search(rf"([0-9a-f]{{40}})\s+{re.escape(ref_name)}(?:\x00|\n|\r)", text)
        if match:
            return match.group(1)

        head_match = re.search(r"([0-9a-f]{40})\s+HEAD\x00[^\n]*symref=HEAD:([^\s\x00]+)", text)
        if head_match and head_match.group(2) == ref_name:
            return head_match.group(1)

        raise SourceError("Canonical commit identity could not be established")

    def _resolve_commit(self) -> str:
        response = self._session.get(
            f"{self.git_base}/info/refs?service=git-upload-pack",
            headers={"Accept": "application/x-git-upload-pack-advertisement"},
            timeout=15,
        )
        if response.status_code != 200:
            raise SourceError(f"Canonical source request failed ({response.status_code})")
        sha = self._commit_from_git_advertisement(response.content, self.ref)
        if not COMMIT_RE.fullmatch(sha):
            raise SourceError("Canonical commit identity could not be established")
        return sha

    def _raw_url(self, commit_sha: str, path: str) -> str:
        encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
        return f"https://raw.githubusercontent.com/{self.repo}/{commit_sha}/{encoded_path}"

    def _manifest_text(self, commit_sha: str) -> str:
        return self._get_text(self._raw_url(commit_sha, MANIFEST_PATH))

    def _manifest_csv_text(self, commit_sha: str) -> str:
        return self._get_text(self._raw_url(commit_sha, MANIFEST_CSV_PATH))

    @staticmethod
    def _extract_manifest_base_commit(manifest: str) -> str | None:
        match = re.search(r"Governing manuscript base commit:\s*`([0-9a-f]{7,40})`", manifest)
        return match.group(1) if match else None

    @staticmethod
    def _approved_rows_csv(manifest_csv: str) -> tuple[ApprovedChapter, ...]:
        reader = csv.DictReader(io.StringIO(manifest_csv))
        approved: list[ApprovedChapter] = []
        required = {
            "order",
            "title",
            "source_path",
            "approval_status",
            "pdf_output",
            "page_count",
            "pdf_text_compare",
            "visual_qa",
            "sync_status",
        }
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise SourceError("Publication CSV manifest is missing required fields")

        for row in reader:
            publication_profile = (
                (row.get("approval_status") or "").strip(),
                (row.get("sync_status") or "").strip(),
            )
            revised_chapter_02 = (
                (row.get("order") or "").strip() == "02"
                and publication_profile == CHAPTER_02_REVISED_PROFILE
            )
            if publication_profile not in APPROVED_PUBLICATION_PROFILES and not revised_chapter_02:
                continue
            if row.get("pdf_text_compare") != "PASS":
                continue
            visual_qa = row.get("visual_qa")
            if visual_qa != "PASS_100_PERCENT" and not (
                revised_chapter_02 and visual_qa == "PASS_AGENT_ALL_PAGES"
            ):
                continue

            order = (row.get("order") or "").strip()
            title = (row.get("title") or "").strip()
            source = (row.get("source_path") or "").strip()
            page_text = (row.get("page_count") or "").strip()
            pdf_output = (row.get("pdf_output") or "").strip()
            if not order or not title or not source or not page_text.isdigit() or not pdf_output:
                raise SourceError(f"Approved manifest row is incomplete for order {order or '?'}")
            if not pdf_output.startswith(f"{PUBLICATION_DIR}/") or not pdf_output.lower().endswith(".pdf"):
                raise SourceError(f"Approved PDF path is invalid for order {order}")

            approved.append(
                ApprovedChapter(
                    order=order,
                    title=title,
                    source=source,
                    pages=int(page_text),
                    pdf_file=PurePosixPath(pdf_output).name,
                )
            )

        if not approved:
            raise SourceError("No publication-approved chapters were established")
        return tuple(approved)

    @staticmethod
    def _parse_markdown_table(manifest: str) -> list[dict[str, str]]:
        table_lines = [line.strip() for line in manifest.splitlines() if line.strip().startswith("|")]
        if len(table_lines) < 3:
            raise SourceError("Publication manifest table is missing")
        header = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
        rows = []
        for line in table_lines[2:]:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != len(header):
                continue
            rows.append(dict(zip(header, cells)))
        return rows

    @classmethod
    def _approved_rows(cls, manifest: str, publication_files: list[str]) -> tuple[ApprovedChapter, ...]:
        rows = cls._parse_markdown_table(manifest)
        pdf_files = sorted(name for name in publication_files if name.lower().endswith(".pdf"))
        approved: list[ApprovedChapter] = []
        for row in rows:
            if row.get("PDF text") != "PASS" or row.get("Visual QA") != "PASS_100_PERCENT":
                continue
            order = row.get("Order", "").strip()
            title = row.get("Title", "").strip()
            source = row.get("Source", "").strip().strip("`")
            page_text = row.get("Pages", "").strip()
            if not order or not title or not source or not page_text.isdigit():
                raise SourceError(f"Approved manifest row is incomplete for order {order or '?'}")
            prefix = f"{order}_"
            matches = [name for name in pdf_files if name.startswith(prefix)]
            if len(matches) != 1:
                raise SourceError(f"Expected exactly one approved PDF for order {order}")
            approved.append(ApprovedChapter(order, title, source, int(page_text), matches[0]))
        if not approved:
            raise SourceError("No publication-approved chapters were established")
        return tuple(approved)

    def _build_snapshot(self, commit_sha: str, now: float | None = None) -> BookSnapshot:
        if not COMMIT_RE.fullmatch(commit_sha):
            raise SourceError("Publication commit identity is invalid")
        manifest = self._manifest_text(commit_sha)
        manifest_csv = self._manifest_csv_text(commit_sha)
        chapters = self._approved_rows_csv(manifest_csv)
        snapshot = BookSnapshot(
            repository=self.repo,
            requested_ref=self.ref,
            commit_sha=commit_sha,
            manifest_base_commit=self._extract_manifest_base_commit(manifest),
            total_pages=sum(ch.pages for ch in chapters),
            chapters=chapters,
            generated_at_unix=now if now is not None else time.time(),
        )
        self._snapshots_by_commit[commit_sha] = snapshot
        return snapshot

    def snapshot(self, force: bool = False) -> BookSnapshot:
        now = time.time()
        if not force and self._snapshot and now - self._snapshot.generated_at_unix < self.ttl_seconds:
            return self._snapshot
        with self._lock:
            now = time.time()
            if not force and self._snapshot and now - self._snapshot.generated_at_unix < self.ttl_seconds:
                return self._snapshot
            commit_sha = self._resolve_commit()
            cached = self._snapshots_by_commit.get(commit_sha)
            if cached:
                snapshot = BookSnapshot(
                    repository=cached.repository,
                    requested_ref=cached.requested_ref,
                    commit_sha=cached.commit_sha,
                    manifest_base_commit=cached.manifest_base_commit,
                    total_pages=cached.total_pages,
                    chapters=cached.chapters,
                    generated_at_unix=now,
                )
                self._snapshots_by_commit[commit_sha] = snapshot
            else:
                snapshot = self._build_snapshot(commit_sha, now=now)
            self._snapshot = snapshot
            return snapshot

    def snapshot_at(self, commit_sha: str) -> BookSnapshot:
        if not COMMIT_RE.fullmatch(commit_sha):
            raise SourceError("Publication commit identity is invalid")
        with self._lock:
            cached = self._snapshots_by_commit.get(commit_sha)
            if cached:
                return cached
            return self._build_snapshot(commit_sha)

    def pdf_bytes(self, filename: str, commit_sha: str) -> bytes:
        snapshot = self.snapshot_at(commit_sha)
        allowed = {chapter.pdf_file for chapter in snapshot.chapters}
        if filename not in allowed:
            raise SourceError("Requested asset is not publication-approved")
        key = (commit_sha, filename)
        with self._lock:
            cached = self._pdf_cache.get(key)
            if cached is not None:
                return cached
        url = self._raw_url(commit_sha, f"{PUBLICATION_DIR}/{filename}")
        response = self._session.get(url, timeout=30)
        if response.status_code != 200:
            raise SourceError(f"Approved publication asset could not be loaded ({response.status_code})")
        if not response.content.startswith(b"%PDF"):
            raise SourceError("Approved publication asset failed PDF validation")
        payload = response.content
        with self._lock:
            self._pdf_cache[key] = payload
        return payload
