from flask import Flask, jsonify, request

from .config import Config
from .embeddings import make_embedder
from .repository import Repository
from .routes import bp
from .storage import FileStorage


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    repository = Repository(app.config)
    embedder = make_embedder(
        app.config.get("EMBEDDING_BACKEND", "hashing"),
        app.config.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
    )
    app.extensions["paper_repository"] = repository
    app.extensions["paper_embedder"] = embedder
    app.extensions["paper_storage"] = FileStorage(
        app.config, getattr(repository, "client", None)
    )
    app.register_blueprint(bp)

    @app.after_request
    def allow_preview_iframes(response):
        """Allow browser previews that embed the app in sandboxed iframes.

        Sandboxed iframes run with an opaque origin ("null") and fetches from them
        are treated as cross-origin; without CORS headers every API call is blocked.
        """
        origin = request.headers.get("Origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Auth-Token"
            )
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PATCH, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Max-Age"] = "600"
            response.headers["Vary"] = "Origin"
        # Pages and API data must never be served stale: auth tokens travel with
        # requests, and cached 401s/logged-out pages cause login redirect loops.
        if response.mimetype in ("text/html", "application/json"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            return ("", 204)

    @app.errorhandler(413)
    def too_large(_error):
        maximum_mb = max(1, int(app.config.get("MAX_CONTENT_LENGTH", 20 * 1024 * 1024) / (1024 * 1024)))
        return jsonify({"error": f"That file is too large. The upload limit is {maximum_mb} MB."}), 413

    return app
