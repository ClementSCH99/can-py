"""Consume NHR9300 measurements without exposing instrument commands."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Mapping, Optional, Protocol
from urllib.error import URLError

LOGGER = logging.getLogger(__name__)


class NHRStreamError(RuntimeError):
    """The read-only NHR measurement stream could not be used."""


class _NHRClient(Protocol):
    def connect(self, instrument_id: str) -> Mapping[str, Any]:
        ...

    def disconnect(self, instrument_id: str) -> Mapping[str, Any]:
        ...

    def acquisition(self, instrument_id: str) -> Mapping[str, Any]:
        ...

    def stream(
        self,
        instrument_id: str,
        *,
        stop_event: threading.Event,
    ) -> Iterator[Mapping[str, Any]]:
        ...


@dataclass(frozen=True)
class NHRMeasurement:
    """Small, validated view of one nhr-rt measurement."""

    instrument_id: str
    timestamp_utc: datetime
    voltage_v: float
    current_a: float
    power_w: float
    temperature_c: Optional[float] = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NHRMeasurement":
        try:
            timestamp_text = str(value["timestamp_utc"])
            if timestamp_text.endswith("Z"):
                timestamp_text = timestamp_text[:-1] + "+00:00"
            timestamp = datetime.fromisoformat(timestamp_text)
            if timestamp.tzinfo is None:
                raise ValueError("timestamp_utc must include a timezone")
            temperature = value.get("temperature_c")
            return cls(
                instrument_id=str(value["instrument_id"]),
                timestamp_utc=timestamp.astimezone(timezone.utc),
                voltage_v=float(value["voltage_v"]),
                current_a=float(value["current_a"]),
                power_w=float(value["power_w"]),
                temperature_c=None if temperature is None else float(temperature),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise NHRStreamError(f"Invalid NHR measurement: {exc}") from exc

    def age_seconds(self, now: Optional[datetime] = None) -> float:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must include a timezone")
        return max(0.0, (current - self.timestamp_utc).total_seconds())


@dataclass(frozen=True)
class NHRStreamStatistics:
    """Timing, transport and completeness evidence for one stream."""

    received_count: int
    first_sample_delay_s: Optional[float]
    observed_rate_hz: Optional[float]
    dropped_count: int
    reconnect_count: int
    state: str
    transport_error: Optional[str]
    acquisition_error: Optional[str]
    acquisition_csv_path: Optional[str]
    acquisition_sample_count: Optional[int]
    error: Optional[str]


def _create_client(base_url: str) -> _NHRClient:
    try:
        from nhr9300 import NHRServiceClient
    except ImportError as exc:
        raise NHRStreamError(
            "nhr9300 client is not installed. Install nhr-rt in this "
            "environment with: python -m pip install -e <path-to-nhr-rt> "
            "--no-build-isolation"
        ) from exc
    return NHRServiceClient(base_url)


class NHRMeasurementStream:
    """Own a cooperative SSE worker with bounded buffering and reconnects."""

    # Prevent two readers from competing for the same service stream.
    _active_workers: dict[tuple[str, str], "NHRMeasurementStream"] = {}
    _active_workers_lock = threading.Lock()
    _recoverable_errors = (
        ConnectionAbortedError,
        ConnectionResetError,
        BrokenPipeError,
        TimeoutError,
        URLError,
        OSError,
    )

    def __init__(
        self,
        instrument_id: str,
        base_url: str = "http://127.0.0.1:9300",
        stale_after_s: float = 2.0,
        queue_size: int = 100,
        reconnect_delays_s: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0),
        client_factory: Callable[[str], _NHRClient] = _create_client,
    ) -> None:
        if not instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        if stale_after_s <= 0:
            raise ValueError("stale_after_s must be positive")
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        if not reconnect_delays_s or any(delay < 0 for delay in reconnect_delays_s):
            raise ValueError("reconnect_delays_s must contain non-negative values")

        self.instrument_id = instrument_id
        self.base_url = base_url.rstrip("/")
        self.stale_after_s = stale_after_s
        self.reconnect_delays_s = reconnect_delays_s
        self._client_factory = client_factory

        self._samples: "queue.Queue[NHRMeasurement]" = queue.Queue(queue_size)
        self._latest: Optional[NHRMeasurement] = None

        self._error: Optional[str] = None
        self._transport_error: Optional[str] = None
        self._acquisition_error: Optional[str] = None
        self._acquisition_csv_path: Optional[str] = None
        self._acquisition_sample_count: Optional[int] = None
        self._state = "stopped"

        self._client: Optional[_NHRClient] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = threading.Event()
        self._first_sample = threading.Event()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._started_monotonic: Optional[float] = None
        self._first_received_monotonic: Optional[float] = None
        self._last_received_monotonic: Optional[float] = None
        self._received_count = 0
        self._dropped_count = 0
        self._reconnect_count = 0
        self._ever_connected = False

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def error(self) -> Optional[str]:
        with self._lock:
            return self._error

    @property
    def transport_error(self) -> Optional[str]:
        with self._lock:
            return self._transport_error

    @property
    def buffered_sample_count(self) -> int:
        return self._samples.qsize()

    def start(self, timeout_s: float = 10.0) -> "NHRMeasurementStream":
        """Start one worker and wait until its first valid measurement."""
        if self.running:
            return self
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")

        self._claim_worker()
        self._reset_session()
        self._thread = threading.Thread(
            target=self._run,
            name=f"nhr-stream-{self.instrument_id}",
            daemon=True,
        )
        self._thread.start()

        # Connection and first data share one overall readiness deadline.
        deadline = time.monotonic() + timeout_s
        if not self._connected.wait(max(0.0, deadline - time.monotonic())):
            detail = self.transport_error
            self.stop()
            suffix = f": {detail}" if detail else ""
            raise NHRStreamError(
                f"Timed out connecting to NHR service at {self.base_url}{suffix}"
            )
        if self.error:
            self.stop()
            raise NHRStreamError(self.error)
        if not self._first_sample.wait(max(0.0, deadline - time.monotonic())):
            self.stop()
            raise NHRStreamError(
                f"Connected to NHR service at {self.base_url}, but no valid "
                f"measurement arrived within {timeout_s:.1f} seconds"
            )
        if self.error:
            self.stop()
            raise NHRStreamError(self.error)
        return self

    def stop(self, timeout_s: float = 3.0) -> None:
        """Request SSE shutdown, join the reader, then disconnect the service."""
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        with self._lock:
            self._state = "stopping"
        LOGGER.info("NHR stop requested: instrument=%s", self.instrument_id)

        # Let the SSE iterator leave its own socket before disconnecting.
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout_s)

        if thread is not None and thread.is_alive():
            message = (
                f"NHR worker did not stop within {timeout_s:.1f} seconds; "
                "disconnect was not forced"
            )
            with self._lock:
                self._error = message
                self._state = "stop-timeout"
            LOGGER.warning("%s: instrument=%s", message, self.instrument_id)
            return

        self._thread = None

        if self._ever_connected and self._client is not None:
            try:
                self._client.disconnect(self.instrument_id)
            except Exception as exc:
                message = f"NHR disconnect failed: {exc}"
                with self._lock:
                    self._error = message
                LOGGER.warning("%s: instrument=%s", message, self.instrument_id)
        with self._lock:
            self._state = "stopped"
        self._release_worker()
        LOGGER.info("NHR worker stopped cleanly: instrument=%s", self.instrument_id)

    def latest(self) -> Optional[NHRMeasurement]:
        newest = self._latest
        while True:
            try:
                newest = self._samples.get_nowait()
            except queue.Empty:
                break
        if newest is not None:
            self._latest = newest
        return newest

    def is_stale(self, now: Optional[datetime] = None) -> bool:
        measurement = self.latest()
        return (
            measurement is None
            or measurement.age_seconds(now) > self.stale_after_s
        )

    def statistics(self) -> NHRStreamStatistics:
        with self._lock:
            started = self._started_monotonic
            first = self._first_received_monotonic
            last = self._last_received_monotonic
            count = self._received_count
            dropped = self._dropped_count
            reconnects = self._reconnect_count
            state = self._state
            transport_error = self._transport_error
            acquisition_error = self._acquisition_error
            csv_path = self._acquisition_csv_path
            acquisition_count = self._acquisition_sample_count
            error = self._error
        span = None if first is None or last is None else last - first
        return NHRStreamStatistics(
            received_count=count,
            first_sample_delay_s=(
                None if started is None or first is None else first - started
            ),
            observed_rate_hz=(
                (count - 1) / span
                if span is not None and span > 0 and count >= 2
                else None
            ),
            dropped_count=dropped,
            reconnect_count=reconnects,
            state=state,
            transport_error=transport_error,
            acquisition_error=acquisition_error,
            acquisition_csv_path=csv_path,
            acquisition_sample_count=acquisition_count,
            error=error,
        )

    def _reset_session(self) -> None:
        self._stop_event.clear()
        self._connected.clear()
        self._first_sample.clear()
        while True:
            try:
                self._samples.get_nowait()
            except queue.Empty:
                break
        with self._lock:
            self._error = None
            self._transport_error = None
            self._acquisition_error = None
            self._acquisition_csv_path = None
            self._acquisition_sample_count = None
            self._state = "starting"
            self._latest = None
            self._started_monotonic = time.monotonic()
            self._first_received_monotonic = None
            self._last_received_monotonic = None
            self._received_count = 0
            self._dropped_count = 0
            self._reconnect_count = 0
            self._ever_connected = False

    def _claim_worker(self) -> None:
        key = (self.base_url, self.instrument_id)
        with self._active_workers_lock:
            owner = self._active_workers.get(key)
            if owner is not None and owner is not self:
                raise NHRStreamError(
                    f"An NHR worker is already active for {self.instrument_id} "
                    f"at {self.base_url}"
                )
            self._active_workers[key] = self

    def _release_worker(self) -> None:
        key = (self.base_url, self.instrument_id)
        with self._active_workers_lock:
            if self._active_workers.get(key) is self:
                del self._active_workers[key]

    def _publish(self, measurement: NHRMeasurement) -> None:
        received_at = time.monotonic()
        with self._lock:
            if self._first_received_monotonic is None:
                self._first_received_monotonic = received_at
            self._last_received_monotonic = received_at
            self._received_count += 1
            self._transport_error = None
            self._state = "streaming"
        try:
            self._samples.put_nowait(measurement)
        except queue.Full:
            with self._lock:
                self._dropped_count += 1
            try:
                self._samples.get_nowait()
            except queue.Empty:
                pass
            self._samples.put_nowait(measurement)
        self._first_sample.set()

    def _run(self) -> None:
        delay_index = 0
        try:
            self._client = self._client_factory(self.base_url)
            while not self._stop_event.is_set():
                try:
                    is_reconnect = self._ever_connected
                    with self._lock:
                        self._state = "reconnecting" if is_reconnect else "connecting"
                        if is_reconnect:
                            self._reconnect_count += 1

                    self._client.connect(self.instrument_id)
                    self._ever_connected = True
                    self._connected.set()
                    LOGGER.info(
                        "%s: instrument=%s url=%s",
                        "NHR reconnected" if is_reconnect else "NHR connected",
                        self.instrument_id,
                        self.base_url,
                    )

                    # Only this worker thread consumes the blocking SSE iterator.
                    received_on_connection = False
                    for raw_measurement in self._client.stream(
                        self.instrument_id,
                        stop_event=self._stop_event,
                    ):
                        if self._stop_event.is_set():
                            break
                        measurement = NHRMeasurement.from_mapping(raw_measurement)
                        self._publish(measurement)
                        received_on_connection = True
                        delay_index = 0
                    if self._stop_event.is_set():
                        break

                    # EOF is unexpected here; inspect acquisition before retrying.
                    self._inspect_acquisition()
                    self._set_transport_error("NHR SSE stream ended unexpectedly")
                    if received_on_connection:
                        delay_index = 0
                except self._recoverable_errors as exc:
                    if self._stop_event.is_set():
                        break
                    self._inspect_acquisition()
                    self._set_transport_error(
                        f"NHR transport lost: {type(exc).__name__}: {exc}"
                    )
                except NHRStreamError as exc:
                    with self._lock:
                        self._error = str(exc)
                        self._state = "failed"
                    self._connected.set()
                    self._first_sample.set()
                    return
                except Exception as exc:
                    with self._lock:
                        self._error = f"NHR worker failed: {exc}"
                        self._state = "failed"
                    self._connected.set()
                    self._first_sample.set()
                    return

                # Waiting on the event keeps the backoff immediately interruptible.
                delay = self.reconnect_delays_s[
                    min(delay_index, len(self.reconnect_delays_s) - 1)
                ]
                delay_index = min(delay_index + 1, len(self.reconnect_delays_s) - 1)
                if self._stop_event.wait(delay):
                    break
        finally:
            with self._lock:
                if self._state not in ("failed", "stop-timeout"):
                    self._state = "reader-stopped"
            self._connected.set()
            self._first_sample.set()

    def _set_transport_error(self, message: str) -> None:
        with self._lock:
            self._transport_error = message
            self._state = "reconnecting"
        LOGGER.info("%s: instrument=%s", message, self.instrument_id)

    def _inspect_acquisition(self) -> None:
        if self._client is None:
            return
        try:
            state = self._client.acquisition(self.instrument_id)
        except Exception as exc:
            LOGGER.info(
                "NHR acquisition state unavailable: instrument=%s reason=%s",
                self.instrument_id,
                exc,
            )
            return
        last_error = state.get("last_error")
        csv_path = state.get("csv_path")
        sample_count_value = state.get("sample_count")
        sample_count = (
            int(sample_count_value) if sample_count_value is not None else None
        )
        with self._lock:
            self._acquisition_csv_path = (
                str(csv_path) if csv_path is not None else None
            )
            self._acquisition_sample_count = sample_count
            if last_error:
                self._acquisition_error = str(last_error)
                self._error = (
                    f"NHR acquisition error: {last_error}; "
                    f"csv={csv_path}; samples={sample_count}"
                )
        if last_error:
            LOGGER.error(
                "NHR acquisition error: instrument=%s error=%s csv=%s samples=%s",
                self.instrument_id,
                last_error,
                csv_path,
                sample_count,
            )
