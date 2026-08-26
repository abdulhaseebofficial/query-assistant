"""Sending feedback, and reading it.

Two things here are easy to get wrong and expensive to get wrong.

Feedback holds email addresses people typed in, and it lives in the same database
as the demo tables — so like `users`, it must stay off every whitelist the SQL
editor and the AI engine work from.

And reading it is gated by ADMIN_USERNAME. Unset has to mean *nobody*, not
everybody: a deployment that forgot to set it should show the feedback to no one,
rather than to the first person who signs up.
"""

import re
import uuid

import pytest

from backend import feedback


def send(client, message, email=None, page=None):
    data = {"message": message}
    if email:
        data["email"] = email
    if page:
        data["page"] = page
    return client.post("/feedback", data=data)


@pytest.fixture
def signed_in_admin(client, monkeypatch):
    """A signed-in account that ADMIN_USERNAME names."""
    name = f"boss{uuid.uuid4().hex[:6]}"
    client.post("/register", data={"username": name, "email": f"{name}@e.com",
                                   "password": "a-good-password"})
    monkeypatch.setenv("ADMIN_USERNAME", name)
    return client, name


class TestSending:
    def test_the_form_opens_without_an_account(self, client):
        assert client.get("/feedback").status_code == 200

    def test_a_message_is_recorded(self, client):
        before = feedback.count()

        response = send(client, "The Roman Urdu for last month isn't understood.")

        assert response.status_code == 200
        assert "Thanks" in response.get_data(as_text=True)
        assert feedback.count() == before + 1
        assert feedback.recent()[0]["message"].startswith("The Roman Urdu")

    def test_an_empty_message_is_refused(self, client):
        before = feedback.count()

        response = send(client, "   ")

        assert "Please write something first." in response.get_data(as_text=True)
        assert feedback.count() == before

    def test_an_email_is_optional(self, client):
        send(client, "No address here")
        assert feedback.recent()[0]["email"] is None

    def test_an_email_is_kept_when_given(self, client):
        send(client, "Reply to me", email="someone@example.com")
        assert feedback.recent()[0]["email"] == "someone@example.com"

    def test_the_page_it_came_from_is_kept(self, client):
        send(client, "This page confused me", page="/connect-db")
        assert feedback.recent()[0]["page"] == "/connect-db"

    def test_a_signed_in_sender_is_attributed(self, client):
        name = f"sender{uuid.uuid4().hex[:6]}"
        client.post("/register", data={"username": name, "email": f"{name}@e.com",
                                       "password": "a-good-password"})

        send(client, "Signed in feedback")

        assert feedback.recent()[0]["username"] == name

    def test_an_anonymous_sender_has_no_username(self, client):
        send(client, "Anonymous feedback")
        assert feedback.recent()[0]["username"] is None

    def test_a_very_long_message_is_capped_not_rejected(self, client):
        send(client, "x" * 10_000)
        assert len(feedback.recent()[0]["message"]) == feedback.MAX_MESSAGE


