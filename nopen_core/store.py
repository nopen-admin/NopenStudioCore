"""Private SQLite task memory and transactional schema migration."""

import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

APPLICATION_ID = 0x4E534343
SCHEMA_VERSION = 2
STATES = ("PENDING", "RUNNING", "PAUSED", "BLOCKED", "DONE", "FAILED")

MIGRATIONS = (
    (
        """CREATE TABLE control (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            mode TEXT NOT NULL CHECK (mode IN ('STOPPED', 'PAUSED', 'READY'))
        )""",
        "INSERT INTO control VALUES (1, 'STOPPED')",
        """CREATE TABLE permissions (
            capability TEXT PRIMARY KEY,
            decision TEXT NOT NULL CHECK (decision IN ('ACKNOWLEDGED', 'DECLINED', 'REVOKED'))
        ) WITHOUT ROWID""",
        """CREATE TABLE tasks (
            id TEXT PRIMARY KEY NOT NULL,
            goal TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('PENDING','RUNNING','PAUSED','BLOCKED','DONE','FAILED')),
            summary TEXT NOT NULL DEFAULT '',
            unknowns TEXT NOT NULL DEFAULT '',
            next_step TEXT NOT NULL DEFAULT ''
        )""",
        """CREATE TABLE events (
            seq INTEGER PRIMARY KEY,
            occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            task_id TEXT REFERENCES tasks(id),
            kind TEXT NOT NULL,
            source TEXT NOT NULL,
            detail TEXT NOT NULL
        )""",
        """CREATE TABLE actions (
            seq INTEGER PRIMARY KEY,
            id TEXT NOT NULL UNIQUE,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            kind TEXT NOT NULL CHECK (kind = 'checkpoint'),
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED', 'DONE'))
        )""",
        """CREATE TABLE checkpoints (
            action_id TEXT PRIMARY KEY NOT NULL REFERENCES actions(id),
            task_id TEXT NOT NULL REFERENCES tasks(id),
            event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq),
            snapshot TEXT NOT NULL
        )""",
    ),
    (
        "ALTER TABLE tasks ADD COLUMN priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5)",
        "ALTER TABLE tasks ADD COLUMN deadline TEXT NOT NULL DEFAULT ''",
        "CREATE INDEX events_by_task ON events(task_id, seq)",
        "CREATE INDEX queued_actions ON actions(seq) WHERE status = 'QUEUED'",
        """CREATE TRIGGER events_no_update BEFORE UPDATE ON events
           BEGIN SELECT RAISE(ABORT, 'append-only events'); END""",
        """CREATE TRIGGER events_no_delete BEFORE DELETE ON events
           BEGIN SELECT RAISE(ABORT, 'append-only events'); END""",
    ),
)


class CoreError(Exception):
    """An expected error that can be reported without dumping local inputs."""


def state_dir():
    configured = os.environ.get("XDG_STATE_HOME", "")
    base = Path(configured) if os.path.isabs(configured) else Path.home() / ".local" / "state"
    return base / "nopen-studio-core"


def validate_private(path, file_type, mode):
    info = path.lstat()
    if (not file_type(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != mode
            or (file_type is stat.S_ISREG and info.st_nlink != 1)):
        raise CoreError("Yerel durum yolu güvensiz. Sahipliği ve dosya izinlerini denetleyin.")


@contextmanager
def transaction(db, write=False):
    db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _migrate(db, initialize):
    with transaction(db, write=True):
        app_id = db.execute("PRAGMA application_id").fetchone()[0]
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if app_id == APPLICATION_ID and 1 <= version <= SCHEMA_VERSION:
            pass
        elif (initialize and app_id == 0 and version == 0
              and db.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone() is None):
            db.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        else:
            raise CoreError("Veritabanı kimliği veya şema sürümü desteklenmiyor.")
        for target in range(version + 1, SCHEMA_VERSION + 1):
            for statement in MIGRATIONS[target - 1]:
                db.execute(statement)
            db.execute(f"PRAGMA user_version = {target}")


@contextmanager
def connect(initialize=False):
    root = state_dir()
    path = root / "memory.sqlite3"
    if initialize:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.exists() and not root.is_symlink():
        raise CoreError("Önce nopen init komutunu çalıştırın.")
    validate_private(root, stat.S_ISDIR, 0o700)
    if initialize:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
    if not path.exists() and not path.is_symlink():
        raise CoreError("Önce nopen init komutunu çalıştırın.")
    validate_private(path, stat.S_ISREG, 0o600)
    for suffix in ("-wal", "-shm", "-journal"):
        try:
            validate_private(root / (path.name + suffix), stat.S_ISREG, 0o600)
        except FileNotFoundError:
            pass

    db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=5)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA trusted_schema = OFF")
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA synchronous = FULL")
        _migrate(db, initialize)
        if db.execute("PRAGMA journal_mode = WAL").fetchone()[0] != "wal":
            raise CoreError("SQLite WAL etkinleştirilemedi.")
        yield db
    finally:
        db.close()
