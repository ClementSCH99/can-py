import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from canpy.capture import CANCapture
from canpy.config.manager import ConfigManager
from canpy.nhr import ExternalSnapshot
from canpy.storage import CANFrame


REQUIRED_DBC_SIGNALS = {
    "minCellTemp",
    "maxCellTemp",
    "minCellV",
    "maxCellV",
}


def frame():
    return CANFrame(
        timestamp_utc=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
        source_timestamp=123.0,
        can_id=0x431,
        dlc=8,
        data=b"\x00" * 8,
        is_extended=False,
        is_remote=False,
        is_error=False,
        parsed_signals={"minCellV": 3.2, "maxCellV": 4.1},
    )


def snapshot():
    return ExternalSnapshot(
        timestamp_utc=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
        health="ok",
        signals={
            "MinCellTemp": 18.0,
            "MaxCellTemp": 40.0,
            "MinCellVolt": 3.2,
            "MaxCellVolt": 4.1,
        },
    )


def statistics(*, sent_count=1, last_error=None):
    return SimpleNamespace(
        offered_count=1,
        sent_count=sent_count,
        dropped_count=0,
        coalesced_count=0,
        retry_count=0,
        rejected_count=0,
        last_error=last_error,
    )


def configured_capture(forwarder, assembler):
    config = ConfigManager()
    config.load_defaults_conf()
    config._settings["capture"].update(
        {"mode": "count", "count": 1, "no_console": True}
    )
    config._settings["dbc"]["file"] = "test.dbc"

    capture = CANCapture(
        config,
        nhr_forwarder=forwarder,
        nhr_snapshot_assembler=assembler,
    )
    capture.bus = Mock()
    capture.bus.recv.return_value = Mock()
    return capture


def test_capture_offers_snapshot_and_stops_worker():
    forwarder = Mock()
    forwarder.statistics.return_value = statistics()
    assembler = Mock(required_dbc_signals=REQUIRED_DBC_SIGNALS)
    assembler.observe.return_value = snapshot()
    capture = configured_capture(forwarder, assembler)

    with patch("canpy.capture.CANParser") as parser_class:
        parser_class.return_value.get_expected_signals.return_value = (
            REQUIRED_DBC_SIGNALS
        )
        parser_class.return_value.parse_frame.return_value = frame()
        result = capture.capture()

    assert result is True
    forwarder.start.assert_called_once_with()
    forwarder.offer.assert_called_once_with(assembler.observe.return_value)
    forwarder.stop.assert_called_once_with()


def test_forwarding_failure_does_not_prevent_can_recording():
    forwarder = Mock()
    forwarder.statistics.return_value = statistics(sent_count=0)
    forwarder.offer.side_effect = RuntimeError("NHR unavailable")
    assembler = Mock(required_dbc_signals=REQUIRED_DBC_SIGNALS)
    assembler.observe.return_value = snapshot()
    capture = configured_capture(forwarder, assembler)
    capture.config_manager._settings["output"]["formats"] = ["csv"]
    writer = Mock()

    with (
        patch("canpy.capture.CANParser") as parser_class,
        patch("canpy.capture.WriterFactory.create", return_value=writer),
    ):
        parser_class.return_value.get_expected_signals.return_value = (
            REQUIRED_DBC_SIGNALS
        )
        parser_class.return_value.parse_frame.return_value = frame()
        result = capture.capture()

    assert result is False
    writer.write_frame.assert_called_once_with(parser_class.return_value.parse_frame.return_value)
    writer.stop_streaming.assert_called_once_with()
    capture.bus.shutdown.assert_called_once_with()


def test_capture_rejects_dbc_missing_required_snapshot_signal():
    forwarder = Mock()
    assembler = Mock(required_dbc_signals=REQUIRED_DBC_SIGNALS)
    capture = configured_capture(forwarder, assembler)

    with patch("canpy.capture.CANParser") as parser_class:
        parser_class.return_value.get_expected_signals.return_value = {
            "minCellTemp",
            "maxCellTemp",
            "minCellV",
        }
        result = capture.capture()

    assert result is False
    forwarder.start.assert_not_called()
    capture.bus.recv.assert_not_called()


