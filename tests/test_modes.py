"""Integration tests for the product modes and shared W001 memory."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuddyModesCLI(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        self.env = dict(os.environ, XDG_STATE_HOME=temp.name)

    def cli(self, *args, code=0):
        result = subprocess.run(
            [str(ROOT / "nopen"), *args], env=self.env, cwd=ROOT,
            capture_output=True, text=True, timeout=12,
        )
        self.assertEqual(result.returncode, code, result.stderr)
        return result

    def data(self, *args):
        return json.loads(self.cli(*args).stdout)

    def test_modes_before_init_list_no_enabled_os_capabilities(self):
        listing = self.data("modes")
        self.assertEqual(listing["active_mode"], "operator")
        self.assertEqual(listing["modes"]["operator"]["status"], "AVAILABLE")
        self.assertEqual(listing["modes"]["companion"]["status"], "NOT IMPLEMENTED")
        self.assertEqual(
            set(listing["capabilities"]),
            {"screen-read", "input-control", "microphone", "audio-output", "network"},
        )
        for capability in listing["capabilities"].values():
            self.assertEqual(capability, {"status": "NOT IMPLEMENTED", "os_access": False})
        self.assertFalse(list(self.path.iterdir()))

    def test_companion_selection_before_init_does_not_touch_storage(self):
        for command in [("init", "--accept"), ("status",), ("run", "--once")]:
            with self.subTest(command=command):
                rejected = self.cli("--mode", "companion", *command, code=1)
                self.assertIn("Companion Buddy — NOT IMPLEMENTED", rejected.stderr)
                self.assertEqual(rejected.stdout, "")
                self.assertFalse(list(self.path.iterdir()))

    def test_brand_and_operator_status_preserve_w001_fields(self):
        self.assertIn("Nopen Buddy", self.cli("--help").stdout)
        init = self.cli("init", "--accept")
        self.assertIn("NOPEN BUDDY", init.stderr)
        permissions = json.loads(init.stdout)
        self.assertEqual(set(permissions), {"screen-read", "screen-control"})
        self.assertEqual(self.data("status"), {
            "active_mode": "operator", "mode": "STOPPED", "permissions": permissions,
            "queued_actions": 0, "tasks": [],
        })
        self.assertEqual(self.data("--mode", "operator", "status"), self.data("status"))
        self.assertFalse(any(entry["os_access"] for entry in self.data("modes")["capabilities"].values()))

    def test_modes_keep_shared_task_history_through_stop_and_restart(self):
        self.cli("init", "--decline")
        self.cli("task", "add", "demo", "Kurgu görevi")
        self.cli("task", "evidence", "demo", "fixture:5", "Kurgu kanıt")
        self.cli("task", "decision", "demo", "approve", "Kurgu karar")
        self.cli("task", "checkpoint", "demo", "a1")
        self.assertEqual(self.data("run", "--once")["processed"], "a1")
        self.cli("stop")
        before = self.data("export")
        saved = self.data("handoff", "demo")
        self.data("modes")
        self.cli("--mode", "companion", "run", "--once", code=1)
        self.assertEqual(self.data("export"), before)
        self.assertIsNone(self.data("--mode", "operator", "run", "--once")["processed"])
        self.assertEqual(self.data("handoff", "demo"), saved)
        self.assertEqual(len(self.data("export")["checkpoints"]), 1)
