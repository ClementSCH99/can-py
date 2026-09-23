"""Build a derived CSV by joining NHR samples with selected CAN signals."""

from __future__ import annotations

import csv
import math
import os
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, Mapping, Optional, Sequence, TextIO


class MergedCSVError(RuntimeError):
    """The two source CSV files could not be merged safely."""


@dataclass(frozen=True)
class MergeResult:
    """Output identity and auditable UTC coverage for one derived CSV."""

    path: str
    row_count: int
    can_start_utc: str
    can_end_utc: str
    nhr_start_utc: str
    nhr_end_utc: str
    overlap_duration_s: float
    can_rows_before_nhr: int
    can_rows_after_nhr: int
    nhr_rows_merged: int
    current_normalization: Optional[dict] = None


@dataclass(frozen=True)
class _TimeProfile:
    start: float
    end: float
    row_count: int


def load_signal_file(path: str) -> set[str]:
    """Load one DBC signal name per line, ignoring blanks and comments."""
    signal_path = Path(path)
    if not signal_path.is_file():
        raise MergedCSVError(f"Merged signal file not found: {path}")
    signals: set[str] = set()
    try:
        with signal_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                signal = raw_line.split("#", 1)[0].strip()
                if signal:
                    signals.add(signal)
    except OSError as exc:
        raise MergedCSVError(f"Could not read merged signal file {path}: {exc}") from exc
    return signals


