import csv
import hashlib
import json

import pytest

from canpy.nhr import NHRRecordingEvidenceError, read_nhr_workflow_evidence


def write_csv(path, rows=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp_utc", "voltage_v"])
        writer.writeheader()
        writer.writerows(rows or [{"timestamp_utc": "2026-09-15T12:00:00Z", "voltage_v": "100"}])


def describe(path, role, **extra):
    content = path.read_bytes()
    return {
        "role": role,
        "path": str(path.resolve()),
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        **extra,
    }


def finalized_fixture(tmp_path, run_id="run-123"):
    run_dir = tmp_path / "workflow-runs" / run_id
    session = run_dir / "measurements" / "session.csv"
    sequence = run_dir / "measurements" / "sequence.csv"
    stage0 = run_dir / "measurements" / "stages" / "01-charge.csv"
    stage1 = run_dir / "measurements" / "stages" / "02-rest.csv"
    for path in (session, sequence, stage0, stage1):
        write_csv(path)
    manifest_path = run_dir / "session-evidence.json"
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "instrument_id": "nhr-79503",
        "state": "finalized",
        "finalized": True,
        "files": [
            describe(session, "session_measurements"),
            describe(sequence, "workflow_sequence"),
            describe(stage0, "workflow_stage", stage_index=0),
            describe(stage1, "workflow_stage", stage_index=1),
        ],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    snapshot = {
        "run_id": run_id,
        "instrument_id": "nhr-79503",
        "state": "passed",
        "recording": {"finalized": True, "manifest_path": str(manifest_path.resolve())},
    }
    return snapshot, manifest, manifest_path


class FakeClient:
    def __init__(self, snapshots):
        self.snapshots = iter(snapshots)
        self.runtime_called = False

    def workflow_run(self, instrument_id, run_id):
        assert instrument_id == "nhr-79503"
        assert run_id == "run-123"
        return next(self.snapshots)

    def runtime(self, instrument_id):
        self.runtime_called = True
        raise AssertionError("surveillance runtime must never be used")


@pytest.mark.parametrize(
    ("scope", "stage_index", "role", "suffix"),
    [
        ("session", None, "session_measurements", "session.csv"),
        ("sequence", None, "workflow_sequence", "sequence.csv"),
        ("stage", 1, "workflow_stage", "02-rest.csv"),
    ],
)
def test_resolves_session_sequence_and_stage_from_exact_finalized_manifest(
    tmp_path, scope, stage_index, role, suffix
):
    snapshot, _, _ = finalized_fixture(tmp_path)
    client = FakeClient([snapshot])
    result = read_nhr_workflow_evidence(
        "http://127.0.0.1:9300",
        "nhr-79503",
        "run-123",
        scope=scope,
        stage_index=stage_index,
        client_factory=lambda _: client,
    )
    assert result.role == role
    assert result.csv_path.endswith(suffix)
    assert client.runtime_called is False


def test_active_and_finalizing_run_are_polled_until_terminal_and_finalized(tmp_path):
    final, _, manifest_path = finalized_fixture(tmp_path)
    active = {
        **final,
        "state": "running",
        "recording": {"finalized": False, "path": str(manifest_path.parent / "measurements/session.csv")},
    }
    finalizing = {**active, "state": "finalizing"}
    client = FakeClient([active, finalizing, final])
    result = read_nhr_workflow_evidence(
        "http://127.0.0.1:9300",
        "nhr-79503",
        "run-123",
        timeout_s=1,
        poll_interval_s=0.001,
        client_factory=lambda _: client,
    )
    assert result.workflow_state == "passed"


@pytest.mark.parametrize("requested", [3, 99])
def test_missing_stage_lists_available_indices(tmp_path, requested):
    snapshot, _, _ = finalized_fixture(tmp_path)
    with pytest.raises(NHRRecordingEvidenceError, match="available stage indices: 0, 1"):
        read_nhr_workflow_evidence(
            "http://127.0.0.1:9300",
            "nhr-79503",
            "run-123",
            scope="stage",
            stage_index=requested,
            client_factory=lambda _: FakeClient([snapshot]),
        )


def test_ambiguous_stage_lists_available_indices(tmp_path):
    snapshot, manifest, manifest_path = finalized_fixture(tmp_path)
    duplicate = dict(manifest["files"][-1])
    manifest["files"].append(duplicate)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(NHRRecordingEvidenceError, match="stage index 1 is ambiguous"):
        read_nhr_workflow_evidence(
            "http://127.0.0.1:9300",
            "nhr-79503",
            "run-123",
            scope="stage",
            stage_index=1,
            client_factory=lambda _: FakeClient([snapshot]),
        )


@pytest.mark.parametrize("field", ["size_bytes", "sha256"])
def test_invalid_artifact_size_or_hash_is_rejected(tmp_path, field):
    snapshot, manifest, manifest_path = finalized_fixture(tmp_path)
    artifact = manifest["files"][0]
    artifact[field] = artifact[field] + 1 if field == "size_bytes" else "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(NHRRecordingEvidenceError, match="mismatch"):
        read_nhr_workflow_evidence(
            "http://127.0.0.1:9300",
            "nhr-79503",
            "run-123",
            client_factory=lambda _: FakeClient([snapshot]),
        )


def test_terminal_unfinalized_run_is_rejected_without_surveillance_fallback(tmp_path):
    final, _, _ = finalized_fixture(tmp_path)
    final["recording"] = {"finalized": False, "error": "close failed"}
    client = FakeClient([final])
    with pytest.raises(NHRRecordingEvidenceError, match="not finalized"):
        read_nhr_workflow_evidence(
            "http://127.0.0.1:9300",
            "nhr-79503",
            "run-123",
            client_factory=lambda _: client,
        )
    assert client.runtime_called is False


def test_run_id_is_required_and_no_run_is_discovered():
    with pytest.raises(NHRRecordingEvidenceError, match="explicit NHR workflow run ID"):
        read_nhr_workflow_evidence(
            "http://127.0.0.1:9300", "nhr-79503", ""
        )
