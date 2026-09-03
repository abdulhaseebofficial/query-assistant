"""Blueprint registration."""


def register_blueprints(app):
    from query_assistant.web.blueprints.auth.routes import blueprint as auth
    from query_assistant.web.blueprints.datasets.routes import blueprint as datasets
    from query_assistant.web.blueprints.feedback.routes import blueprint as feedback
    from query_assistant.web.blueprints.learning.routes import blueprint as learning
    from query_assistant.web.blueprints.main.routes import blueprint as main
    from query_assistant.web.blueprints.sql_console.routes import blueprint as sql_console

    for blueprint in (main, datasets, sql_console, feedback, learning, auth):
        app.register_blueprint(blueprint)
