import os
from flask import Flask,jsonify

from config import config_by_name
from app.extensions import db, migrate, jwt, cors


def create_app(config_name=None):
    """application factory function to create and configure a Flask app instance"""

    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    _init_extensions(app)
    _register_blueprints(app)

    @app.get("/api/health")
    def health_check():
        """health check endpoint to verify the app is running"""
        db_status = "ok"
        try:
            db.session.execute("SELECT 1")
        except Exception as e:
            db_status = f"error: {str(e)}"

        return jsonify(
            {
                "status": "healthy",
                "database": db_status,
                "environment": config_name
            }
        ), 200

    return app


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