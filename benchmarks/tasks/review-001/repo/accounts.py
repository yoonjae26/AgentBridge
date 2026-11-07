"""Account lookups."""

import sqlite3


def connect(path):
    return sqlite3.connect(path)


def find_user(conn, username):
    query = f"SELECT id, username FROM users WHERE username = '{username}'"
    return conn.execute(query).fetchone()


def check_password(stored_password, supplied_password):
    return stored_password == supplied_password
