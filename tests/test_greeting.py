"""The home page heading follows the time of day.

The wording lives in one place (backend/greeting.py) and the browser script is
handed the finished phrases rather than the rules, so there is no second copy to
drift. These tests pin the bands, the name handling, and the fact that the page
carries everything the script needs.
"""

import pytest

from backend.greeting import BANDS, greet, phrase_for_hour, phrases_by_hour


class TestBands:
    @pytest.mark.parametrize(
        "hour, expected",
        [
            (0, "Working late?"),
            (3, "Working late?"),
            (4, "Working late?"),
            (5, "Good morning"),
            (9, "Good morning"),
            (11, "Good morning"),
            (12, "Good afternoon"),
            (15, "Good afternoon"),
            (16, "Good afternoon"),
            (17, "Good evening"),
            (20, "Good evening"),
            (21, "Good evening"),
            (22, "Working late?"),
            (23, "Working late?"),
        ],
    )
    def test_each_hour_lands_in_the_right_band(self, hour, expected):
        assert phrase_for_hour(hour) == expected

    def test_every_hour_of_the_day_has_a_phrase(self):
        phrases = phrases_by_hour()

        assert len(phrases) == 24
        assert all(phrases)

    def test_the_hours_before_dawn_belong_to_the_night_before(self):
        """Midnight isn't morning. Ordering the bands naively puts it there."""
        assert phrase_for_hour(2) == phrase_for_hour(23)

    @pytest.mark.parametrize("hour", [-1, 24, 100])
    def test_an_impossible_hour_is_rejected(self, hour):
        with pytest.raises(ValueError):
            phrase_for_hour(hour)


class TestName:
    def test_a_name_is_appended_to_a_greeting(self):
        assert greet(9, "abdul") == "Good morning, abdul"

    def test_no_name_leaves_the_greeting_alone(self):
        assert greet(9) == "Good morning"
        assert greet(9, "") == "Good morning"

    def test_a_name_is_not_appended_to_a_question(self):
        """"Working late?, abdul" is not a sentence."""
        assert greet(2, "abdul") == "Working late?"


class TestThePage:
    def test_the_heading_is_a_greeting(self, client):
        body = client.get("/").get_data(as_text=True)

        assert any(phrase in body for _start, phrase in BANDS)
        assert "Ask your data a question" not in body

    def test_the_page_carries_every_hour_for_the_browser_to_pick_from(self, client):
        """The script re-picks from the reader's clock, so it needs all 24."""
        body = client.get("/").get_data(as_text=True)

        assert "data-phrases=" in body
        for _start, phrase in BANDS:
            assert phrase in body

    def test_an_anonymous_visitor_gets_no_name(self, client):
        body = client.get("/").get_data(as_text=True)
        assert 'data-name=""' in body

    def test_the_greeting_still_renders_alongside_a_result(self, client):
        body = client.get("/", query_string={"q": "highest paid employees"}).get_data(as_text=True)

        assert any(phrase in body for _start, phrase in BANDS)
        assert "Task understood" in body
