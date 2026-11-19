"""Commit/rollback and close SQLite connections, including on Windows failures."""
from contextlib import contextmanager
import sqlite3


@contextmanager
def connection(path,uri=False):
    db=sqlite3.connect(path,timeout=5,uri=uri)
    db.row_factory=sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()
