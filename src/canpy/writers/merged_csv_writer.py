"""Build a derived CSV by joining NHR samples with selected CAN signals."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, Mapping, Optional, Sequence, TextIO


class MergedCSVError(RuntimeError):
    """The two source CSV files could not be merged safely."""


@dataclass(frozen=True)
class MergeResult:
    path: str
    row_count: int


def load_signal_file(path: str) -> set[str]:
    """Load one DBC signal name per line, ignoring blanks and # comments."""
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
        raise MergedCSVError(
            f"Could not read merged signal file {path}: {exc}"
        ) from exc
    return signals


class MergedCSVWriter:
    """Perform a streaming backward-as-of join over closed source CSV files."""

    def __init__(self, stale_after_s: float = 2.0) -> None:
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
        can_start_timestamp, can_end_timestamp = self._can_time_bounds(can_path)
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")

        try:
            with can_path.open("r", newline="", encoding="utf-8-sig") as can_handle:
                with nhr_path.open(
                    "r", newline="", encoding="utf-8-sig"
                ) as nhr_handle:
                    row_count = self._merge_handles(
                        can_handle=can_handle,
                        nhr_handle=nhr_handle,
                        output_path=temporary,
                        signals=selected_signals,
                        can_start_timestamp=can_start_timestamp,
                        can_end_timestamp=can_end_timestamp,
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

        return MergeResult(path=str(destination.resolve()), row_count=row_count)

    def _merge_handles(
        self,
        *,
        can_handle: TextIO,
        nhr_handle: TextIO,
        output_path: Path,
        signals: Sequence[str],
        can_start_timestamp: float,
        can_end_timestamp: float,
    ) -> int:
        can_reader = csv.DictReader(can_handle)
        nhr_reader = csv.DictReader(nhr_handle)
        can_fields = self._require_header(can_reader, "CAN")
        nhr_fields = self._require_header(nhr_reader, "NHR")

        if "timestamp" not in can_fields and "timestamp_utc" not in can_fields:
            raise MergedCSVError(
                "CAN CSV is missing required timestamp or timestamp_utc column"
            )
        if "timestamp_utc" not in nhr_fields:
            raise MergedCSVError(
                "NHR CSV is missing required column: timestamp_utc"
            )
        missing_signals = sorted(set(signals) - set(can_fields))
        if missing_signals:
            raise MergedCSVError(
                "CAN CSV is missing selected signal column(s): "
                + ", ".join(missing_signals)
            )

        output_fields = [f"nhr_{field}" for field in nhr_fields]
        for signal in signals:
            output_fields.extend(
                (
                    f"can_{signal}",
                    f"can_{signal}_age_s",
                    f"can_{signal}_status",
                )
            )

        can_rows = self._timed_can_rows(can_reader)
        next_can = next(can_rows, None)
        signal_state: Dict[str, tuple[str, float]] = {}
        previous_nhr_timestamp: Optional[float] = None
        row_count = 0

        with output_path.open("w", newline="", encoding="utf-8") as output_handle:
            writer = csv.DictWriter(output_handle, fieldnames=output_fields)
            writer.writeheader()

            for line_number, nhr_row in enumerate(nhr_reader, start=2):
                nhr_timestamp = self._parse_nhr_timestamp(
                    nhr_row.get("timestamp_utc"), line_number
                )
                if (
                    previous_nhr_timestamp is not None
                    and nhr_timestamp < previous_nhr_timestamp
                ):
                    raise MergedCSVError(
                        f"NHR CSV timestamps are not monotonic at line {line_number}"
                    )
                previous_nhr_timestamp = nhr_timestamp
                if nhr_timestamp < can_start_timestamp:
                    continue
                if nhr_timestamp > can_end_timestamp:
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
                    value_column = f"can_{signal}"
                    age_column = f"can_{signal}_age_s"
                    status_column = f"can_{signal}_status"
                    state = signal_state.get(signal)
                    if state is None:
                        output_row[value_column] = ""
                        output_row[age_column] = ""
                        output_row[status_column] = "missing"
                    else:
                        value, signal_timestamp = state
                        age_s = nhr_timestamp - signal_timestamp
                        output_row[value_column] = value
                        output_row[age_column] = f"{age_s:.6f}"
                        output_row[status_column] = (
                            "stale" if age_s >= self.stale_after_s else "fresh"
                        )
                writer.writerow(output_row)
                row_count += 1

            # Validate the remainder even if the NHR recording ended first.
            for _ in can_rows:
                pass

        if row_count == 0:
            raise MergedCSVError(
                "CAN and NHR CSV files have no overlapping UTC time window"
            )
        return row_count

    def _can_time_bounds(self, path: Path) -> tuple[float, float]:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fields = self._require_header(reader, "CAN")
            if "timestamp" not in fields and "timestamp_utc" not in fields:
                raise MergedCSVError(
                    "CAN CSV is missing required timestamp or timestamp_utc column"
                )
            first: Optional[float] = None
            last: Optional[float] = None
            for timestamp, _ in self._timed_can_rows(reader):
                if first is None:
                    first = timestamp
                last = timestamp
        if first is None or last is None:
            raise MergedCSVError("CAN CSV contains no data rows")
        return first, last

    def _timed_can_rows(
        self, reader: Iterable[Mapping[str, str]]
    ) -> Iterator[tuple[float, Mapping[str, str]]]:
        previous_timestamp: Optional[float] = None
        for line_number, row in enumerate(reader, start=2):
            timestamp = self._parse_can_timestamp(row, line_number)
            if previous_timestamp is not None and timestamp < previous_timestamp:
                raise MergedCSVError(
                    f"CAN CSV timestamps are not monotonic at line {line_number}"
                )
            previous_timestamp = timestamp
            yield timestamp, row

    @classmethod
    def _parse_can_timestamp(
        cls, row: Mapping[str, str], line_number: int
    ) -> float:
        timestamp_utc = row.get("timestamp_utc")
        if timestamp_utc:
            return cls._parse_iso_timestamp(
                timestamp_utc, "CAN timestamp_utc", line_number
            )
        raw_timestamp = row.get("timestamp")
        try:
            return float(raw_timestamp)
        except (TypeError, ValueError) as exc:
            raise MergedCSVError(
                f"Invalid CAN timestamp at line {line_number}: {raw_timestamp!r}"
            ) from exc

    @staticmethod
    def _parse_nhr_timestamp(value: Optional[str], line_number: int) -> float:
        if not value:
            raise MergedCSVError(
                f"Missing NHR timestamp_utc at line {line_number}"
            )
        return MergedCSVWriter._parse_iso_timestamp(
            value, "NHR timestamp_utc", line_number
        )

    @staticmethod
    def _parse_iso_timestamp(
        value: str, label: str, line_number: int
    ) -> float:
        timestamp_text = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            timestamp = datetime.fromisoformat(timestamp_text)
        except ValueError as exc:
            raise MergedCSVError(
                f"Invalid {label} at line {line_number}: {value!r}"
            ) from exc
        if timestamp.tzinfo is None:
            raise MergedCSVError(
                f"{label} has no timezone at line {line_number}"
            )
        return timestamp.astimezone(timezone.utc).timestamp()

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
