"""Turns a query result set into the minimal JSON shape the Chart.js partial
(src/query_assistant/web/templates/partials/_chart.html) needs to draw a bar/line/pie chart.
"""

MAX_POINTS = 20


def _is_numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numeric_columns(columns, rows):
    numeric = []
    for col in columns:
        if col.lower() == "id" or col.lower().endswith("_id"):
            continue
        values = [row[col] for row in rows if row[col] is not None]
        if values and all(_is_numeric(v) for v in values):
            numeric.append(col)
    return numeric


def build_chart_data(columns, rows, chart_type_hint="none"):
    if not rows or len(rows) < 2 or not columns:
        return None

    numeric_cols = _numeric_columns(columns, rows)
    if not numeric_cols:
        return None

    value_col = numeric_cols[0]
    label_col = next((c for c in columns if c not in numeric_cols), columns[0])

    sample = rows[:MAX_POINTS]
    labels = [str(row[label_col]) if row[label_col] is not None else "" for row in sample]
    values = [row[value_col] if row[value_col] is not None else 0 for row in sample]

    chart_type = chart_type_hint if chart_type_hint in ("bar", "line", "pie") else "bar"

    return {
        "type": chart_type,
        "labels": labels,
        "values": values,
        "value_label": value_col.replace("_", " "),
    }
