import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """base configuration class with shared default settings for all environments"""

    SECRET_KEY = os.environ.get('SECRET_KEY',"dev-secret-change-me")
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY',"dev-jwt-secret-change-me")

    #NFR-SEC-02: access token expires after 15 minutes. Paired with refresh token for long-lived sessions.
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)

    #NFR-SEC-03: refresh token expires after 7 days. Paired with access token for long-lived sessions.
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    #third party integrations read from env, not hardcoded in config.py

    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    SUPABASE_BUCKET = os.environ.get('SUPABASE_BUCKET', "driver-documents")

    #Africa-talking sms integration
    AT_USERNAME = os.environ.get("AT_USERNAME")
    AT_API_KEY = os.environ.get("AT_API_KEY")  

    #email
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "True") == "True"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")

    #frontend origin for CORS, default to localhost:5173 for development
    FRONTEND_ORIGIN = os.environ.get('FRONTEND_ORIGIN', "http://localhost:5173")

    # Flask-Limiter storage. In-memory is fine for a single-instance Phase 1
    # deployment; move to a real backend (e.g. Redis) only if/when Phase 2's
    # multiple-instance setup makes in-memory limits inconsistent across instances.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = "200 per day;50 per hour"

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or (f"sqlite:///{os.path.join(basedir, 'dev.db')}")

class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

    # fail-fast validation intentionally does NOT live here anymore.
    # app.config.from_object() is passed this class directly, never an
    # instance — so an __init__ check here would silently never run. See
    # validate_config() in app/__init__.py, which is the version that
    # actually executes, called explicitly after config is loaded.

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig
}

# Vars validate_config() requires to be non-empty outside development/testing.
REQUIRED_IN_PRODUCTION = ["SECRET_KEY", "JWT_SECRET_KEY", "DATABASE_URL"]