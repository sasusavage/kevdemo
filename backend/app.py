"""
Application factory for the Prism Portal backend.
"""
import os
from flask import Flask, send_from_directory
from flask_cors import CORS
from config import config_map
from extensions import db

# Path to the frontend HTML files (parent directory of backend/)
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def create_app(config_name: str | None = None) -> Flask:
    """
    Build and return the Flask application.

    Args:
        config_name: One of 'development' | 'production'.
                     Falls back to the FLASK_ENV env var.
    """
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    # ── Extensions ──────────────────────────────
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    db.init_app(app)

    # ── Register blueprints ─────────────────────
    from routes import api as api_blueprint
    app.register_blueprint(api_blueprint)

    # ── Create tables if they don't exist ───────
    with app.app_context():
        import models  # noqa: F401 – ensure models are loaded
        db.create_all()

    # ── Health-check route ──────────────────────
    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    # ── Serve frontend pages ────────────────────
    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "dashboard_overview.html")

    @app.route("/dashboard")
    def dashboard():
        return send_from_directory(FRONTEND_DIR, "dashboard_overview.html")

    @app.route("/inventory")
    def inventory():
        return send_from_directory(FRONTEND_DIR, "inventory_management.html")

    @app.route("/distributors")
    def distributors():
        return send_from_directory(FRONTEND_DIR, "distributor_performance.html")

    @app.route("/order")
    def order_form():
        """
        Social media quick-order form.
        Accepts ?ref=D{id} to pre-populate the distributor.
        """
        return send_from_directory(FRONTEND_DIR, "quick_order.html")

    return app


# ── Dev entry-point ─────────────────────────────
if __name__ == "__main__":
    application = create_app()
    port = int(os.getenv("PORT", 5001))
    application.run(host="0.0.0.0", port=port)
