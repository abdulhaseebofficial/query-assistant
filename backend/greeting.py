"""The heading on the home page, which follows the time of day.

The wording lives here and nowhere else. The page is rendered on the server, but
the server's clock is not the reader's — a deployment sits in UTC while the person
looking at it does not — so a small script on the page recomputes the greeting from
the browser's own hour. To keep that from becoming a second copy of the wording
that drifts from this one, the script is handed these phrases and only decides
*which* of them applies.
"""

# (hour the band starts, phrase). Ordered, and the last band wraps past midnight.
BANDS = (
    (5, "Good morning"),
    (12, "Good afternoon"),
    (17, "Good evening"),
    (22, "Working late?"),
)

# Before 05:00 belongs to the band that started the previous evening.
OVERNIGHT = BANDS[-1][1]


def phrase_for_hour(hour):
    """The greeting for a 24-hour clock hour."""
    if not 0 <= hour <= 23:
        raise ValueError(f"hour must be 0-23, got {hour}")

    chosen = OVERNIGHT
    for start, phrase in BANDS:
        if hour >= start:
            chosen = phrase
    return chosen


def greet(hour, name=None):
    """The full heading, with the reader's name when there is one.

    A name is only appended to the greetings that read as an address. "Working
    late?, abdul" is not a sentence, so that band is left alone.
    """
    phrase = phrase_for_hour(hour)
    if name and not phrase.endswith("?"):
        return f"{phrase}, {name}"
    return phrase


def phrases_by_hour():
    """The 24 phrases, one per hour, for the browser-side script to index into.

    Handing over the answers rather than the rules is what stops the wording from
    being written a second time in JavaScript.
    """
    return [phrase_for_hour(hour) for hour in range(24)]