class TestReading:
    def test_the_admin_can_read_it(self, signed_in_admin):
        client, _name = signed_in_admin
        send(client, "Something worth reading")

        body = client.get("/feedback/all").get_data(as_text=True)

        assert "Something worth reading" in body

    def test_a_signed_in_stranger_cannot(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_USERNAME", "somebody-else")
        name = f"nosy{uuid.uuid4().hex[:6]}"
        client.post("/register", data={"username": name, "email": f"{name}@e.com",
                                       "password": "a-good-password"})

        assert client.get("/feedback/all").status_code == 404

    def test_a_signed_out_visitor_is_sent_to_login(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_USERNAME", "anyone")

        response = client.get("/feedback/all")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_with_no_admin_configured_nobody_can_read_it(self, client, monkeypatch):
        """Unset means nobody, not everybody."""
        monkeypatch.delenv("ADMIN_USERNAME", raising=False)
        name = f"first{uuid.uuid4().hex[:6]}"
        client.post("/register", data={"username": name, "email": f"{name}@e.com",
                                       "password": "a-good-password"})

        assert client.get("/feedback/all").status_code == 404

    def test_an_empty_admin_username_names_nobody(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_USERNAME", "   ")
        name = f"blank{uuid.uuid4().hex[:6]}"
        client.post("/register", data={"username": name, "email": f"{name}@e.com",
                                       "password": "a-good-password"})

        assert client.get("/feedback/all").status_code == 404

    def test_newest_first(self, client):
        send(client, "older one")
        send(client, "newer one")

        messages = [entry["message"] for entry in feedback.recent()]

        assert messages.index("newer one") < messages.index("older one")


class TestTheLink:
    def test_every_page_offers_it(self, client):
        for path in ("/", "/sql", "/learn", "/upload", "/connect-db", "/login"):
            assert "/feedback" in client.get(path).get_data(as_text=True), path

    def test_the_admin_link_is_hidden_from_everyone_else(self, client):
        assert "/feedback/all" not in client.get("/").get_data(as_text=True)

    def test_the_admin_sees_the_link(self, signed_in_admin):
        client, _name = signed_in_admin
        assert "/feedback/all" in client.get("/").get_data(as_text=True)

    def test_the_link_carries_the_page_it_came_from(self, client):
        body = client.get("/connect-db").get_data(as_text=True)
        assert re.search(r'/feedback\?from=/connect-db', body)


class TestItStaysOutOfReach:
    """Feedback holds addresses people typed in. It shares a database with the demo
    tables, so the only thing keeping it private is being absent from the whitelists."""

    def test_the_sql_editor_cannot_read_it(self, client):
        body = client.post("/sql", data={"sql": "SELECT * FROM feedback",
                                         "source": "demo"}).get_data(as_text=True)

        assert "No table called" in body

    def test_the_ai_engine_cannot_be_told_to_read_it(self):
        from backend.engines.ai_engine import BUILTIN_TABLES, _validate_select

        assert "feedback" not in BUILTIN_TABLES
        assert _validate_select("SELECT * FROM feedback", BUILTIN_TABLES) is None

    def test_a_natural_language_question_cannot_reach_it(self, client):
        body = client.get("/", query_string={"q": "show me all feedback"}).get_data(as_text=True)
        assert "someone@example.com" not in body

    def test_a_join_cannot_smuggle_it_in(self, client):
        body = client.post(
            "/sql",
            data={"sql": "SELECT e.name, f.email FROM employees e JOIN feedback f ON e.id = f.id",
                  "source": "demo"},
        ).get_data(as_text=True)

        assert "No table called" in body


class TestRateLimit:
    def test_submissions_are_throttled(self, rate_limited_client):
        """A public write endpoint with a text box needs a ceiling."""
        codes = [send(rate_limited_client, f"spam {i}").status_code for i in range(12)]
        assert 429 in codes


class TestContactLink:
    """Ways to reach the maintainer directly, for anything the box doesn't suit.

    Both, because they reach different people: email needs no account and suits
    someone reporting a bug, LinkedIn suits someone who wants to know who built it.
    """

    LINKEDIN = "https://www.linkedin.com/in/abdulhaseebkashmiri/"
    EMAIL = "abdul.haseeb.kashmiri@outlook.com"

    def test_the_form_offers_both(self, client):
        body = client.get("/feedback").get_data(as_text=True)

        assert self.LINKEDIN in body
        assert self.EMAIL in body

    def test_the_thanks_page_offers_both_too(self, client):
        body = send(client, "Something to say").get_data(as_text=True)

        assert "Thanks" in body
        assert self.LINKEDIN in body
        assert self.EMAIL in body

    def test_the_email_opens_a_mail_client_with_a_subject(self, client):
        """Without a subject line every message arrives titled nothing."""
        body = client.get("/feedback").get_data(as_text=True)

        assert f"mailto:{self.EMAIL}" in body
        assert "subject=" in body

    def test_it_opens_safely_in_a_new_tab(self, client):
        """target=_blank without rel=noopener hands the opened page a handle back
        to this one."""
        body = client.get("/feedback").get_data(as_text=True)
        link = re.search(r'<a[^>]*linkedin\.com[^>]*>', body).group(0)

        assert 'target="_blank"' in link
        assert "noopener" in link
