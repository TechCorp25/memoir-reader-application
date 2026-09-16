from __future__ import annotations

import os


def create_app():
    # Keep source-validation modules importable in minimal test environments.
    from flask import Flask
    from .routes import bp
    from .source import CanonicalBookSource

    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.update(
        MEMOIR_REPO=os.getenv("MEMOIR_REPO", "techcorp-DevApps/memoir"),
        MEMOIR_REF=os.getenv("MEMOIR_REF", "main"),
        SOURCE_CACHE_TTL_SECONDS=int(os.getenv("SOURCE_CACHE_TTL_SECONDS", "300")),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    app.extensions["book_source"] = CanonicalBookSource(
        repo=app.config["MEMOIR_REPO"],
        ref=app.config["MEMOIR_REF"],
        ttl_seconds=app.config["SOURCE_CACHE_TTL_SECONDS"],
    )
    app.register_blueprint(bp)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; worker-src 'self' blob: https://cdn.jsdelivr.net; "
            "connect-src 'self' https://cdn.jsdelivr.net; font-src 'self' data: https://cdn.jsdelivr.net; "
            "frame-ancestors 'none'; base-uri 'self'",
        )
        return response

    return app
