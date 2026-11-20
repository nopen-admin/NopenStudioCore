"""Read-only observer contract and simulated ScreenCast lifecycle."""

from abc import ABC, abstractmethod
from contextlib import ExitStack
from time import monotonic

WINDOW = 2
MAX_FRAME_BYTES = 16 * 1024 * 1024
REQUEST_TIMEOUT = 30
FRAME_TIMEOUT = 0.25
MIN_FRAME_INTERVAL = 1.0
PORTAL_ERRORS = (OSError, ValueError)


class ScreenObserver(ABC):
    """An observation lease with explicit admission and no background consumer."""

    @abstractmethod
    def start(self, *, consent):
        """Return ACTIVE, BLOCKED or UNAVAILABLE."""

    @abstractmethod
    def check(self):
        """Report the current state and discard a disconnected lease."""

    @abstractmethod
    def capture(self):
        """Pull at most one transient frame, or return None."""

    @abstractmethod
    def close(self):
        """Discard all session and stream references."""


class MockObserver(ScreenObserver):
    """Single-slot fixture observer. A full slot applies backpressure."""

    def __init__(self):
        self.active = False
        self._frame = None

    def start(self, *, consent):
        if consent is not True:
            self.close()
            return "BLOCKED"
        self.active = True
        return "ACTIVE"

    def check(self):
        return "ACTIVE" if self.active else "STOPPED"

    def offer(self, fixture):
        if not self.active or self._frame is not None or len(fixture) > MAX_FRAME_BYTES:
            return False
        self._frame = bytes(fixture)
        return True

    def capture(self):
        frame, self._frame = self._frame, None
        return frame

    def close(self):
        self.active = False
        self._frame = None


class FedoraWaylandObserver(ScreenObserver):
    """ScreenCast contract. The CLI supplies no native D-Bus/PipeWire transport.

    Injected transports must observe deadlines and propagate local IPC errors as
    OSError. start must report visible portal approval and the selected streams.
    cancel_request must abort any outstanding request after an IPC failure.
    The restricted PipeWire session may open only the approved WINDOW node.
    """

    def __init__(self, transport=None, clock=monotonic):
        self._transport = transport
        self._clock = clock
        self._session = None
        self._stream = None
        self._cleanup = ExitStack()
        self._next_frame = 0

    def _request(self, method, *args, **options):
        try:
            return method(*args, timeout=REQUEST_TIMEOUT, **options)
        except PORTAL_ERRORS:
            self._transport.cancel_request()
            raise

    def start(self, *, consent):
        self.close()
        if consent is not True:
            return "BLOCKED"
        if self._transport is None:
            return "UNAVAILABLE"

        transport = self._transport
        try:
            with ExitStack() as cleanup:
                session = self._request(transport.create_session)
                cleanup.callback(transport.close_session, session)
                if not isinstance(session, str) or not session:
                    return "UNAVAILABLE"
                self._request(transport.select_sources, session, types=WINDOW,
                              multiple=False, persist_mode=0)
                approved, streams = self._request(transport.start, session)
                if approved is not True:
                    return "BLOCKED"
                if len(streams) != 1 or streams[0]["source_type"] != WINDOW:
                    return "BLOCKED"
                node = streams[0]["node"]
                if type(node) is not int or not 0 < node < 2**32:
                    return "BLOCKED"
                if not transport.session_alive(session):
                    return "UNAVAILABLE"
                stream = transport.open_pipewire(session, streams[0], timeout=FRAME_TIMEOUT)
                cleanup.callback(stream.close)
                if not transport.session_alive(session):
                    return "UNAVAILABLE"
                self._cleanup = cleanup.pop_all()
                self._session = session
                self._stream = stream
                self._next_frame = self._clock()
        except (OSError, ValueError, KeyError, TypeError):
            return "UNAVAILABLE"
        return "ACTIVE"

    def check(self):
        if self._session is None:
            return "STOPPED" if self._transport is not None else "UNAVAILABLE"
        try:
            if self._transport.session_alive(self._session):
                return "ACTIVE"
        except PORTAL_ERRORS:
            pass
        self.close()
        return "STOPPED"

    def capture(self):
        if self.check() != "ACTIVE" or self._clock() < self._next_frame:
            return None
        self._next_frame = self._clock() + MIN_FRAME_INTERVAL
        try:
            frame = self._stream.pull(timeout=FRAME_TIMEOUT, max_bytes=MAX_FRAME_BYTES)
            if self.check() != "ACTIVE":
                return None
            if frame is None or (isinstance(frame, bytes) and len(frame) <= MAX_FRAME_BYTES):
                return frame
        except PORTAL_ERRORS:
            pass
        self.close()
        return None

    def close(self):
        cleanup, self._cleanup = self._cleanup, ExitStack()
        self._session = None
        self._stream = None
        try:
            cleanup.close()
        except PORTAL_ERRORS:
            # Every registered close is attempted, with local references already cleared.
            pass


def observe_status():
    return {"status": "UNAVAILABLE", "implementation": "NOT IMPLEMENTED", "active": False}
