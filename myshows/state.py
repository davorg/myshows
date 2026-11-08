"""Private local state and last-successful-response storage."""

import fcntl
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone


class AppError(Exception):
    """A message suitable for displaying without exposing credentials."""


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class State:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.credentials = self.directory / "credentials.json"

    @contextmanager
    def lock(self):
        # Refresh tokens are single-use: serialize all commands in this state dir.
        fd = os.open(self.directory / "lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AppError("Another My Shows command is using this state directory.") from None
            yield
        finally:
            os.close(fd)

    def load(self):
        try:
            self.credentials.chmod(0o600)
            value = json.loads(self.credentials.read_text())
        except FileNotFoundError:
            raise AppError("Run python3 -m myshows configure first.") from None
        except (ValueError, TypeError):
            raise AppError("Invalid credentials file; run configure again.") from None
        if not isinstance(value, dict) or not value.get("client_id"):
            raise AppError("Invalid credentials file; run configure again.")
        return value

    def save(self, credentials):
        # Replace atomically; never truncate the only copy of a rotated token.
        fd, temporary = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(credentials, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.credentials)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class Cache:
    def __init__(self, state, account):
        self.account = account
        path = state.directory / "cache.sqlite3"
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        path.chmod(0o600)
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS responses (
            account TEXT, key TEXT, data TEXT, source TEXT,
            last_success_at TEXT, last_attempt_at TEXT, error TEXT,
            PRIMARY KEY (account, key))""")

    def close(self):
        self.db.close()

    def seed(self, key, data, source, last_success_at, error=None):
        """Restore a validated fallback without replacing newer local state."""
        with self.db:
            self.db.execute("""INSERT OR IGNORE INTO responses VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (self.account, key, json.dumps(data) if data is not None else None,
                             source, last_success_at, last_success_at, error))

    def read(self, key):
        self.db.row_factory = sqlite3.Row
        row = self.db.execute(
            "SELECT * FROM responses WHERE account=? AND key=?", (self.account, key)
        ).fetchone()
        if row is None:
            return {"data": None, "source": None, "last_success_at": None,
                    "last_attempt_at": None, "error": None, "state": "unknown"}
        result = dict(row)
        result.pop("account")
        result.pop("key")
        result["data"] = json.loads(result["data"]) if result["data"] is not None else None
        result["state"] = "unknown" if result["data"] is None else ("stale" if result["error"] else "cached")
        return result

    def fetch(self, key, source, loader, offline=False):
        if offline:
            return self.read(key)
        attempted = timestamp()
        try:
            data = loader()
        except AppError as exc:
            # Deliberately preserve the last good value and its successful date.
            with self.db:
                self.db.execute("""INSERT INTO responses
                    (account, key, source, last_attempt_at, error) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(account, key) DO UPDATE SET
                    last_attempt_at=excluded.last_attempt_at, error=excluded.error""",
                    (self.account, key, source, attempted, str(exc)))
            result = self.read(key)
            result["state"] = "stale" if result["data"] is not None else "unknown"
            return result
        with self.db:
            self.db.execute("""INSERT INTO responses VALUES (?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(account, key) DO UPDATE SET data=excluded.data,
                source=excluded.source, last_success_at=excluded.last_success_at,
                last_attempt_at=excluded.last_attempt_at, error=NULL""",
                (self.account, key, json.dumps(data), source, timestamp(), attempted))
        result = self.read(key)
        result["state"] = "fresh"
        return result
