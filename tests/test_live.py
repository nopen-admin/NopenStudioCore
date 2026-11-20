"""Process-level tests for queue hints, cancellation, and durable restart."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

CLI = Path(__file__).resolve().parents[1] / "nopen"


class LiveCLITests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.state = Path(root.name) / "nopen-studio-core"
        self.env = dict(os.environ, XDG_STATE_HOME=root.name)
        self.cli("init", "--accept")

    def cli(self, *args, code=0):
        result = subprocess.run([CLI, *args], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertNotEqual(result.stdout, "")
        return json.loads(result.stdout)

    def wait_for(self, condition):
        deadline = time.monotonic() + 5
        while not condition():
            if time.monotonic() >= deadline:
                self.fail("Runner did not react before the fallback timer.")
            time.sleep(0.025)

    def runner(self, interval="300"):
        proc = subprocess.Popen([CLI, "run", "--check-interval", interval], env=self.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.kill_and_wait, proc)
        self.wait_for(lambda: (self.state / "runner.wake").exists()
                      and self.cli("status")["mode"] == "READY")
        return proc

    def kill_and_wait(self, proc):
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)

    def test_queue_wakes_runner_and_pause_blocks_new_actions(self):
        proc = self.runner()
        self.cli("pause")
        self.cli("task", "add", "demo", "Synthetic")
        self.cli("task", "checkpoint", "demo", "one")
        self.assertEqual(self.cli("status")["queued_actions"], 1)
        self.cli("resume")
        self.wait_for(lambda: self.cli("status")["queued_actions"] == 0)
        self.cli("stop")
        self.assertEqual(proc.wait(timeout=5), 0)

    def test_timed_check_finds_durable_action_when_no_wake_arrives(self):
        self.cli("task", "add", "demo", "Synthetic")
        proc = self.runner(interval="1")
        script = """
from nopen_core import core
from nopen_core.store import connect
with connect() as db:
    core.queue_checkpoint(db, "demo", "silent", "")
"""
        subprocess.run([sys.executable, "-c", script], env=self.env, cwd=CLI.parent,
                       check=True, timeout=5)
        self.wait_for(lambda: self.cli("status")["queued_actions"] == 0)
        self.assertEqual(self.cli("handoff", "demo")["last_checkpoint"]["action_id"], "silent")
        self.cli("stop")
        self.assertEqual(proc.wait(timeout=5), 0)

    def test_sigkill_restart_does_not_replay_committed_checkpoint(self):
        proc = self.runner()
        self.cli("task", "add", "demo", "Synthetic")
        self.cli("task", "checkpoint", "demo", "one")
        self.wait_for(lambda: self.cli("status")["queued_actions"] == 0)
        self.cli("simulate-intervention")
        self.cli("task", "checkpoint", "demo", "two")
        self.kill_and_wait(proc)
        self.assertEqual(self.cli("run", "--once"), {"mode": "PAUSED", "processed": None})
        self.assertEqual(self.cli("task", "checkpoint", "demo", "one")["status"], "DONE")
        self.cli("resume")
        self.assertEqual(self.cli("run", "--once")["processed"], "two")
        self.assertEqual([cp["action_id"] for cp in self.cli("export")["checkpoints"]], ["one", "two"])

    def test_cli_observation_status_and_start_are_inactive(self):
        self.assertFalse(self.cli("observe", "status")["active"])
        self.assertEqual(self.cli("observe", "start", code=1)["status"], "BLOCKED")
        self.assertEqual(self.cli("observe", "start", "--consent", code=1)["status"], "UNAVAILABLE")
        self.assertEqual(self.cli("observe", "stop"), {"status": "STOPPED", "active": False})
        self.assertFalse(self.cli("observe", "status")["active"])
        events = [entry["detail"] for entry in self.cli("export")["events"]
                  if entry["kind"] == "observe-stop"]
        self.assertEqual(events, [{"status": "STOPPED"}])
