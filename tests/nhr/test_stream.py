from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from canpy.nhr import NHRMeasurement, NHRMeasurementStream, NHRStreamError


def measurement(index: int = 0) -> dict:
    return {
        "instrument_id": "nhr-79503",
        "timestamp_utc": (
            datetime.now(timezone.utc) + timedelta(milliseconds=index)
        ).isoformat(),
        "monotonic_s": 123.0 + index,
        "voltage_v": 350.0 + index,
        "current_a": 2.0,
        "power_w": 700.0 + (2 * index),
        "temperature_c": 24.0,
    }


class FiniteClient:
    def __init__(self, values: list[dict]) -> None:
        self.values = values
        self.connected = False
        self.disconnected = False

    def connect(self, instrument_id: str) -> dict:
        self.connected = True
        return {"connected": True}

    def disconnect(self, instrument_id: str) -> dict:
        self.disconnected = True
        return {"connected": False}

    def stream(self, instrument_id: str):
        yield from self.values


class BlockingClient(FiniteClient):
    def __init__(self) -> None:
        super().__init__([])
        self.stop_requested = threading.Event()

    def disconnect(self, instrument_id: str) -> dict:
        self.stop_requested.set()
        return super().disconnect(instrument_id)

    def stream(self, instrument_id: str):
        yield measurement()
        while not self.stop_requested.wait(0.01):
            pass


def wait_until_finished(stream: NHRMeasurementStream) -> None:
    deadline = time.monotonic() + 1.0
    while stream.running and time.monotonic() < deadline:
        time.sleep(0.01)


def test_measurement_validates_and_reports_age() -> None:
    timestamp = datetime.now(timezone.utc) - timedelta(seconds=3)
    value = measurement()
    value["timestamp_utc"] = timestamp.isoformat()

    parsed = NHRMeasurement.from_mapping(value)

    assert parsed.voltage_v == 350.0
    assert parsed.age_seconds() == pytest.approx(3.0, abs=0.1)


def test_invalid_measurement_is_rejected() -> None:
    with pytest.raises(NHRStreamError, match="voltage_v"):
        NHRMeasurement.from_mapping(
            {
                "instrument_id": "nhr-79503",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "current_a": 1.0,
                "power_w": 1.0,
            }
        )


def test_stream_keeps_a_bounded_backlog_and_newest_sample() -> None:
    client = FiniteClient([measurement(0), measurement(1), measurement(2)])
    stream = NHRMeasurementStream(
        "nhr-79503",
        queue_size=2,
        client_factory=lambda _: client,
    )

    stream.start()
    wait_until_finished(stream)

    assert stream.buffered_sample_count == 2
    assert stream.latest().voltage_v == 352.0
    assert client.connected is True
    assert client.disconnected is True


def test_stop_disconnects_and_ends_background_reader() -> None:
    client = BlockingClient()
    stream = NHRMeasurementStream(
        "nhr-79503",
        client_factory=lambda _: client,
    )
    stream.start()

    stream.stop()

    assert stream.running is False
    assert client.disconnected is True


def test_connection_failure_is_actionable() -> None:
    class FailingClient(FiniteClient):
        def connect(self, instrument_id: str) -> dict:
            raise OSError("service unavailable")

    stream = NHRMeasurementStream(
        "nhr-79503",
        client_factory=lambda _: FailingClient([]),
    )

    with pytest.raises(NHRStreamError, match="service unavailable"):
        stream.start()


def test_stale_state_uses_utc_timestamp() -> None:
    value = measurement()
    value["timestamp_utc"] = (
        datetime.now(timezone.utc) - timedelta(seconds=5)
    ).isoformat()
    client = FiniteClient([value])
    stream = NHRMeasurementStream(
        "nhr-79503",
        stale_after_s=2.0,
        client_factory=lambda _: client,
    )
    stream.start()
    wait_until_finished(stream)

    assert stream.is_stale() is True
