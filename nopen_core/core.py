"""Task history, consent records and the local checkpoint queue."""

import fcntl
import json
import os
import stat
from contextlib import contextmanager

from .store import CoreError, state_dir, transaction, validate_private

CAPABILITIES = ("screen-read", "screen-control")
CONTEXT_FIELDS = ("summary", "unknowns", "next_step", "priority", "deadline")
HISTORY_KINDS = ("evidence", "human-decision", "task-state", "task-added")


def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def event(db, kind, source, detail, task_id=None):
    return db.execute(
        "INSERT INTO events (task_id, kind, source, detail) VALUES (?, ?, ?, ?)",
        (task_id, kind, source, encode(detail)),
    ).lastrowid


def permissions(db):
    decisions = dict(db.execute("SELECT capability, decision FROM permissions").fetchall())
    return {
        capability: {
            "decision": decisions.get(capability, "UNSET"),
            "implementation": "NOT IMPLEMENTED",
            "os_access": False,
        }
        for capability in CAPABILITIES
    }


def initialize(db, accepted):
    with transaction(db, write=True):
        if db.execute("SELECT 1 FROM permissions LIMIT 1").fetchone() is None:
            decision = "ACKNOWLEDGED" if accepted else "DECLINED"
            for capability in CAPABILITIES:
                db.execute("INSERT INTO permissions VALUES (?, ?)", (capability, decision))
                event(db, "permission", "human", {"capability": capability, "decision": decision})
        return permissions(db)


def revoke(db, capability):
    targets = CAPABILITIES if capability == "all" else (capability,)
    with transaction(db, write=True):
        for target in targets:
            change = db.execute(
                """INSERT INTO permissions VALUES (?, 'REVOKED')
                   ON CONFLICT(capability) DO UPDATE SET decision = 'REVOKED'
                   WHERE decision != 'REVOKED'""", (target,),
            )
            if change.rowcount:
                event(db, "permission", "human", {"capability": target, "decision": "REVOKED"})
        if "screen-read" in targets:
            event(db, "observe-stop", "human", {"status": "STOPPED"})
        return permissions(db)


def require_initialized(db):
    if db.execute("SELECT count(*) FROM permissions").fetchone()[0] != len(CAPABILITIES):
        raise CoreError("İzin kaydı tamamlanmadı. nopen init komutunu çalıştırın.")


def task_row(db, task_id):
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise CoreError("Görev bulunamadı.")
    return dict(row)


def add_task(db, task_id, goal, priority, deadline):
    with transaction(db, write=True):
        change = db.execute(
            """INSERT INTO tasks (id, goal, state, priority, deadline)
               VALUES (?, ?, 'PENDING', ?, ?) ON CONFLICT(id) DO NOTHING""",
            (task_id, goal, priority, deadline),
        )
        if not change.rowcount:
            raise CoreError("Bu görev kimliği zaten kullanılıyor.")
        event(db, "task-added", "human", {"goal": goal, "priority": priority,
                                        "deadline": deadline, "state": "PENDING"}, task_id)
        return task_row(db, task_id)


def update_task(db, task_id, kind, detail):
    with transaction(db, write=True):
        task_row(db, task_id)
        if kind == "task-state":
            db.execute("UPDATE tasks SET state = ? WHERE id = ?", (detail["state"], task_id))
        if kind == "context":
            for field in CONTEXT_FIELDS:
                if field in detail:
                    db.execute(f"UPDATE tasks SET {field} = ? WHERE id = ?", (detail[field], task_id))
        return event(db, kind, "human", detail, task_id)


def unpack(row, json_field):
    result = dict(row)
    result[json_field] = json.loads(result[json_field])
    return result


def _handoff(db, task_id):
    result = task_row(db, task_id)
    history = {kind: [] for kind in HISTORY_KINDS}
    for row in db.execute("SELECT * FROM events WHERE task_id = ? ORDER BY seq", (task_id,)):
        if row["kind"] in history:
            history[row["kind"]].append(unpack(row, "detail"))
    result["evidence"] = history["evidence"]
    result["last_human_approval"] = next(
        (entry for entry in reversed(history["human-decision"])
         if entry["detail"]["decision"] == "approve"), None,
    )
    result["last_human_decision"] = next(iter(reversed(history["human-decision"])), None)
    state_history = history["task-state"] or history["task-added"]
    result["last_confirmed_state"] = state_history[-1] if state_history else None
    return result


