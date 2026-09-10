from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from canpy.nhr.forwarder import (
    ExternalSnapshot,
    ExternalSnapshotForwarder,
    ExternalSnapshotForwardingError,
    _RuntimeBindings,
)


class AmbiguousError(RuntimeError):
    pass


class APIError(RuntimeError):
    pass


class FakeClient:
    def __init__(self, configuration=None, gate=None):
        self._configuration = configuration or valid_configuration()
        self.gate = gate

    def configuration(self):
        if self.gate is not None:
            self.gate.wait(timeout=2)
        return self._configuration


class FakePublisher:
    def __init__(self, fail_ambiguously_once=False, publish_gate=None):
        self.fail_ambiguously_once = fail_ambiguously_once
        self.publish_gate = publish_gate
        self.synchronized = False
        self.calls = []
        self.pending = None
        self.sent = threading.Event()
        self.entered_publish = threading.Event()
        self.publish_times = []
        self.next_sequence = 0

    def synchronize_sequence(self):
        self.synchronized = True
        return self.next_sequence

    def publish(self, **payload):
        self.entered_publish.set()
        if self.publish_gate is not None:
            self.publish_gate.wait(timeout=2)
        self.publish_times.append(time.monotonic())
        copied = dict(payload)
        copied["signals"] = dict(payload["signals"])
        self.calls.append(copied)
        if self.fail_ambiguously_once:
            self.fail_ambiguously_once = False
            self.pending = copied
            raise AmbiguousError("response lost")
        receipt = {"sequence": self.next_sequence}
        self.next_sequence += 1
        self.sent.set()
        return receipt

    def retry_pending(self):
        self.calls.append(
            {**self.pending, "signals": dict(self.pending["signals"])}
        )
        self.pending = None
        receipt = {"sequence": self.next_sequence}
        self.next_sequence += 1
        self.sent.set()
        return receipt


def valid_configuration():
    return {
        "api_versions": ["v1"],
        "contracts": {"external_snapshot": "1.0"},
        "capabilities": ["external_snapshot_publication"],
        "instruments": [
            {"instrument_id": "sim-1", "backend": "simulator"}
        ],
    }


def runtime_factory(client, publisher):
    def create(*_args):
        return _RuntimeBindings(
            client=client,
            publisher=publisher,
            ambiguous_errors=(AmbiguousError,),
            api_errors=(APIError,),
        )

    return create


def snapshot(value, second=0):
    return ExternalSnapshot(
        timestamp_utc=datetime(2026, 9, 10, 12, 0, second, tzinfo=timezone.utc),
        health="ok",
        signals={"pack_voltage_v": value, "hv_permissive": True},
    )


def wait_for(predicate, timeout_s=2.0):
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition was not reached before timeout")
        time.sleep(0.01)


def test_snapshot_requires_utc_finite_typed_data():
    accepted = snapshot(90)
    assert accepted.signals == {"pack_voltage_v": 90.0, "hv_permissive": True}

    with pytest.raises(ValueError, match="timezone-aware"):
        ExternalSnapshot(
            timestamp_utc=datetime(2026, 9, 10, 12, 0),
            health="ok",
            signals={"pack_voltage_v": 90.0},
        )
    with pytest.raises(ValueError, match="finite"):
        ExternalSnapshot(
            timestamp_utc=datetime.now(timezone.utc),
            health="ok",
            signals={"pack_voltage_v": float("nan")},
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("api_versions", [], "API v1"),
        ("contracts", {}, "contract 1.0"),
        ("capabilities", [], "snapshot publication"),
        ("instruments", [], "not configured"),
    ],
)
def test_handshake_rejects_incompatible_service(field, value, message):
    configuration = valid_configuration()
    configuration[field] = value
    forwarder = ExternalSnapshotForwarder(
        "sim-1",
        "bms-test",
        runtime_factory=runtime_factory(
            FakeClient(configuration), FakePublisher()
        ),
    ).start()

    with pytest.raises(ExternalSnapshotForwardingError, match=message):
        forwarder.wait_ready()
    assert forwarder.statistics().state == "failed"


def test_bounded_queue_drops_oldest_without_blocking_producer():
    gate = threading.Event()
    publisher = FakePublisher()
    forwarder = ExternalSnapshotForwarder(
        "sim-1",
        "bms-test",
        queue_size=2,
        runtime_factory=runtime_factory(FakeClient(gate=gate), publisher),
    ).start()
    try:
        forwarder.offer(snapshot(90, 0))
        forwarder.offer(snapshot(91, 1))
        forwarder.offer(snapshot(92, 2))
        assert forwarder.statistics().dropped_count == 1

        gate.set()
        forwarder.wait_ready()
        assert publisher.sent.wait(timeout=2)
        assert publisher.calls[0]["signals"]["pack_voltage_v"] == 92.0
    finally:
        gate.set()
        forwarder.stop()


