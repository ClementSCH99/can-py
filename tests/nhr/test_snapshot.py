from datetime import datetime, timedelta, timezone
from pathlib import Path

from canpy import CANParser
from canpy.nhr import BMS_POC_V2_MAPPING, ExternalSnapshotAssembler
from canpy.storage import CANFrame


def frame(timestamp_utc, parsed_signals):
    return CANFrame(
        timestamp_utc=timestamp_utc,
        source_timestamp=123.0,
        can_id=0x431,
        dlc=8,
        data=b"\x00" * 8,
        is_extended=False,
        is_remote=False,
        is_error=False,
        parsed_signals=parsed_signals,
    )


def test_poc_mapping_matches_selected_dbc_and_snapshot_names():
    assert {
        item.dbc_name: (item.snapshot_name, item.unit)
        for item in BMS_POC_V2_MAPPING
    } == {
        "minCellTemp": ("MinCellTemp", "degC"),
        "maxCellTemp": ("MaxCellTemp", "degC"),
        "minCellV": ("MinCellVolt", "V"),
        "maxCellV": ("MaxCellVolt", "V"),
    }


def test_poc_mapping_signals_exist_in_reference_dbc():
    dbc_file = Path(__file__).parents[2] / "dbc" / "6.44.4.0.dbc"
    parser = CANParser(str(dbc_file))

    assert ExternalSnapshotAssembler(
        BMS_POC_V2_MAPPING
    ).required_dbc_signals <= parser.get_expected_signals()


def test_assembler_waits_for_complete_multi_frame_snapshot():
    assembler = ExternalSnapshotAssembler(BMS_POC_V2_MAPPING)
    voltage_time = datetime(2026, 9, 10, 12, 0, 1, tzinfo=timezone.utc)
    temperature_time = voltage_time + timedelta(milliseconds=100)

    assert assembler.observe(
        frame(voltage_time, {"minCellV": 3.25, "maxCellV": 4.10})
    ) is None
    snapshot = assembler.observe(
        frame(
            temperature_time,
            {"minCellTemp": 18.5, "maxCellTemp": 41.0},
        )
    )

    assert snapshot.timestamp_utc == voltage_time
    assert snapshot.signals == {
        "MinCellTemp": 18.5,
        "MaxCellTemp": 41.0,
        "MinCellVolt": 3.25,
        "MaxCellVolt": 4.10,
    }


def test_assembler_keeps_oldest_slow_signal_timestamp():
    assembler = ExternalSnapshotAssembler(BMS_POC_V2_MAPPING)
    initial_time = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    assembler.observe(
        frame(initial_time, {"minCellTemp": 18.5, "maxCellTemp": 41.0})
    )
    assembler.observe(
        frame(
            initial_time + timedelta(milliseconds=20),
            {"minCellV": 3.25, "maxCellV": 4.10},
        )
    )

    snapshot = assembler.observe(
        frame(
            initial_time + timedelta(milliseconds=220),
            {"minCellV": 3.24, "maxCellV": 4.11},
        )
    )

    assert snapshot.timestamp_utc == initial_time
    assert snapshot.signals["MinCellVolt"] == 3.24
