"""Static content for the /learn page: SQL concept cards and FAQ entries."""

CONCEPTS = [
    {
        "level": "Basic",
        "title": "SELECT — retrieving data",
        "explanation": "SELECT pulls columns out of a table. Name the columns you want, or use * for all of them.",
        "sql": "SELECT name, salary FROM employees;",
        "try_query": "employees",
    },
    {
        "level": "Basic",
        "title": "WHERE — filtering rows",
        "explanation": "WHERE narrows the result down to only the rows that match a condition.",
        "sql": "SELECT * FROM employees WHERE department_id = 1;",
        "try_query": "employees in the IT department",
    },
    {
        "level": "Basic",
        "title": "ORDER BY — sorting results",
        "explanation": "ORDER BY sorts the result set by a column, ascending (ASC) or descending (DESC).",
        "sql": "SELECT name, price\nFROM products\nORDER BY price DESC;",
        "try_query": "most expensive products",
    },
    {
        "level": "Basic",
        "title": "LIMIT — capping results",
        "explanation": "LIMIT caps how many rows come back — the standard way to answer a 'top 5' question.",
        "sql": "SELECT name, salary\nFROM employees\nORDER BY salary DESC\nLIMIT 5;",
        "try_query": "highest paid employees",
    },
    {
        "level": "Intermediate",
        "title": "Aggregate functions — COUNT, SUM, AVG",
        "explanation": "Aggregate functions collapse many rows into one summary value: how many, how much, or on average how much.",
        "sql": "SELECT COUNT(*) AS count FROM employees;",
        "try_query": "how many employees are there",
    },
    {
        "level": "Intermediate",
        "title": "GROUP BY — summarizing per group",
        "explanation": "GROUP BY buckets rows together (like 'per category') so an aggregate can run separately on each bucket.",
        # One table, no join: the point of this lesson is the bucketing. The
        # LEFT JOIN lesson below owns the departments example — the two used to
        # print the identical query under two different headings.
        "sql": (
            "SELECT category, COUNT(*) AS product_count\n"
            "FROM products\n"
            "GROUP BY category;"
        ),
        "try_query": "products by category",
    },
    {
        "level": "Intermediate",
        "title": "LIKE — pattern matching",
        "explanation": "LIKE searches inside text using % as a wildcard for 'anything here'. It's what powers most keyword search.",
        "sql": "SELECT * FROM products WHERE name LIKE '%Laptop%';",
        "try_query": "orders for Laptop Pro 15",
    },
    {
        "level": "Advanced",
        "title": "JOIN — combining tables",
        "explanation": "A JOIN lines up rows from two tables on a shared column, so you can pull matching data from both at once.",
        "sql": (
            "SELECT c.name, p.name, o.total_amount\n"
            "FROM orders o\n"
            "JOIN customers c ON o.customer_id = c.id\n"
            "JOIN products p ON o.product_id = p.id;"
        ),
        "try_query": "orders from Global Traders Ltd",
    },
    {
        "level": "Advanced",
        "title": "LEFT JOIN — keeping unmatched rows",
        "explanation": "LEFT JOIN keeps every row from the left table even without a match on the right — so departments with zero employees still show up.",
        "sql": (
            "SELECT d.name, COUNT(e.id) AS employee_count\n"
            "FROM departments d\n"
            "LEFT JOIN employees e ON e.department_id = d.id\n"
            "GROUP BY d.id;"
        ),
        "try_query": "list all departments",
    },
    {
        "level": "Advanced",
        "title": "Date functions — filtering by time",
        "explanation": "SQLite's strftime() extracts parts of a date — this is how 'this month' or 'last month' filters get built.",
        "sql": (
            "SELECT *\n"
            "FROM orders\n"
            "WHERE strftime('%Y-%m', order_date)\n"
            "    = strftime('%Y-%m', 'now');"
        ),
        "try_query": "orders this month",
    },
]

FAQS = [
    (
        "What is SQL?",
        "SQL (Structured Query Language) is the standard language for asking a relational database questions "
        "and telling it what to do — read, filter, combine and summarize data.",
    ),
    (
        "Is my search safe from SQL injection?",
        "Yes. Every value this assistant plugs into a query goes through a parameterized placeholder (?), never "
        "raw string concatenation — so typed input can never be interpreted as SQL code.",
    ),
    (
        "What's the difference between WHERE and HAVING?",
        "WHERE filters individual rows before any grouping happens. HAVING filters groups after GROUP BY has "
        "combined rows, e.g. 'departments with more than 5 employees'.",
    ),
    (
        "Why does the assistant sometimes say it doesn't understand?",
        "It's a rule-based engine — it looks for known keywords like 'employees', 'orders' or 'total'. If none "
        "appear, it can't tell which table you mean. Try one of the example chips for phrasing that works.",
    ),
    (
        "Can this be connected to a real company database?",
        "This demo runs on a local SQLite file. To point it at a production system, swap the connection in "
        "backend/database.py for your real database (e.g. PostgreSQL or MySQL) and match the table/column names "
        "used in backend/engines/rule_engine.py.",
    ),
    (
        "What does the % symbol mean in a query?",
        "It's a wildcard used with LIKE — '%chair%' matches any text containing 'chair', anywhere in the string.",
    ),
    (
        "Why do some results show one big number instead of a table?",
        "That happens when the question implies a summary, like 'total revenue' or 'how many employees'. The "
        "assistant runs an aggregate query (COUNT/SUM/AVG) instead of listing individual rows.",
    ),
]
