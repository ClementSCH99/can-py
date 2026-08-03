import json

import pytest

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
    input_path.write_text(
        "\n".join(json.dumps(frame) for frame in make_synthetic_frames(5)) + "\n",
        encoding="utf-8",
    )

    frames = load_ndjson_frames(input_path, limit=3)

    assert len(frames) == 3
    assert frames[0]["can_id"] == "0x100"


def test_capture_duration_prefers_host_utc():
    frames = [
        {
            "timestamp_utc": "2026-08-03T12:00:00+00:00",
            "timestamp": 500.0,
        },
        {
            "timestamp_utc": "2026-08-03T12:00:02.5+00:00",
            "timestamp": 900.0,
        },
    ]

    assert capture_duration_seconds(frames) == pytest.approx(2.5)


def test_load_ndjson_frames_rejects_incomplete_record(tmp_path):
    input_path = tmp_path / "capture.ndjson"
    input_path.write_text('{"timestamp": 1.0}\n{"timestamp":', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid NDJSON at line 2"):
        load_ndjson_frames(input_path)
