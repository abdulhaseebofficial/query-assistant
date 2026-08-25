# frontend/

This folder holds **everything the browser actually sees and loads** — the web pages and their styling. There's no Python here, and no business logic — just HTML and CSS (plus a little bit of JavaScript for things like the dark-mode toggle and charts).

The backend (`backend/app.py`) fills these pages with real data before sending them to the browser.

## What's in this folder

### `templates/` — the web pages

These are `.html` files written using **Jinja2** (a templating language that comes with Flask). Think of each one as a normal HTML page, but with special `{{ }}` and `{% %}` markers where the backend can insert real data — for example, `{{ current_user.username }}` gets replaced with the logged-in user's actual name.

| File | Page |
|---|---|
| `index.html` | Home page — ask a question about the demo database. |
| `upload.html` | Upload your own CSV file. |
| `dataset.html` | Ask questions about your uploaded CSV. |
| `connect.html` | Connect an external SQLite file or PostgreSQL database. |
| `connect_table.html` | Ask questions about a table in a connected external database. |
| `learn.html` | The "Learn SQL" lessons and FAQ page. |
| `login.html` / `register.html` | Sign in / create an account. |
| `history.html` | A logged-in user's past questions. |

**`templates/partials/`** holds small pieces of HTML that get reused across several pages, instead of being copy-pasted into each one:
- `_nav.html` — the top navigation bar (logo, links, login/logout, dark-mode switch).
- `_chart.html` — the code that draws a chart from a query's results.

### `static/css/` — the styling

Plain CSS files, no build step or framework needed.

- `style.css` — styling for every page except the Learn SQL page.
- `learn.css` — styling just for the Learn SQL page.

## How a page gets built

1. Someone visits a URL, like `/`.
2. `backend/app.py` runs the matching route, gets the data it needs, and calls `render_template("index.html", ...)`.
3. Flask fills in `index.html`'s `{{ }}` placeholders with that data and sends the finished HTML to the browser.

For the full picture of how the backend and frontend fit together, see the [README.md](../README.md) in the project root.
