"""
db.py — data-access layer
Uses MySQL when it is reachable (auto-creates and seeds the database if empty).
Falls back to a local SQLite file so the project can always be demonstrated.

MySQL settings come from environment variables / .env (defaults suit XAMPP):
  DB_HOST=localhost  DB_PORT=3306  DB_USER=root  DB_PASSWORD=  DB_NAME=business_finance_db
Set FORCE_SQLITE=1 to skip MySQL.
"""
import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal

import seed

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "demo_data.db")
BACKEND = None          # "MySQL" or "SQLite"
NOTE = ""               # why the fallback was used (shown in the footer)
VERSION = 0             # bumped on every write so the analytics cache refreshes


def _mysql_cfg(with_db=True):
    cfg = dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "3306")),
               user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
               connection_timeout=3)
    if with_db:
        cfg["database"] = os.getenv("DB_NAME", seed.DB_NAME)
    return cfg


def _connect():
    if BACKEND == "MySQL":
        import mysql.connector
        return mysql.connector.connect(**_mysql_cfg())
    con = sqlite3.connect(SQLITE_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _clean(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.decode()
    return v


def query(sql, params=()):
    """Run a SELECT (written with %s placeholders) and return a list of dicts."""
    con = _connect()
    try:
        if BACKEND == "MySQL":
            cur = con.cursor(dictionary=True)
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        else:
            rows = [dict(r) for r in con.execute(sql.replace("%s", "?"), tuple(params)).fetchall()]
        return [{k: _clean(v) for k, v in r.items()} for r in rows]
    finally:
        con.close()


def execute(sql, params=()):
    """Run an INSERT/UPDATE/DELETE and return the last inserted id."""
    global VERSION
    con = _connect()
    try:
        if BACKEND == "MySQL":
            cur = con.cursor()
            cur.execute(sql, tuple(params))
        else:
            cur = con.execute(sql.replace("%s", "?"), tuple(params))
        con.commit()
        VERSION += 1
        return cur.lastrowid
    finally:
        con.close()


def _create_and_seed(con, mysql):
    cur = con.cursor()
    for t in seed.TABLES:
        ddl = seed.SCHEMA[t]
        if not mysql:
            ddl = ddl.replace("INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        cur.execute(ddl)
    try:                                            # upgrade databases created before the customer panel
        cur.execute("ALTER TABLE customers ADD COLUMN password VARCHAR(255)")
        con.commit()
    except Exception:
        pass
    cur.execute("SELECT COUNT(*) FROM products")
    if cur.fetchone()[0] == 0:
        print("[db] empty database - loading demo data ...")
        data = seed.generate()
        ph = "%s" if mysql else "?"
        for t in seed.TABLES:
            cols = seed.COLUMNS[t]
            sql = "INSERT INTO %s (%s) VALUES (%s)" % (t, ", ".join(cols), ", ".join([ph] * len(cols)))
            rows = data[t]
            for i in range(0, len(rows), 1000):
                cur.executemany(sql, rows[i:i + 1000])
        con.commit()
    cur.execute("UPDATE customers SET name = 'Aarav Sharma', email = '%s' "
                "WHERE customer_id = 1" % seed.DEMO_CUSTOMER[0])
    con.commit()
    cur.execute("SELECT password FROM customers WHERE customer_id = 1")
    row = cur.fetchone()
    if row and not row[0]:                          # customer login
        cur.execute("UPDATE customers SET password = '%s' WHERE customer_id = 1" % seed._hash(seed.DEMO_CUSTOMER[1]))
        con.commit()
    cur.close()


def init():
    """Pick the backend. Called once at start-up."""
    global BACKEND, NOTE
    if os.getenv("FORCE_SQLITE") != "1":
        try:
            import mysql.connector
            con = mysql.connector.connect(**_mysql_cfg(with_db=False))
            cur = con.cursor()
            name = os.getenv("DB_NAME", seed.DB_NAME)
            cur.execute("CREATE DATABASE IF NOT EXISTS `%s` CHARACTER SET utf8mb4" % name)
            cur.execute("USE `%s`" % name)
            cur.close()
            _create_and_seed(con, mysql=True)
            con.close()
            BACKEND = "MySQL"
            print("[db] connected to MySQL database '%s'" % name)
            return BACKEND
        except Exception as e:                      # MySQL missing / not running / bad login
            NOTE = "Connected to local database"
            print("[db] MySQL unavailable - using local database")
    else:
        NOTE = "FORCE_SQLITE=1"
    BACKEND = "SQLite"
    con = sqlite3.connect(SQLITE_PATH)
    _create_and_seed(con, mysql=False)
    con.close()
    return BACKEND
