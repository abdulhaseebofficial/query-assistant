"""The rule engine must decline questions it can't actually answer.

Every builder in rule_engine.py ends in a catch-all "list everything" branch. Before
`unsupported_constraints` existed, that branch answered questions it had not
understood: "employees earning more than 100000" returned all 18 employees under the
explanation "Lists all employees, sorted by name". The user has no way to tell that
apart from a correct answer, which makes it worse than no answer at all.

These tests pin both halves of the behaviour — what it must refuse, and what it must
still answer, so the fix can't be over-applied into refusing everything.
"""

import pytest

from backend.engines.rule_engine import (
    get_reference_data,
    interpret,
    reference_names,
    unsupported_constraints,
)

# Each of these silently returned a wrong result before the gate was added.
UNANSWERABLE = [
    ("which department has the most employees", "a ranking"),
    ("employees earning more than 100000", "a comparison"),
    ("employees hired in 2023", "a specific number"),
    ("top 3 most expensive products", "a ranking"),
    ("customers who never ordered anything", "a negation"),
    ("list departments with more than 3 people", "a comparison"),
    ("orders placed before March", "a date range"),
    ("employees per department", "a grouping"),
    ("products under 100 rupees", "a comparison"),
    ("customers without any orders", "a negation"),
    ("revenue for each product", "a grouping"),
]

# These are the phrasings the templates genuinely encode. The gate must not eat them.
ANSWERABLE = [
    "employees in the IT department",
    "highest paid employees",
    "newest employees",
    "products low on stock",
    "most expensive products",
    "cheapest products",
    "the lowest paid employee",
    "highest salary person in this company",
    "top earners",
    "customers in Lahore",
    "total revenue this month",
    "pending orders",
    "cancelled orders",
    "how many employees are there",
    "kitne employees hain",
    "average salary in sales",
    "sales team ka total salary kitna hai",
    "show me all departments",
    # The database's own values, which look like constraints and are not. The Learn
    # page links straight to the first of these, and it was refused as asking for
    # "a specific number" because of the 15 in the product's name.
    "orders for Laptop Pro 15",
    "orders for 27-inch Monitor",
]


class TestRefusesRatherThanGuessing:
    @pytest.mark.parametrize("question, _label", UNANSWERABLE)
    def test_the_question_is_declined(self, conn, question, _label):
        assert interpret(question, conn) is None, "answered a question it cannot express"

    @pytest.mark.parametrize("question, label", UNANSWERABLE)
    def test_the_reason_is_reported(self, question, label):
        """The UI shows this reason, so it has to name the right thing."""
        assert label in unsupported_constraints(question)

    def test_a_full_table_dump_is_never_passed_off_as_an_answer(self, conn):
        """The specific regression: 18 employees returned as if they were the answer."""
        assert interpret("employees earning more than 100000", conn) is None


class TestStillAnswersWhatItKnows:
    @pytest.mark.parametrize("question", ANSWERABLE)
    def test_supported_phrasings_survive_the_gate(self, conn, question):
        result = interpret(question, conn)
        assert result is not None, "the gate is refusing a question it does handle"
        assert result["sql"].lstrip().upper().startswith("SELECT")

    @pytest.mark.parametrize("question", ANSWERABLE)
    def test_the_generated_sql_actually_runs(self, conn, question):
        result = interpret(question, conn)
        conn.execute(result["sql"], result["params"]).fetchall()

    @pytest.mark.parametrize(
        "question",
        ["highest paid employees", "most expensive products", "least expensive products"],
    )
    def test_ranking_words_inside_a_recognised_phrase_are_not_treated_as_constraints(self, question):
        """"highest paid" is encoded; a bare "highest" is not. Only the second refuses."""
        assert unsupported_constraints(question) == []