def test_capture_creates_merged_csv_after_sources_close(tmp_path):
    forwarder = Mock(
        base_url="http://127.0.0.1:9300", instrument_id="nhr-79503"
    )
    forwarder.statistics.return_value = statistics()
    assembler = Mock(required_dbc_signals=REQUIRED_DBC_SIGNALS)
    assembler.observe.return_value = snapshot()
    evidence = SimpleNamespace(
        csv_path=str(tmp_path / "nhr.csv"), sample_count=10, active=False
    )
    evidence_reader = Mock(return_value=evidence)
    capture = CANCapture(
        configured_capture(forwarder, assembler).config_manager,
        nhr_forwarder=forwarder,
        nhr_snapshot_assembler=assembler,
        merged_signals={"maxCellV"},
        nhr_run_id="run-123",
        nhr_evidence_reader=evidence_reader,
    )
    (tmp_path / "test.dbc").write_text("VERSION \"test\"", encoding="utf-8")
    (tmp_path / "can_capture_20260910.csv").write_text(
        "timestamp_utc,maxCellV\n", encoding="utf-8"
    )
    capture.config_manager._settings["dbc"]["file"] = str(tmp_path / "test.dbc")
    capture.config_manager._settings["output"]["directory"] = str(tmp_path)
    capture.bus = Mock()
    capture.bus.recv.return_value = Mock()
    writer = Mock()
    writer.start_streaming.return_value = {
        "csv": str(tmp_path / "can_capture_20260910.csv")
    }

    with (
        patch("canpy.capture.CANParser") as parser_class,
        patch("canpy.capture.WriterFactory.create", return_value=writer),
        patch.object(capture, "_write_merged_csv") as write_merged,
    ):
        parser_class.return_value.get_expected_signals.return_value = (
            REQUIRED_DBC_SIGNALS
        )
        parser_class.return_value.parse_frame.return_value = frame()
        capture.config_manager._settings["output"]["formats"] = ["csv"]
        result = capture.capture()

    assert result is True
    writer.stop_streaming.assert_called_once_with()
    write_merged.assert_called_once_with()
    manifest = json.loads(Path(capture._manifest_path).read_text(encoding="utf-8"))
    assert manifest["final_state"] == "completed"
    assert manifest["closure_reason"] == "count_limit"
    assert manifest["forwarding_statistics"]["sent_count"] == 1
    assert "run_id" not in json.dumps(manifest)


def test_ctrl_c_closes_can_before_resolving_already_finalized_run(tmp_path):
    events = []
    forwarder = Mock(base_url="http://127.0.0.1:9300", instrument_id="nhr-79503")
    forwarder.statistics.return_value = statistics()
    assembler = Mock(required_dbc_signals=REQUIRED_DBC_SIGNALS)
    evidence = SimpleNamespace(
        csv_path=str(tmp_path / "session.csv"),
        run_id="run-123",
        workflow_state="passed",
        role="session_measurements",
        size_bytes=42,
        sha256="c" * 64,
    )

    def read_evidence(*args, **kwargs):
        events.append("resolve_nhr")
        return evidence

    capture = CANCapture(
        configured_capture(forwarder, assembler).config_manager,
        nhr_forwarder=forwarder,
        nhr_snapshot_assembler=assembler,
        merged_signals={"maxCellV"},
        nhr_run_id="run-123",
        nhr_evidence_reader=read_evidence,
    )
    capture.config_manager._settings["capture"].update({"mode": "continuous", "count": None})
    capture.config_manager._settings["output"]["formats"] = ["csv"]
    (tmp_path / "test.dbc").write_text("VERSION \"test\"", encoding="utf-8")
    (tmp_path / "can.csv").write_text(
        "timestamp_utc,maxCellV\n", encoding="utf-8"
    )
    capture.config_manager._settings["dbc"]["file"] = str(tmp_path / "test.dbc")
    capture.config_manager._settings["output"]["directory"] = str(tmp_path)
    capture.bus = Mock()
    capture.bus.recv.side_effect = KeyboardInterrupt
    writer = Mock()
    writer.start_streaming.return_value = {"csv": str(tmp_path / "can.csv")}
    writer.stop_streaming.side_effect = lambda: events.append("close_can")
    merge_result = SimpleNamespace(
        path=str(tmp_path / "merged.csv"),
        can_start_utc="2026-09-15T12:00:00Z",
        can_end_utc="2026-09-15T12:00:01Z",
        nhr_start_utc="2026-09-15T12:00:00Z",
        nhr_end_utc="2026-09-15T12:00:01Z",
        overlap_duration_s=1.0,
        can_rows_before_nhr=0,
        can_rows_after_nhr=0,
        nhr_rows_merged=2,
        normalization={"schema_version": 1, "charge_sign": "positive"},
    )

    with (
        patch("canpy.capture.CANParser") as parser_class,
        patch("canpy.capture.WriterFactory.create", return_value=writer),
        patch("canpy.capture.MergedCSVWriter") as merged_writer,
    ):
        parser_class.return_value.get_expected_signals.return_value = REQUIRED_DBC_SIGNALS
        merged_writer.return_value.merge.return_value = merge_result
        assert capture.capture() is True

    assert events == ["close_can", "resolve_nhr"]
    manifest = json.loads(Path(capture._manifest_path).read_text(encoding="utf-8"))
    assert manifest["closure_reason"] == "user_interrupt"
    report = json.loads((tmp_path / "merged.report.json").read_text(encoding="utf-8"))
    assert report["normalization"] == merge_result.normalization


