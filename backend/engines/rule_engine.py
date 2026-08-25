"""Keyword-based English/Roman-Urdu -> SQL translator for the built-in demo
schema. This is the fallback engine used when the AI engine is unavailable
or fails, so every query it builds is a fixed, hand-written SQL template with
only the filter values parameterized — there's no user input in the SQL
structure itself, which makes this engine inherently injection-safe.
"""

import re

EMPLOYEE_WORDS = {
    "employee", "employees", "staff", "worker", "workers", "mulazim", "karyakar",
    "salary", "salaries", "paid", "hired", "position",
}
DEPARTMENT_WORDS = {"department", "departments", "dept", "depts"}
PRODUCT_WORDS = {"product", "products", "item", "items", "inventory", "stock"}
CUSTOMER_WORDS = {"customer", "customers", "client", "clients"}
ORDER_WORDS = {"order", "orders", "sale", "sales", "revenue", "purchase", "purchases", "transaction", "transactions"}

COUNT_PHRASES = ("how many", "count", "kitne", "kitni", "number of")
SUM_PHRASES = ("total", "sum", "kul", "revenue")
AVG_PHRASES = ("average", "avg", "mean", "ausat")

STATUS_WORDS = {
    "completed": "Completed", "complete": "Completed",
    "pending": "Pending",
    "cancelled": "Cancelled", "canceled": "Cancelled",
}

# Every phrase the builders below actually encode into SQL. Kept as one list so
# `unsupported_constraints` can subtract it from a question and look at what's left.
RECOGNISED_PHRASES = (
    COUNT_PHRASES
    + SUM_PHRASES
    + AVG_PHRASES
    + tuple(STATUS_WORDS)
    # build_employees_query
    + ("highest paid", "top paid", "best paid", "most paid", "newest", "recently hired", "new joiners", "recent hires")
    # build_products_query
    + ("low stock", "low on stock", "low in stock", "out of stock", "running low", "kam stock")
    + ("most expensive", "least expensive", "expensive", "costly", "priciest", "cheap", "affordable", "budget")
    # build_orders_query
    + ("today", "this month", "current month", "last month", "previous month", "this year", "current year")
)

# A question can name a constraint these fixed templates have no way to express —
# a threshold, a ranking, a negation, a date range. Before this check existed the
# builders quietly fell through to their catch-all branch, so "employees earning
# more than 100000" returned *every* employee under the explanation "Lists all
# employees, sorted by name". A confidently wrong answer is worse than no answer,
# so `interpret` now declines and lets the caller say so.
UNSUPPORTED_PATTERNS = (
    (r"\d", "a specific number"),
    (r"\b(more|greater|higher|larger|older|newer|bigger)\s+than\b", "a comparison"),
    (r"\b(less|fewer|lower|smaller|cheaper)\s+than\b", "a comparison"),
    (r"\b(over|under|above|below|at least|at most|minimum|maximum|between)\b", "a comparison"),
    (r"\b(zyada|ziada)\b", "a comparison"),
    (r"\b(most|least|top|bottom|highest|lowest|biggest|largest|smallest|best|worst|rank)\b", "a ranking"),
    (r"\b(never|without|none|not|no)\b", "a negation"),
    (r"\b(nahi|bina)\b", "a negation"),
    (r"\b(haven'?t|hasn'?t|didn'?t|don'?t|doesn'?t)\b", "a negation"),
    (r"\b(per|each|group(ed)? by|breakdown|grouped)\b", "a grouping"),
    (r"\b(before|after|since|during|last year|yesterday|older|since)\b", "a date range"),
    (
        r"\b(january|february|march|april|june|july|august|september|october|november|december)\b",
        "a date range",
    ),
    (r"\b(who|which|whose|that)\s+\w*\s*(ordered|bought|purchased|placed|joined)\b", "a link between tables"),
)


