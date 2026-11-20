"""Synthetic portal, PipeWire, and observer lifecycle fixtures."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nopen_core import core, live
from nopen_core.observer import FedoraWaylandObserver, MAX_FRAME_BYTES, MockObserver, WINDOW
from nopen_core.store import connect

FRAME = b"fixture-frame"


class Portal:
    def __init__(self):
        self.approved = True
        self.alive = False
        self.streams = [{"source_type": WINDOW, "node": 47, "pipewire-serial": 92}]
        self.calls = []
        self.options = None
        self.frame = FRAME
        self.fail_at = None
        self.end_during_pull = False

    def record(self, operation):
        self.calls.append(operation)
        if self.fail_at == operation:
            raise TimeoutError("synthetic deadline")

    def create_session(self, *, timeout):
        self.record("CreateSession")
        self.alive = True
        return "fixture-session"

    def select_sources(self, session, **options):
        self.record("SelectSources")
        self.options = options

    def start(self, session, *, timeout):
        self.record("Start")
        return self.approved, self.streams

    def cancel_request(self):
        self.record("Request.Close")

    def session_alive(self, session):
        return self.alive

    def open_pipewire(self, session, selected, *, timeout):
        self.record("OpenPipeWireRemote")
        if selected is not self.streams[0]:
            raise AssertionError("unexpected stream")
        return self

    def pull(self, *, timeout, max_bytes):
        self.record("pull")
        if timeout > 0.25 or max_bytes != MAX_FRAME_BYTES:
            raise AssertionError("unbounded pull")
        if self.end_during_pull:
            self.alive = False
        return self.frame

    def close(self):
        self.record("PipeWire.Close")

    def close_session(self, session):
        self.record("Session.Close")
        self.alive = False


class ScreenObserverTests(unittest.TestCase):
    def setUp(self):
        self.portal = Portal()
        self.now = 100
        self.observer = FedoraWaylandObserver(self.portal, clock=lambda: self.now)
        self.addCleanup(self.observer.close)

    def test_no_local_consent_opens_nothing(self):
        self.assertEqual(self.observer.start(consent=False), "BLOCKED")
        self.assertIsNone(self.observer.capture())
        self.assertEqual(self.portal.calls, [])
        self.assertEqual(FedoraWaylandObserver().start(consent=True), "UNAVAILABLE")

    def test_portal_denial_closes_session_before_pipewire(self):
        self.portal.approved = False
        self.assertEqual(self.observer.start(consent=True), "BLOCKED")
        self.assertIsNone(self.observer.capture())
        self.assertEqual(self.portal.calls, ["CreateSession", "SelectSources", "Start", "Session.Close"])

    def test_wrong_or_multiple_source_fails_closed(self):
        window = {"source_type": WINDOW, "node": 47}
        for streams in [[{"source_type": 1, "node": 4}], [window, window], [], [{}],
                        [{"source_type": WINDOW, "node": True}]]:
            with self.subTest(streams=streams):
                self.portal.streams = streams
                self.assertNotEqual(self.observer.start(consent=True), "ACTIVE")
                self.assertIsNone(self.observer.capture())
        self.assertNotIn("OpenPipeWireRemote", self.portal.calls)

    def test_one_transient_pull_per_second_and_idempotent_teardown(self):
        self.assertEqual(self.observer.start(consent=True), "ACTIVE")
        self.assertEqual(self.portal.options,
                         {"types": WINDOW, "multiple": False, "persist_mode": 0, "timeout": 30})
        self.assertEqual(self.observer.capture(), FRAME)
        self.assertIsNone(self.observer.capture())
        self.now += 1
        self.assertEqual(self.observer.capture(), FRAME)
        self.observer.close()
        self.observer.close()
        self.assertIsNone(self.observer.capture())
        self.assertEqual(self.portal.calls.count("pull"), 2)
        self.assertEqual(self.portal.calls[-2:], ["PipeWire.Close", "Session.Close"])
        self.assertEqual(self.portal.calls.count("Session.Close"), 1)

    def test_disconnect_during_frame_drops_frame_and_releases_both_handles(self):
        self.assertEqual(self.observer.start(consent=True), "ACTIVE")
        self.portal.end_during_pull = True
        self.assertIsNone(self.observer.capture())
        self.assertEqual(self.observer.check(), "STOPPED")
        self.assertEqual(self.portal.calls[-2:], ["PipeWire.Close", "Session.Close"])
        self.assertIsNone(self.observer.capture())

    def test_session_loss_before_capture_avoids_read(self):
        self.assertEqual(self.observer.start(consent=True), "ACTIVE")
        self.portal.alive = False
        self.assertIsNone(self.observer.capture())
        self.assertNotIn("pull", self.portal.calls)

    def test_timeout_and_close_failure_tear_down(self):
        cases = {
            "CreateSession": ["Request.Close"],
            "SelectSources": ["Request.Close", "Session.Close"],
            "Start": ["Request.Close", "Session.Close"],
            "OpenPipeWireRemote": ["Session.Close"],
        }
        for stage, cleanup in cases.items():
            with self.subTest(stage=stage):
                self.portal.fail_at = stage
                self.assertEqual(self.observer.start(consent=True), "UNAVAILABLE")
                self.assertEqual(self.portal.calls[-len(cleanup):], cleanup)
        self.portal.fail_at = None
        self.observer.start(consent=True)
        self.portal.fail_at = "PipeWire.Close"
        self.observer.close()
        self.assertEqual(self.portal.calls[-2:], ["PipeWire.Close", "Session.Close"])
        self.assertEqual(self.observer.check(), "STOPPED")

    def test_stalled_or_oversized_frame_cancels_the_lease(self):
        self.observer.start(consent=True)
        self.portal.fail_at = "pull"
        self.assertIsNone(self.observer.capture())
        self.assertEqual(self.observer.check(), "STOPPED")
        self.portal.fail_at = None
        self.observer.start(consent=True)
        self.portal.frame = bytes(MAX_FRAME_BYTES + 1)
        self.assertIsNone(self.observer.capture())
        self.assertEqual(self.observer.check(), "STOPPED")

    def test_mock_backpressure_and_no_queued_fixture_after_close(self):
        mock = MockObserver()
        self.assertFalse(mock.offer(FRAME))
        self.assertEqual(mock.start(consent=True), "ACTIVE")
        self.assertTrue(mock.offer(FRAME))
        self.assertFalse(mock.offer(b"another"))
        self.assertEqual(mock.capture(), FRAME)
        self.assertTrue(mock.offer(b"another"))
        mock.close()
        self.assertIsNone(mock.capture())


class ObserverRunnerTests(unittest.TestCase):
    def test_control_events_close_the_injected_lease_without_auto_reopen(self):
        transitions = ("pause-resume", "stop", "human-intervention", "revoke", "observe-stop")
        for transition in transitions:
            with self.subTest(transition=transition), tempfile.TemporaryDirectory() as root:
                self.check_transition(Path(root), transition)

    def check_transition(self, root, transition):
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(root)}), connect(initialize=True) as db:
            core.initialize(db, False)
            core.change_mode(db, "run")
            portal = Portal()
            observer = FedoraWaylandObserver(portal)
            self.assertEqual(observer.start(consent=True), "ACTIVE")

            def control_event(_fd, _interval):
                if transition == "pause-resume":
                    core.change_mode(db, "pause")
                    core.change_mode(db, "resume")
                elif transition == "revoke":
                    core.revoke(db, "screen-read")
                elif transition == "observe-stop":
                    live.observation_stopped(db)
                else:
                    core.change_mode(db, transition)

            if transition == "stop":
                after_event = None
            else:
                def after_event(_fd, _interval):
                    self.assertEqual(observer.check(), "STOPPED")
                    core.change_mode(db, "stop")
            callbacks = iter([control_event, after_event])
            with patch.object(live, "wait", side_effect=lambda fd, interval: next(callbacks)(fd, interval)):
                live.run_loop(db, None, 30, lambda: False, self.fail, observer)
            self.assertEqual(portal.calls[-2:], ["PipeWire.Close", "Session.Close"])
            self.assertEqual(portal.calls.count("Start"), 1)
            self.assertIsNone(observer.capture())
