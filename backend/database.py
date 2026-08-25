"""Schema and seed data for the built-in demo database (data/company.db).

init_db() is idempotent — it creates tables if missing and only inserts the
sample rows the first time (when `departments` is empty), so it's safe to
call on every app startup.
"""

import sqlite3
from datetime import date, timedelta

from backend.config import DB_PATH

DB_NAME = DB_PATH

DEPARTMENTS = [
    ("IT", "Karachi", "Ali Raza"),
    ("Sales", "Lahore", "Sana Malik"),
    ("HR", "Karachi", "Bilal Ahmed"),
    ("Marketing", "Islamabad", "Ayesha Khan"),
    ("Finance", "Lahore", "Usman Tariq"),
]

# (name, department_name, position, salary, email, hire_date)
EMPLOYEES = [
    ("Ahmed Raza", "IT", "Software Engineer", 120000, "ahmed.raza@company.com", "2022-03-15"),
    ("Fatima Sheikh", "IT", "Senior Developer", 145000, "fatima.sheikh@company.com", "2020-06-01"),
    ("Hassan Ali", "IT", "QA Engineer", 95000, "hassan.ali@company.com", "2023-01-10"),
    ("Zainab Malik", "Sales", "Sales Executive", 80000, "zainab.malik@company.com", "2021-09-20"),
    ("Omar Farooq", "Sales", "Sales Manager", 130000, "omar.farooq@company.com", "2019-04-12"),
    ("Ayesha Siddiqui", "Sales", "Sales Executive", 78000, "ayesha.siddiqui@company.com", "2022-11-05"),
    ("Bilal Hussain", "HR", "HR Executive", 75000, "bilal.hussain@company.com", "2021-02-18"),
    ("Sana Tariq", "HR", "HR Manager", 110000, "sana.tariq@company.com", "2018-07-22"),
    ("Usman Khalid", "Marketing", "Marketing Executive", 82000, "usman.khalid@company.com", "2022-05-30"),
    ("Mariam Yousuf", "Marketing", "Marketing Manager", 125000, "mariam.yousuf@company.com", "2020-01-14"),
    ("Kamran Iqbal", "Finance", "Accountant", 90000, "kamran.iqbal@company.com", "2021-08-09"),
    ("Nida Ashraf", "Finance", "Finance Manager", 135000, "nida.ashraf@company.com", "2019-12-01"),
    ("Farhan Sheikh", "IT", "DevOps Engineer", 128000, "farhan.sheikh@company.com", "2023-04-25"),
    ("Hira Nadeem", "Sales", "Sales Executive", 79000, "hira.nadeem@company.com", "2023-06-15"),
    ("Talha Rasheed", "HR", "Recruiter", 70000, "talha.rasheed@company.com", "2022-09-01"),
    ("Iqra Basit", "Marketing", "Content Strategist", 76000, "iqra.basit@company.com", "2023-02-20"),
    ("Danish Aslam", "Finance", "Financial Analyst", 88000, "danish.aslam@company.com", "2022-07-11"),
    ("Sara Naveed", "IT", "Product Manager", 140000, "sara.naveed@company.com", "2020-10-03"),
]

# (name, category, price, stock_quantity)
PRODUCTS = [
    ("Laptop Pro 15", "Electronics", 1200.00, 25),
    ("Wireless Mouse", "Electronics", 25.00, 200),
    ("Office Chair", "Furniture", 150.00, 40),
    ("Standing Desk", "Furniture", 350.00, 15),
    ("Notebook Pack", "Stationery", 8.00, 500),
    ("Pen Set", "Stationery", 5.00, 800),
    ("Accounting Software License", "Software", 299.00, 60),
    ("CRM Software License", "Software", 499.00, 45),
    ("27-inch Monitor", "Electronics", 320.00, 30),
    ("Mechanical Keyboard", "Electronics", 85.00, 5),
    ("Filing Cabinet", "Furniture", 180.00, 3),
    ("Whiteboard", "Stationery", 45.00, 20),
]

