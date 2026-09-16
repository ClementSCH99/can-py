"""Resolve finalized workflow evidence through the public NHR-RT contract."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional


TERMINAL_WORKFLOW_STATES = {"passed", "stopped", "failed", "interrupted"}
NHR_SCOPES = {"session", "sequence", "stage"}
ROLE_BY_SCOPE = {
    "session": "session_measurements",
    "sequence": "workflow_sequence",
    "stage": "workflow_stage",
}


class NHRRecordingEvidenceError(RuntimeError):
    """The requested NHR workflow evidence is not finalized or trustworthy."""


@dataclass(frozen=True)
class NHRRecordingEvidence:
    """Verified metadata for one immutable, run-owned NHR CSV artifact."""

    csv_path: str
    run_id: str
    instrument_id: str
    workflow_state: str
    scope: str
    role: str
    size_bytes: int
    sha256: str
    stage_index: Optional[int] = None
    manifest_path: Optional[str] = None


def read_nhr_workflow_evidence(
    base_url: str,
    instrument_id: str,
    run_id: str,
    *,
    scope: str = "session",
    stage_index: Optional[int] = None,
    timeout_s: float = 60.0,
    poll_interval_s: float = 0.5,
    client_factory: Optional[Callable[[str], Any]] = None,
) -> NHRRecordingEvidence:
    """Resolve and verify one finalized artifact for an exact workflow run.

    This function never reads ``runtime.acquisition.evidence_path`` and never
    discovers another run. The public run snapshot and its finalized
    ``session-evidence.json`` manifest are the only authorities used.
    """
    if not isinstance(run_id, str) or not run_id.strip():
        raise NHRRecordingEvidenceError(
            "An explicit NHR workflow run ID is required; no run was selected"
        )
    if scope not in NHR_SCOPES:
        raise NHRRecordingEvidenceError(
            f"Invalid NHR scope {scope!r}; expected session, sequence, or stage"
        )
    if scope == "stage" and (
        not isinstance(stage_index, int)
        or isinstance(stage_index, bool)
        or stage_index < 0
    ):
        raise NHRRecordingEvidenceError(
            "--nhr-stage-index must be a non-negative integer when scope=stage"
        )
    if scope != "stage" and stage_index is not None:
        raise NHRRecordingEvidenceError(
            "--nhr-stage-index is valid only when scope=stage"
        )
    if timeout_s <= 0 or poll_interval_s <= 0:
        raise NHRRecordingEvidenceError(
            "NHR finalization timeout and poll interval must be positive"
        )

    client = _make_client(base_url, client_factory)
    snapshot = _wait_for_finalized_run(
        client,
        instrument_id,
        run_id,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
    )
    return _artifact_from_snapshot(
        snapshot,
        instrument_id=instrument_id,
        run_id=run_id,
        scope=scope,
        stage_index=stage_index,
    )


def read_nhr_recording_evidence(
    base_url: str,
    instrument_id: str,
    run_id: str,
    **kwargs: Any,
) -> NHRRecordingEvidence:
    """Compatibility name for exact-run finalized workflow evidence."""
    return read_nhr_workflow_evidence(base_url, instrument_id, run_id, **kwargs)


def _make_client(base_url: str, client_factory: Optional[Callable[[str], Any]]) -> Any:
    if client_factory is not None:
        return client_factory(base_url)
    try:
        from nhr9300 import NHRServiceClient
    except ImportError as exc:
        raise NHRRecordingEvidenceError(
            "nhr9300 is not installed; finalized workflow evidence cannot be read"
        ) from exc
    try:
        return NHRServiceClient(base_url)
    except Exception as exc:
        raise NHRRecordingEvidenceError(
            f"Could not initialize NHR client: {type(exc).__name__}: {exc}"
        ) from exc


def _wait_for_finalized_run(
    client: Any,
    instrument_id: str,
    run_id: str,
    *,
    timeout_s: float,
    poll_interval_s: float,
) -> Mapping[str, Any]:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            snapshot = client.workflow_run(instrument_id, run_id)
        except Exception as exc:
            raise NHRRecordingEvidenceError(
                f"Could not read NHR workflow run {run_id}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(snapshot, Mapping):
            raise NHRRecordingEvidenceError(
                f"NHR workflow run {run_id} returned an invalid snapshot"
            )
        if snapshot.get("run_id") != run_id:
            raise NHRRecordingEvidenceError(
                f"NHR service returned run {snapshot.get('run_id')!r} instead of {run_id!r}"
            )
        if snapshot.get("instrument_id") != instrument_id:
            raise NHRRecordingEvidenceError(
                "NHR workflow snapshot instrument does not match the requested instrument"
            )
        state = snapshot.get("state")
        recording = snapshot.get("recording")
        finalized = (
            isinstance(recording, Mapping) and recording.get("finalized") is True
        )
        if state in TERMINAL_WORKFLOW_STATES:
            if not finalized:
                detail = recording.get("error") if isinstance(recording, Mapping) else None
                suffix = f": {detail}" if detail else ""
                raise NHRRecordingEvidenceError(
                    f"NHR workflow run {run_id} is terminal ({state}) but its "
                    f"recording is not finalized{suffix}"
                )
            return snapshot
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise NHRRecordingEvidenceError(
                f"Timed out after {timeout_s:g} s waiting for NHR workflow run "
                f"{run_id} to become terminal with recording.finalized=true "
                f"(last state: {state})"
            )
        time.sleep(min(poll_interval_s, remaining))


def _artifact_from_snapshot(
    snapshot: Mapping[str, Any],
    *,
    instrument_id: str,
    run_id: str,
    scope: str,
    stage_index: Optional[int],
) -> NHRRecordingEvidence:
    recording = snapshot.get("recording")
    if not isinstance(recording, Mapping):
        raise NHRRecordingEvidenceError("Finalized run is missing recording metadata")
    raw_manifest_path = recording.get("manifest_path")
    if not isinstance(raw_manifest_path, str) or not raw_manifest_path.strip():
        raise NHRRecordingEvidenceError(
            "Finalized run does not expose session-evidence.json"
        )
    manifest_path = Path(raw_manifest_path)
    if not manifest_path.is_absolute() or not manifest_path.is_file():
        raise NHRRecordingEvidenceError(
            f"Finalized evidence manifest not found: {raw_manifest_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NHRRecordingEvidenceError(
            f"Could not read finalized evidence manifest {manifest_path}: {exc}"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise NHRRecordingEvidenceError("Finalized evidence manifest is not an object")
    if manifest.get("run_id") != run_id or manifest.get("instrument_id") != instrument_id:
        raise NHRRecordingEvidenceError(
            "Finalized evidence manifest identity does not match the requested run"
        )
    if manifest.get("finalized") is not True:
        raise NHRRecordingEvidenceError("Evidence manifest is not finalized")
    if manifest_path.parent.name != run_id:
        raise NHRRecordingEvidenceError(
            "Evidence manifest does not belong to the requested run directory"
        )
    files = manifest.get("files")
    if not isinstance(files, list):
        raise NHRRecordingEvidenceError("Evidence manifest files list is invalid")

    role = ROLE_BY_SCOPE[scope]
    candidates = [
        item
        for item in files
        if isinstance(item, Mapping) and item.get("role") == role
    ]
    if scope == "stage":
        available = sorted(
            {
                item.get("stage_index")
                for item in candidates
                if isinstance(item.get("stage_index"), int)
                and not isinstance(item.get("stage_index"), bool)
            }
        )
        candidates = [
            item for item in candidates if item.get("stage_index") == stage_index
        ]
        if len(candidates) != 1:
            available_text = ", ".join(str(value) for value in available) or "none"
            reason = "ambiguous" if len(candidates) > 1 else "not found"
            raise NHRRecordingEvidenceError(
                f"NHR stage index {stage_index} is {reason}; available stage indices: "
                f"{available_text}"
            )
    elif len(candidates) != 1:
        raise NHRRecordingEvidenceError(
            f"Expected exactly one finalized {role} artifact, found {len(candidates)}"
        )

    artifact = candidates[0]
    artifact_path = _verify_artifact(artifact, manifest_path.parent, role)
    return NHRRecordingEvidence(
        csv_path=str(artifact_path),
        run_id=run_id,
        instrument_id=instrument_id,
        workflow_state=str(snapshot.get("state")),
        scope=scope,
        role=role,
        size_bytes=int(artifact["size_bytes"]),
        sha256=str(artifact["sha256"]),
        stage_index=stage_index,
        manifest_path=str(manifest_path.resolve()),
    )


def _verify_artifact(
    artifact: Mapping[str, Any], run_directory: Path, expected_role: str
) -> Path:
    if artifact.get("role") != expected_role:
        raise NHRRecordingEvidenceError("Selected NHR artifact role changed unexpectedly")
    raw_path = artifact.get("path")
    size_bytes = artifact.get("size_bytes")
    expected_sha = artifact.get("sha256")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise NHRRecordingEvidenceError("Selected NHR artifact has no path")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
        raise NHRRecordingEvidenceError("Selected NHR artifact has invalid size_bytes")
    if (
        not isinstance(expected_sha, str)
        or len(expected_sha) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in expected_sha)
    ):
        raise NHRRecordingEvidenceError("Selected NHR artifact has invalid SHA-256")
    path = Path(raw_path)
    if not path.is_absolute() or not path.is_file():
        raise NHRRecordingEvidenceError(f"Selected NHR artifact not found: {raw_path}")
    resolved = path.resolve()
    try:
        resolved.relative_to(run_directory.resolve())
    except ValueError as exc:
        raise NHRRecordingEvidenceError(
            "Selected NHR artifact is outside the requested run directory"
        ) from exc

    digest = hashlib.sha256()
    observed_size = 0
    try:
        with resolved.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
                observed_size += len(block)
    except OSError as exc:
        raise NHRRecordingEvidenceError(
            f"Could not verify selected NHR artifact {resolved}: {exc}"
        ) from exc
    if observed_size != size_bytes:
        raise NHRRecordingEvidenceError(
            f"NHR artifact size mismatch: manifest={size_bytes}, actual={observed_size}"
        )
    observed_sha = digest.hexdigest()
    if observed_sha.lower() != expected_sha.lower():
        raise NHRRecordingEvidenceError(
            f"NHR artifact SHA-256 mismatch: manifest={expected_sha}, actual={observed_sha}"
        )
    return resolved
