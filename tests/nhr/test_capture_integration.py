from __future__ import annotations

import can

from canpy.capture import CANCapture
from canpy.nhr import NHRMeasurement, NHRStreamStatistics


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
        self.start_timeout = None

    def start(self, timeout_s: float) -> None:
        self.started = True
        self.start_timeout = timeout_s

    def stop(self) -> None:
        self.stopped = True

    def latest(self):
        return NHRMeasurement.from_mapping(
            {
                "instrument_id": self.instrument_id,
                "timestamp_utc": "2026-07-28T17:25:42+00:00",
                "voltage_v": 90.0,
                "current_a": 0.04,
                "power_w": 3.6,
                "temperature_c": 24.0,
            }
        )

    def statistics(self):
        return NHRStreamStatistics(
            received_count=1,
            first_sample_delay_s=0.1,
            observed_rate_hz=None,
            dropped_count=0,
            error=None,
        )

    def is_stale(self):
        return False


def test_capture_owns_nhr_stream_lifecycle() -> None:
    nhr_stream = RecordingNHRStream()
    bus = OneMessageBus()
    capture = CANCapture(nhr_stream=nhr_stream)
    capture.bus = bus

    assert capture.capture(count=1) is True

    assert nhr_stream.started is True
    assert nhr_stream.start_timeout == 10.0
    assert nhr_stream.stopped is True
    assert bus.was_shutdown is True
