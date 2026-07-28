from __future__ import annotations

import can

from canpy.capture import CANCapture


class OneMessageBus:
    def __init__(self) -> None:
        self.sent = False
        self.was_shutdown = False

    def recv(self, timeout: float):
        if self.sent:
            return None
        self.sent = True
        return can.Message(
            timestamp=1.0,
            arbitration_id=0x123,
            data=[0x01, 0x02],
            is_extended_id=False,
        )

    def shutdown(self) -> None:
        self.was_shutdown = True


class RecordingNHRStream:
    instrument_id = "nhr-79503"
    error = None

    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def latest(self):
        return None


def test_capture_owns_nhr_stream_lifecycle() -> None:
    nhr_stream = RecordingNHRStream()
    bus = OneMessageBus()
    capture = CANCapture(nhr_stream=nhr_stream)
    capture.bus = bus

    assert capture.capture(count=1) is True

    assert nhr_stream.started is True
    assert nhr_stream.stopped is True
    assert bus.was_shutdown is True
