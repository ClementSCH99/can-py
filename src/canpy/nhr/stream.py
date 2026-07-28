"""Consume NHR9300 measurements without exposing instrument commands."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Mapping, Optional, Protocol


class NHRStreamError(RuntimeError):
    """The read-only NHR measurement stream could not be used."""


class _NHRClient(Protocol):
    def connect(self, instrument_id: str) -> Mapping[str, Any]:
        ...

    def disconnect(self, instrument_id: str) -> Mapping[str, Any]:
        ...

    def stream(self, instrument_id: str) -> Iterator[Mapping[str, Any]]:
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
    """Timing and completeness evidence for one client-side stream."""

    received_count: int
    first_sample_delay_s: Optional[float]
    observed_rate_hz: Optional[float]
    dropped_count: int
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
    """Own a background SSE reader and retain only a bounded sample backlog."""

    def __init__(
        self,
        instrument_id: str,
        base_url: str = "http://127.0.0.1:9300",
        stale_after_s: float = 2.0,
        queue_size: int = 100,
        client_factory: Callable[[str], _NHRClient] = _create_client,
    ) -> None:
        if not instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        if stale_after_s <= 0:
            raise ValueError("stale_after_s must be positive")
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        self.instrument_id = instrument_id
        self.base_url = base_url.rstrip("/")
        self.stale_after_s = stale_after_s
        self._client_factory = client_factory
        self._samples: "queue.Queue[NHRMeasurement]" = queue.Queue(queue_size)
        self._latest: Optional[NHRMeasurement] = None
        self._error: Optional[str] = None
        self._client: Optional[_NHRClient] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._first_sample = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._started_monotonic: Optional[float] = None
        self._first_received_monotonic: Optional[float] = None
        self._last_received_monotonic: Optional[float] = None
        self._received_count = 0
        self._dropped_count = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def error(self) -> Optional[str]:
        with self._lock:
            return self._error

    @property
    def buffered_sample_count(self) -> int:
        return self._samples.qsize()

    def start(self, timeout_s: float = 10.0) -> "NHRMeasurementStream":
        """Connect and wait until the first valid measurement is available."""
        if self.running:
            return self
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._stop.clear()
        self._ready.clear()
        self._first_sample.clear()
        while True:
            try:
                self._samples.get_nowait()
            except queue.Empty:
                break
        with self._lock:
            self._error = None
            self._latest = None
            self._started_monotonic = time.monotonic()
            self._first_received_monotonic = None
            self._last_received_monotonic = None
            self._received_count = 0
            self._dropped_count = 0
        self._thread = threading.Thread(
            target=self._run,
            name=f"nhr-stream-{self.instrument_id}",
            daemon=True,
        )
        self._thread.start()
        deadline = time.monotonic() + timeout_s
        if not self._ready.wait(max(0.0, deadline - time.monotonic())):
            self.stop()
            raise NHRStreamError(
                f"Timed out connecting to NHR service at {self.base_url}"
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
        self._stop.set()
        client = self._client
        if client is not None:
            try:
                client.disconnect(self.instrument_id)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout_s)
            if self._thread.is_alive():
                with self._lock:
                    self._error = (
                        f"NHR stream did not stop within {timeout_s:.1f} seconds"
                    )
            else:
                self._thread = None

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
            error=error,
        )

    def _publish(self, measurement: NHRMeasurement) -> None:
        received_at = time.monotonic()
        with self._lock:
            if self._first_received_monotonic is None:
                self._first_received_monotonic = received_at
            self._last_received_monotonic = received_at
            self._received_count += 1
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
        connected = False
        try:
            self._client = self._client_factory(self.base_url)
            self._client.connect(self.instrument_id)
            connected = True
            self._ready.set()
            for raw_measurement in self._client.stream(self.instrument_id):
                if self._stop.is_set():
                    break
                self._publish(NHRMeasurement.from_mapping(raw_measurement))
        except Exception as exc:
            with self._lock:
                self._error = f"NHR stream failed: {exc}"
            self._ready.set()
        finally:
            with self._lock:
                if (
                    not self._stop.is_set()
                    and self._received_count == 0
                    and self._error is None
                ):
                    self._error = "NHR stream ended before its first measurement"
            if connected and not self._stop.is_set() and self._client is not None:
                try:
                    self._client.disconnect(self.instrument_id)
                except Exception:
                    pass
            self._ready.set()
            self._first_sample.set()
