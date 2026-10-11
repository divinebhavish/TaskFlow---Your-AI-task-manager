# Direct (non-LLM) access to the tasks table, used by the Board and Insights pages.
# All queries are parameterized so user input never gets spliced into SQL.

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "my_tasks.db"

STATUSES = ["pending", "in_progress", "completed"]
PRIORITIES = ["low", "medium", "high"]

STATUS_LABELS = {"pending": "Pending", "in_progress": "In progress", "completed": "Completed"}
STATUS_ICONS = {
    "pending": ":material/radio_button_unchecked:",
    "in_progress": ":material/progress_activity:",
    "completed": ":material/check_circle:",
}
STATUS_COLORS = {"pending": "orange", "in_progress": "blue", "completed": "green"}
PRIORITY_COLORS = {"low": "gray", "medium": "violet", "high": "red"}


def _connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    """Create the table and add the newer columns (priority, due_date) if missing."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT CHECK (status IN ('pending', 'in_progress', 'completed')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        if "priority" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'medium'")
            conn.execute("UPDATE tasks SET priority = 'medium' WHERE priority IS NULL")
        if "due_date" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN due_date DATE")
    renumber_ids()


def renumber_ids():
    """Keep task ids a gap-free 1..N sequence (oldest task = 1), so the numbers users see stay in order."""
    with _connect() as conn:
        ids = [row[0] for row in conn.execute("SELECT id FROM tasks ORDER BY id")]
        if ids != list(range(1, len(ids) + 1)):
            # Flip to negatives first so the new ids never collide with existing ones.
            conn.execute("UPDATE tasks SET id = -id")
            conn.executemany("UPDATE tasks SET id = ? WHERE id = ?", [(n, -old) for n, old in enumerate(ids, 1)])
        conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'tasks'", (len(ids),))


def load_tasks() -> pd.DataFrame:
    with _connect() as conn:
        df = pd.read_sql_query(
            "SELECT id, title, description, status, priority, due_date, created_at "
            "FROM tasks ORDER BY id",
            conn,
        )
    df["status"] = df["status"].fillna("pending")
    df["priority"] = df["priority"].fillna("medium")
    df["due_date"] = pd.to_datetime(df["due_date"], errors="coerce").dt.date
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    return df


def add_task(title, description="", status="pending", priority="medium", due_date=None):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO tasks (title, description, status, priority, due_date) VALUES (?, ?, ?, ?, ?)",
            (title, description or None, status, priority, _iso(due_date)),
        )


def update_task(task_id, **fields):
    allowed = {"title", "description", "status", "priority", "due_date"}
    fields = {k: (_iso(v) if k == "due_date" else v) for k, v in fields.items() if k in allowed}
    if not fields:
        return
    assignments = ", ".join(f"{column} = ?" for column in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", (*fields.values(), int(task_id)))


def delete_tasks(task_ids):
    with _connect() as conn:
        conn.executemany("DELETE FROM tasks WHERE id = ?", [(int(i),) for i in task_ids])
    renumber_ids()


def summary(df: pd.DataFrame) -> dict:
    today = date.today()
    open_tasks = df[df["status"] != "completed"]
    overdue = open_tasks["due_date"].apply(lambda d: d is not None and not pd.isna(d) and d < today)
    total = len(df)
    done = int((df["status"] == "completed").sum())
    return {
        "total": total,
        "pending": int((df["status"] == "pending").sum()),
        "in_progress": int((df["status"] == "in_progress").sum()),
        "completed": done,
        "overdue": int(overdue.sum()),
        "completion": done / total if total else 0.0,
    }


def _iso(value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
