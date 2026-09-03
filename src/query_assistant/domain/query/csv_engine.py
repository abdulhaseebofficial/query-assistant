"""Turns an uploaded CSV into a queryable SQLite table (`custom_data`), and
provides a simple keyword-search query builder for it when the AI engine is
unavailable.
"""

import csv
import io
import re
from functools import cache

from query_assistant.domain.query.phrases import (
    ALL_PHRASES,
    AVG_PHRASES,
    COUNT_PHRASES,
    HIGHEST_PHRASES,
    LOWEST_PHRASES,
    OVERVIEW_PHRASES,
    SINGLE_ROW_PHRASES,
    SUM_PHRASES,
)
from query_assistant.infrastructure.database.connection import quote_ident


@cache
def _phrase_group_pattern(phrases):
    """One compiled alternation for a group of phrases.

    The groups are module constants asked the same question on every request, so
    compiling one pattern per phrase per call meant re-escaping the same strings
    thousands of times. Word boundaries matter: "min" must not match inside
    "administration", and "max" must not match inside "maximum_capacity".
    """
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in phrases) + r")\b")


def any_phrase(text, phrases):
    """True when any phrase appears as a whole word (or run of words) in `text`."""
    return _phrase_group_pattern(tuple(phrases)).search(text) is not None


MAX_ROWS = 5000
SAMPLE_SIZE = 500

