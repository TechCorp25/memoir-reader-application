# Memoir Reader Application

A publication-fidelity digital reader for **The Long Road To Nowhere**.

## Source integrity

The application does not store or edit manuscript prose. At runtime it resolves the canonical repository `techcorp-DevApps/memoir`, pins the current `main` commit, reads the publication manifests, and exposes only chapter PDFs whose canonical approval/synchronisation profile is explicitly trusted and whose PDF text and visual QA checks pass. This includes the author-directed completed opening sequence recorded on 22 September 2026.

If the canonical source or approval state cannot be verified, the reader fails closed rather than silently using stale content.

## Reader model

- fixed 6×9 publication pages
- portrait/constrained viewport: one page
- sufficiently wide landscape viewport: two-page spread
- right-to-left swipe: one logical turn forward
- left-to-right swipe: one logical turn backward
- keyboard and low-emphasis fallback buttons
- restrained paper treatment and gutter depth
- no vertical chapter scrolling
- source commit retained internally and exposed only in low-emphasis diagnostics

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
npm test
flask --app app run --debug
```

Open http://127.0.0.1:5000.

## Render

`render.yaml` defines a single Python web service. The app requires outbound HTTPS access to GitHub and the pinned PDF.js CDN asset. No database is required.