class MergedCSVWriter:
    """Perform a streaming backward-as-of join over closed source CSV files.

    Output rows follow the selected NHR grid inside the overlapping UTC window.
    CAN and NHR inputs are read-only. A unique same-directory temporary file is
    flushed and atomically replaced only after complete validation.
    """

    def __init__(self, stale_after_s: float = 2.5) -> None:
        if stale_after_s <= 0:
            raise ValueError("stale_after_s must be positive")
        self.stale_after_s = stale_after_s

    def merge(
        self,
        *,
        can_csv_path: str,
        nhr_csv_path: str,
        output_path: str,
        signals: Sequence[str],
    ) -> MergeResult:
        selected_signals = tuple(sorted(set(signals)))
        if not selected_signals:
            raise MergedCSVError("At least one CAN signal must be selected")
        can_path = self._require_file(can_csv_path, "CAN")
        nhr_path = self._require_file(nhr_csv_path, "NHR")
        can_profile = self._time_profile(can_path, "CAN")
        nhr_profile = self._time_profile(nhr_path, "NHR")
        overlap_start = max(can_profile.start, nhr_profile.start)
        overlap_end = min(can_profile.end, nhr_profile.end)
        if overlap_start > overlap_end:
            raise MergedCSVError("CAN and NHR CSV files have no overlapping UTC time window")

        can_rows_before, can_rows_after = self._count_can_outside_nhr(
            can_path, nhr_profile.start, nhr_profile.end
        )
        destination = Path(output_path)
        if destination.resolve() in {can_path.resolve(), nhr_path.resolve()}:
            raise MergedCSVError(
                "Merged CSV destination must not overwrite a CAN or NHR source"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            with can_path.open("r", newline="", encoding="utf-8-sig") as can_handle:
                with nhr_path.open("r", newline="", encoding="utf-8-sig") as nhr_handle:
                    row_count, current_audit = self._merge_handles(
                        can_handle=can_handle,
                        nhr_handle=nhr_handle,
                        output_path=temporary,
                        signals=selected_signals,
                        overlap_start=overlap_start,
                        overlap_end=overlap_end,
                    )
            os.replace(temporary, destination)
        except (MergedCSVError, OSError, csv.Error, ValueError) as exc:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            if isinstance(exc, MergedCSVError):
                raise
            raise MergedCSVError(f"Could not create merged CSV: {exc}") from exc

        return MergeResult(
            path=str(destination.resolve()),
            row_count=row_count,
            can_start_utc=self._format_utc(can_profile.start),
            can_end_utc=self._format_utc(can_profile.end),
            nhr_start_utc=self._format_utc(nhr_profile.start),
            nhr_end_utc=self._format_utc(nhr_profile.end),
            overlap_duration_s=max(0.0, overlap_end - overlap_start),
            can_rows_before_nhr=can_rows_before,
            can_rows_after_nhr=can_rows_after,
            nhr_rows_merged=row_count,
            current_normalization=current_audit,
        )

    def _merge_handles(
        self,
        *,
        can_handle: TextIO,
        nhr_handle: TextIO,
        output_path: Path,
        signals: Sequence[str],
        overlap_start: float,
        overlap_end: float,
    ) -> tuple[int, Optional[dict]]:
        can_reader = csv.DictReader(can_handle)
        nhr_reader = csv.DictReader(nhr_handle)
        can_fields = self._require_header(can_reader, "CAN")
        nhr_fields = self._require_header(nhr_reader, "NHR")
        self._require_timestamp_column(can_fields, "CAN")
        self._require_timestamp_column(nhr_fields, "NHR")
        missing_signals = sorted(set(signals) - set(can_fields))
        if missing_signals:
            raise MergedCSVError(
                "CAN CSV is missing selected signal column(s): " + ", ".join(missing_signals)
            )
        normalize_current = "batteryCurrent" in signals
        if normalize_current and "current_a" not in nhr_fields:
            raise MergedCSVError("NHR CSV is missing current_a for batteryCurrent normalization")

        output_fields = [f"nhr_{field}" for field in nhr_fields]
        for signal in signals:
            output_fields.extend(
                (f"can_{signal}", f"can_{signal}_age_s", f"can_{signal}_status")
            )
        can_rows = self._timed_rows(can_reader, "CAN")
        next_can = next(can_rows, None)
        signal_state: Dict[str, tuple[str, float]] = {}
        row_count = 0
        current_windows: Dict[int, list[tuple[float, float]]] = {}

        with output_path.open("w", newline="", encoding="utf-8") as output_handle:
            writer = csv.DictWriter(output_handle, fieldnames=output_fields)
            writer.writeheader()
            for nhr_timestamp, nhr_row in self._timed_rows(nhr_reader, "NHR"):
                if nhr_timestamp < overlap_start or nhr_timestamp > overlap_end:
                    continue
                while next_can is not None and next_can[0] <= nhr_timestamp:
                    can_timestamp, can_row = next_can
                    for signal in signals:
                        value = can_row.get(signal, "")
                        if value is not None and value.strip() != "":
                            signal_state[signal] = (value, can_timestamp)
                    next_can = next(can_rows, None)
                output_row = {
                    f"nhr_{field}": nhr_row.get(field, "") for field in nhr_fields
                }
                for signal in signals:
                    state = signal_state.get(signal)
                    if state is None:
                        output_row[f"can_{signal}"] = ""
                        output_row[f"can_{signal}_age_s"] = ""
                        output_row[f"can_{signal}_status"] = "missing"
                    else:
                        value, signal_timestamp = state
                        age_s = nhr_timestamp - signal_timestamp
                        if signal == "batteryCurrent":
                            try:
                                can_current = float(value)
                            except ValueError as exc:
                                raise MergedCSVError(f"Invalid CAN batteryCurrent: {value!r}") from exc
                            if not math.isfinite(can_current):
                                raise MergedCSVError("CAN batteryCurrent must be finite")
                            value = str(-can_current)
                            if age_s < self.stale_after_s:
                                raw_nhr = nhr_row.get("current_a", "")
                                try:
                                    nhr_current = float(raw_nhr)
                                except (TypeError, ValueError):
                                    nhr_current = math.nan
                                if math.isfinite(nhr_current):
                                    window = int((nhr_timestamp - overlap_start) // 5)
                                    current_windows.setdefault(window, []).append((can_current, nhr_current))
                        output_row[f"can_{signal}"] = value
                        output_row[f"can_{signal}_age_s"] = f"{age_s:.6f}"
                        output_row[f"can_{signal}_status"] = (
                            "stale" if age_s >= self.stale_after_s else "fresh"
                        )
                writer.writerow(output_row)
                row_count += 1
            for _ in can_rows:
                pass
            output_handle.flush()
            os.fsync(output_handle.fileno())
        if row_count == 0:
            raise MergedCSVError(
                "CAN and NHR UTC ranges intersect but contain no NHR row in the overlap"
            )
        current_audit = None
        if normalize_current:
            comparable = []
            for values in current_windows.values():
                if len(values) < 3:
                    continue
                can_median = statistics.median(item[0] for item in values)
                nhr_median = statistics.median(item[1] for item in values)
                if abs(can_median) < 0.5 or abs(nhr_median) < 0.5:
                    continue
                comparable.append((can_median, nhr_median))
            current_audit = {
                "can_signal": "batteryCurrent", "nhr_field": "current_a",
                "can_factor": -1, "reference_convention": "nhr",
                "window_s": 5, "active_threshold_a": 0.5,
                "relative_magnitude_tolerance": 0.2,
                "comparable_windows": len(comparable),
                "verification": "inconclusive",
            }
            if len(comparable) >= 3:
                opposite_fraction = sum(c * n < 0 for c, n in comparable) / len(comparable)
                median_relative_error = statistics.median(
                    abs(abs(c) - abs(n)) / max(abs(n), 0.5) for c, n in comparable
                )
                current_audit.update(
                    opposite_sign_fraction=opposite_fraction,
                    median_relative_magnitude_error=median_relative_error,
                )
                if opposite_fraction < 0.8 or median_relative_error > 0.2:
                    raise MergedCSVError(
                        "CAN batteryCurrent and NHR current_a contradict the configured "
                        "current normalization (5 s window plausibility check)"
                    )
                current_audit["verification"] = "plausible"
        return row_count, current_audit

    def _time_profile(self, path: Path, label: str) -> _TimeProfile:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            self._require_timestamp_column(self._require_header(reader, label), label)
            first: Optional[float] = None
            last: Optional[float] = None
            count = 0
            for timestamp, _ in self._timed_rows(reader, label):
                if first is None:
                    first = timestamp
                last = timestamp
                count += 1
        if first is None or last is None:
            raise MergedCSVError(f"{label} CSV contains no data rows")
        return _TimeProfile(first, last, count)

    def _count_can_outside_nhr(
        self, path: Path, nhr_start: float, nhr_end: float
    ) -> tuple[int, int]:
        before = after = 0
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            self._require_timestamp_column(self._require_header(reader, "CAN"), "CAN")
            for timestamp, _ in self._timed_rows(reader, "CAN"):
                if timestamp < nhr_start:
                    before += 1
                elif timestamp > nhr_end:
                    after += 1
        return before, after

    def _timed_rows(
        self, reader: Iterable[Mapping[str, str]], label: str
    ) -> Iterator[tuple[float, Mapping[str, str]]]:
        previous: Optional[float] = None
        for line_number, row in enumerate(reader, start=2):
            timestamp = self._parse_utc_timestamp(
                row.get("timestamp_utc"), f"{label} timestamp_utc", line_number
            )
            if previous is not None and timestamp < previous:
                raise MergedCSVError(
                    f"{label} CSV timestamps are not monotonic at line {line_number}"
                )
            previous = timestamp
            yield timestamp, row

    @staticmethod
    def _parse_utc_timestamp(value: Optional[str], label: str, line_number: int) -> float:
        if not value:
            raise MergedCSVError(f"Missing {label} at line {line_number}")
        timestamp_text = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            timestamp = datetime.fromisoformat(timestamp_text)
        except ValueError as exc:
            raise MergedCSVError(
                f"Invalid {label} at line {line_number}: {value!r}"
            ) from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
            raise MergedCSVError(f"{label} is not UTC at line {line_number}")
        return timestamp.timestamp()

    @staticmethod
    def _format_utc(value: float) -> str:
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _require_file(path: str, label: str) -> Path:
        candidate = Path(path)
        if not candidate.is_file():
            raise MergedCSVError(f"{label} CSV not found: {path}")
        return candidate

    @staticmethod
    def _require_header(reader: csv.DictReader, label: str) -> list[str]:
        if not reader.fieldnames:
            raise MergedCSVError(f"{label} CSV is empty or has no header")
        return list(reader.fieldnames)

    @staticmethod
    def _require_timestamp_column(fields: Sequence[str], label: str) -> None:
        if "timestamp_utc" not in fields:
            raise MergedCSVError(f"{label} CSV is missing required column: timestamp_utc")
