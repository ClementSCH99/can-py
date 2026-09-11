from datetime import datetime, timezone
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
        nhr_evidence_reader=evidence_reader,
    )
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
