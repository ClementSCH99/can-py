import json
from datetime import datetime, timezone

import pytest

from canpy.storage import CANFrame
from canpy.tools.recording_baseline import (
    capture_duration_seconds,
    load_ndjson_frames,
    make_synthetic_frames,
    run_baseline,
)


def test_baseline_writes_and_reads_same_frames(tmp_path):
    frames = make_synthetic_frames(12)

    results = run_baseline(frames, tmp_path)

    assert [result["format"] for result in results] == ["csv", "json"]
    assert all(result["frames"] == 12 for result in results)
    assert all(
        result["capture_seconds"] == pytest.approx(0.011, abs=0.000001)
        for result in results
    )
    assert all(result["complete_records"] == 12 for result in results)
    assert all(result["readback_ok"] for result in results)
    assert all(result["size_bytes"] > 0 for result in results)


def test_load_ndjson_frames_respects_limit(tmp_path):
    input_path = tmp_path / "capture.ndjson"
    records = [
        {
            "timestamp_utc": frame.timestamp_utc.isoformat(),
            "source_timestamp": frame.source_timestamp,
            "can_id": frame.can_id,
            "dlc": frame.dlc,
            "data_hex": frame.data.hex(),
            "is_extended": frame.is_extended,
            "is_remote": frame.is_remote,
            "is_error": frame.is_error,
            "parsed_signals": frame.parsed_signals,
        }
        for frame in make_synthetic_frames(5)
    ]
    input_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    frames = load_ndjson_frames(input_path, limit=3)

    assert len(frames) == 3
    assert frames[0].can_id == 0x100


def test_capture_duration_prefers_host_utc():
    frames = [
        CANFrame(
            timestamp_utc=datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc),
            source_timestamp=500.0,
            can_id=0x100,
            dlc=0,
            data=b"",
            is_extended=False,
            is_remote=False,
            is_error=False,
        ),
        CANFrame(
            timestamp_utc=datetime(
                2026, 8, 3, 12, 0, 2, 500000, tzinfo=timezone.utc
            ),
            source_timestamp=900.0,
            can_id=0x100,
            dlc=0,
            data=b"",
            is_extended=False,
            is_remote=False,
            is_error=False,
        ),
    ]

    assert capture_duration_seconds(frames) == pytest.approx(2.5)


def test_load_ndjson_frames_rejects_incomplete_record(tmp_path):
    input_path = tmp_path / "capture.ndjson"
    valid_record = {
        "timestamp": 1.0,
        "can_id": "0x100",
        "dlc": 0,
        "data_hex": "",
    }
    input_path.write_text(
        json.dumps(valid_record) + '\n{"timestamp":',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid NDJSON at line 2"):
        load_ndjson_frames(input_path)