def _without_recognised_phrases(text):
    """Strip the phrases the templates do encode, leaving only what they don't.

    Longest first, so "most expensive" is consumed before the bare "most" in
    UNSUPPORTED_PATTERNS can match it.
    """
    for phrase in sorted(RECOGNISED_PHRASES, key=len, reverse=True):
        text = text.replace(phrase, " ")
    return text


def unsupported_constraints(text):
    """Names of the constraints in `text` that no template can express.

    Empty means the rule engine can answer honestly; anything else means it would
    be guessing.
    """
    residue = _without_recognised_phrases(text)
    found = []
    for pattern, label in UNSUPPORTED_PATTERNS:
        if re.search(pattern, residue) and label not in found:
            found.append(label)
    return found


def word_in(word, text):
    return re.search(r"\b" + re.escape(word.lower()) + r"\b", text) is not None


def any_word_in(words, text):
    return any(word_in(w, text) for w in words)


def get_reference_data(conn):
    departments = [r[0] for r in conn.execute("SELECT name FROM departments").fetchall()]
    categories = [r[0] for r in conn.execute("SELECT DISTINCT category FROM products").fetchall()]
    cities = [r[0] for r in conn.execute("SELECT DISTINCT city FROM customers").fetchall()]
    product_names = [r[0] for r in conn.execute("SELECT name FROM products").fetchall()]
    customer_names = [r[0] for r in conn.execute("SELECT name FROM customers").fetchall()]
    return {
        "departments": departments,
        "categories": categories,
        "cities": cities,
        "product_names": product_names,
        "customer_names": customer_names,
    }


def detect_domain(text):
    checks = [
        ("employees", EMPLOYEE_WORDS),
        ("departments", DEPARTMENT_WORDS),
        ("customers", CUSTOMER_WORDS),
        ("products", PRODUCT_WORDS),
        ("orders", ORDER_WORDS),
    ]
    for domain, words in checks:
        if any_word_in(words, text):
            return domain
    return None


def detect_aggregate(text):
    if any_word_in(COUNT_PHRASES, text):
        return "count"
    if any_word_in(SUM_PHRASES, text):
        return "sum"
    if any_word_in(AVG_PHRASES, text):
        return "avg"
    return None


def find_match(options, text):
    for option in options:
        opt_lower = option.lower()
        if len(option) <= 3:
            # Short abbreviations (e.g. "IT", "HR") collide with common English
            # words ("it", "hr"), so only match with a disambiguating cue nearby.
            if not word_in(opt_lower, text):
                continue
            has_context = any_word_in(DEPARTMENT_WORDS, text) or re.search(
                r"\bin\s+(the\s+)?" + re.escape(opt_lower) + r"\b", text
            )
            if has_context:
                return option
        elif opt_lower in text:
            return option
    return None


def build_employees_query(text, aggregate, ref):
    department = find_match(ref["departments"], text)
    top_paid = any(p in text for p in ("highest paid", "top paid", "best paid", "most paid"))
    newest = any(p in text for p in ("newest", "recently hired", "new joiners", "recent hires"))

    where_sql = ""
    params = []
    explanation_filter = ""
    if department:
        where_sql = " WHERE d.name = ?"
        params.append(department)
        explanation_filter = f" in the {department} department"

    if aggregate == "count":
        sql = f"SELECT COUNT(*) AS count FROM employees e JOIN departments d ON e.department_id = d.id{where_sql};"
        explanation = f"Counts how many employees work{explanation_filter or ' at the company'}."
    elif aggregate == "sum" and "salary" in text:
        sql = f"SELECT SUM(e.salary) AS total FROM employees e JOIN departments d ON e.department_id = d.id{where_sql};"
        explanation = f"Adds up the total salary of employees{explanation_filter or ' at the company'}."
    elif aggregate == "avg" and "salary" in text:
        sql = (
            "SELECT AVG(e.salary) AS average FROM employees e "
            f"JOIN departments d ON e.department_id = d.id{where_sql};"
        )
        explanation = f"Calculates the average salary of employees{explanation_filter or ' at the company'}."
    else:
        order_sql = " ORDER BY e.name"
        limit_sql = ""
        if top_paid:
            order_sql = " ORDER BY e.salary DESC"
            limit_sql = " LIMIT 5"
            explanation = f"Lists the 5 highest-paid employees{explanation_filter}."
        elif newest:
            order_sql = " ORDER BY e.hire_date DESC"
            limit_sql = " LIMIT 5"
            explanation = f"Lists the 5 most recently hired employees{explanation_filter}."
        else:
            explanation = f"Lists all employees{explanation_filter or ''}, sorted by name."

        sql = (
            "SELECT e.name, d.name AS department, e.position, e.salary, e.email, e.hire_date "
            f"FROM employees e JOIN departments d ON e.department_id = d.id{where_sql}{order_sql}{limit_sql};"
        )

    return sql, params, explanation


