import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """base configuration class with shared default settings for all environments"""

    SECRET_KEY = os.environ.get('SECRET_KEY',"dev-secret-change-me")
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY',"dev-jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=12)

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    #third party integrations read from env, not hardcoded in config.py

    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    SUPABASE_BUCKET = os.environ.get('SUPABASE_BUCKET', "driver-documents")

    #Africa-talking sms intergration
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

    def __init__(self):
        "fail loudly if production secrets were left at dev defaults"
        if not os.environ.get("SECRET_KEY") or not os.environ.get("JWT_SECRET_KEY"):
            raise RuntimeError(
               "SECRET_KEY and JWT_SECRET_KEY must be set via environment "
                "variables in production."   
            )
        
        if not self.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError("DATABASE_URL must be set in production")

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig
}