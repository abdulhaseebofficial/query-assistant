# backend/engines/

An **engine** here just means: code that reads a question typed in plain English (or Roman Urdu) and turns it into an SQL query.

There are three engines, and they're tried in order until one of them can answer the question.

## What's in this folder

| File | What it does |
|---|---|
| `ai_engine.py` | Tried **first**. Sends the question to Claude (Anthropic's AI) and asks it to write the SQL. Only works if an `ANTHROPIC_API_KEY` is set up — otherwise it's skipped automatically. Before running anything the AI writes, it double-checks the SQL is safe: it must be a single read-only `SELECT`, and it's only allowed to look at specific tables (so it can never peek at things like saved passwords). |
| `rule_engine.py` | Used for the **built-in demo database** (departments, employees, products, customers, orders) when the AI engine isn't available. It works by looking for keywords in the question — like "employees", "highest paid", or "kitne" (Urdu for "how many") — and building the matching SQL query from a fixed template. |
| `csv_engine.py` | Handles CSV files that a user uploads. It reads the file, figures out each column's data type, saves it as a table, and — like `rule_engine.py` — can build a simple keyword-search query if the AI engine isn't available. |

## Why two ways of answering the same question?

The AI engine is smarter and more flexible, but it needs an internet connection and an API key. The rule-based engines (`rule_engine.py` and `csv_engine.py`) are simpler and less flexible, but they always work, don't cost anything, and don't depend on any outside service. This means the app still works even if the AI is turned off.
