"""Words and phrases that mean the same thing whatever data is being queried.

Both engines need these. rule_engine answers questions about the built-in demo
schema; csv_engine answers them about whatever table someone uploaded — but "kitne"
means "how many" in both, and "sab dikhao" means "show me everything" in both.

They live here rather than in either engine because the last time a phrase list was
written out twice, one copy grew and the other didn't: "highest paid" was understood
while "highest salary" was refused, and nothing about either file made that visible.
Schema-specific vocabulary (salaries, stock levels) stays with the engine that knows
about salaries and stock.

English and Roman Urdu sit in the same tuples on purpose. Real questions mix them in
one sentence, so there's no point pretending they're separate languages to detect.
"""

COUNT_PHRASES = ("how many", "count", "kitne", "kitni", "kitna", "number of")

# Words that ask for a sum, kept apart from nouns that merely imply one. "revenue"
# reads as "the revenue total" when it's a topic, but as a column name when someone
# has uploaded a spreadsheet with a Revenue column — and there, "highest revenue" is
# a ranking, not a sum. Only an engine that knows which situation it's in should
# treat the noun as an aggregate.
SUM_PHRASES = ("total", "sum", "kul")
SUM_NOUNS = ("revenue", "aamdani")

AVG_PHRASES = ("average", "avg", "mean", "ausat")

# "total kitni sales hui" contains both a sum word and a count word. Which is meant
# depends on the noun: you total an amount, you count a thing.
MONEY_WORDS = (
    "revenue", "sales", "salary", "salaries", "amount", "price", "cost", "total_amount",
    "aamdani", "tankhwah", "bikri", "qeemat", "keemat",
)

# Someone asking for exactly one row rather than a list.
SINGLE_ROW_PHRASES = (
    "sirf aik", "sirf ek", "sirf 1", "srif aik", "srif ek",
    "only one", "only 1", "just one", "just 1", "top 1", "number 1",
    "aik hi", "ek hi", "single", "one only",
)

# Someone asking for the whole thing rather than a part of it.
OVERVIEW_PHRASES = (
    "sara data", "saara data", "sab data", "sab kuch", "sabkuch", "poora data", "pura data",
    "all the data", "all data", "everything", "the database", "whole database",
    "entire database", "data dikhao", "data dikhayo", "company ka data", "company data",
    "show me the data", "sari information", "saari maloomat",
    "sab dikhao", "sab dikhayo", "sara dikhao", "poora dikhao", "show all",
)

# Ranking, in the general "biggest / smallest of this column" sense.
HIGHEST_PHRASES = (
    "highest", "largest", "biggest", "maximum", "max", "top", "most",
    "sabse zyada", "sab se zyada", "sabse bara", "zyada se zyada",
)
LOWEST_PHRASES = (
    "lowest", "smallest", "minimum", "min", "least", "bottom",
    "sabse kam", "sab se kam", "sabse chota", "kam se kam",
)


# Every phrase above, longest first. Callers subtract these from a question so that
# what remains is the part naming actual values to search for — otherwise "average
# revenue" looks for rows containing the text "average". Built once at import: the
# tuples are constants, and this used to be re-sorted on every question.
ALL_PHRASES = tuple(
    sorted(
        set(
            COUNT_PHRASES + SUM_PHRASES + SUM_NOUNS + AVG_PHRASES
            + SINGLE_ROW_PHRASES + OVERVIEW_PHRASES + HIGHEST_PHRASES + LOWEST_PHRASES
        ),
        key=len,
        reverse=True,
    )
)

