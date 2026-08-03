"""Measure the current CSV and NDJSON writers with identical CAN frames."""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from canpy.storage import CANFrame
from canpy.writers import CSVWriter, JSONWriter


Frame = CANFrame


def make_synthetic_frames(frame_count: int) -> List[Frame]:
    """Build deterministic frames for procedure checks, not format selection."""
    frames = []
    for index in range(frame_count):
        value = index % 256
        source_timestamp = 1_700_000_000.0 + index * 0.001
        frames.append(
            CANFrame(
                timestamp_utc=datetime.fromtimestamp(
                    source_timestamp,
                    tz=timezone.utc,
                ),
                source_timestamp=source_timestamp,
                can_id=0x100 + index % 32,
                dlc=8,
                data=bytes((value + offset) % 256 for offset in range(8)),
                is_extended=False,
                is_remote=False,
                is_error=False,
                parsed_signals={
                    "SyntheticCounter": index,
                    "SyntheticValue": value / 10.0,
                },
            )
        )
    return frames


def load_ndjson_frames(path: Path, limit: Optional[int] = None) -> List[Frame]:
    """Load a small existing NDJSON recording for identical writer replay."""
    frames = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid NDJSON at line {line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"NDJSON line {line_number} is not an object")
            frames.append(frame_from_record(value, line_number))
            if limit is not None and len(frames) >= limit:
                break

    if not frames:
        raise ValueError("The NDJSON input contains no frames")
    return frames


