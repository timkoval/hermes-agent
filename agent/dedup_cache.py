"""Cross-session file-read deduplication cache.

When a file hasn't changed since it was last read by the agent, return a
lightweight ``[cached]`` stub instead of re-sending the full content.
Cache is scoped to a workspace directory and survives /new + profile switches.
"""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FileDedupCache:
    """SQLite-backed cache keyed on (path, mtime_ns, size)."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._local = threading.local()

    def _conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self._db_path))
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute(
                "CREATE TABLE IF NOT EXISTS file_cache ("
                "  path TEXT NOT NULL,"
                "  mtime_ns INTEGER NOT NULL,"
                "  size INTEGER NOT NULL,"
                "  session_id TEXT,"
                "  cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  PRIMARY KEY (path)"
                ")"
            )
        return self._local.conn

    def check(self, path: Path) -> Optional[str]:
        """Return a ``[cached]`` stub if file is unchanged, or None."""
        try:
            st = path.stat()
        except (OSError, IOError):
            return None

        key = (str(path.resolve()), st.st_mtime_ns, st.st_size)
        row = self._conn().execute(
            "SELECT session_id FROM file_cache WHERE path = ? AND mtime_ns = ? AND size = ?",
            key,
        ).fetchone()

        if row:
            return (
                f"[cached] {path} — same as session {row[0][:12]}, "
                f"{st.st_size:,} bytes, no changes. Use read_file with offset "
                f"to re-read specific sections."
            )
        return None

    def store(self, path: Path, session_id: str) -> None:
        """Record that *path* was read in *session_id*."""
        try:
            st = path.stat()
        except (OSError, IOError):
            return
        self._conn().execute(
            "INSERT OR REPLACE INTO file_cache (path, mtime_ns, size, session_id) "
            "VALUES (?, ?, ?, ?)",
            (str(path.resolve()), st.st_mtime_ns, st.st_size, session_id),
        )
        self._conn().commit()

    def invalidate(self, path: str) -> None:
        """Remove a path from the cache (e.g., after file modification)."""
        self._conn().execute(
            "DELETE FROM file_cache WHERE path = ?",
            (str(Path(path).resolve()),),
        )
        self._conn().commit()

    def prune(self, max_entries: int = 10000) -> int:
        """Drop oldest entries if cache exceeds *max_entries*. Returns count removed."""
        count = self._conn().execute("SELECT COUNT(*) FROM file_cache").fetchone()[0]
        if count > max_entries:
            self._conn().execute(
                "DELETE FROM file_cache WHERE rowid IN ("
                "  SELECT rowid FROM file_cache ORDER BY cached_at ASC LIMIT ?"
                ")",
                (count - max_entries,),
            )
            removed = self._conn().execute("SELECT changes()").fetchone()[0]
            self._conn().commit()
            return removed
        return 0
