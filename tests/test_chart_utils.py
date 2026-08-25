"""build_chart_data() decides whether a result set is worth drawing at all —
getting that wrong means either a missing chart or a meaningless one."""

from backend.utils import chart_utils

ROWS = [
    {"department": "IT", "headcount": 6, "id": 1},
    {"department": "Sales", "headcount": 4, "id": 2},
    {"department": "HR", "headcount": 3, "id": 3},
]
COLUMNS = ["department", "headcount", "id"]


def test_builds_a_chart_from_a_label_column_and_a_numeric_column():
    chart = chart_utils.build_chart_data(COLUMNS, ROWS)

    assert chart["type"] == "bar"
    assert chart["labels"] == ["IT", "Sales", "HR"]
    assert chart["values"] == [6, 4, 3]
    assert chart["value_label"] == "headcount"


def test_id_columns_are_never_charted_as_values():
    """`id` is numeric but plotting it is meaningless."""
    chart = chart_utils.build_chart_data(["name", "id"], [{"name": "a", "id": 1}, {"name": "b", "id": 2}])
    assert chart is None


def test_an_explicit_hint_overrides_the_bar_default():
    chart = chart_utils.build_chart_data(COLUMNS, ROWS, "line")
    assert chart["type"] == "line"


def test_an_unknown_hint_falls_back_to_bar():
    chart = chart_utils.build_chart_data(COLUMNS, ROWS, "sunburst")
    assert chart["type"] == "bar"


def test_a_single_row_is_not_charted():
    assert chart_utils.build_chart_data(COLUMNS, ROWS[:1]) is None


def test_an_empty_result_set_is_not_charted():
    assert chart_utils.build_chart_data(COLUMNS, []) is None


def test_a_text_only_result_set_is_not_charted():
    rows = [{"name": "Ali", "city": "Karachi"}, {"name": "Sana", "city": "Lahore"}]
    assert chart_utils.build_chart_data(["name", "city"], rows) is None


def test_long_result_sets_are_capped():
    rows = [{"label": f"r{i}", "value": i} for i in range(100)]
    chart = chart_utils.build_chart_data(["label", "value"], rows)
    assert len(chart["labels"]) == chart_utils.MAX_POINTS


def test_booleans_are_not_treated_as_numbers():
    rows = [{"name": "a", "active": True}, {"name": "b", "active": False}]
    assert chart_utils.build_chart_data(["name", "active"], rows) is None