# (name, email, city, phone)
CUSTOMERS = [
    ("Global Traders Ltd", "contact@globaltraders.com", "Karachi", "021-1112233"),
    ("Bright Future Enterprises", "info@brightfuture.com", "Lahore", "042-2223344"),
    ("Nexus Solutions", "hello@nexussolutions.com", "Islamabad", "051-3334455"),
    ("Prime Retail Co", "sales@primeretail.com", "Karachi", "021-4445566"),
    ("Silver Line Traders", "contact@silverline.com", "Lahore", "042-5556677"),
    ("Horizon Group", "info@horizongroup.com", "Faisalabad", "041-6667788"),
    ("Metro Distributors", "metro@distrib.com", "Karachi", "021-7778899"),
    ("Alpha Corp", "alpha@corp.com", "Islamabad", "051-8889900"),
    ("Blue Ocean Traders", "blueocean@traders.com", "Lahore", "042-9990011"),
    ("City Mart", "citymart@mail.com", "Multan", "061-1231234"),
]

# (customer_index, product_index, quantity, days_ago, status) — 1-based indexes into CUSTOMERS/PRODUCTS
ORDERS = [
    (1, 1, 2, 3, "Completed"),
    (2, 9, 5, 10, "Completed"),
    (3, 7, 3, 15, "Pending"),
    (4, 3, 10, 20, "Completed"),
    (5, 2, 20, 25, "Completed"),
    (6, 8, 2, 35, "Completed"),
    (7, 4, 4, 40, "Pending"),
    (8, 1, 1, 45, "Completed"),
    (9, 6, 50, 50, "Cancelled"),
    (10, 5, 30, 55, "Completed"),
    (1, 9, 3, 65, "Completed"),
    (2, 3, 6, 70, "Completed"),
    (3, 10, 8, 75, "Pending"),
    (4, 12, 15, 80, "Completed"),
    (5, 7, 4, 85, "Completed"),
    (6, 1, 1, 95, "Completed"),
    (7, 2, 15, 100, "Completed"),
    (8, 11, 2, 105, "Pending"),
    (9, 4, 3, 110, "Completed"),
    (10, 8, 1, 115, "Cancelled"),
    (1, 5, 40, 5, "Completed"),
    (3, 6, 60, 8, "Completed"),
    (6, 9, 2, 33, "Pending"),
    (8, 2, 10, 2, "Completed"),
    (2, 1, 1, 0, "Completed"),
]


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            manager_name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department_id INTEGER NOT NULL REFERENCES departments(id),
            position TEXT NOT NULL,
            salary INTEGER NOT NULL,
            email TEXT NOT NULL,
            hire_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            stock_quantity INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            city TEXT NOT NULL,
            phone TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL,
            order_date TEXT NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS query_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            source TEXT NOT NULL,
            query_text TEXT NOT NULL,
            sql_text TEXT NOT NULL,
            engine TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("SELECT COUNT(*) FROM departments")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO departments (name, location, manager_name) VALUES (?, ?, ?)",
            DEPARTMENTS,
        )

        dept_ids = {name: i + 1 for i, (name, _, _) in enumerate(DEPARTMENTS)}
        employee_rows = [
            (name, dept_ids[dept], position, salary, email, hire_date)
            for name, dept, position, salary, email, hire_date in EMPLOYEES
        ]
        cur.executemany(
            "INSERT INTO employees (name, department_id, position, salary, email, hire_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            employee_rows,
        )

        cur.executemany(
            "INSERT INTO products (name, category, price, stock_quantity) VALUES (?, ?, ?, ?)",
            PRODUCTS,
        )

        cur.executemany(
            "INSERT INTO customers (name, email, city, phone) VALUES (?, ?, ?, ?)",
            CUSTOMERS,
        )

        today = date.today()
        product_prices = {i + 1: p[2] for i, p in enumerate(PRODUCTS)}
        order_rows = []
        for customer_idx, product_idx, qty, days_ago, status in ORDERS:
            order_date = (today - timedelta(days=days_ago)).isoformat()
            total_amount = round(qty * product_prices[product_idx], 2)
            order_rows.append((customer_idx, product_idx, qty, order_date, total_amount, status))

        cur.executemany(
            "INSERT INTO orders (customer_id, product_id, quantity, order_date, total_amount, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            order_rows,
        )

    conn.commit()
    conn.close()
