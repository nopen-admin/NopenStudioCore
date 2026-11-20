"""Local wake hints for the durable single-runner checkpoint queue."""

from contextlib import contextmanager
import os
import select
import stat

from . import core
from .store import CoreError, state_dir, transaction, validate_private

DEFAULT_CHECK_INTERVAL = 30


@contextmanager
def wake_channel():
    path = state_dir() / "runner.wake"
    try:
        os.mkfifo(path, 0o600)
    except FileExistsError:
        pass
    validate_private(path, stat.S_ISFIFO, 0o600)
    fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        yield fd
    finally:
        os.close(fd)


def poke(fd):
    try:
        os.write(fd, b"\0")
    except OSError:
        # A full pipe already has a wake queued. Other failures use the timer.
        pass


def notify():
    path = state_dir() / "runner.wake"
    try:
        validate_private(path, stat.S_ISFIFO, 0o600)
        fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except (OSError, CoreError):
        return
    try:
        poke(fd)
    finally:
        os.close(fd)


def wait(fd, interval):
    poller = select.poll()
    poller.register(fd, select.POLLIN)
    if poller.poll(int(interval * 1000)):
        try:
            os.read(fd, 4096)
        except BlockingIOError:
            pass


def observation_stopped(db):
    with transaction(db, write=True):
        core.event(db, "observe-stop", "human", {"status": "STOPPED"})


def _observation_cancelled(db, since):
    with transaction(db):
        return core.mode(db) != "READY" or db.execute(
            """SELECT 1 FROM events WHERE seq > ? AND (
                 kind IN ('pause', 'stop', 'human-intervention', 'observe-stop') OR
                 (kind = 'permission' AND json_extract(detail, '$.decision') = 'REVOKED')
               ) LIMIT 1""",
            (since,),
        ).fetchone() is not None


def run_loop(db, fd, interval, stopping, report, observer):
    # The CLI never starts an observer. An injected fixture lease is owned by
    # this loop and invalidated by every subsequent safety event.
    try:
        since = db.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]
        while not stopping():
            if observer.check() == "ACTIVE" and _observation_cancelled(db, since):
                observer.close()
            mode, action = core.step(db)
            if mode == "STOPPED":
                return
            if action is not None:
                report(action)
            elif not stopping():
                wait(fd, interval)
    finally:
        observer.close()