class TestValuesAreNotConstraints:
    """A product named "Laptop Pro 15" contains a digit; that isn't a threshold.

    The filter it produces is a plain equality the templates express happily, so
    stripping the database's own values out of the question before looking for
    constraints is what lets these through.
    """

    @pytest.mark.parametrize(
        "question, value",
        [
            ("orders for Laptop Pro 15", "Laptop Pro 15"),
            ("orders for 27-inch Monitor", "27-inch Monitor"),
        ],
    )
    def test_a_name_containing_a_digit_still_filters_on_that_name(self, conn, question, value):
        result = interpret(question, conn)
        assert result is not None, "refused a question whose only digit was in a product name"
        assert value in result["params"]

    def test_a_real_constraint_beside_such_a_name_is_still_refused(self, conn):
        """Only the name is exempt — the rest of the question is still inspected."""
        assert interpret("orders for Laptop Pro 15 grouped by month", conn) is None

    def test_the_reason_given_is_the_real_one(self, conn):
        """Reporting "a specific number" here would blame the product's name."""
        names = reference_names(get_reference_data(conn))
        reasons = unsupported_constraints("orders for laptop pro 15 grouped by month", names)
        assert reasons == ["a grouping"]

    def test_a_short_name_is_not_matched_inside_another_word(self, conn):
        """The IT department is two characters; "without" contains them both."""
        assert interpret("customers without any orders", conn) is None


class TestOffTopicQuestions:
    @pytest.mark.parametrize("question", ["tell me a joke", "what is the weather", "hello"])
    def test_questions_about_nothing_in_the_schema_are_declined(self, conn, question):
        assert interpret(question, conn) is None


class TestFailureIsExplained:
    """describe_failure() drives which message the page shows. Getting it wrong means
    telling someone to add an API key when the real problem is their question."""

    def test_an_off_topic_question_is_marked_off_topic(self):
        from backend.app import describe_failure

        detail = describe_failure("tell me a joke")
        assert detail["on_topic"] is False

    def test_an_on_topic_question_names_its_unsupported_constraints(self):
        from backend.app import describe_failure

        detail = describe_failure("employees earning more than 100000")
        assert detail["on_topic"] is True
        assert "a comparison" in detail["constraints"]

    def test_ai_is_reported_unavailable_with_no_key(self):
        from backend.app import describe_failure

        assert describe_failure("employees earning more than 100000")["ai_available"] is False
        assert describe_failure("anything")["provider"] is None

    def test_the_provider_is_named_once_a_key_is_set(self, monkeypatch):
        import backend.engines.ai_engine as ai_engine
        from backend.app import describe_failure

        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(ai_engine, "_get_client", lambda provider: object())

        detail = describe_failure("employees earning more than 100000")
        assert detail["ai_available"] is True
        assert detail["provider"] == "Gemini"


class TestThePageSaysSomethingUseful:
    def test_an_unsupported_question_explains_what_to_do_about_it(self, client):
        response = client.get("/", query_string={"q": "employees earning more than 100000"})
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "needs AI turned on" in body
        assert "GEMINI_API_KEY" in body
        assert "a comparison" in body

    def test_an_off_topic_question_does_not_blame_the_missing_api_key(self, client):
        body = client.get("/", query_string={"q": "tell me a joke"}).get_data(as_text=True)

        assert "GEMINI_API_KEY" not in body
        assert "not something this database can answer" in body

    def test_with_ai_on_the_message_points_at_the_model_not_the_key(self, client, monkeypatch):
        import backend.engines.ai_engine as ai_engine

        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(ai_engine, "_get_client", lambda provider: object())
        monkeypatch.setitem(ai_engine._GENERATORS, "gemini", lambda *args: None)

        body = client.get("/", query_string={"q": "employees earning more than 100000"}).get_data(as_text=True)

        assert "Gemini couldn't turn that into a valid query" in body
        assert "GEMINI_API_KEY" not in body, "told the user to add a key they already have"

    def test_a_supported_question_still_returns_a_normal_answer(self, client):
        body = client.get("/", query_string={"q": "employees in the IT department"}).get_data(as_text=True)

        assert "Task understood" in body
        assert "SELECT" in body


