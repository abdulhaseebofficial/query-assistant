"""Adapters for databases the user attaches at runtime, and the little that's shared
between them."""


def quote_ident(name):
    """Quote a schema-supplied identifier for interpolation into SQL.

    Table names can't be bound as parameters, so they get interpolated — and a table
    name is not automatically safe just because it came from the database's own
    catalogue, since the database itself may be one an attacker uploaded. Both SQLite
    and PostgreSQL allow a double quote inside an identifier, which would otherwise
    close the quoting early and let the rest of the name be read as SQL. Doubling the
    quote is the escape both engines define, so one function covers both connectors.
    """
    return '"' + name.replace('"', '""') + '"'
