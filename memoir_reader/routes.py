from __future__ import annotations

import io
import os
from flask import Blueprint, current_app, jsonify, render_template, request, send_file

from .assembly import PublicationAssemblyError
from .front_matter import load_front_matter_authority, resolve_approved_asset_path
from .publication import build_publication_payload
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

    publication_assembly: dict[str, object]
    try:
        authority = load_front_matter_authority(expected_canonical_repository=snapshot.repository)
        publication_assembly = {
            "status": "ready" if authority.ready else "blocked",
            "front_cover": authority.cover_status,
            "front_cover_materialized": authority.ready,
            "back_cover": authority.back_cover_status,
            "back_cover_materialized": authority.back_cover_ready,
        }
    except PublicationAssemblyError as exc:
        publication_assembly = {"status": "invalid", "error": str(exc)}

    return jsonify(
        {
            "status": "ok",
            "canonical_source": snapshot.repository,
            "commit_sha": snapshot.commit_sha,
            "application_commit": os.getenv("RENDER_GIT_COMMIT"),
            "approved_chapters": len(snapshot.chapters),
            "pages": snapshot.total_pages,
            "publication_assembly": publication_assembly,
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


@bp.get("/api/publication")
def publication_manifest():
    """Expose the physical-book model only when every required authority is valid.

    The existing manuscript-only reader remains on /api/book until the approved
    front-cover bytes are materialised. This endpoint therefore acts as the
    activation gate for the physical publication model and intentionally returns
    503 while that authority is incomplete.
    """

    try:
        snapshot = source().snapshot()
    except SourceError as exc:
        return jsonify({"error": "canonical_source_unavailable", "message": str(exc)}), 503

    try:
        authority = load_front_matter_authority(expected_canonical_repository=snapshot.repository)
        payload = build_publication_payload(snapshot, authority)
    except PublicationAssemblyError as exc:
        return jsonify(
            {
                "error": "publication_assembly_unavailable",
                "message": str(exc),
                "commit_sha": snapshot.commit_sha,
            }
        ), 503

    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Memoir-Commit"] = snapshot.commit_sha
    return response


@bp.get("/api/front-matter-asset/<asset_id>")
def front_matter_asset(asset_id: str):
    """Serve only exact, SHA-verified, author-approved application-side assets."""

    try:
        snapshot = source().snapshot()
    except SourceError as exc:
        return jsonify({"error": "canonical_source_unavailable", "message": str(exc)}), 503

    try:
        authority = load_front_matter_authority(expected_canonical_repository=snapshot.repository)
        asset = authority.approved_asset(asset_id)
        asset_path = resolve_approved_asset_path(asset)
    except PublicationAssemblyError as exc:
        return jsonify({"error": "front_matter_asset_unavailable", "message": str(exc)}), 404

    response = send_file(
        asset_path,
        mimetype=asset.mime_type,
        download_name=asset_path.name,
        conditional=False,
        max_age=31536000,
    )
    response.set_etag(asset.sha256)
    response.headers["X-Asset-SHA256"] = asset.sha256
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


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
