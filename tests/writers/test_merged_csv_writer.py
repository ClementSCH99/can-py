from __future__ import annotations

import csv
from datetime import datetime, timezone

import pytest

from canpy.writers import MergedCSVError, MergedCSVWriter, load_signal_file


def write_csv(path, fieldnames, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def test_merge_uses_latest_non_future_can_values_and_freshness(tmp_path) -> None:
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    output_path = tmp_path / "merged.csv"
    write_csv(
        can_path,
        ["timestamp", "PackVoltage", "VehicleSpeed"],
        [
            {"timestamp": "100.0", "PackVoltage": "350", "VehicleSpeed": ""},
            {"timestamp": "101.0", "PackVoltage": "", "VehicleSpeed": "12"},
            {"timestamp": "103.0", "PackVoltage": "351", "VehicleSpeed": "13"},
        ],
    )
    write_csv(
        nhr_path,
        ["timestamp_utc", "instrument_id", "voltage_v"],
        [
            {"timestamp_utc": utc(99.0), "instrument_id": "nhr-1", "voltage_v": "349"},
            {"timestamp_utc": utc(101.5), "instrument_id": "nhr-1", "voltage_v": "350"},
            {"timestamp_utc": utc(103.0), "instrument_id": "nhr-1", "voltage_v": "351"},
        ],
    )

    result = MergedCSVWriter(stale_after_s=2.0).merge(
        can_csv_path=str(can_path),
        nhr_csv_path=str(nhr_path),
        output_path=str(output_path),
        signals=["PackVoltage", "VehicleSpeed"],
    )

    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert result.row_count == 2
    assert rows[0]["nhr_voltage_v"] == "350"
    assert rows[0]["can_PackVoltage"] == "350"
    assert rows[0]["can_PackVoltage_age_s"] == "1.500000"
    assert rows[0]["can_PackVoltage_status"] == "fresh"
    assert rows[1]["can_PackVoltage"] == "351"
    assert rows[1]["can_VehicleSpeed"] == "13"
    assert rows[1]["can_VehicleSpeed_status"] == "fresh"


def test_exact_stale_threshold_is_stale(tmp_path) -> None:
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    write_csv(
        can_path,
        ["timestamp", "SignalA"],
        [
            {"timestamp": "10", "SignalA": "1"},
            {"timestamp": "12", "SignalA": ""},
        ],
    )
    write_csv(nhr_path, ["timestamp_utc"], [{"timestamp_utc": utc(12)}])

    output_path = tmp_path / "merged.csv"
    MergedCSVWriter(stale_after_s=2.0).merge(
        can_csv_path=str(can_path),
        nhr_csv_path=str(nhr_path),
        output_path=str(output_path),
        signals=["SignalA"],
    )
    with output_path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["can_SignalA_status"] == "stale"


def test_can_timestamp_utc_is_preferred_and_output_is_intersection(tmp_path) -> None:
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    output_path = tmp_path / "merged.csv"
    write_csv(
        can_path,
        ["timestamp", "timestamp_utc", "SignalA"],
        [
            {"timestamp": "9000", "timestamp_utc": utc(10), "SignalA": "1"},
            {"timestamp": "9001", "timestamp_utc": utc(11), "SignalA": "2"},
        ],
    )
    write_csv(
        nhr_path,
        ["timestamp_utc"],
        [
            {"timestamp_utc": utc(9)},
            {"timestamp_utc": utc(10.5)},
            {"timestamp_utc": utc(12)},
        ],
    )

    result = MergedCSVWriter().merge(
        can_csv_path=str(can_path),
        nhr_csv_path=str(nhr_path),
        output_path=str(output_path),
        signals=["SignalA"],
    )

    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert result.row_count == 1
    assert rows[0]["nhr_timestamp_utc"] == utc(10.5)
    assert rows[0]["can_SignalA"] == "1"


def test_signal_file_supports_comments_and_blanks(tmp_path) -> None:
    signal_file = tmp_path / "signals.txt"
    signal_file.write_text(
        "# standard signals\nPackVoltage\n\nVehicleSpeed # optional\nPackVoltage\n",
        encoding="utf-8",
    )
    assert load_signal_file(str(signal_file)) == {"PackVoltage", "VehicleSpeed"}


@pytest.mark.parametrize(
    ("can_rows", "nhr_rows", "message"),
    [
        (
            [{"timestamp": "2", "SignalA": "1"}, {"timestamp": "1", "SignalA": "2"}],
            [{"timestamp_utc": utc(2)}],
            "CAN CSV timestamps are not monotonic",
        ),
        (
            [{"timestamp": "1", "SignalA": "1"}],
            [{"timestamp_utc": utc(2)}, {"timestamp_utc": utc(1)}],
            "NHR CSV timestamps are not monotonic",
        ),
    ],
)
def test_non_monotonic_sources_are_rejected(
    tmp_path, can_rows, nhr_rows, message
) -> None:
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    output_path = tmp_path / "merged.csv"
    write_csv(can_path, ["timestamp", "SignalA"], can_rows)
    write_csv(nhr_path, ["timestamp_utc"], nhr_rows)

    with pytest.raises(MergedCSVError, match=message):
        MergedCSVWriter().merge(
            can_csv_path=str(can_path),
            nhr_csv_path=str(nhr_path),
            output_path=str(output_path),
            signals=["SignalA"],
        )
    assert not output_path.exists()


def test_missing_selected_signal_is_rejected(tmp_path) -> None:
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    write_csv(can_path, ["timestamp"], [{"timestamp": "1"}])
    write_csv(nhr_path, ["timestamp_utc"], [{"timestamp_utc": utc(1)}])

    with pytest.raises(MergedCSVError, match="SignalA"):
        MergedCSVWriter().merge(
            can_csv_path=str(can_path),
            nhr_csv_path=str(nhr_path),
            output_path=str(tmp_path / "merged.csv"),
            signals=["SignalA"],
        )