def frame_from_record(record: Dict[str, Any], line_number: int) -> CANFrame:
    """Convert current or legacy NDJSON fields into the canonical frame model."""
    timestamp_text = record.get("timestamp_utc")
    source_timestamp = record.get("source_timestamp", record.get("timestamp"))
    if source_timestamp is None:
        raise ValueError(f"NDJSON line {line_number} has no source timestamp")

    if timestamp_text:
        timestamp_utc = datetime.fromisoformat(
            str(timestamp_text).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    else:
        timestamp_utc = datetime.fromtimestamp(
            float(source_timestamp),
            tz=timezone.utc,
        )

    can_id_value = record.get("can_id_dec", record.get("can_id"))
    if can_id_value is None:
        raise ValueError(f"NDJSON line {line_number} has no CAN ID")
    can_id = (
        int(can_id_value, 0)
        if isinstance(can_id_value, str)
        else int(can_id_value)
    )

    data_hex = record.get("data_hex")
    if data_hex is not None:
        data = bytes.fromhex(str(data_hex))
    elif record.get("data_bytes") is not None:
        data = bytes(record["data_bytes"])
    else:
        raise ValueError(f"NDJSON line {line_number} has no CAN payload")

    return CANFrame(
        timestamp_utc=timestamp_utc,
        source_timestamp=float(source_timestamp),
        can_id=can_id,
        dlc=int(record["dlc"]),
        data=data,
        is_extended=bool(record.get("is_extended", False)),
        is_remote=bool(record.get("is_remote", False)),
        is_error=bool(record.get("is_error", False)),
        parsed_signals=record.get("parsed_signals", record.get("parsed")),
    )


def expected_signals(frames: Iterable[Frame]) -> Set[str]:
    """Collect parsed-signal columns used by the current CSV writer."""
    names: Set[str] = set()
    for frame in frames:
        parsed = frame.parsed_signals
        if isinstance(parsed, dict):
            names.update(str(name) for name in parsed)
    return names


def frame_time_seconds(frame: Frame) -> float:
    """Return the best common timeline value available on a baseline frame."""
    return frame.timestamp_utc.timestamp()


def capture_duration_seconds(frames: Sequence[Frame]) -> float:
    """Measure the time represented between the first and last ordered frame."""
    if len(frames) < 2:
        return 0.0
    return max(0.0, frame_time_seconds(frames[-1]) - frame_time_seconds(frames[0]))


def count_complete_records(format_name: str, path: Path) -> int:
    """Read a completed baseline output and return its data-record count."""
    if format_name == "csv":
        with path.open("r", newline="", encoding="utf-8") as handle:
            return sum(1 for _ in csv.DictReader(handle))

    with path.open("r", encoding="utf-8") as handle:
        count = 0
        for line in handle:
            if line.strip():
                json.loads(line)
                count += 1
        return count


def measure_writer(
    format_name: str,
    frames: Sequence[Frame],
    output_dir: Path,
) -> Dict[str, Any]:
    """Write all frames, close the file, then measure and validate the result."""
    signals = expected_signals(frames)
    writer_class = CSVWriter if format_name == "csv" else JSONWriter
    writer = writer_class(output_dir=str(output_dir), expected_signals=signals)
    paths = writer.start_streaming(filename=f"baseline_{format_name}")

    started = time.perf_counter()
    for frame in frames:
        writer.write_frame(frame)
    writer.stop_streaming()
    elapsed = time.perf_counter() - started

    output_path = Path(paths[format_name])
    size_bytes = output_path.stat().st_size
    complete_records = count_complete_records(format_name, output_path)
    frame_count = len(frames)

    return {
        "format": format_name,
        "path": str(output_path.resolve()),
        "frames": frame_count,
        "capture_seconds": capture_duration_seconds(frames),
        "complete_records": complete_records,
        "readback_ok": complete_records == frame_count,
        "size_bytes": size_bytes,
        "bytes_per_frame": size_bytes / frame_count,
        "write_seconds": elapsed,
        "frames_per_second": frame_count / elapsed if elapsed else 0.0,
    }


def run_baseline(frames: Sequence[Frame], output_dir: Path) -> List[Dict[str, Any]]:
    """Run the two current writers against the same in-memory frame sequence."""
    if not frames:
        raise ValueError("At least one frame is required")

    output_dir.mkdir(parents=True, exist_ok=True)
    return [
        measure_writer("csv", frames, output_dir),
        measure_writer("json", frames, output_dir),
    ]


def print_results(input_description: str, results: Sequence[Dict[str, Any]]) -> None:
    """Print a compact, copyable baseline report."""
    print()
    print(f"Input: {input_description}")
    print(
        "Format | Frames | Capture (s) | Size (bytes) | Bytes/frame | "
        "Write (s) | Frames/s | Readback"
    )
    print("-" * 102)
    for result in results:
        readback = "OK" if result["readback_ok"] else "FAILED"
        print(
            f"{result['format']:6} | "
            f"{result['frames']:6d} | "
            f"{result['capture_seconds']:11.3f} | "
            f"{result['size_bytes']:12d} | "
            f"{result['bytes_per_frame']:11.2f} | "
            f"{result['write_seconds']:9.4f} | "
            f"{result['frames_per_second']:8.1f} | "
            f"{readback}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure current CSV and NDJSON recording behavior."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--input-ndjson",
        type=Path,
        help="Small representative NDJSON capture to replay.",
    )
    source.add_argument(
        "--synthetic-frames",
        type=int,
        help="Deterministic frame count for procedure validation only.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of frames loaded from --input-ndjson.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for disposable baseline outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.synthetic_frames is not None:
        if args.synthetic_frames <= 0:
            raise SystemExit("--synthetic-frames must be greater than zero")
        frames = make_synthetic_frames(args.synthetic_frames)
        description = f"deterministic synthetic frames ({len(frames)})"
    else:
        if args.limit is not None and args.limit <= 0:
            raise SystemExit("--limit must be greater than zero")
        frames = load_ndjson_frames(args.input_ndjson, args.limit)
        description = f"{args.input_ndjson.resolve()} ({len(frames)} frames)"

    output_dir = args.output_dir.resolve()
    results = run_baseline(frames, output_dir)
    print_results(description, results)
    return 0 if all(result["readback_ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
