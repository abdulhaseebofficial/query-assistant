"""Builds the CSV files served by the /export routes.

The reason this isn't three lines of `csv.DictWriter` inline in app.py is
`_neutralise_formula`. A CSV cell that starts with `=`, `+`, `-`, `@`, a tab, or a
carriage return is interpreted as a *formula* by Excel, LibreOffice, and Google
Sheets — not as text. So a row of query output like:

    =cmd|'/c calc.exe'!A0

is a working command-execution payload the moment the person who downloaded the
file opens it. The data doesn't have to come from an attacker's own database
either: any CSV or external database connected to this app can carry cells like
that, and the export hands them straight to whoever clicked "Download CSV".

This is CSV injection (a.k.a. formula injection), and the fix is to prefix such
cells with a single quote, which spreadsheet software treats as "the rest of this
cell is literal text".
"""

import csv
import io

# Excel/Sheets treat a cell beginning with any of these as a formula.
FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _neutralise_formula(value):
    """Return `value` unchanged unless it would be read as a spreadsheet formula.

    Real numbers are passed through untouched — they arrive from the database as
    int/float, not str. A *string* that merely looks numeric ("-5", "+3.2") is also
    left alone, so a text column of negative numbers doesn't get mangled; only
    strings that start with a trigger character and aren't a plain number get the
    leading quote.
    """
    if not isinstance(value, str) or not value.startswith(FORMULA_TRIGGERS):
        return value

    try:
        float(value)
        return value
    except ValueError:
        return "'" + value


def build_csv(columns, rows):
    """Render rows as CSV text, with every cell safe to open in a spreadsheet."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({col: _neutralise_formula(row.get(col)) for col in columns})
    return buffer.getvalue()
