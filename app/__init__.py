import os
from flask import Flask,jsonify,g, request
from werkzeug.exceptions import HTTPException
from pythonjsonlogger import jsonlogger

from config import config_by_name, REQUIRED_IN_PRODUCTION
from app.extensions import db, migrate, jwt, cors, mail, limiter


def create_app(config_name=None):
    """application factory function to create and configure a Flask app instance"""

    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    validate_config(app, config_name)
    _init_extensions(app)
    _register_blueprints(app)

    @app.get("/api/health")
    def health_check():
        """health check endpoint to verify the app is running"""
        db_status = "ok"
        try:
            db.session.execute("SELECT 1")
        except Exception:
            """Dont leak raw exception, might contain connection string or other sensitive info. Log it instead."""
            app.logger.exception("Health check db connectivity failure")
            db_status = "error"
        return jsonify(
            {
                "status": "healthy",
                "database": db_status,
                "environment": config_name
            }
        ), 200

    return app

def validate_config(app, config_name):
    """
    Validates that required configuration variables are set in production.
    Raises RuntimeError if any required variable is missing.
    fail fast at start up if required secrets/config are missing 
    rather than booting into a broken/insecure state
    Only strict outside development/testing where sensible fallbacks exist. In dev/test, we allow defaults to be used for convenience.
    """
    if config_name == "development" or config_name == "testing":
        return
 
    missing = [key for key in REQUIRED_IN_PRODUCTION if not os.environ.get(key)]
    if missing:
        raise RuntimeError(
            f"Missing required configuration for '{config_name}': {', '.join(missing)}. "
            "Set these as real environment variables before starting the app — "
            "do not rely on config.py's development fallback defaults in production."
        )

def _init_extensions(app):
    db.init_app(app)
    migrate.init_app(app,db)
    jwt.init_app(app)
    cors.init_app(app,resources={r"/api/*":{"origins":app.config['FRONTEND_ORIGIN']}})


def _register_blueprints(app):
    """
    Register all blueprints for the application.
    """
    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp,url_prefix="/api/auth")

    from app.communications.routes import communications_bp
    app.register_blueprint(communications_bp,url_prefix="/api/communications")

    from app.trucks.routes import trucks_bp
    app.register_blueprint(trucks_bp,url_prefix="/api/trucks")