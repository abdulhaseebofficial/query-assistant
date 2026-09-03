"""End-to-end checks against the Flask test client: routing, the security
headers every response must carry, and the auth boundary on /history."""

import uuid

import pytest


def test_index_renders_the_search_form(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Query Assistant" in response.data


def test_a_question_returns_results_and_the_generated_sql(client):
    response = client.get("/", query_string={"q": "employees in the IT department"})
    assert response.status_code == 200
    assert b"SELECT" in response.data


def test_an_unrecognised_question_does_not_crash(client):
    response = client.get("/", query_string={"q": "tell me a joke"})
    assert response.status_code == 200


def test_export_returns_a_csv_attachment(client):
    response = client.get("/export", query_string={"q": "employees in the IT department"})
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]


def test_export_without_an_understandable_question_is_a_404(client):
    response = client.get("/export", query_string={"q": "tell me a joke"})
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/", "/learn", "/upload", "/connect-db", "/login", "/register"])
def test_public_pages_are_reachable(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "header, expected",
    [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ],
)
def test_security_headers_are_present_on_every_response(client, header, expected):
    assert client.get("/").headers[header] == expected


def test_a_content_security_policy_is_set(client):
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_history_requires_a_login(client):
    response = client.get("/history")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_a_users_query_history_is_recorded_after_registering(client):
    username = f"tester_{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/register",
        data={"username": username, "email": f"{username}@example.com", "password": "a-good-password"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    client.get("/", query_string={"q": "employees in the IT department"})

    history = client.get("/history")
    assert history.status_code == 200
    assert b"employees in the IT department" in history.data


def test_registration_rejects_a_short_password(client):
    username = f"tester_{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/register",
        data={"username": username, "email": f"{username}@example.com", "password": "short"},
    )
    assert response.status_code == 200
    assert b"at least 8 characters" in response.data


def test_login_with_wrong_credentials_is_rejected(client):
    response = client.post("/login", data={"username": "nobody", "password": "wrong-password"})
    assert response.status_code == 200
    assert b"Incorrect username or password" in response.data


def test_favicon_returns_no_content(client):
    assert client.get("/favicon.ico").status_code == 204


def test_an_unknown_path_is_a_404(client):
    assert client.get("/no-such-page").status_code == 404
