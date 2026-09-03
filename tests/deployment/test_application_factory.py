"""Application-factory and package-resource smoke tests."""


def test_factory_creates_distinct_app_instances(tmp_path):
    from query_assistant import create_app

    first = create_app({"TESTING": True, "DATABASE_PATH": str(tmp_path / "first.db")})
    second = create_app({"TESTING": True, "DATABASE_PATH": str(tmp_path / "second.db")})
    assert first is not second


def test_expected_blueprints_are_registered(app):
    assert {"main", "auth", "datasets", "feedback", "learning", "sql_console"} <= set(app.blueprints)


def test_packaged_template_and_static_asset_render(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/css/base.css").status_code == 200
