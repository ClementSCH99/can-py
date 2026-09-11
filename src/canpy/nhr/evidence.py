"""Read NHR acquisition evidence metadata through the public service API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class NHRRecordingEvidenceError(RuntimeError):
    """The NHR service did not expose usable acquisition evidence."""


@dataclass(frozen=True)
class NHRRecordingEvidence:
    """Read-only metadata needed to build a CAN/NHR merged CSV."""

    csv_path: str
    sample_count: int
    active: bool


def read_nhr_recording_evidence(
    base_url: str, instrument_id: str
) -> NHRRecordingEvidence:
    """Return the current acquisition CSV without requesting NHR control.

    Relative evidence paths are resolved from the absolute output directory
    advertised by the service. This lets CAN-PY and nhr-rt run from different
    working directories while still referring to the same local file.
    """
    try:
        from nhr9300 import NHRServiceClient
    except ImportError as exc:
        raise NHRRecordingEvidenceError(
            "nhr9300 is not installed; the NHR CSV path cannot be read"
        ) from exc

    try:
        client = NHRServiceClient(base_url)
        configuration = client.configuration()
        runtime = client.runtime(instrument_id)
    except Exception as exc:
        raise NHRRecordingEvidenceError(
            f"Could not read NHR runtime evidence: {type(exc).__name__}: {exc}"
        ) from exc

    acquisition = runtime.get("acquisition")
    if not isinstance(acquisition, Mapping):
        raise NHRRecordingEvidenceError(
            "NHR runtime is missing acquisition metadata"
        )
    raw_path = acquisition.get("evidence_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise NHRRecordingEvidenceError(
            "NHR runtime does not expose an acquisition CSV path"
        )

    csv_path = Path(raw_path)
    if not csv_path.is_absolute():
        diagnostic = configuration.get("output_dir_diagnostic")
        output_dir = (
            diagnostic.get("path") if isinstance(diagnostic, Mapping) else None
        )
        if not isinstance(output_dir, str) or not output_dir.strip():
            raise NHRRecordingEvidenceError(
                "Relative NHR evidence path has no advertised output directory"
            )
        csv_path = Path(output_dir) / csv_path.name

    sample_count = acquisition.get("sample_count")
    if not isinstance(sample_count, int) or isinstance(sample_count, bool):
        raise NHRRecordingEvidenceError(
            "NHR runtime acquisition sample_count is invalid"
        )
    active = acquisition.get("active")
    if not isinstance(active, bool):
        raise NHRRecordingEvidenceError(
            "NHR runtime acquisition active flag is invalid"
        )

    return NHRRecordingEvidence(
        csv_path=str(csv_path.resolve()),
        sample_count=sample_count,
        active=active,
    )
