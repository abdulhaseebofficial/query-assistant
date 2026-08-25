# backend/engines/

An **engine** here just means: code that reads a question typed in plain English (or Roman Urdu) and turns it into an SQL query.

There are three engines, and they're tried in order until one of them can answer the question.

## What's in this folder

| File | What it does |
|---|---|
| `ai_engine.py` | Tried **first**. Sends the question to an AI model and asks it to write the SQL. It can use either **Google Gemini** (`GEMINI_API_KEY`) or **Anthropic Claude** (`ANTHROPIC_API_KEY`) — whichever key you've set up. If neither is set, this engine is skipped automatically. Before running anything the AI writes, it double-checks the SQL is safe: it must be a single read-only `SELECT`, and it's only allowed to look at specific tables (so it can never peek at things like saved passwords). |
| `rule_engine.py` | Used for the **built-in demo database** (departments, employees, products, customers, orders) when the AI engine isn't available. It works by looking for keywords in the question — like "employees", "highest paid", or "kitne" (Urdu for "how many") — and building the matching SQL query from a fixed template. It only answers the phrasings it genuinely knows; see "When it refuses to answer" below. |
| `csv_engine.py` | Handles CSV files that a user uploads. It reads the file, figures out each column's data type, saves it as a table, and — like `rule_engine.py` — can build a simple keyword-search query if the AI engine isn't available. |

## Why two ways of answering the same question?

The AI engine is smarter and more flexible, but it needs an internet connection and an API key. The rule-based engines (`rule_engine.py` and `csv_engine.py`) are simpler and less flexible, but they always work, don't cost anything, and don't depend on any outside service. This means the app still works even if the AI is turned off.

## When it refuses to answer

`rule_engine.py` builds SQL from fixed templates, so there are questions it simply cannot express — anything with a threshold ("more than 100000"), a ranking ("which department has the most"), a negation ("customers who never ordered"), a date range ("before March"), or a grouping ("per department").

It used to answer those anyway, by falling through to its "list everything" branch. Asking *"employees earning more than 100000"* returned all 18 employees, labelled "Lists all employees, sorted by name" — an answer that looks right and isn't.

Now it checks first (`unsupported_constraints`) and declines, and the page tells the user which part it couldn't handle and that an API key would answer it. If you add a phrase to a builder, add it to `RECOGNISED_PHRASES` too, or the gate will keep refusing questions the builder can now handle.

## Choosing between Gemini and Claude

You don't have to choose — set whichever key you have and the app works it out:

| What you set in `.env` | What runs |
|---|---|
| `GEMINI_API_KEY` | Gemini |
| `ANTHROPIC_API_KEY` | Claude |
| Both | Gemini (it's the default when there's a tie) |
| Both, plus `AI_PROVIDER=anthropic` | Claude — `AI_PROVIDER` always wins |
| Neither | The rule-based engines |

The safety check described above is the **same code for both providers**. Whichever model writes the query, it goes through one validator before anything is allowed to run — a provider is never trusted to have followed instructions.