def build_departments_query(text, aggregate, ref):
    sql = (
        "SELECT d.name, d.location, d.manager_name, COUNT(e.id) AS employee_count "
        "FROM departments d LEFT JOIN employees e ON e.department_id = d.id "
        "GROUP BY d.id ORDER BY d.name;"
    )
    explanation = "Lists every department along with its location, manager and how many employees work there."
    return sql, [], explanation


def build_products_query(text, aggregate, ref):
    category = find_match(ref["categories"], text)
    low_stock = any(
        p in text for p in ("low stock", "low on stock", "low in stock", "out of stock", "running low", "kam stock")
    )
    expensive = any(p in text for p in ("expensive", "costly", "most expensive", "priciest"))
    cheap = any(p in text for p in ("cheap", "affordable", "budget", "least expensive"))

    where_sql = ""
    params = []
    explanation_filter = ""
    if category:
        where_sql = " WHERE category = ?"
        params.append(category)
        explanation_filter = f" in the {category} category"
    elif low_stock:
        where_sql = " WHERE stock_quantity < 10"
        explanation_filter = " that are running low on stock (fewer than 10 left)"

    if aggregate == "count":
        sql = f"SELECT COUNT(*) AS count FROM products{where_sql};"
        explanation = f"Counts how many products{explanation_filter or ' are in the catalog'}."
    elif aggregate == "sum" and "stock" in text:
        sql = f"SELECT SUM(stock_quantity) AS total FROM products{where_sql};"
        explanation = f"Adds up the total stock quantity of products{explanation_filter or ''}."
    elif aggregate == "avg" and "price" in text:
        sql = f"SELECT AVG(price) AS average FROM products{where_sql};"
        explanation = f"Calculates the average price of products{explanation_filter or ''}."
    else:
        order_sql = " ORDER BY name"
        limit_sql = ""
        if expensive:
            order_sql = " ORDER BY price DESC"
            limit_sql = " LIMIT 5"
            explanation = "Lists the 5 most expensive products."
        elif cheap:
            order_sql = " ORDER BY price ASC"
            limit_sql = " LIMIT 5"
            explanation = "Lists the 5 cheapest products."
        else:
            explanation = f"Lists all products{explanation_filter or ''}, sorted by name."

        sql = f"SELECT name, category, price, stock_quantity FROM products{where_sql}{order_sql}{limit_sql};"

    return sql, params, explanation


def build_customers_query(text, aggregate, ref):
    city = find_match(ref["cities"], text)

    where_sql = ""
    params = []
    explanation_filter = ""
    if city:
        where_sql = " WHERE city = ?"
        params.append(city)
        explanation_filter = f" based in {city}"

    if aggregate == "count":
        sql = f"SELECT COUNT(*) AS count FROM customers{where_sql};"
        explanation = f"Counts how many customers{explanation_filter or ' the company has'}."
    else:
        explanation = f"Lists all customers{explanation_filter or ''}, sorted by name."
        sql = f"SELECT name, email, city, phone FROM customers{where_sql} ORDER BY name;"

    return sql, params, explanation


