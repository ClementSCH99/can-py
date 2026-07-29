from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from canpy.nhr import NHRMeasurement, NHRMeasurementStream, NHRStreamError


def measurement(index: int = 0, timestamp: str | None = None) -> dict:
    return {
        "instrument_id": "nhr-79503",
        "timestamp_utc": timestamp
        or (datetime.now(timezone.utc) + timedelta(milliseconds=index)).isoformat(),
        "monotonic_s": 123.0 + index,
        "voltage_v": 350.0 + index,
        "current_a": 2.0,
        "power_w": 700.0 + (2 * index),
        "temperature_c": 24.0,
    }


def wait_for(predicate, timeout_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        assert time.monotonic() < deadline
        time.sleep(0.005)


class BlockingClient:
    def __init__(self, values: list[dict] | None = None) -> None:
        self.values = values or [measurement()]
        self.events: list[str] = []
        self.connect_count = 0
        self.acquisition_state = {
            "last_error": None,
            "csv_path": "runs/nhr.csv",
            "sample_count": 1,
        }

    def connect(self, instrument_id: str) -> dict:
        self.connect_count += 1
        self.events.append("connect")
        return {"connected": True}

    def disconnect(self, instrument_id: str) -> dict:
        self.events.append("disconnect")
        return {"connected": False}

    def acquisition(self, instrument_id: str) -> dict:
        self.events.append("acquisition")
        return self.acquisition_state

    def stream(self, instrument_id: str, *, stop_event: threading.Event):
        self.events.append("stream-enter")
        for value in self.values:
            yield value
        stop_event.wait()
        self.events.append("reader-exit")


class ReconnectingClient(BlockingClient):
    def __init__(self, *, acquisition_error: str | None = None) -> None:
        super().__init__([])
        self.stream_count = 0
        self.acquisition_state["last_error"] = acquisition_error
        self.acquisition_state["sample_count"] = 12

    def stream(self, instrument_id: str, *, stop_event: threading.Event):
        self.stream_count += 1
        if self.stream_count == 1:
            yield measurement(0)
            raise ConnectionResetError("simulated reset")
        yield measurement(1)
        stop_event.wait()
        self.events.append("reader-exit")


def make_stream(client, **kwargs) -> NHRMeasurementStream:
    kwargs.setdefault("reconnect_delays_s", (0.0,))
    return NHRMeasurementStream(
        "nhr-79503",
        client_factory=lambda _: client,
        **kwargs,
    )


def test_measurement_preserves_timestamp_and_reports_age() -> None:
    timestamp_text = "2026-07-28T17:25:42.123456+00:00"
    parsed = NHRMeasurement.from_mapping(measurement(timestamp=timestamp_text))

    assert parsed.timestamp_utc.isoformat() == timestamp_text
    assert parsed.voltage_v == 350.0


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


def test_start_and_stop_follow_event_join_disconnect_order() -> None:
    client = BlockingClient()
    stream = make_stream(client)
    stream.start()

    stream.stop()

    assert stream.running is False
    assert stream.state == "stopped"
    assert client.events.index("reader-exit") < client.events.index("acquisition")
    assert client.events.index("acquisition") < client.events.index("disconnect")
    statistics = stream.statistics()
    assert statistics.acquisition_csv_path == "runs/nhr.csv"
    assert statistics.acquisition_sample_count == 1
    assert client.events.index("reader-exit") < client.events.index("disconnect")


def test_stream_keeps_bounded_queue_and_drops_oldest() -> None:
    client = BlockingClient([measurement(0), measurement(1), measurement(2)])
    stream = make_stream(client, queue_size=2)
    stream.start()
    wait_for(lambda: stream.statistics().received_count == 3)

    assert stream.buffered_sample_count == 2
    assert stream.latest().voltage_v == 352.0
    assert stream.statistics().dropped_count == 1
    stream.stop()


def test_reconnects_after_temporary_transport_loss() -> None:
    client = ReconnectingClient()
    stream = make_stream(client)
    stream.start()
    wait_for(lambda: stream.statistics().received_count >= 2)

    statistics = stream.statistics()
    assert client.connect_count >= 2
    assert statistics.reconnect_count >= 1
    assert statistics.transport_error is None
    stream.stop()


def test_stop_does_not_reconnect() -> None:
    client = BlockingClient()
    stream = make_stream(client)
    stream.start()

    stream.stop()

    assert client.connect_count == 1


def test_stop_timeout_does_not_force_disconnect() -> None:
    class SlowClient(BlockingClient):
        def stream(self, instrument_id: str, *, stop_event: threading.Event):
            yield measurement()
            time.sleep(0.1)

    client = SlowClient()
    stream = make_stream(client)
    stream.start()

    stream.stop(timeout_s=0.01)

    assert stream.state == "stop-timeout"
    assert "disconnect" not in client.events
    time.sleep(0.12)
    stream.stop()
    assert "disconnect" in client.events


def test_transport_loss_without_acquisition_error_is_distinct() -> None:
    class TransportOnlyClient(ReconnectingClient):
        def stream(self, instrument_id: str, *, stop_event: threading.Event):
            self.stream_count += 1
            if self.stream_count == 1:
                yield measurement(0)
                raise ConnectionResetError("simulated reset")
            stop_event.wait()
            if False:
                yield {}

    client = TransportOnlyClient()
    stream = make_stream(client)
    stream.start()
    wait_for(lambda: stream.statistics().reconnect_count >= 1)

    assert "transport lost" in stream.statistics().transport_error
    assert stream.statistics().acquisition_error is None
    stream.stop()


def test_acquisition_error_includes_csv_and_sample_count() -> None:
    client = ReconnectingClient(acquisition_error="IVI read failed")
    stream = make_stream(client)
    with pytest.raises(NHRStreamError, match="IVI read failed"):
        stream.start()

    statistics = stream.statistics()
    assert statistics.acquisition_error == "IVI read failed"
    assert statistics.acquisition_csv_path == "runs/nhr.csv"
    assert statistics.acquisition_sample_count == 12
    assert "samples=12" in statistics.error


def test_second_worker_for_same_instrument_is_rejected() -> None:
    first_client = BlockingClient()
    first = make_stream(first_client)
    second = make_stream(BlockingClient())
    first.start()
    try:
        with pytest.raises(NHRStreamError, match="already active"):
            second.start()
    finally:
        first.stop()


def test_connection_failure_is_actionable_and_interruptible() -> None:
    class FailingClient(BlockingClient):
        def connect(self, instrument_id: str) -> dict:
            raise OSError("service unavailable")

    stream = make_stream(FailingClient(), reconnect_delays_s=(0.01,))

    with pytest.raises(NHRStreamError, match="service unavailable"):
        stream.start(timeout_s=0.05)


def test_start_requires_first_measurement() -> None:
    class EmptyClient(BlockingClient):
        def stream(self, instrument_id: str, *, stop_event: threading.Event):
            stop_event.wait()
            if False:
                yield {}

    stream = make_stream(EmptyClient([]))

    with pytest.raises(NHRStreamError, match="no valid measurement"):
        stream.start(timeout_s=0.05)


def test_stale_state_uses_utc_timestamp() -> None:
    value = measurement(
        timestamp=(datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    )
    client = BlockingClient([value])
    stream = make_stream(client, stale_after_s=2.0)
    stream.start()

    assert stream.is_stale() is True
    stream.stop()
