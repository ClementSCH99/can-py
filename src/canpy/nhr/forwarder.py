"""Forward decoded CAN snapshots to NHR-RT outside the CAN capture path."""

from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Tuple, Type, Union


SignalValue = Union[float, bool]


class ExternalSnapshotForwardingError(RuntimeError):
    """The optional NHR-RT forwarding path could not operate correctly."""


@dataclass(frozen=True)
class ExternalSnapshot:
    """One complete, timestamped view of a decoded external source."""

    timestamp_utc: datetime
    health: str
    signals: Mapping[str, SignalValue]

    def __post_init__(self) -> None:
        if self.timestamp_utc.utcoffset() is None:
            raise ValueError("timestamp_utc must be timezone-aware")
        if self.timestamp_utc.utcoffset() != timedelta(0):
            raise ValueError("timestamp_utc must use UTC")
        if not self.health.strip():
            raise ValueError("health must not be empty")
        if not self.signals:
            raise ValueError("signals must not be empty")

        copied = {}
        for name, value in self.signals.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("signal names must be non-empty strings")
            if isinstance(value, bool):
                copied[name] = value
                continue
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(
                    f"signal {name!r} must be a finite number or boolean"
                )
            copied[name] = float(value)
        object.__setattr__(self, "signals", MappingProxyType(copied))


@dataclass(frozen=True)
class ForwarderStatistics:
    """Bounded forwarding evidence that can be included in a session summary."""

    state: str
    offered_count: int
    sent_count: int
    rejected_count: int
    dropped_count: int
    coalesced_count: int
    retry_count: int
    queued_count: int
    last_sequence: Optional[int]
    last_error: Optional[str]


@dataclass(frozen=True)
class _RuntimeBindings:
    client: Any
    publisher: Any
    ambiguous_errors: Tuple[Type[BaseException], ...]
    api_errors: Tuple[Type[BaseException], ...]


def _load_runtime(
    base_url: str,
    instrument_id: str,
    source_id: str,
    timeout_s: float,
) -> _RuntimeBindings:
    try:
        from nhr9300 import (
            ExternalSnapshotPublisher,
            NHRAPIError,
            NHRProtocolError,
            NHRServiceClient,
            NHRTransportError,
        )
    except ImportError as exc:
        raise ExternalSnapshotForwardingError(
            "nhr9300 is not installed. Install the dependency-free NHR-RT "
            "client package in the CAN-PY environment."
        ) from exc

    client = NHRServiceClient(base_url)
    publisher = ExternalSnapshotPublisher(
        client,
        instrument_id,
        source_id,
        timeout_s=timeout_s,
    )
    return _RuntimeBindings(
        client=client,
        publisher=publisher,
        ambiguous_errors=(NHRTransportError, NHRProtocolError),
        api_errors=(NHRAPIError,),
    )


def _require_external_snapshot_contract(
    configuration: Mapping[str, Any], instrument_id: str
) -> None:
    api_versions = configuration.get("api_versions")
    contracts = configuration.get("contracts")
    capabilities = configuration.get("capabilities")
    instruments = configuration.get("instruments")

    if not isinstance(api_versions, list) or "v1" not in api_versions:
        raise ExternalSnapshotForwardingError(
            "NHR service does not advertise API v1"
        )
    if (
        not isinstance(contracts, Mapping)
        or contracts.get("external_snapshot") != "1.0"
    ):
        raise ExternalSnapshotForwardingError(
            "NHR service does not expose external snapshot contract 1.0"
        )
    if (
        not isinstance(capabilities, list)
        or "external_snapshot_publication" not in capabilities
    ):
        raise ExternalSnapshotForwardingError(
            "NHR service does not support external snapshot publication"
        )
    if not isinstance(instruments, list) or not any(
        isinstance(item, Mapping) and item.get("instrument_id") == instrument_id
        for item in instruments
    ):
        raise ExternalSnapshotForwardingError(
            f"NHR instrument {instrument_id!r} is not configured"
        )


