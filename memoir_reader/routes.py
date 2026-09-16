from __future__ import annotations

import io
from flask import Blueprint, current_app, jsonify, render_template, request, send_file

from .source import SourceError

bp = Blueprint("reader", __name__)


def source():
    return current_app.extensions["book_source"]


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/health")
def health():
    try:
        snapshot = source().snapshot()
    except SourceError as exc:
        return jsonify({"status": "degraded", "canonical_source": "unverified", "error": str(exc)}), 503
    return jsonify(
        {
            "status": "ok",
            "canonical_source": snapshot.repository,
            "commit_sha": snapshot.commit_sha,
            "approved_chapters": len(snapshot.chapters),
            "pages": snapshot.total_pages,
        }
    )


@bp.get("/api/book")
def book_manifest():
    try:
        response = jsonify(source().snapshot().as_dict())
        response.headers["Cache-Control"] = "no-store"
        return response
    except SourceError as exc:
        return jsonify({"error": "canonical_source_unavailable", "message": str(exc)}), 503


@bp.get("/api/document/<path:filename>")
def publication_document(filename: str):
    requested_commit = request.args.get("commit", "")
    try:
        payload = source().pdf_bytes(filename, requested_commit)
    except SourceError as exc:
        return jsonify({"error": "publication_asset_unavailable", "message": str(exc)}), 404
    response = send_file(
        io.BytesIO(payload),
        mimetype="application/pdf",
        download_name=filename,
        conditional=False,
        max_age=31536000,
    )
    response.headers["X-Memoir-Commit"] = requested_commit
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
