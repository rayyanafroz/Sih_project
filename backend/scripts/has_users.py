"""Exit 0 if the database has been seeded (at least one user exists), 1 otherwise.

Used by run.sh to decide whether the demo data needs to be created.
Usage (from backend/):  .venv/bin/python -m scripts.has_users
"""
import sys

from sqlalchemy import inspect, text

from app.db import engine


def seeded() -> bool:
    try:
        if not inspect(engine).has_table("users"):
            return False
        with engine.connect() as conn:
            return bool(conn.execute(text("SELECT COUNT(*) FROM users")).scalar())
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(0 if seeded() else 1)