def build_orders_query(text, aggregate, ref):
    status = None
    for word, canonical in STATUS_WORDS.items():
        if word_in(word, text):
            status = canonical
            break

    date_filter = None
    if "today" in text:
        date_filter = "today"
    elif "this month" in text or "current month" in text:
        date_filter = "this_month"
    elif "last month" in text or "previous month" in text:
        date_filter = "last_month"
    elif "this year" in text or "current year" in text:
        date_filter = "this_year"

    customer = find_match(ref["customer_names"], text)
    product = find_match(ref["product_names"], text)

    conditions = []
    params = []
    explanation_parts = []

    if status:
        conditions.append("o.status = ?")
        params.append(status)
        explanation_parts.append(f"with status {status}")

    if date_filter == "today":
        conditions.append("DATE(o.order_date) = DATE('now')")
        explanation_parts.append("placed today")
    elif date_filter == "this_month":
        conditions.append("strftime('%Y-%m', o.order_date) = strftime('%Y-%m', 'now')")
        explanation_parts.append("placed this month")
    elif date_filter == "last_month":
        conditions.append("strftime('%Y-%m', o.order_date) = strftime('%Y-%m', 'now', '-1 month')")
        explanation_parts.append("placed last month")
    elif date_filter == "this_year":
        conditions.append("strftime('%Y', o.order_date) = strftime('%Y', 'now')")
        explanation_parts.append("placed this year")

    if customer:
        conditions.append("c.name = ?")
        params.append(customer)
        explanation_parts.append(f"from {customer}")

    if product:
        conditions.append("p.name = ?")
        params.append(product)
        explanation_parts.append(f"for {product}")

    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    explanation_filter = (" " + ", ".join(explanation_parts)) if explanation_parts else ""

    base_from = (
        "FROM orders o "
        "JOIN customers c ON o.customer_id = c.id "
        "JOIN products p ON o.product_id = p.id"
    )

    if aggregate == "count":
        sql = f"SELECT COUNT(*) AS count {base_from}{where_sql};"
        explanation = f"Counts how many orders were placed{explanation_filter or ''}."
    elif aggregate == "sum":
        sql = f"SELECT SUM(o.total_amount) AS total {base_from}{where_sql};"
        explanation = f"Adds up the total revenue from orders{explanation_filter or ''}."
    elif aggregate == "avg":
        sql = f"SELECT AVG(o.total_amount) AS average {base_from}{where_sql};"
        explanation = f"Calculates the average order value{explanation_filter or ''}."
    else:
        sql = (
            "SELECT c.name AS customer, p.name AS product, o.quantity, o.order_date, "
            f"o.total_amount, o.status {base_from}{where_sql} ORDER BY o.order_date DESC;"
        )
        explanation = f"Lists orders{explanation_filter or ''}, most recent first."

    return sql, params, explanation


DOMAIN_BUILDERS = {
    "employees": build_employees_query,
    "departments": build_departments_query,
    "products": build_products_query,
    "customers": build_customers_query,
    "orders": build_orders_query,
}


def interpret(user_input, conn):
    """Build SQL for `user_input`, or return None when that can't be done honestly.

    None has two causes, and the caller is told which via `unsupported_constraints`:
    the question isn't about this schema at all, or it is but asks for something
    these fixed templates can't express.
    """
    text = user_input.strip().lower()
    domain = detect_domain(text)
    if domain is None:
        return None

    # Refuse before building. Every builder ends in a catch-all "list everything"
    # branch, so without this the answer to an unsupported question is a full table
    # dump wearing an explanation that describes a question nobody asked.
    if unsupported_constraints(text):
        return None

    aggregate = detect_aggregate(text)
    ref = get_reference_data(conn)
    sql, params, explanation = DOMAIN_BUILDERS[domain](text, aggregate, ref)
    return {
        "domain": domain,
        "aggregate": aggregate,
        "sql": sql,
        "params": params,
        "explanation": explanation,
    }