class TestAiPathEndToEnd:
    """With a provider configured, its SQL should reach the page — proving the wiring,
    without a network call."""

    @pytest.fixture
    def gemini_returning(self, monkeypatch):
        import backend.engines.ai_engine as ai_engine

        def _install(payload):
            monkeypatch.setenv("GEMINI_API_KEY", "test-key")
            monkeypatch.setattr(ai_engine, "_get_client", lambda provider: object())
            monkeypatch.setitem(ai_engine._GENERATORS, "gemini", lambda *args: payload)

        return _install

    def test_a_question_the_rules_refuse_is_answered_by_the_model(self, client, gemini_returning):
        gemini_returning({
            "sql": "SELECT name, salary FROM employees WHERE salary > 100000 ORDER BY salary DESC",
            "explanation": "Lists employees earning more than 100,000.",
            "chart_type": "bar",
        })

        body = client.get("/", query_string={"q": "employees earning more than 100000"}).get_data(as_text=True)

        assert "Task understood" in body
        assert "Lists employees earning more than 100,000." in body
        assert "Fatima Sheikh" in body, "the query didn't actually run"

    def test_the_answer_is_labelled_as_coming_from_ai(self, client, gemini_returning):
        gemini_returning({
            "sql": "SELECT name FROM employees WHERE salary > 100000",
            "explanation": "High earners.",
            "chart_type": "none",
        })

        body = client.get("/", query_string={"q": "employees earning more than 100000"}).get_data(as_text=True)
        assert "engine-ai" in body

    def test_unsafe_model_sql_still_falls_back_instead_of_running(self, client, gemini_returning):
        gemini_returning({
            "sql": "SELECT username, password_hash FROM users",
            "explanation": "Oops.",
            "chart_type": "none",
        })

        body = client.get("/", query_string={"q": "employees earning more than 100000"}).get_data(as_text=True)
        assert "password_hash" not in body


class TestSingleRowRequests:
    """Asking for one and getting five isn't a wrong answer, but it isn't the answer.

    The Roman Urdu forms matter here: "sirf aik ka" is how the question actually gets
    asked, and it went unrecognised while the English "the highest paid employee"
    worked.
    """

    ONE_ROW = [
        "mujha data nikal kar doh highest salary ka bataye sirf aik ka",
        "highest salary sirf ek",
        "sabse zyada salary sirf aik",
        "only one highest paid employee",
        "just one highest paid",
        "top 1 highest paid",
        "the highest paid employee",
        "highest salary person in this company",
        "cheapest product only one",
    ]

    FIVE_ROWS = [
        "highest paid employees",
        "top earners",
        "cheapest products",
        "newest employees",
    ]

    @pytest.mark.parametrize("question", ONE_ROW)
    def test_asking_for_one_returns_one(self, conn, question):
        result = interpret(question, conn)

        assert result is not None, "refused a question it can answer"
        assert len(conn.execute(result["sql"], result["params"]).fetchall()) == 1

    @pytest.mark.parametrize("question", ONE_ROW)
    def test_the_explanation_does_not_promise_five(self, conn, question):
        assert "5" not in interpret(question, conn)["explanation"]

    @pytest.mark.parametrize("question", FIVE_ROWS)
    def test_a_plural_question_still_returns_a_list(self, conn, question):
        result = interpret(question, conn)

        assert result is not None
        assert len(conn.execute(result["sql"], result["params"]).fetchall()) == 5

    @pytest.mark.parametrize("question", ["top 1 highest paid", "only 1 highest paid"])
    def test_a_digit_meaning_one_is_not_refused_as_an_unsupported_number(self, conn, question):
        """LIMIT 1 is expressible, so "top 1" must not hit the "a specific number" gate."""
        assert unsupported_constraints(question) == []
        assert interpret(question, conn) is not None

    def test_a_digit_that_is_not_one_is_still_refused(self, conn):
        """LIMIT 3 is not something these templates can express."""
        assert interpret("top 3 highest paid", conn) is None
