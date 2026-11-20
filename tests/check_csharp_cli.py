"""Linux process checks against a managed or Native AOT CLI command."""

import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def launch_guard():
    library = ctypes.CDLL("libseccomp.so.2")
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_release.argtypes = [ctypes.c_void_p]

    def restrict():
        rules = library.seccomp_init(0x7FFF0000)
        if not rules:
            os._exit(90)
        for call in (b"socket", b"socketpair", b"connect", b"accept", b"accept4", b"sendto",
                     b"sendmsg", b"sendmmsg", b"recvmsg", b"recvmmsg", b"recvfrom", b"bind",
                     b"listen", b"io_uring_setup", b"socketcall"):
            number = library.seccomp_syscall_resolve_name(call)
            if number >= 0 and library.seccomp_rule_add(rules, 0x80000000, number, 0):
                os._exit(90)
        if library.seccomp_load(rules):
            os._exit(90)
        library.seccomp_release(rules)

    return restrict


def main(command):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        state = root / "csharp"
        env = dict(os.environ)
        env.pop("DOTNET_EnableDiagnostics", None)
        if Path(command[0]).name == "dotnet":
            env["DOTNET_EnableDiagnostics"] = "0"
        guard = launch_guard()
        probe = subprocess.run([sys.executable, "-c", "import socket; socket.socket()"],
                               preexec_fn=guard, capture_output=True, timeout=10)
        assert probe.returncode == -signal.SIGSYS, probe.returncode

        def cli(*args, expected=0):
            result = subprocess.run([*command, *args], env=env, preexec_fn=guard,
                                    capture_output=True, text=True, timeout=15)
            assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
            return json.loads(result.stdout)

        assert cli("--state", state, "status")["state"] == "IDLE"
        first = cli("--state", state, "demo", "demo", "--approve")
        assert first["checkpoint"] == {"key": "demo", "skill": "fixture", "result": "fixture-completed"}
        assert cli("--state", state, "demo", "demo", "--approve")["checkpoint"] == first["checkpoint"]
        print("PASS startup, explicit approval, checkpoint, and cross-process idempotency under seccomp")

        def read_reply(proc):
            assert select.select([proc.stdout], [], [], 5)[0], "Console response timed out."
            return json.loads(proc.stdout.readline())

        def send(proc, text):
            proc.stdin.write(text + "\n")
            proc.stdin.flush()
            return read_reply(proc)

        with subprocess.Popen([*command, "--state", state, "run"], env=env, preexec_fn=guard,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as live:
            try:
                assert read_reply(live)["state"] == "IDLE"
                assert cli("--state", state, "status", expected=1)["state"] == "BLOCKED"
                assert send(live, "read the screen")["state"] == "UNSUPPORTED"
                assert send(live, "kurgu görev çalıştır pending")["state"] == "NEEDS_APPROVAL"
                live.kill()
                assert live.wait(timeout=5) == -signal.SIGKILL
            finally:
                if live.poll() is None:
                    live.kill()

        assert cli("--state", state, "status")["state"] == "IDLE"
        assert cli("--state", state, "demo", "demo", "--approve")["checkpoint"] == first["checkpoint"]
        assert cli("--state", state, "demo", "pending", "--approve")["state"] == "DONE"
        print("PASS exclusive writer, unknown intent, SIGKILL recovery, and explicit reapproval")

        with subprocess.Popen([*command, "--state", state, "run"], env=env, preexec_fn=guard,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as live:
            try:
                assert read_reply(live)["state"] == "IDLE"
                live.terminate()
                assert live.wait(timeout=5) == 0
            finally:
                if live.poll() is None:
                    live.kill()
        assert cli("--state", state, "status")["state"] == "PAUSED"
        print("PASS SIGTERM wakes idle console and persists PAUSED")

        legacy = root / "python"
        legacy_env = dict(os.environ, XDG_STATE_HOME=str(legacy))
        for args in [("init", "--decline"), ("task", "add", "fixture", "Synthetic task"),
                     ("task", "evidence", "fixture", "fixture:9", "Synthetic evidence"),
                     ("task", "checkpoint", "fixture", "old"), ("run", "--once"), ("stop",)]:
            subprocess.run([ROOT / "nopen", *args], env=legacy_env,
                           check=True, capture_output=True, timeout=10)
        source = legacy / "nopen-studio-core" / "memory.sqlite3"
        snapshot = root / "synthetic #%.sqlite3"
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src, sqlite3.connect(snapshot) as dst:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")
        digest = hashlib.sha256(snapshot.read_bytes()).digest()
        assert cli("--sqlite-copy", snapshot, "status")["tasks"] == 1
        export = cli("--sqlite-copy", snapshot, "export")
        handoff = cli("--sqlite-copy", snapshot, "handoff", "fixture")
        assert handoff["task"]["goal"] == "Synthetic task"
        assert handoff["last_checkpoint"]["action_id"] == "old"
        assert export["checkpoints"][0] == handoff["last_checkpoint"]
        assert any(event["kind"] == "evidence" for event in handoff["history"])
        assert hashlib.sha256(snapshot.read_bytes()).digest() == digest
        assert not any(Path(str(snapshot) + suffix).exists() for suffix in ("-wal", "-shm", "-journal"))
        print("PASS W003 fixture read-only status, export, handoff, and unchanged SHA-256")

        incompatible = root / "incompatible.sqlite3"
        incompatible.write_bytes(snapshot.read_bytes())
        with sqlite3.connect(incompatible) as db:
            db.execute("PRAGMA user_version=99")
        wrong_shape = root / "wrong-shape.sqlite3"
        wrong_shape.write_bytes(snapshot.read_bytes())
        with sqlite3.connect(wrong_shape) as db:
            db.execute("ALTER TABLE tasks DROP COLUMN summary")
        broken = root / "broken.sqlite3"
        broken.write_bytes(b"synthetic corrupt database")
        with_sidecar = root / "sidecar.sqlite3"
        with_sidecar.write_bytes(snapshot.read_bytes())
        Path(str(with_sidecar) + "-wal").touch()
        raw_wal = root / "raw-wal-header.sqlite3"
        raw_wal.write_bytes(source.read_bytes())
        assert raw_wal.read_bytes()[18:20] == b"\x02\x02"
        for path in (incompatible, wrong_shape, broken, with_sidecar, raw_wal, source):
            assert cli("--sqlite-copy", path, "status", expected=1)["state"] == "BLOCKED"
        print("PASS incompatible schema, corrupted file, WAL sidecar and live path are rejected")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python3 tests/check_csharp_cli.py CLI [CLI arguments...]")
    main(sys.argv[1:])
