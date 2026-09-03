"""Uploaded-dataset use cases."""

from query_assistant.domain.query.csv_engine import clear_dataset, get_dataset_info, load_csv
from query_assistant.services.query_service import get_connection, run_table


def get_current_dataset():
    conn = get_connection()
    try:
        return get_dataset_info(conn)
    finally:
        conn.close()


def upload_dataset(stream, name):
    conn = get_connection()
    try:
        return load_csv(stream, conn, name)
    finally:
        conn.close()


def remove_dataset():
    conn = get_connection()
    try:
        clear_dataset(conn)
    finally:
        conn.close()


def query_dataset(question, meta):
    return run_table(question, {**meta, "name": "custom_data"})
