from types import SimpleNamespace
from unittest.mock import patch

import pytest

from canpy.nhr import NHRRecordingEvidenceError, read_nhr_recording_evidence


class FakeClient:
    def __init__(self, base_url):
        self.base_url = base_url

    def configuration(self):
        return {"output_dir_diagnostic": {"path": "C:/nhr-runs/test"}}

    def runtime(self, instrument_id):
        assert instrument_id == "nhr-79503"
        return {
            "acquisition": {
                "evidence_path": "runs/nhr-79503_20260910.csv",
                "sample_count": 42,
                "active": False,
            }
        }


def test_relative_nhr_csv_is_resolved_from_advertised_output_directory():
    fake_module = SimpleNamespace(NHRServiceClient=FakeClient)
    with patch.dict("sys.modules", {"nhr9300": fake_module}):
        result = read_nhr_recording_evidence(
            "http://127.0.0.1:9300", "nhr-79503"
        )

    assert result.csv_path.replace("\\", "/") == (
        "C:/nhr-runs/test/nhr-79503_20260910.csv"
    )
    assert result.sample_count == 42
    assert result.active is False


def test_missing_runtime_evidence_path_is_rejected():
    class MissingPathClient(FakeClient):
        def runtime(self, instrument_id):
            return {"acquisition": {"sample_count": 0, "active": False}}

    fake_module = SimpleNamespace(NHRServiceClient=MissingPathClient)
    with patch.dict("sys.modules", {"nhr9300": fake_module}):
        with pytest.raises(NHRRecordingEvidenceError, match="CSV path"):
            read_nhr_recording_evidence(
                "http://127.0.0.1:9300", "nhr-79503"
            )
