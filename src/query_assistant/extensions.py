"""Flask extensions, created once and bound by the application factory."""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_wtf import CSRFProtect

csrf = CSRFProtect()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per minute"])


def init_extensions(app):
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
