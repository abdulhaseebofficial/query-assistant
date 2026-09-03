# Tests

The suite is isolated from production data and AI credentials. Its factory fixture uses a temporary SQLite database, disables CSRF only for ordinary test clients, and clears provider keys so tests never make billable network calls.

```bash
python -m pytest
python -m pytest -v
python -m pytest tests/security/test_sql_guardrails.py
```

## Organization

- `unit/` contains framework-independent query, greeting, and chart behavior.
- `integration/database/` covers attached databases, dialect handling, and query cost.
- `integration/providers/` covers mocked AI-provider selection and failure behavior.
- `integration/routes/` covers Flask pages and persistence across requests.
- `security/` covers SQL restrictions, headers, rate limits, SSRF, identifiers, and export safety.
- `deployment/` covers configuration, Vercel cold starts, and documentation contracts.
- `end_to_end/` covers complete upload, query, account, and connected-database journeys.

Name tests as behavioral claims. Put a test at the lowest level that can prove the behavior without weakening its realism.
