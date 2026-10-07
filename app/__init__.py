import os
import uuid
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
    _register_error_handlers(app)
    _register_request_id(app)
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
    
def _register_request_id(app):
    """
    every request gets a correlation ID: reused from an incoming
    X-Request-ID header if the client/proxy supplied one, otherwise generated.
    Available as g.request_id anywhere during the request (route handlers,
    service functions, audit.service.record() calls), and echoed back in the
    response header for client-side correlation/debugging.
    """
 
    @app.before_request
    def set_request_id():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
 
    @app.after_request
    def add_request_id_header(response):
        response.headers["X-Request-ID"] = g.get("request_id", "-")
        return response

def _register_error_handlers(app):
    """consistent JSON error responses for all unhandled exceptions, including HTTPException subclasses"""
    @app.errorhandler(HTTPException)
    def handle_http_exception(err):
        return jsonify(
            {
                "error": err.name,
                "message": err.description,
                "request_id": g.get("request_id", "-"),
            }
        ), err.code
 
    @app.errorhandler(Exception)
    def handle_unexpected_exception(err):
        # Full detail goes to the server-side structured log, correlated by
        # request_id — never to the response body.
        app.logger.exception("Unhandled exception")
        return jsonify(
            {
                "error": "Internal Server Error",
                "message": "Something went wrong. Reference the request ID if contacting support.",
                "request_id": g.get("request_id", "-"),
            }
        ), 500


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