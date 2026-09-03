# Query Assistant architecture

## Overview

Query Assistant is a server-rendered Flask application organized as an installable `src/` package. The application factory builds local, test, CI, and Vercel instances through one startup path. HTTP routes are grouped by feature, use-case orchestration lives in services, pure query behavior lives in the domain, application persistence lives in repositories, and external systems live in infrastructure.

## Final tree

`PROJECT_STRUCTURE.txt` is the complete generated file-by-file tree for external
handoff. Regenerate it with `python scripts/generate_structure.py`; CI checks it
with `python scripts/generate_structure.py --check` to prevent drift.

```text
sql-project/
├── api/index.py
├── src/query_assistant/
│   ├── app.py, config.py, extensions.py, exceptions.py
│   ├── web/
│   │   ├── blueprints/{main,auth,datasets,feedback,learning,sql_console}/
│   │   ├── templates/{main,auth,datasets,feedback,learning,sql_console,partials}/
│   │   ├── static/{css,js}/
│   │   ├── error_handlers.py, presentation.py, security.py
│   ├── services/{auth,dataset,feedback,greeting,query,sql_console}_service.py
│   ├── domain/query/{csv_engine,phrases,rule_engine}.py
│   ├── domain/validation/sql_guardrails.py
│   ├── repositories/{user_repository,feedback_repository}.py
│   ├── infrastructure/
│   │   ├── ai/providers.py
│   │   └── database/{connection,initialization}.py
│   │       └── connectors/{sqlite,postgresql}.py
│   ├── content/learning.py
│   └── utilities/{charts,csv_export}.py
├── instance/{.gitignore,uploads/.gitkeep}
├── tests/{unit,integration,security,deployment,end_to_end}/
├── docs/{architecture,screenshots}/
├── scripts/{check_architecture.py,verify_deployment.py}
├── run.py, vercel.json, pyproject.toml
└── project and community documentation
```

## Startup flow

`run.py` and `api/index.py` both import `query_assistant.create_app`; root `index.py`
exports the same WSGI object for Vercel's Flask framework discovery without a
path-rewriting rule. The factory loads `Config`, resolves writable paths, initializes
LoginManager, CSRFProtect, and Limiter, registers Blueprints and error/security handlers,
installs template filters, initializes the application database, and returns the app.

## Feature ownership

| Blueprint | URLs | Service/repository |
|---|---|---|
| `main` | `/`, `/export`, `/favicon.ico` | `query_service`, `user_repository` |
| `auth` | `/register`, `/login`, `/logout`, `/history` | `auth_service`, `user_repository` |
| `datasets` | `/upload`, `/dataset*`, `/connect-db*` | `dataset_service`, `query_service`, connectors |
| `feedback` | `/feedback`, `/feedback/all` | `feedback_service`, `feedback_repository` |
| `learning` | `/learn` | packaged learning content |
| `sql_console` | `/sql` | `sql_console_service` and shared SQL guardrails |

## Responsibility migration map

| Original | Responsibility | Destination | Action/reason | References updated |
|---|---|---|---|---|
| `backend/app.py` | App setup, routes, filters, security, orchestration | `app.py`, `extensions.py`, `web/`, `services/` | Split mixed responsibilities | entry points, templates, tests |
| `backend/auth.py` | User persistence and auth use cases | `repositories/user_repository.py`, `services/auth_service.py`, auth Blueprint | Split HTTP validation from persistence | loader, routes, tests |
| `backend/feedback.py` | Feedback persistence/admin policy | `repositories/feedback_repository.py`, `services/feedback_service.py` | Split submission use case from persistence | context processor, routes, tests |
| `backend/sql_console.py` | Source selection and guarded execution | `services/sql_console_service.py` | Move application use case out of web module | route and tests |
| `backend/engines/*` | Pure query interpretation plus provider integration | `domain/query/`, `domain/validation/`, `infrastructure/ai/` | Separate pure policy from external SDKs | services and tests |
| `backend/db.py`, `database.py` | DB adapter, schema, seed | `infrastructure/database/connection.py`, `initialization.py` | Clarify connection vs initialization | repositories, services, tests |
| `backend/connectors/*` | Attached DB implementations | `infrastructure/database/connectors/` | Isolate implementation details | services, tests |
| `frontend/` | Jinja and browser assets | `web/templates/`, `web/static/` | Package deployment-safe assets | factory and template references |
| `data/uploads/.gitkeep` | Runtime placeholder | `instance/uploads/.gitkeep` | Use Flask-style runtime location | config and ignore files |
| `project-handoff/` | Duplicated manual tree | this document | One authoritative architecture source | documentation |

## Runtime data

New local installations use `instance/company.db` and `instance/uploads/`. `DATA_DIR` remains supported unchanged. If an existing `data/company.db` is detected and `DATA_DIR` is unset, it is used automatically to prevent silent data loss. Vercel continues to set `DATA_DIR=/tmp/query-assistant`; durable serverless storage still requires `DATABASE_URL`.

## Testing strategy

- `unit/`: pure query and output behavior.
- `integration/`: Flask routes, databases, and mocked provider integration.
- `security/`: SQL restrictions, headers, rate limits, SSRF, and export safety.
- `deployment/`: Vercel, configuration, and documentation contracts.
- `end_to_end/`: complete user workflows.

Tests create a factory instance bound to a temporary database and keep AI credentials cleared. Architecture and deployment scripts supplement Ruff and pytest in CI.

## Adding a feature

Add its HTTP adapter under `web/blueprints/`, coordinate the use case in `services/`, place framework-free rules in `domain/`, persistence in `repositories/`, and external implementations in `infrastructure/`. Register the Blueprint centrally, use feature-scoped templates, add the narrowest appropriate test level, and run all checks documented in `CONTRIBUTING.md`.