def handoff(db, task_id):
    with transaction(db):
        result = _handoff(db, task_id)
        checkpoint = db.execute(
            "SELECT * FROM checkpoints WHERE task_id = ? ORDER BY event_seq DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        result["last_checkpoint"] = unpack(checkpoint, "snapshot") if checkpoint else None
        return result


def export_memory(db):
    with transaction(db):
        return {
            "format": "nopen-core-memory-v1",
            "mode": mode(db),
            "permissions": permissions(db),
            "tasks": [dict(row) for row in db.execute("SELECT * FROM tasks ORDER BY id")],
            "events": [unpack(row, "detail") for row in db.execute("SELECT * FROM events ORDER BY seq")],
            "actions": [unpack(row, "payload") for row in db.execute("SELECT * FROM actions ORDER BY seq")],
            "checkpoints": [
                unpack(row, "snapshot") for row in db.execute("SELECT * FROM checkpoints ORDER BY event_seq")
            ],
        }


def queue_checkpoint(db, task_id, action_id, note):
    payload = encode({"note": note})
    with transaction(db, write=True):
        existing = db.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
        if existing is not None:
            if (existing["task_id"], existing["kind"], existing["payload"]) != (task_id, "checkpoint", payload):
                raise CoreError("Eylem kimliği farklı bir istek için zaten kullanılmış.")
            return unpack(existing, "payload")
        task_row(db, task_id)
        db.execute(
            "INSERT INTO actions (id, task_id, kind, payload) VALUES (?, ?, 'checkpoint', ?)",
            (action_id, task_id, payload),
        )
        event(db, "action-queued", "human", {"action_id": action_id}, task_id)
        return unpack(db.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone(), "payload")


def mode(db):
    return db.execute("SELECT mode FROM control WHERE id = 1").fetchone()[0]


def status(db):
    with transaction(db):
        return {
            "mode": mode(db),
            "permissions": permissions(db),
            "tasks": [dict(row) for row in db.execute("SELECT id, state FROM tasks ORDER BY id")],
            "queued_actions": db.execute("SELECT count(*) FROM actions WHERE status = 'QUEUED'").fetchone()[0],
        }


def change_mode(db, operation):
    transitions = {
        "run": {"STOPPED": "READY"},
        "pause": {"STOPPED": "PAUSED", "READY": "PAUSED"},
        "human-intervention": {"STOPPED": "PAUSED", "READY": "PAUSED"},
        "resume": {"PAUSED": "READY"},
        "stop": {"READY": "STOPPED", "PAUSED": "STOPPED"},
    }
    with transaction(db, write=True):
        previous = mode(db)
        updated = transitions[operation].get(previous, previous)
        if previous != updated or operation == "human-intervention":
            db.execute("UPDATE control SET mode = ? WHERE id = 1", (updated,))
            source = "simulation" if operation == "human-intervention" else "human"
            event(db, operation, source, {"previous": previous, "mode": updated})
        return updated


@contextmanager
def runner_lock():
    path = state_dir() / "runner.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        validate_private(path, stat.S_ISREG, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CoreError("Bu bellek için bir nopen run süreci zaten açık.") from None
        yield
    finally:
        os.close(fd)


def step(db):
    # An action and its effects fit in one write transaction. Pause and stop
    # use the same write lock, so neither can race a later action admission.
    with transaction(db, write=True):
        current = mode(db)
        if current != "READY":
            return current, None
        action = db.execute(
            """SELECT actions.* FROM actions JOIN tasks ON tasks.id = actions.task_id
               WHERE actions.status = 'QUEUED' AND tasks.state IN ('PENDING', 'RUNNING')
               ORDER BY actions.seq LIMIT 1"""
        ).fetchone()
        if action is None:
            return current, None
        task_id = action["task_id"]
        action_id = action["id"]
        change = db.execute("UPDATE tasks SET state = 'RUNNING' WHERE id = ? AND state = 'PENDING'", (task_id,))
        if change.rowcount:
            event(db, "task-state", "scheduler", {"state": "RUNNING"}, task_id)
        seq = event(db, "checkpoint", "scheduler", {"action_id": action_id}, task_id)
        snapshot = _handoff(db, task_id)
        snapshot["note"] = json.loads(action["payload"])["note"]
        db.execute("INSERT INTO checkpoints VALUES (?, ?, ?, ?)", (action_id, task_id, seq, encode(snapshot)))
        db.execute("UPDATE actions SET status = 'DONE' WHERE id = ?", (action_id,))
        return current, action_id