GENERIC_STOPWORDS = {
    "a", "an", "the", "of", "for", "me", "show", "list", "all", "find", "get",
    "please", "want", "need", "some", "any", "row", "rows", "record", "records",
    "is", "are", "was", "were", "this", "that", "these", "those", "there",
    "in", "on", "at", "to", "with", "how", "many", "much", "count", "total",
    "number", "dataset", "data", "does", "did", "search", "give", "tell",
    "ka", "ki", "ke", "ko", "mai", "mujhe", "mein", "hai", "chahiye", "de", "do",
    "kitne", "kitni", "kitna", "hain", "hein", "hy", "ho", "kya", "kaun", "kon",
    "dikhao", "dikhayo", "batao", "bataye", "sab", "sara", "saara",
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
    # Decode the bytes ourselves rather than wrapping the stream. Werkzeug hands the
    # upload route a SpooledTemporaryFile, and before Python 3.11 that isn't an
    # io.IOBase and has no readable() â€” so io.TextIOWrapper raised AttributeError and
    # every upload failed on 3.10 while passing everywhere else. Reading it whole
    # costs nothing here: the request is capped at 5 MB and every row is materialised
    # a few lines below anyway.
    raw = file_stream.read()
    text = raw if isinstance(raw, str) else raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))

    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("The file appears to be empty.") from None

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

    columns_sql = ", ".join(f'"{name}" {sql_type}' for name, sql_type in zip(columns, types, strict=True))
    cur.execute(f"CREATE TABLE custom_data ({columns_sql})")

    placeholders = ", ".join("?" for _ in columns)
    converted_rows = [
        [convert_value(v, t) for v, t in zip(row, types, strict=True)]
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
            for i, (col, label, t) in enumerate(zip(columns, header, types, strict=True))
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


def _column_tokens(columns):
    """Every word that names a column, so it isn't searched for as a *value*.

    Headers are sanitised to snake_case, so "Units Sold" arrives as `units_sold`
    while the question says "units sold". Both the whole name and its parts count.
    """
    tokens = set()
    for column in columns:
        tokens.add(column.lower())
        tokens.update(part for part in column.lower().split("_") if len(part) > 1)
    return tokens


def _names_a_column(word, column_tokens):
    """Whether `word` is the name of a column rather than a value to search for.

    Plurals are tolerated in both directions, including the -ies form: a column
    headed "Product" is asked about as "products" at least as often as "product",
    and "City" is asked about as "cities".
    """
    candidates = {word, word + "s", word.rstrip("s")}
    if word.endswith("ies"):
        candidates.add(word[:-3] + "y")
    if word.endswith("y"):
        candidates.add(word[:-1] + "ies")
    return bool(candidates & column_tokens)


def _numeric_column(columns, types, text):
    """The numeric column the question names, if it names one."""
    if not types:
        return None
    for column, sql_type in zip(columns, types, strict=True):
        if sql_type not in ("INTEGER", "REAL"):
            continue
        if column.lower() in text or column.lower().replace("_", " ") in text:
            return column
    return None


def build_custom_query(user_input, columns, table_name="custom_data", placeholder="?", types=None):
    """Turn a question about an uploaded table into SQL.

    Three shapes, in order of how specific the question is: an aggregate over a named
    numeric column, a ranking by one, or a keyword search across every column.

    A word that names a column is dropped from the search terms rather than looked for
    in the data. Without that, "revenue kitna hai" searched every cell for the text
    "revenue", found none, and reported "Lists matching rows" with nothing under it â€”
    which reads as "your data is empty" rather than "I misunderstood".
    """
    text = user_input.strip().lower()

    # Strip the words that say *what kind* of answer is wanted before looking for the
    # words that say *which rows*. Without this, "average revenue" searched every cell
    # for the text "average", matched nothing, and averaged an empty set to null.
    residue = text
    for phrase in ALL_PHRASES:
        residue = residue.replace(phrase, " ")

    column_tokens = _column_tokens(columns)
    keywords = [
        word for word in residue.split()
        if word not in GENERIC_STOPWORDS
        and not _names_a_column(word, column_tokens)
        and len(word) > 1
    ]

    # "sab dikhao" asks for the table, not for rows containing the word "sab".
    if any_phrase(text, OVERVIEW_PHRASES):
        keywords = []

    table_sql = quote_ident(table_name)
    cols_sql = ", ".join(quote_ident(c) for c in columns)

    conditions = []
    params = []
    for keyword in keywords:
        col_conditions = " OR ".join(
            f"CAST({quote_ident(c)} AS TEXT) LIKE {placeholder}" for c in columns
        )
        conditions.append(f"({col_conditions})")
        params.extend([f"%{keyword}%"] * len(columns))
    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    numeric = _numeric_column(columns, types, text)
    label = numeric.replace("_", " ") if numeric else ""

    # A ranking by a named numeric column: "highest revenue", "sabse kam price".
    # Checked before the aggregates because it's the more specific reading â€” "highest
    # revenue" names a row, "total revenue" names a number.
    if numeric:
        limit = 1 if any_phrase(text, SINGLE_ROW_PHRASES) else 5
        row_word = "row" if limit == 1 else f"{limit} rows"
        if any_phrase(text, HIGHEST_PHRASES):
            sql = (
                f"SELECT {cols_sql} FROM {table_sql}{where_clause} "
                f"ORDER BY {quote_ident(numeric)} DESC LIMIT {limit};"
            )
            return sql, params, f"The {row_word} with the highest {label}.", False
        if any_phrase(text, LOWEST_PHRASES):
            sql = (
                f"SELECT {cols_sql} FROM {table_sql}{where_clause} "
                f"ORDER BY {quote_ident(numeric)} ASC LIMIT {limit};"
            )
            return sql, params, f"The {row_word} with the lowest {label}.", False

    # An aggregate over a named numeric column: "total revenue", "average price".
    if numeric:
        if any_phrase(text, AVG_PHRASES):
            sql = f"SELECT AVG({quote_ident(numeric)}) AS average FROM {table_sql}{where_clause};"
            return sql, params, f"Calculates the average {label}.", True
        if any_phrase(text, SUM_PHRASES):
            sql = f"SELECT SUM({quote_ident(numeric)}) AS total FROM {table_sql}{where_clause};"
            return sql, params, f"Adds up the total {label}.", True

    if any_phrase(text, COUNT_PHRASES):
        # "revenue kitna hai" asks how *much*, not how many â€” the same distinction
        # rule_engine draws, and it turns on whether the question named an amount.
        if numeric:
            sql = f"SELECT SUM({quote_ident(numeric)}) AS total FROM {table_sql}{where_clause};"
            return sql, params, f"Adds up the total {label}.", True

        sql = f"SELECT COUNT(*) AS count FROM {table_sql}{where_clause};"
        explanation = (
            "Counts how many rows match the search terms." if keywords
            else "Counts how many rows the dataset has."
        )
        return sql, params, explanation, True

    sql = f"SELECT {cols_sql} FROM {table_sql}{where_clause} LIMIT 200;"
    explanation = (
        "Lists matching rows (showing up to 200)." if keywords
        else "Lists every row in the dataset (showing up to 200)."
    )
    return sql, params, explanation, False
