"""
Storage layer — SQLite persistence for portfolio, signals, learning, and reports.
"""
import sqlite3
import json
import os
from datetime import datetime
from agent.config import DB_PATH


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS weekly_state (
            week_id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            phase TEXT NOT NULL,
            data JSON NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id INTEGER NOT NULL,
            allocation JSON NOT NULL,
            regime TEXT NOT NULL,
            rationale TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id INTEGER NOT NULL,
            weekly_return REAL,
            cumulative_return REAL,
            sharpe REAL,
            sortino REAL,
            max_drawdown REAL,
            volatility REAL,
            benchmark_spy REAL,
            benchmark_ew REAL,
            benchmark_rp REAL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS signal_weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id INTEGER NOT NULL,
            weights JSON NOT NULL,
            confidence JSON NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS learning_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id INTEGER NOT NULL,
            errors JSON,
            improvements JSON,
            prediction_vs_actual JSON,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS price_cache (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (ticker, date)
        );
    """)
    conn.commit()
    conn.close()


def get_current_week_id():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT MAX(week_id) FROM weekly_state")
    row = c.fetchone()
    conn.close()
    return row[0] if row[0] else 0


def save_weekly_state(phase, data, week_start=None):
    conn = get_connection()
    c = conn.cursor()
    if week_start is None:
        week_start = datetime.now().strftime("%Y-%m-%d")
    week_id = get_current_week_id()
    if phase == "scan":
        week_id += 1
    c.execute(
        "INSERT INTO weekly_state (week_id, week_start, phase, data) VALUES (?, ?, ?, ?)",
        (week_id, week_start, phase, json.dumps(data))
    )
    conn.commit()
    conn.close()
    return week_id


def save_portfolio(week_id, allocation, regime, rationale=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO portfolios (week_id, allocation, regime, rationale) VALUES (?, ?, ?, ?)",
        (week_id, json.dumps(allocation), regime, rationale)
    )
    conn.commit()
    conn.close()


def save_performance(week_id, metrics):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO performance (week_id, weekly_return, cumulative_return, sharpe,
            sortino, max_drawdown, volatility, benchmark_spy, benchmark_ew, benchmark_rp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        week_id, metrics.get("weekly_return"), metrics.get("cumulative_return"),
        metrics.get("sharpe"), metrics.get("sortino"), metrics.get("max_drawdown"),
        metrics.get("volatility"), metrics.get("benchmark_spy"),
        metrics.get("benchmark_ew"), metrics.get("benchmark_rp")
    ))
    conn.commit()
    conn.close()


def save_signal_weights(week_id, weights, confidence):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO signal_weights (week_id, weights, confidence) VALUES (?, ?, ?)",
        (week_id, json.dumps(weights), json.dumps(confidence))
    )
    conn.commit()
    conn.close()


def save_learning_log(week_id, errors, improvements, pred_vs_actual):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO learning_log (week_id, errors, improvements, prediction_vs_actual) VALUES (?, ?, ?, ?)",
        (week_id, json.dumps(errors), json.dumps(improvements), json.dumps(pred_vs_actual))
    )
    conn.commit()
    conn.close()


def get_latest_portfolio():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM portfolios ORDER BY week_id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        return {"week_id": row["week_id"], "allocation": json.loads(row["allocation"]),
                "regime": row["regime"], "rationale": row["rationale"]}
    return None


def get_latest_signal_weights():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM signal_weights ORDER BY week_id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        return {"weights": json.loads(row["weights"]), "confidence": json.loads(row["confidence"])}
    return None


def get_all_performance():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM performance ORDER BY week_id ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_portfolios():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM portfolios ORDER BY week_id ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_weekly_state(week_id, phase=None):
    conn = get_connection()
    c = conn.cursor()
    if phase:
        c.execute("SELECT * FROM weekly_state WHERE week_id=? AND phase=?", (week_id, phase))
    else:
        c.execute("SELECT * FROM weekly_state WHERE week_id=? ORDER BY created_at DESC LIMIT 1", (week_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"week_id": row["week_id"], "phase": row["phase"], "data": json.loads(row["data"])}
    return None


def get_all_learning_logs():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM learning_log ORDER BY week_id ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]
