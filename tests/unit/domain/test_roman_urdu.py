"""Questions asked the way they're actually asked here â€” Roman Urdu, or mixed with
English in one sentence.

Every case in this file was found by asking the running app real questions and
noticing the answer was wrong. Three kinds of wrong showed up, and the third is the
dangerous one:

* refused as off-topic, because a word like "grahak" or "saman" wasn't in the
  vocabulary at all;
* answered from the wrong table, because the domain words collided;
* answered from the right table with a filter silently dropped â€” "IT walay
  employees" returned all eighteen employees, explained as "Lists all employees".
  Nothing in that output tells you the department was ignored.
"""

import pytest

from query_assistant.domain.query.rule_engine import (
    detect_aggregate,
    detect_domain,
    interpret,
    wants_overview,
)


class TestVocabulary:
    """A word missing from the lists reads as "this database can't answer that",
    which is untrue and sends people away."""

    @pytest.mark.parametrize(
        "question, domain",
        [
            ("kon kon kaam karta hai", "employees"),
            ("kitne log kaam karte hain", "employees"),
            ("mulazmeen ki list", "employees"),
            ("tankhwah kitni hai", "employees"),
            ("saman ki list", "products"),
            ("kya kya cheezein hain", "products"),
            ("average price kya hai", "products"),
            ("qeemat batao products ki", "products"),
            ("grahak", "customers"),
            ("khareedar ki list", "customers"),
            ("bikri kitni hui", "orders"),
            ("kul aamdani", "orders"),
            ("shuba ki list", "departments"),
        ],
    )
    def test_the_question_reaches_the_right_table(self, question, domain):
        assert detect_domain(question) == domain

    @pytest.mark.parametrize("question", ["tell me a joke", "what is the weather", "hello there"])
    def test_genuinely_unrelated_questions_are_still_off_topic(self, question):
        assert detect_domain(question) is None


class TestDepartmentFilterIsNotDropped:
    """A two-letter department name needs a nearby cue to be told apart from the
    English word "it" â€” and the Roman Urdu cue comes *after* the name, not before.
    Missing it meant the filter vanished and every employee was returned as the answer.
    """

    @pytest.mark.parametrize(
        "question, department",
        [
            ("IT walay employees", "IT"),
            ("IT wale log", "IT"),
            ("HR wale log", "HR"),
            ("IT ke employees", "IT"),
            ("HR ki team", "HR"),
            ("employees in the IT department", "IT"),
            ("IT department employees", "IT"),
        ],
    )
    def test_the_department_is_bound_as_a_parameter(self, conn, question, department):
        result = interpret(question, conn)

        assert result is not None
        assert department in result["params"], "the department filter was dropped"

    def test_a_filtered_question_returns_fewer_rows_than_the_whole_table(self, conn):
        everyone = interpret("sare employees dikhao", conn)
        just_it = interpret("IT walay employees", conn)

        all_rows = conn.execute(everyone["sql"], everyone["params"]).fetchall()
        it_rows = conn.execute(just_it["sql"], just_it["params"]).fetchall()

        assert 0 < len(it_rows) < len(all_rows)

    def test_the_english_word_it_is_not_mistaken_for_the_department(self, conn):
        """"it is a good day for employees" names no department."""
        result = interpret("it is a good day for employees", conn)

        assert result is not None
        assert result["params"] == []


class TestAggregates:
    @pytest.mark.parametrize(
        "question, aggregate",
        [
            ("kitne employees hain", "count"),
            ("kitne log kaam karte hain", "count"),
            ("how many orders", "count"),
            ("total kitne orders", "count"),
            ("total kitni sales hui", "sum"),
            ("kul aamdani", "sum"),
            ("total revenue this month", "sum"),
            ("average price kya hai", "avg"),
            ("ausat salary", "avg"),
        ],
    )
    def test_the_right_aggregate_is_chosen(self, question, aggregate):
        assert detect_aggregate(question) == aggregate

    def test_totalling_an_amount_beats_counting_rows(self):
        """"total kitni sales hui" has both a sum word and a count word. It's asking
        how much, not how many â€” and it used to answer how many."""
        assert detect_aggregate("total kitni sales hui") == "sum"

    def test_counting_still_wins_when_there_is_no_amount_to_total(self):
        assert detect_aggregate("total kitne employees") == "count"

    def test_counting_departments_returns_a_number_not_a_listing(self, conn):
        """This builder ignored its aggregate argument entirely."""
        result = interpret("kitne departments hain", conn)

        assert result is not None
        assert result["aggregate"] == "count"
        rows = conn.execute(result["sql"], result["params"]).fetchall()
        assert len(rows) == 1
        assert rows[0]["count"] == 5


class TestRomanUrduDates:
    @pytest.mark.parametrize(
        "question, fragment",
        [
            ("aaj ke orders", "today"),
            ("is mahine ki sales", "this month"),
            ("pichle mahine ke orders", "last month"),
            ("is saal ki sales", "this year"),
        ],
    )
    def test_the_period_reaches_the_explanation(self, conn, question, fragment):
        result = interpret(question, conn)

        assert result is not None
        assert fragment in result["explanation"], "the date filter was dropped"

    def test_a_dated_question_filters_the_rows(self, conn):
        everything = interpret("orders dikhao", conn)
        this_month = interpret("is mahine ki sales", conn)

        all_rows = conn.execute(everything["sql"], everything["params"]).fetchall()
        month_rows = conn.execute(this_month["sql"], this_month["params"]).fetchall()

        assert len(month_rows) < len(all_rows)


class TestOverviewQuestions:
    """"Show me everything" is a fair question with no single query behind it. Being
    told the database can't answer it is both untrue and a dead end."""

    @pytest.mark.parametrize(
        "question",
        [
            "mujha sara data dikhayo company ka",
            "show me all the data",
            "sab kuch dikhao",
            "company ka data",
            "everything",
            "show me the database",
            "poora data dikhao",
        ],
    )
    def test_the_question_is_recognised_as_asking_for_everything(self, question):
        assert wants_overview(question)

    @pytest.mark.parametrize(
        "question",
        ["employees in the IT department", "pending orders", "tell me a joke", "cheapest products"],
    )
    def test_a_specific_question_is_not_treated_as_an_overview(self, question):
        assert not wants_overview(question)

    def test_the_page_offers_the_tables_instead_of_refusing(self, client):
        body = client.get("/", query_string={"q": "mujha sara data dikhayo company ka"}).get_data(
            as_text=True
        )

        assert "Which part of it?" in body
        assert "not something this database can answer" not in body
        for table in ("employees", "departments", "products", "customers", "orders"):
            assert f"/?q=all+{table}" in body


class TestNoSilentlyWrongAnswers:
    """The whole point: an answer that looks right and isn't is worse than no answer.
    Each of these returned the full table with the constraint quietly discarded."""

    @pytest.mark.parametrize(
        "question, must_not_return_everything",
        [
            ("IT walay employees", "employees"),
            ("aaj ke orders", "orders"),
            ("HR wale log", "employees"),
        ],
    )
    def test_a_constraint_is_either_applied_or_the_question_is_declined(
        self, conn, question, must_not_return_everything
    ):
        result = interpret(question, conn)
        if result is None:
            return  # declining is an acceptable outcome; answering wrongly is not

        rows = conn.execute(result["sql"], result["params"]).fetchall()
        total = conn.execute(f"SELECT COUNT(*) AS c FROM {must_not_return_everything}").fetchone()["c"]
        assert len(rows) < total, "the filter was dropped and the whole table came back"
