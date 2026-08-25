import csv
import io
import re

MAX_ROWS = 5000
SAMPLE_SIZE = 500

GENERIC_STOPWORDS = {
    "a", "an", "the", "of", "for", "me", "show", "list", "all", "find", "get",
    "please", "want", "need", "some", "any", "row", "rows", "record", "records",
    "is", "are", "was", "were", "this", "that", "these", "those", "there",
    "in", "on", "at", "to", "with", "how", "many", "much", "count", "total",
    "number", "dataset", "data", "does", "did", "search", "give", "tell",
    "ka", "ki", "ke", "ko", "mai", "mujhe", "mein", "hai", "chahiye", "de", "do",
    "kitne", "kitni",
}


def sanitize_column_name(name, index, used):
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_").lower()
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"col_{cleaned}" if cleaned else f"col_{index}"

    final = cleaned
    n = 1
    while final in used:
        n += 1
        final = f"{cleaned}_{n}"
    used.add(final)
    return final


def infer_type(values):
    if not values:
        return "TEXT"

    def is_int(v):
        try:
            int(v)
            return True
        except ValueError:
            return False

    def is_float(v):
        try:
            float(v)
            return True
        except ValueError:
            return False

    if all(is_int(v) for v in values):
        return "INTEGER"
    if all(is_float(v) for v in values):
        return "REAL"
    return "TEXT"


def convert_value(value, sql_type):
    value = value.strip()
    if value == "":
        return None
    if sql_type == "INTEGER":
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            return value  # keep the original text rather than silently dropping it
    if sql_type == "REAL":
        try:
            return float(value)
        except ValueError:
            return value  # keep the original text rather than silently dropping it
    return value


def sample_rows(rows, size):
    if len(rows) <= size:
        return rows
    step = len(rows) / size
    return [rows[int(i * step)] for i in range(size)]


def load_csv(file_stream, conn, dataset_name="dataset"):
    text_stream = io.TextIOWrapper(file_stream, encoding="utf-8-sig", errors="replace")
    reader = csv.reader(text_stream)

    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("The file appears to be empty.")

    header = [h for h in header if h is not None]
    if not header:
        raise ValueError("No columns found in the file's first row.")

    used = set()
    columns = [sanitize_column_name(h, i, used) for i, h in enumerate(header)]

    rows = []
    for row in reader:
        if len(rows) >= MAX_ROWS:
            break
        row = (row + [""] * len(header))[: len(header)]
        rows.append(row)

    if not rows:
        raise ValueError("No data rows found below the header.")

    sample = sample_rows(rows, SAMPLE_SIZE)
    types = []
    for col_idx in range(len(header)):
        values = [r[col_idx] for r in sample if r[col_idx].strip() != ""]
        types.append(infer_type(values))

    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS custom_data")
    cur.execute("DROP TABLE IF EXISTS custom_meta")

    columns_sql = ", ".join(f'"{name}" {sql_type}' for name, sql_type in zip(columns, types))
    cur.execute(f"CREATE TABLE custom_data ({columns_sql})")

    placeholders = ", ".join("?" for _ in columns)
    converted_rows = [
        [convert_value(v, t) for v, t in zip(row, types)]
        for row in rows
    ]
    cur.executemany(f"INSERT INTO custom_data VALUES ({placeholders})", converted_rows)

    cur.execute(
        "CREATE TABLE custom_meta (dataset_name TEXT, column_name TEXT, display_label TEXT, "
        "col_type TEXT, position INTEGER)"
    )
    cur.executemany(
        "INSERT INTO custom_meta VALUES (?, ?, ?, ?, ?)",
        [
            (dataset_name, col, label, t, i)
            for i, (col, label, t) in enumerate(zip(columns, header, types))
        ],
    )

    conn.commit()
    return get_dataset_info(conn)


def get_dataset_info(conn):
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='custom_meta'"
    ).fetchall()
    if not tables:
        return None

    meta_rows = conn.execute(
        "SELECT dataset_name, column_name, display_label, col_type FROM custom_meta ORDER BY position"
    ).fetchall()
    if not meta_rows:
        return None

    row_count = conn.execute("SELECT COUNT(*) FROM custom_data").fetchone()[0]

    return {
        "name": meta_rows[0][0],
        "columns": [r[1] for r in meta_rows],
        "labels": [r[2] for r in meta_rows],
        "types": [r[3] for r in meta_rows],
        "row_count": row_count,
    }


def clear_dataset(conn):
    conn.execute("DROP TABLE IF EXISTS custom_data")
    conn.execute("DROP TABLE IF EXISTS custom_meta")
    conn.commit()


def build_custom_query(user_input, columns, table_name="custom_data", placeholder="?"):
    text = user_input.strip().lower()
    words = [w.strip() for w in text.split() if w.strip()]
    keywords = [w for w in words if w not in GENERIC_STOPWORDS and len(w) > 1]

    is_count = any(
        re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None
        for phrase in ("how many", "count", "kitne", "kitni", "number of")
    )

    conditions = []
    params = []
    for kw in keywords:
        col_conditions = " OR ".join(f'CAST("{c}" AS TEXT) LIKE {placeholder}' for c in columns)
        conditions.append(f"({col_conditions})")
        params.extend([f"%{kw}%"] * len(columns))

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    table_sql = f'"{table_name}"'

    if is_count:
        sql = f"SELECT COUNT(*) AS count FROM {table_sql}{where_clause};"
        explanation = "Counts how many rows match the search terms."
    else:
        cols_sql = ", ".join(f'"{c}"' for c in columns)
        sql = f"SELECT {cols_sql} FROM {table_sql}{where_clause} LIMIT 200;"
        explanation = "Lists matching rows (showing up to 200)."

    return sql, params, explanation, is_count