def test_ctrl_c_without_run_id_preserves_sources_and_prints_postprocess_command(
    tmp_path, capsys
):
    forwarder = Mock(base_url="http://127.0.0.1:9300", instrument_id="nhr-79503")
    forwarder.statistics.return_value = statistics()
    assembler = Mock(required_dbc_signals=REQUIRED_DBC_SIGNALS)
    evidence_reader = Mock()
    capture = CANCapture(
        configured_capture(forwarder, assembler).config_manager,
        nhr_forwarder=forwarder,
        nhr_snapshot_assembler=assembler,
        merged_signals={"maxCellV"},
        nhr_evidence_reader=evidence_reader,
    )
    (tmp_path / "test.dbc").write_text("VERSION \"test\"", encoding="utf-8")
    (tmp_path / "can.csv").write_text("timestamp_utc,maxCellV\n", encoding="utf-8")
    capture.config_manager._settings["dbc"]["file"] = str(tmp_path / "test.dbc")
    capture.config_manager._settings["output"]["directory"] = str(tmp_path)
    capture.config_manager._settings["capture"].update({"mode": "continuous", "count": None})
    capture.config_manager._settings["output"]["formats"] = ["csv"]
    capture.bus = Mock()
    capture.bus.recv.side_effect = KeyboardInterrupt
    writer = Mock()
    writer.start_streaming.return_value = {"csv": str(tmp_path / "can.csv")}

    with (
        patch("canpy.capture.CANParser") as parser_class,
        patch("canpy.capture.WriterFactory.create", return_value=writer),
    ):
        parser_class.return_value.get_expected_signals.return_value = REQUIRED_DBC_SIGNALS
        assert capture.capture() is True

    output = capsys.readouterr().out
    evidence_reader.assert_not_called()
    assert "canpy.tools.merge_nhr_csv" in output
    assert "--nhr-run-id REPLACE_WITH_EXACT_RUN_ID" in output
    assert "runtime" not in output


def test_capture_error_writes_failed_manifest_after_closing_writer(tmp_path):
    forwarder = Mock()
    forwarder.statistics.return_value = statistics()
    assembler = Mock(required_dbc_signals=REQUIRED_DBC_SIGNALS)
    capture = configured_capture(forwarder, assembler)
    capture.config_manager._settings["output"].update(
        {"formats": ["csv"], "directory": str(tmp_path)}
    )
    dbc = tmp_path / "test.dbc"
    dbc.write_text("VERSION \"test\"", encoding="utf-8")
    capture.config_manager._settings["dbc"]["file"] = str(dbc)
    source = tmp_path / "can.csv"
    source.write_text("timestamp_utc,maxCellV\n", encoding="utf-8")
    capture.bus.recv.side_effect = RuntimeError("CAN receive failed")
    writer = Mock()
    writer.start_streaming.return_value = {"csv": str(source)}

    with (
        patch("canpy.capture.CANParser") as parser_class,
        patch("canpy.capture.WriterFactory.create", return_value=writer),
    ):
        parser_class.return_value.get_expected_signals.return_value = REQUIRED_DBC_SIGNALS
        assert capture.capture() is False

    writer.stop_streaming.assert_called_once_with()
    manifest = json.loads(Path(capture._manifest_path).read_text(encoding="utf-8"))
    assert manifest["final_state"] == "failed"
    assert manifest["closure_reason"] == "capture_error"
    assert source.exists()


def test_duration_limit_writes_successful_manifest(tmp_path):
    config = ConfigManager()
    config.load_defaults_conf()
    config._settings["capture"].update({"mode": "duration", "duration": 1})
    config._settings["output"].update({"formats": ["csv"], "directory": str(tmp_path)})
    source = tmp_path / "can.csv"
    source.write_text("timestamp_utc\n", encoding="utf-8")
    capture = CANCapture(config)
    capture.bus = Mock()
    writer = Mock()
    writer.start_streaming.return_value = {"csv": str(source)}

    with (
        patch("canpy.capture.CANParser") as parser_class,
        patch("canpy.capture.WriterFactory.create", return_value=writer),
        patch("canpy.capture.time.time", side_effect=[0.0, 2.0]),
    ):
        parser_class.return_value.get_expected_signals.return_value = None
        assert capture.capture() is True

    manifest = json.loads(Path(capture._manifest_path).read_text(encoding="utf-8"))
    assert manifest["final_state"] == "completed"
    assert manifest["closure_reason"] == "duration_limit"