class ExternalSnapshotForwarder:
    """Own one bounded queue and one NHR publisher worker for a source.

    ``offer`` never performs network I/O and never waits for queue capacity.
    The worker coalesces queued data and publishes at the configured maximum
    cadence. Ambiguous responses retain the publisher's exact pending payload
    and retry it before any newer snapshot.
    """

    DEFAULT_RECONNECT_DELAYS_S = (0.5, 1.0, 2.0, 5.0)

    def __init__(
        self,
        instrument_id: str,
        source_id: str,
        *,
        base_url: str = "http://127.0.0.1:9300",
        queue_size: int = 16,
        publish_rate_hz: float = 5.0,
        signal_max_age_s: float = 2.5,
        communication_loss_fault_after_s: float = 5.0,
        timeout_s: float = 1.0,
        reconnect_delays_s: Tuple[float, ...] = DEFAULT_RECONNECT_DELAYS_S,
        runtime_factory: Callable[..., _RuntimeBindings] = _load_runtime,
    ) -> None:
        if not instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        if not source_id.strip():
            raise ValueError("source_id must not be empty")
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        if publish_rate_hz <= 0:
            raise ValueError("publish_rate_hz must be positive")
        if signal_max_age_s <= 0:
            raise ValueError("signal_max_age_s must be positive")
        if communication_loss_fault_after_s <= signal_max_age_s:
            raise ValueError(
                "communication_loss_fault_after_s must be greater than "
                "signal_max_age_s"
            )
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if not reconnect_delays_s or any(delay < 0 for delay in reconnect_delays_s):
            raise ValueError("reconnect_delays_s must contain non-negative values")

        self.instrument_id = instrument_id
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")
        self.queue_size = queue_size
        self.publish_rate_hz = publish_rate_hz
        self.signal_max_age_s = signal_max_age_s
        self.communication_loss_fault_after_s = (
            communication_loss_fault_after_s
        )
        self.timeout_s = timeout_s
        self.reconnect_delays_s = reconnect_delays_s
        self._runtime_factory = runtime_factory

        self._snapshots = queue.Queue(maxsize=queue_size)
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._state = "stopped"
        self._offered_count = 0
        self._sent_count = 0
        self._rejected_count = 0
        self._dropped_count = 0
        self._coalesced_count = 0
        self._retry_count = 0
        self._last_sequence = None
        self._last_error = None

    def start(self) -> "ExternalSnapshotForwarder":
        """Start the forwarding worker; the handshake runs in that worker."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ExternalSnapshotForwardingError("forwarder is already active")
            self._stop_event.clear()
            self._ready_event.clear()
            self._state = "starting"
            self._last_error = None
            self._thread = threading.Thread(
                target=self._run,
                name=f"nhr-forward-{self.source_id}",
                daemon=True,
            )
            self._thread.start()
        return self

    def wait_ready(self, timeout_s: float = 5.0) -> None:
        """Wait for the worker-owned compatibility handshake to finish."""
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if not self._ready_event.wait(timeout_s):
            raise ExternalSnapshotForwardingError(
                "timed out waiting for the NHR forwarding handshake"
            )
        with self._lock:
            if self._state == "failed":
                raise ExternalSnapshotForwardingError(
                    self._last_error or "NHR forwarding handshake failed"
                )

    def offer(self, snapshot: ExternalSnapshot) -> None:
        """Offer a snapshot without network I/O or waiting for queue capacity."""
        if not isinstance(snapshot, ExternalSnapshot):
            raise TypeError("snapshot must be an ExternalSnapshot")
        with self._lock:
            if self._state not in {"starting", "running"}:
                raise ExternalSnapshotForwardingError("forwarder is not active")
            self._offered_count += 1

        try:
            self._snapshots.put_nowait(snapshot)
            return
        except queue.Full:
            pass

        try:
            self._snapshots.get_nowait()
        except queue.Empty:
            pass
        else:
            with self._lock:
                self._dropped_count += 1
        try:
            self._snapshots.put_nowait(snapshot)
        except queue.Full:
            # The consumer/producer race can refill the queue between operations.
            with self._lock:
                self._dropped_count += 1

    def stop(self, timeout_s: float = 3.0) -> None:
        """Request cooperative shutdown and enforce a bounded join."""
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            if self._state != "failed":
                self._state = "stopping"
        self._stop_event.set()
        thread.join(timeout_s)
        if thread.is_alive():
            raise ExternalSnapshotForwardingError(
                f"forwarding worker did not stop within {timeout_s:.1f} seconds"
            )

    def statistics(self) -> ForwarderStatistics:
        with self._lock:
            return ForwarderStatistics(
                state=self._state,
                offered_count=self._offered_count,
                sent_count=self._sent_count,
                rejected_count=self._rejected_count,
                dropped_count=self._dropped_count,
                coalesced_count=self._coalesced_count,
                retry_count=self._retry_count,
                queued_count=self._snapshots.qsize(),
                last_sequence=self._last_sequence,
                last_error=self._last_error,
            )

    def _run(self) -> None:
        try:
            runtime = self._runtime_factory(
                self.base_url,
                self.instrument_id,
                self.source_id,
                self.timeout_s,
            )
            configuration = runtime.client.configuration()
            _require_external_snapshot_contract(configuration, self.instrument_id)
            runtime.publisher.synchronize_sequence()
        except Exception as exc:
            self._fail(f"NHR forwarding handshake failed: {type(exc).__name__}: {exc}")
            self._ready_event.set()
            return

        with self._lock:
            self._state = "running"
        self._ready_event.set()

        period_s = 1.0 / self.publish_rate_hz
        next_publication = time.monotonic()
        latest_snapshot = None
        pending = False
        reconnect_attempt = 0

        try:
            while not self._stop_event.is_set():
                if pending:
                    with self._lock:
                        self._retry_count += 1
                    try:
                        receipt = runtime.publisher.retry_pending()
                    except runtime.ambiguous_errors as exc:
                        self._record_error(exc)
                        delay_s = self.reconnect_delays_s[
                            min(reconnect_attempt, len(self.reconnect_delays_s) - 1)
                        ]
                        reconnect_attempt += 1
                        if self._stop_event.wait(delay_s):
                            break
                        continue
                    except runtime.api_errors as exc:
                        self._record_rejection(exc)
                        pending = False
                    else:
                        self._record_receipt(receipt)
                        pending = False
                        reconnect_attempt = 0
                    next_publication = time.monotonic() + period_s
                    continue

                wait_s = max(0.0, next_publication - time.monotonic())
                queue_timeout_s = min(wait_s, 0.05) if latest_snapshot else 0.05
                try:
                    latest_snapshot = self._snapshots.get(timeout=queue_timeout_s)
                except queue.Empty:
                    pass
                else:
                    # Bound coalescing work even if a producer continuously
                    # refills the queue faster than the publication cadence.
                    for _ in range(self.queue_size - 1):
                        try:
                            latest_snapshot = self._snapshots.get_nowait()
                        except queue.Empty:
                            break
                        with self._lock:
                            self._coalesced_count += 1

                if latest_snapshot is None:
                    continue
                if time.monotonic() < next_publication:
                    continue

                snapshot = self._snapshot_for_publication(latest_snapshot)
                try:
                    receipt = runtime.publisher.publish(
                        timestamp_utc=snapshot.timestamp_utc.isoformat(),
                        health=snapshot.health,
                        signals=snapshot.signals,
                    )
                except runtime.ambiguous_errors as exc:
                    self._record_error(exc)
                    pending = True
                    reconnect_attempt = 0
                except runtime.api_errors as exc:
                    self._record_rejection(exc)
                else:
                    self._record_receipt(receipt)
                    reconnect_attempt = 0
                next_publication = time.monotonic() + period_s
        except Exception as exc:
            self._fail(
                f"NHR forwarding worker failed: {type(exc).__name__}: {exc}"
            )
            return
        finally:
            with self._lock:
                if self._state != "failed":
                    self._state = "stopped"

    def _snapshot_for_publication(
        self, snapshot: ExternalSnapshot
    ) -> ExternalSnapshot:
        """Mark expired CAN data stale without changing its source timestamp."""
        age_s = max(
            0.0,
            (datetime.now(timezone.utc) - snapshot.timestamp_utc).total_seconds(),
        )
        if snapshot.health != "ok" or age_s <= self.signal_max_age_s:
            return snapshot
        health = (
            "fault"
            if age_s >= self.communication_loss_fault_after_s
            else "stale"
        )
        return ExternalSnapshot(
            timestamp_utc=snapshot.timestamp_utc,
            health=health,
            signals=snapshot.signals,
        )

    def _record_receipt(self, receipt: Mapping[str, Any]) -> None:
        sequence = receipt.get("sequence")
        with self._lock:
            self._sent_count += 1
            self._last_sequence = sequence if isinstance(sequence, int) else None
            self._last_error = None

    def _record_rejection(self, exc: BaseException) -> None:
        with self._lock:
            self._rejected_count += 1
            self._last_error = f"{type(exc).__name__}: {exc}"

    def _record_error(self, exc: BaseException) -> None:
        with self._lock:
            self._last_error = f"{type(exc).__name__}: {exc}"

    def _fail(self, message: str) -> None:
        with self._lock:
            self._state = "failed"
            self._last_error = message
