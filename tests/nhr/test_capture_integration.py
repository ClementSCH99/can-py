from __future__ import annotations

import time
from datetime import datetime, timezone

import can
import pytest

from canpy.capture import CANCapture
from canpy.nhr import NHRMeasurement, NHRStreamStatistics


class OneMessageBus:
    def __init__(self, timestamps=None) -> None:
        self.timestamps = None if timestamps is None else list(timestamps)
        self.default_sent = False
        self.was_shutdown = False

    def recv(self, timeout: float):
        if self.timestamps is None:
            if self.default_sent:
                return None
            self.default_sent = True
            timestamp = time.time()
        else:
            if not self.timestamps:
                return None
            timestamp = self.timestamps.pop(0)
        return can.Message(
            timestamp=timestamp,
            arbitration_id=0x123,
            data=[0x01, 0x02],
            is_extended_id=False,
        )

    def shutdown(self) -> None:
        self.was_shutdown = True


class RecordingNHRStream:
    instrument_id = "nhr-79503"
    error = None

    def __init__(self, events=None) -> None:
        self.started = False
        self.stopped = False
        self.start_timeout = None
        self.events = events

    def start(self, timeout_s: float) -> None:
        self.started = True
        self.start_timeout = timeout_s
        if self.events is not None:
            self.events.append("nhr-first-sample")

    def stop(self) -> None:
        self.stopped = True

    def latest(self):
        return NHRMeasurement.from_mapping(
            {
                "instrument_id": self.instrument_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
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
            reconnect_count=0,
            state="streaming",
            transport_error=None,
            acquisition_error=None,
            acquisition_csv_path="runs/nhr.csv",
            acquisition_sample_count=1,
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


def test_can_writer_starts_after_first_nhr_sample(monkeypatch, tmp_path) -> None:
    events = []
    nhr_stream = RecordingNHRStream(events)
    bus = OneMessageBus()

    class RecordingWriter:
        def start_streaming(self):
            events.append("can-writer-start")

        def write_frame(self, frame):
            pass

        def stop_streaming(self):
            pass

        def get_stats(self):
            return {"fps": 0.0, "elapsed_seconds": 0.0}

    monkeypatch.setattr(
        "canpy.capture.WriterFactory.create",
        lambda *args, **kwargs: RecordingWriter(),
    )
    capture = CANCapture(log_formats=["csv"], nhr_stream=nhr_stream)
    capture.output_dir = str(tmp_path)
    capture.bus = bus

    assert capture.capture(count=1) is True
    assert events.index("nhr-first-sample") < events.index("can-writer-start")


def test_can_frame_keeps_source_timestamp_and_adds_host_utc(monkeypatch) -> None:
    written_frames = []

    class RecordingWriter:
        def start_streaming(self):
            pass

        def write_frame(self, frame):
            written_frames.append(frame)

        def stop_streaming(self):
            return {"csv": "can.csv"}

        def get_stats(self):
            return {"fps": 0.0, "elapsed_seconds": 0.0}

    monkeypatch.setattr(
        "canpy.capture.WriterFactory.create",
        lambda *args, **kwargs: RecordingWriter(),
    )
    capture = CANCapture(log_formats=["csv"], nhr_stream=RecordingNHRStream())
    capture.bus = OneMessageBus([123.456])

    before = time.time()
    assert capture.capture(count=1) is True
    after = time.time()

    assert len(written_frames) == 1
    frame = written_frames[0]
    assert frame["source_timestamp"] == 123.456
    assert before <= frame["timestamp"] <= after
    assert datetime.fromisoformat(frame["timestamp_utc"]).timestamp() == pytest.approx(
        frame["timestamp"]
    )


def test_can_status_reports_zero_traffic_even_without_console_frames(
    capsys,
) -> None:
    capture = CANCapture()
    capture._capture_started_at = 100.0
    capture._last_can_status_time = 100.0

    capture._print_can_status(110.0)

    output = capsys.readouterr().out
    assert "No CAN traffic detected for 10.0s" in output
    assert "received: 0 (0.0 fps)" in output
    assert "recorded: 0 (0.0 fps)" in output


def test_can_status_distinguishes_received_and_recorded_frames(capsys) -> None:
    capture = CANCapture()
    capture._capture_started_at = 100.0
    capture._last_can_status_time = 100.0
    capture._received_frame_count = 12
    capture._recorded_frame_count = 3

    capture._print_can_status(110.0)

    output = capsys.readouterr().out
    assert "received: 12 (1.2 fps)" in output
    assert "recorded: 3 (0.3 fps)" in output
    assert "No CAN traffic" not in output
