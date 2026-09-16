import json
from pathlib import Path

import pytest

from canpy.capture_manifest import (
    CaptureManifestError,
    build_capture_manifest,
    load_capture_manifest,
    portable_relative_path,
    validate_portable_path,
    write_json_atomic,
)


def manifest_payload(tmp_path, *, final_state="completed", closure_reason="count_limit"):
    source = tmp_path / "can_capture_20260916_101500.csv"
    source.write_text("timestamp_utc,SignalA\n", encoding="utf-8")
    manifest_path = tmp_path / "can_capture_20260916_101500.manifest.json"
    payload = build_capture_manifest(
        manifest_path=manifest_path,
        capture_id="can_capture_20260916_101500",
        started_at_utc="2026-09-16T14:15:00Z",
        ended_at_utc="2026-09-16T14:16:00Z",
        final_state=final_state,
        closure_reason=closure_reason,
        frame_count=10,
        source_paths=[("csv", source)],
        effective_config={"can": {"bitrate": 500000}},
        profile={"path": "configs/canpy/profile.yaml", "sha256": "a" * 64},
        dbc={"path": "dbc/test.dbc", "sha256": "b" * 64},
        nhr_identity={
            "service_url": "http://127.0.0.1:9300",
            "instrument_id": "nhr-79503",
            "source_id": "bms-poc-v2",
        },
        forwarding_statistics={"sent_count": 4},
        merge_defaults={
            "scope": "sequence", "can_stale_after_s": 2.5, "signals": ["SignalA"]
        },
    )
    return manifest_path, source, payload


def test_manifest_is_atomic_portable_and_contains_no_run_id(tmp_path):
    manifest_path, _, payload = manifest_payload(tmp_path)
    write_json_atomic(manifest_path, payload)
    loaded = load_capture_manifest(manifest_path)
    assert loaded["sources"][0]["path"] == "can_capture_20260916_101500.csv"
    assert loaded["forwarding_statistics"]["sent_count"] == 4
    assert "run_id" not in json.dumps(loaded)
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("value", ["C:/capture.csv", "../capture.csv", "a\\b.csv", "a//b.csv"])
def test_manifest_rejects_nonportable_paths(value):
    with pytest.raises(CaptureManifestError):
        validate_portable_path(value)


def test_manifest_rejects_source_outside_root(tmp_path):
    outside = tmp_path.parent / "outside.csv"
    outside.write_text("x", encoding="utf-8")
    try:
        with pytest.raises(CaptureManifestError, match="outside"):
            portable_relative_path(outside, tmp_path)
    finally:
        outside.unlink()


def test_failed_capture_manifest_is_written_but_not_accepted_for_merge(tmp_path):
    manifest_path, source, payload = manifest_payload(
        tmp_path, final_state="failed", closure_reason="capture_error"
    )
    write_json_atomic(manifest_path, payload)
    assert source.exists()
    with pytest.raises(CaptureManifestError, match="not completed"):
        load_capture_manifest(manifest_path)


def test_atomic_failure_preserves_source(tmp_path, monkeypatch):
    manifest_path, source, payload = manifest_payload(tmp_path)

    def fail_replace(*args):
        raise OSError("replace failed")

    monkeypatch.setattr("canpy.capture_manifest.os.replace", fail_replace)
    with pytest.raises(CaptureManifestError, match="replace failed"):
        write_json_atomic(manifest_path, payload)
    assert source.exists()
    assert not manifest_path.exists()
