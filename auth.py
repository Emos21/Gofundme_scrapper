from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import secrets

jwt = JWTManager()


def init_jwt(app):
    """Initialize JWT with app."""
    app.config['JWT_SECRET_KEY'] = app.config.get('SECRET_KEY', secrets.token_hex(32))
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)
    jwt.init_app(app)


def generate_api_key():
    """Generate a random API key."""
    return secrets.token_urlsafe(32)


def hash_password(password):
    """Hash a password."""
    return generate_password_hash(password)


def verify_password(password, password_hash):
    """Verify a password against hash."""
    return check_password_hash(password_hash, password)
