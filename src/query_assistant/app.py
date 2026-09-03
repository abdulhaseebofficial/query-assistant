"""Flask application factory."""

from pathlib import Path

from flask import Flask

from query_assistant.config import Config, runtime_paths
from query_assistant.extensions import init_extensions, login_manager
from query_assistant.infrastructure.database.initialization import init_db
from query_assistant.repositories import user_repository
from query_assistant.web.blueprints import register_blueprints
from query_assistant.web.error_handlers import register_error_handlers
from query_assistant.web.presentation import commas_filter, inject_feedback_admin, sql_for_display
from query_assistant.web.security import set_security_headers


def create_app(config_object=None):
    """Build an isolated application instance and register its dependencies."""
    package_dir = Path(__file__).resolve().parent
    app = Flask(__name__, instance_relative_config=True,
                template_folder=str(package_dir / "web" / "templates"),
                static_folder=str(package_dir / "web" / "static"))
    app.config.from_object(Config)
    if config_object is not None:
        if isinstance(config_object, dict):
            app.config.from_mapping(config_object)
        else:
            app.config.from_object(config_object)

    paths = runtime_paths(app.instance_path)
    app.config.setdefault("DATA_DIR", str(paths["data_dir"]))
    app.config.setdefault("UPLOAD_DIR", str(paths["upload_dir"]))
    app.config.setdefault("DATABASE_PATH", str(paths["database"]))
    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    init_extensions(app)
    register_blueprints(app)
    register_error_handlers(app)
    app.after_request(set_security_headers)
    app.context_processor(inject_feedback_admin)
    app.add_template_filter(sql_for_display, "highlight")
    app.add_template_filter(commas_filter, "commas")
    app.jinja_env.filters["zip"] = zip

    @login_manager.user_loader
    def load_user(user_id):
        return user_repository.find_by_id(user_id)

    init_db(app.config["DATABASE_PATH"])
    return app


__all__ = ["create_app"]
