"""CLI integration tests use isolated state and synthetic values only."""

import ast
import ctypes
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "nopen"
PROBED_COMMANDS = (
    ("doctor",), ("init", "--accept"), ("revoke", "all"),
    ("task", "add", "demo", "Kurgu görev"), ("pause",), ("status",),
    ("task", "evidence", "demo", "fixture:42", "Kurgu kanıt"),
    ("task", "decision", "demo", "approve", "Kurgu onay"),
    ("task", "context", "demo", "--summary", "Özet"),
    ("task", "state", "demo", "PENDING"),
    ("task", "checkpoint", "demo", "a1"), ("resume",), ("run", "--once"),
    ("handoff", "demo"), ("export",), ("simulate-intervention",), ("stop",),
)
sys.path.insert(0, str(ROOT))
from nopen_core.store import APPLICATION_ID, MIGRATIONS, SCHEMA_VERSION


class CoreCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.path))
        self.state = self.path / "nopen-studio-core"
        self.db_path = self.state / "memory.sqlite3"

    def cli(self, *args, code=0):
        result = subprocess.run([str(CLI), *args], env=self.env, cwd=ROOT, capture_output=True,
                                text=True, timeout=12)
        self.assertEqual(result.returncode, code, result.stderr)
        return result

    def data(self, *args):
        return json.loads(self.cli(*args).stdout)

    def seed(self):
        self.cli("init", "--decline")
        self.cli("task", "add", "demo", "Kurgu görev")
        self.cli("task", "checkpoint", "demo", "a1", "--note", "Kurgu kontrol noktası")

    def test_uninitialized_status_and_doctor_do_not_create_state(self):
        self.cli("status", code=1)
        self.assertEqual(self.data("doctor")["desktop_access"], "NOT IMPLEMENTED")
        self.assertFalse(self.state.exists())

    def test_decline_revoke_and_repeat_init(self):
        first = self.cli("init", "--decline")
        self.assertIn("İLK KURULUM VE İZİN BİLDİRİMİ", first.stderr)
        self.assertIn("NOT IMPLEMENTED", first.stderr)
        self.assertEqual(json.loads(first.stdout)["screen-read"]["decision"], "DECLINED")
        self.cli("task", "add", "demo", "Konsol kullanılabilir")
        self.cli("revoke", "screen-read")
        self.cli("revoke", "screen-read")
        permits = self.data("init", "--accept")
        self.assertEqual(permits["screen-read"]["decision"], "REVOKED")
        self.assertEqual(permits["screen-control"]["decision"], "DECLINED")
        events = self.data("export")["events"]
        self.assertEqual(sum(e["detail"].get("decision") == "REVOKED" for e in events), 1)

    def test_acknowledgement_grants_no_access(self):
        permits = self.data("init", "--accept")
        for permit in permits.values():
            self.assertEqual(permit["decision"], "ACKNOWLEDGED")
            self.assertIs(permit["os_access"], False)
            self.assertEqual(permit["implementation"], "NOT IMPLEMENTED")
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.db_path.stat().st_mode & 0o777, 0o600)

    def test_init_checkpoint_stop_restart_and_handoff(self):
        self.seed()
        self.cli("task", "evidence", "demo", "fixture:42", "Kurgu kanıt")
        self.cli("task", "decision", "demo", "approve", "Kurgu onay")
        self.cli("task", "context", "demo", "--summary", "Taslak", "--unknowns", "Kapsam",
                 "--next-step", "İncele", "--priority", "1", "--deadline", "2030-01-10")
        self.assertEqual(self.data("run", "--once")["processed"], "a1")
        self.cli("stop")
        self.assertEqual(self.data("status")["mode"], "STOPPED")
        self.cli("task", "context", "demo", "--summary", "Güncel")
        self.cli("task", "decision", "demo", "deny", "Kurgu ret")
        self.assertIsNone(self.data("run", "--once")["processed"])
        restored = self.data("handoff", "demo")
        self.assertEqual(restored["goal"], "Kurgu görev")
        self.assertEqual(restored["summary"], "Güncel")
        self.assertEqual(restored["deadline"], "2030-01-10")
        self.assertEqual(restored["priority"], 1)
        self.assertEqual(restored["unknowns"], "Kapsam")
        self.assertEqual(restored["next_step"], "İncele")
        self.assertEqual(restored["last_confirmed_state"]["detail"]["state"], "RUNNING")
        self.assertEqual(restored["last_human_approval"]["detail"]["text"], "Kurgu onay")
        self.assertEqual(restored["last_human_decision"]["detail"]["decision"], "deny")
        self.assertEqual(restored["evidence"][0]["detail"]["reference"], "fixture:42")
        snapshot = restored["last_checkpoint"]["snapshot"]
        self.assertEqual(snapshot["summary"], "Taslak")
        self.assertEqual(snapshot["evidence"], restored["evidence"])
        self.assertEqual(snapshot["note"], "Kurgu kontrol noktası")

    def test_idempotent_checkpoint_and_conflicting_reuse(self):
        self.seed()
        duplicate = ("task", "checkpoint", "demo", "a1", "--note", "Kurgu kontrol noktası")
        self.assertEqual(self.data(*duplicate)["status"], "QUEUED")
        self.cli("run", "--once")
        self.assertEqual(self.data(*duplicate)["status"], "DONE")
        self.cli("task", "checkpoint", "demo", "a1", "--note", "Başka", code=1)
        self.assertIsNone(self.data("run", "--once")["processed"])
        export = self.data("export")
        self.assertEqual(len(export["checkpoints"]), 1)
        self.assertEqual(sum(e["kind"] == "action-queued" for e in export["events"]), 1)

    def test_pause_intervention_resume_and_task_block(self):
        self.seed()
        self.cli("pause")
        self.assertEqual(self.data("run", "--once"), {"mode": "PAUSED", "processed": None})
        self.cli("resume")
        self.cli("simulate-intervention")
        self.assertIsNone(self.data("run", "--once")["processed"])
        self.assertEqual(self.data("status")["queued_actions"], 1)
        self.cli("resume")
        self.cli("task", "state", "demo", "BLOCKED")
        self.assertIsNone(self.data("run", "--once")["processed"])
        self.cli("task", "state", "demo", "PENDING")
        self.assertEqual(self.data("run", "--once")["processed"], "a1")
        event = next(e for e in self.data("export")["events"] if e["kind"] == "human-intervention")
        self.assertEqual(event["source"], "simulation")

    def test_concurrent_runner_stop_and_explicit_restart(self):
        self.seed()
        self.cli("pause")
        runner = subprocess.Popen([str(CLI), "run"], env=self.env, cwd=ROOT,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            expires = time.monotonic() + 5
            while time.monotonic() < expires:
                try:
                    with (self.state / "runner.lock").open("rb") as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except FileNotFoundError:
                    pass
                except BlockingIOError:
                    break
                time.sleep(0.02)
            else:
                self.fail("Çalıştırıcı kilidi zamanında alınmadı.")
            self.assertIn("zaten açık", self.cli("run", "--once", code=1).stderr)
            self.cli("stop")
            self.assertEqual(runner.wait(timeout=5), 0)
            self.assertEqual(self.data("status")["queued_actions"], 1)
            self.assertEqual(self.data("run", "--once")["processed"], "a1")
        finally:
            if runner.poll() is None:
                runner.kill()
                runner.wait()

    def test_sigterm_stops_foreground_runner(self):
        self.cli("init", "--decline")
        runner = subprocess.Popen([str(CLI), "run"], env=self.env, cwd=ROOT,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            expires = time.monotonic() + 5
            while self.data("status")["mode"] != "READY":
                if time.monotonic() >= expires:
                    self.fail("Çalıştırıcı zamanında hazır olmadı.")
                time.sleep(0.02)
            runner.terminate()
            self.assertEqual(runner.wait(timeout=5), 0)
            self.assertEqual(self.data("status")["mode"], "STOPPED")
        finally:
            if runner.poll() is None:
                runner.kill()
                runner.wait()

    def test_abrupt_exit_rolls_back_partial_action(self):
        self.seed()
        script = """
import os
import signal
from nopen_core import core
from nopen_core.store import connect
with connect() as db, core.runner_lock():
    core.change_mode(db, "run")
    def crash(sql):
        if sql.startswith("UPDATE actions SET"):
            os.kill(os.getpid(), signal.SIGKILL)
    db.set_trace_callback(crash)
    core.step(db)
"""
        crash = subprocess.run([sys.executable, "-c", script], env=self.env, cwd=ROOT, timeout=10)
        self.assertEqual(crash.returncode, -9)
        interrupted = self.data("export")
        self.assertEqual(interrupted["checkpoints"], [])
        self.assertEqual(interrupted["actions"][0]["status"], "QUEUED")
        self.assertEqual(interrupted["tasks"][0]["state"], "PENDING")
        self.assertEqual(self.data("run", "--once")["processed"], "a1")
        self.assertEqual(len(self.data("export")["checkpoints"]), 1)

    def test_migrate_schema_v1_preserves_data(self):
        self.state.mkdir(mode=0o700)
        with sqlite3.connect(self.db_path) as db:
            db.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            db.execute("PRAGMA user_version = 1")
            for statement in MIGRATIONS[0]:
                db.execute(statement)
            db.execute("INSERT INTO tasks (id, goal, state) VALUES ('old', 'Kurgu kayıt', 'PENDING')")
            db.executemany("INSERT INTO permissions VALUES (?, 'DECLINED')",
                           [("screen-read",), ("screen-control",)])
        self.db_path.chmod(0o600)
        task = self.data("handoff", "old")
        self.assertEqual(task["goal"], "Kurgu kayıt")
        self.assertEqual(task["priority"], 3)
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_failed_migration_is_atomic(self):
        self.seed()
        with sqlite3.connect(self.db_path) as db:
            db.execute("DROP INDEX queued_actions")
            db.execute("PRAGMA user_version = 1")
        self.cli("status", code=1)
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT goal FROM tasks").fetchone()[0], "Kurgu görev")

    def test_wrong_and_corrupt_databases_are_preserved(self):
        for variant in ("wrong", "corrupt"):
            with self.subTest(variant=variant):
                root = self.path / variant
                root.mkdir()
                state = root / self.state.name
                state.mkdir(mode=0o700)
                path = state / self.db_path.name
                if variant == "wrong":
                    with sqlite3.connect(path) as db:
                        db.execute("CREATE TABLE other (id INTEGER)")
                else:
                    path.write_bytes(b"corrupt synthetic database")
                path.chmod(0o600)
                before = path.read_bytes()
                self.env["XDG_STATE_HOME"] = str(root)
                self.cli("init", "--decline", code=1)
                self.cli("status", code=1)
                self.assertEqual(path.read_bytes(), before)

    def test_symlink_and_insecure_modes_are_rejected(self):
        self.seed()
        self.db_path.chmod(0o644)
        self.cli("status", code=1)
        self.db_path.chmod(0o600)
        self.db_path.rename(self.state / "actual")
        self.db_path.symlink_to("actual")
        self.cli("status", code=1)

    def test_event_history_rejects_update_or_delete(self):
        self.seed()
        with sqlite3.connect(self.db_path) as db:
            for statement in ("UPDATE events SET source = 'changed'", "DELETE FROM events"):
                with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                    db.execute(statement)

    def test_production_imports_exclude_network_desktop_and_process_modules(self):
        allowed = {"argparse", "contextlib", "datetime", "fcntl", "json", "os", "pathlib",
                   "platform", "re", "signal", "sqlite3", "stat", "sys", "time", "nopen_core"}
        for path in [CLI, *(ROOT / "nopen_core").glob("*.py")]:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(alias.name.partition(".")[0] in allowed for alias in node.names))
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn(node.module.partition(".")[0], allowed)

    def test_commands_run_with_network_syscalls_denied_and_desktop_access_guarded(self):
        try:
            ctypes.CDLL("libseccomp.so.2")
        except OSError:
            self.skipTest("libseccomp.so.2 gerekli")
        script = """
import ctypes as c
import os
import runpy
import sys

lib = c.CDLL("libseccomp.so.2")
lib.seccomp_init.argtypes = [c.c_uint32]
lib.seccomp_init.restype = c.c_void_p
lib.seccomp_rule_add.argtypes = [c.c_void_p, c.c_uint32, c.c_int, c.c_uint]
lib.seccomp_syscall_resolve_name.argtypes = [c.c_char_p]
lib.seccomp_load.argtypes = [c.c_void_p]
lib.seccomp_release.argtypes = [c.c_void_p]
allow = 0x7fff0000
kill = 0x80000000
ctx = lib.seccomp_init(allow)
if not ctx:
    sys.exit(90)
for name in (b"socket", b"socketpair", b"socketcall", b"connect", b"sendto",
             b"sendmsg", b"sendmmsg", b"recvfrom", b"recvmsg", b"recvmmsg",
             b"accept", b"accept4", b"bind", b"listen", b"io_uring_setup"):
    syscall = lib.seccomp_syscall_resolve_name(name)
    if syscall >= 0 and lib.seccomp_rule_add(ctx, kill, syscall, 0):
        sys.exit(90)
if lib.seccomp_load(ctx):
    sys.exit(90)
lib.seccomp_release(ctx)

def guard(event, args):
    if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn",
                 "socket.__new__", "ctypes.dlopen"}:
        os._exit(91)
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        if path.startswith(("/dev/input", "/dev/uinput", "/dev/snd", "/dev/video",
                            "/dev/dri", "/tmp/.X11-unix")):
            os._exit(91)
sys.addaudithook(guard)
sys.argv = sys.argv[1:]
if sys.argv[-1] == "--test-filter":
    lib.syscall(lib.seccomp_syscall_resolve_name(b"socket"), 2, 1, 0)
    os._exit(92)
runpy.run_path(sys.argv[0], run_name="__main__")
"""
        def guarded(*args):
            return subprocess.run([sys.executable, "-c", script, str(CLI), *args],
                                  env=self.env, cwd=ROOT, capture_output=True, text=True, timeout=12)

        probe = guarded("--help")
        if probe.returncode == 90:
            self.skipTest("Ortam seccomp filtresi yüklemeye izin vermiyor")
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(guarded("--test-filter").returncode, -signal.SIGSYS)
        for args in PROBED_COMMANDS:
            with self.subTest(command=args):
                outcome = guarded(*args)
                self.assertEqual(outcome.returncode, 0, outcome.stderr)

    @unittest.skipUnless(shutil.which("strace"), "strace gerekli")
    def test_no_network_or_desktop_device_syscalls(self):
        probe = subprocess.run(["strace", "-o", os.devnull, "true"], capture_output=True)
        if probe.returncode:
            self.skipTest("Bu ortam ptrace kullanımına izin vermiyor")
        trace = self.path / "syscalls"
        for args in PROBED_COMMANDS:
            with self.subTest(command=args):
                result = subprocess.run(
                    ["strace", "-f", "-qq", "-o", str(trace), "-e", "trace=%network,%file,ioctl",
                     "-e", "signal=none", str(CLI), *args],
                    env=self.env, cwd=ROOT, capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = trace.read_text()
                self.assertNotRegex(calls, r"\b(?:socket|connect|sendto|sendmsg|recvmsg|socketpair)\(")
                self.assertNotRegex(calls, r'"(?:/dev/(?:input|uinput|snd|video|dri)|/tmp/\.X11-unix)')
                self.assertNotRegex(calls, r"\b(?:EVIOC|UI_DEV|SNDRV|TIOCSTI)")


if __name__ == "__main__":
    unittest.main()
