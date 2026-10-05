import json
from types import SimpleNamespace
from unittest.mock import patch

from canpy.capture_manifest import build_capture_manifest, write_json_atomic
from canpy.tools.merge_nhr_csv import _resolve_invocation, _write_report, _parser, main


def test_postprocess_command_accepts_exact_run_and_defaults_to_session(capsys):
    evidence = SimpleNamespace(
        run_id="run-123",
        workflow_state="passed",
        role="session_measurements",
        csv_path="C:/nhr/workflow-runs/run-123/measurements/session.csv",
    )
    result = SimpleNamespace(
        path="C:/out/merged.csv",
        can_start_utc="2026-09-15T12:00:00Z",
        can_end_utc="2026-09-15T12:01:00Z",
        nhr_start_utc="2026-09-15T12:00:10Z",
        nhr_end_utc="2026-09-15T12:00:50Z",
        overlap_duration_s=40.0,
        can_rows_before_nhr=3,
        can_rows_after_nhr=4,
        nhr_rows_merged=41,
    )
    with patch(
        "canpy.tools.merge_nhr_csv.run_merge", return_value=(evidence, result)
    ) as run_merge:
        exit_code = main(
            [
                "--can-csv", "can.csv",
                "--nhr-url", "http://127.0.0.1:9300",
                "--nhr-instrument", "nhr-79503",
                "--nhr-run-id", "run-123",
                "--output", "merged.csv",
                "--signals", "SignalA,SignalB",
            ]
        )
    assert exit_code == 0
    assert run_merge.call_args.kwargs["nhr_scope"] == "session"
    assert run_merge.call_args.kwargs["nhr_run_id"] == "run-123"
    assert "NHR rows merged: 41" in capsys.readouterr().out


def can_manifest(tmp_path):
    can_csv = tmp_path / "can_capture_20260916_101500.csv"
    can_csv.write_text("timestamp_utc,SignalA\n", encoding="utf-8")
    path = tmp_path / "can_capture_20260916_101500.manifest.json"
    payload = build_capture_manifest(
        manifest_path=path,
        capture_id="can_capture_20260916_101500",
        started_at_utc="2026-09-16T10:15:00Z",
        ended_at_utc="2026-09-16T10:16:00Z",
        final_state="completed",
        closure_reason="user_interrupt",
        frame_count=1,
        source_paths=[("csv", can_csv)],
        effective_config={},
        profile=None,
        dbc=None,
        nhr_identity={
            "service_url": "http://127.0.0.1:9300",
            "instrument_id": "nhr-79503",
            "source_id": "bms-poc-v2",
        },
        forwarding_statistics=None,
        merge_defaults={
            "scope": "sequence", "can_stale_after_s": 2.5, "signals": ["SignalA"]
        },
    )
    write_json_atomic(path, payload)
    return path, can_csv


def test_minimal_manifest_invocation_loads_defaults_and_exact_run(tmp_path, capsys):
    manifest, can_csv = can_manifest(tmp_path)
    evidence = SimpleNamespace(
        run_id="exact-run", workflow_state="passed", role="workflow_sequence",
        csv_path=str(tmp_path / "sequence.csv"), size_bytes=12, sha256="a" * 64,
    )
    result = SimpleNamespace(
        path=str(tmp_path / "not-created.csv"), can_start_utc="2026-09-16T10:15:00Z",
        can_end_utc="2026-09-16T10:16:00Z", nhr_start_utc="2026-09-16T10:15:10Z",
        nhr_end_utc="2026-09-16T10:15:50Z", overlap_duration_s=40.0,
        can_rows_before_nhr=1, can_rows_after_nhr=1, nhr_rows_merged=10,
    )
    with patch("canpy.tools.merge_nhr_csv.run_merge", return_value=(evidence, result)) as run:
        assert main(["--can-manifest", str(manifest), "--nhr-run-id", "exact-run"]) == 0
    kwargs = run.call_args.kwargs
    assert kwargs["can_csv"] == str(can_csv.resolve())
    assert kwargs["nhr_scope"] == "sequence"
    assert kwargs["signals"] == ["SignalA"]
    assert kwargs["nhr_run_id"] == "exact-run"
    assert "Explicit overrides: none" in capsys.readouterr().out


def test_manifest_overrides_are_explicit_and_conflicting_modes_fail(tmp_path):
    manifest, _ = can_manifest(tmp_path)
    args = _parser().parse_args(
        [
            "--can-manifest", str(manifest), "--nhr-run-id", "run-1",
            "--nhr-scope", "session", "--signals", "Other", "--can-stale-after", "4",
        ]
    )
    invocation = _resolve_invocation(args)
    assert invocation["nhr_scope"] == "session"
    assert invocation["signals"] == ["Other"]
    assert set(invocation["overrides"]) == {
        "--nhr-scope", "--signals", "--can-stale-after"
    }
    assert main(
        [
            "--can-manifest", str(manifest), "--can-csv", "other.csv",
            "--nhr-run-id", "run-1",
        ]
    ) == 1


def test_merge_report_is_separate_and_complete(tmp_path):
    manifest, _ = can_manifest(tmp_path)
    merged = tmp_path / "merged_capture_20260916_101500.csv"
    merged.write_text("nhr_timestamp_utc\n", encoding="utf-8")
    invocation = _resolve_invocation(
        _parser().parse_args(["--can-manifest", str(manifest), "--nhr-run-id", "run-1"])
    )
    evidence = SimpleNamespace(
        run_id="run-1", workflow_state="passed", role="workflow_sequence",
        csv_path=str(tmp_path / "sequence.csv"), size_bytes=42, sha256="c" * 64,
        manifest_path=str(tmp_path / "session-evidence.json"),
    )
    result = SimpleNamespace(
        path=str(merged), can_start_utc="2026-09-16T10:15:00Z",
        can_end_utc="2026-09-16T10:16:00Z", nhr_start_utc="2026-09-16T10:15:10Z",
        nhr_end_utc="2026-09-16T10:15:50Z", overlap_duration_s=40.0,
        can_rows_before_nhr=2, can_rows_after_nhr=3, nhr_rows_merged=41,
        normalization={"schema_version": 1, "charge_sign": "positive",
                       "signals": {"can_maxChargePower": {"output_unit": "W", "factor": -1000}}},
    )
    report_path = _write_report(invocation, evidence, result)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_path.name == "merged_capture_20260916_101500.report.json"
    assert report["capture_id"] == "can_capture_20260916_101500"
    assert report["nhr_run_id"] == "run-1"
    assert report["nhr_artifact"]["role"] == "workflow_sequence"
    assert report["can_rows_after_nhr"] == 3
    assert report["normalization"] == result.normalization
    assert manifest.read_bytes()