def test_ambiguous_result_retries_identical_payload_before_new_data():
    publisher = FakePublisher(fail_ambiguously_once=True)
    forwarder = ExternalSnapshotForwarder(
        "sim-1",
        "bms-test",
        reconnect_delays_s=(0.0,),
        runtime_factory=runtime_factory(FakeClient(), publisher),
    ).start()
    try:
        forwarder.wait_ready()
        forwarder.offer(snapshot(90))
        assert publisher.sent.wait(timeout=2)
        wait_for(lambda: forwarder.statistics().sent_count == 1)

        assert publisher.calls[0] == publisher.calls[1]
        statistics = forwarder.statistics()
        assert statistics.retry_count == 1
        assert statistics.last_sequence == 0
    finally:
        forwarder.stop()


def test_default_publication_rate_is_five_hz():
    forwarder = ExternalSnapshotForwarder("sim-1", "bms-test")
    assert forwarder.publish_rate_hz == 5.0
    assert forwarder.signal_max_age_s == 2.5
    assert forwarder.communication_loss_fault_after_s == 5.0


def test_expired_snapshot_is_republished_as_stale_with_source_timestamp():
    forwarder = ExternalSnapshotForwarder(
        "sim-1",
        "bms-test",
        signal_max_age_s=2.5,
        communication_loss_fault_after_s=5.0,
    )
    expired = ExternalSnapshot(
        timestamp_utc=datetime.now(timezone.utc) - timedelta(seconds=3.0),
        health="ok",
        signals={"pack_voltage_v": 90.0},
    )

    publication = forwarder._snapshot_for_publication(expired)

    assert publication.health == "stale"
    assert publication.timestamp_utc == expired.timestamp_utc
    assert publication.signals == expired.signals


def test_confirmed_communication_loss_is_republished_as_fault():
    forwarder = ExternalSnapshotForwarder(
        "sim-1",
        "bms-test",
        signal_max_age_s=2.5,
        communication_loss_fault_after_s=5.0,
    )
    lost = ExternalSnapshot(
        timestamp_utc=datetime.now(timezone.utc) - timedelta(seconds=6.0),
        health="ok",
        signals={"pack_voltage_v": 90.0},
    )

    publication = forwarder._snapshot_for_publication(lost)

    assert publication.health == "fault"
    assert publication.timestamp_utc == lost.timestamp_utc

    recovered = ExternalSnapshot(
        timestamp_utc=datetime.now(timezone.utc),
        health="ok",
        signals={"pack_voltage_v": 91.0},
    )
    assert forwarder._snapshot_for_publication(recovered).health == "ok"


def test_slow_publisher_does_not_expand_or_block_the_input_queue():
    publish_gate = threading.Event()
    publisher = FakePublisher(publish_gate=publish_gate)
    forwarder = ExternalSnapshotForwarder(
        "sim-1",
        "bms-test",
        queue_size=2,
        runtime_factory=runtime_factory(FakeClient(), publisher),
    ).start()
    try:
        forwarder.wait_ready()
        forwarder.offer(snapshot(90))
        assert publisher.entered_publish.wait(timeout=1)

        for value in range(100):
            forwarder.offer(snapshot(value))

        statistics = forwarder.statistics()
        assert statistics.queued_count <= 2
        assert statistics.dropped_count > 0
    finally:
        publish_gate.set()
        forwarder.stop()


def test_worker_limits_successive_publications_to_selected_rate():
    publisher = FakePublisher()
    forwarder = ExternalSnapshotForwarder(
        "sim-1",
        "bms-test",
        publish_rate_hz=5.0,
        runtime_factory=runtime_factory(FakeClient(), publisher),
    ).start()
    try:
        forwarder.wait_ready()
        forwarder.offer(snapshot(90))
        wait_for(lambda: len(publisher.publish_times) == 1)
        publisher.sent.clear()
        forwarder.offer(snapshot(91, 1))
        assert publisher.sent.wait(timeout=1)

        assert publisher.publish_times[1] - publisher.publish_times[0] >= 0.18
    finally:
        forwarder.stop()


def test_worker_repeats_latest_snapshot_at_selected_rate():
    publisher = FakePublisher()
    forwarder = ExternalSnapshotForwarder(
        "sim-1",
        "bms-test",
        publish_rate_hz=5.0,
        runtime_factory=runtime_factory(FakeClient(), publisher),
    ).start()
    try:
        forwarder.wait_ready()
        forwarder.offer(snapshot(90))
        wait_for(lambda: len(publisher.calls) >= 3, timeout_s=1.0)

        assert publisher.calls[0]["timestamp_utc"] == publisher.calls[2]["timestamp_utc"]
        assert publisher.calls[0]["signals"] == publisher.calls[2]["signals"]
        assert publisher.publish_times[2] - publisher.publish_times[0] >= 0.36
    finally:
        forwarder.stop()
