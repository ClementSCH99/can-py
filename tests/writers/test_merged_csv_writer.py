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


def test_merge_uses_latest_non_future_values_and_marks_freshness(tmp_path):
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    output_path = tmp_path / "merged.csv"
    write_csv(
        can_path,
        ["timestamp_utc", "maxCellV", "maxCellTemp"],
        [
            {"timestamp_utc": utc(100), "maxCellV": "4.10", "maxCellTemp": ""},
            {"timestamp_utc": utc(101), "maxCellV": "", "maxCellTemp": "35"},
            {"timestamp_utc": utc(103), "maxCellV": "4.15", "maxCellTemp": "36"},
        ],
    )
    write_csv(
        nhr_path,
        ["timestamp_utc", "voltage_v"],
        [
            {"timestamp_utc": utc(99), "voltage_v": "90"},
            {"timestamp_utc": utc(101.5), "voltage_v": "91"},
            {"timestamp_utc": utc(103), "voltage_v": "92"},
        ],
    )

    result = MergedCSVWriter(stale_after_s=2.5).merge(
        can_csv_path=str(can_path),
        nhr_csv_path=str(nhr_path),
        output_path=str(output_path),
        signals=["maxCellV", "maxCellTemp"],
    )

    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert result.row_count == 2
    assert rows[0]["can_maxCellV"] == "4.10"
    assert rows[0]["can_maxCellV_age_s"] == "1.500000"
    assert rows[0]["can_maxCellV_status"] == "fresh"
    assert rows[1]["can_maxCellV"] == "4.15"
    assert rows[1]["can_maxCellTemp"] == "36"
    assert result.can_start_utc == "1970-01-01T00:01:40Z"
    assert result.nhr_rows_merged == 2


def test_merge_rejects_non_overlapping_sources_without_partial_output(tmp_path):
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    output_path = tmp_path / "merged.csv"
    write_csv(can_path, ["timestamp_utc", "SignalA"], [
        {"timestamp_utc": utc(10), "SignalA": "1"}
    ])
    write_csv(nhr_path, ["timestamp_utc"], [{"timestamp_utc": utc(20)}])

    with pytest.raises(MergedCSVError, match="no overlapping UTC"):
        MergedCSVWriter().merge(
            can_csv_path=str(can_path),
            nhr_csv_path=str(nhr_path),
            output_path=str(output_path),
            signals=["SignalA"],
        )
    assert not output_path.exists()
    assert can_path.exists()
    assert nhr_path.exists()


def test_signal_file_supports_comments_blanks_and_duplicates(tmp_path):
    signal_file = tmp_path / "signals.txt"
    signal_file.write_text(
        "# BMS values\nmaxCellV\n\nmaxCellTemp # thermal\nmaxCellV\n",
        encoding="utf-8",
    )
    assert load_signal_file(str(signal_file)) == {"maxCellV", "maxCellTemp"}


def test_can_longer_than_nhr_is_reported_without_changing_can_source(tmp_path):
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    output_path = tmp_path / "merged.csv"
    write_csv(
        can_path,
        ["timestamp_utc", "SignalA"],
        [
            {"timestamp_utc": utc(8), "SignalA": "8"},
            {"timestamp_utc": utc(9), "SignalA": "9"},
            {"timestamp_utc": utc(10), "SignalA": "10"},
            {"timestamp_utc": utc(11), "SignalA": "11"},
            {"timestamp_utc": utc(12), "SignalA": "12"},
            {"timestamp_utc": utc(13), "SignalA": "13"},
        ],
    )
    write_csv(
        nhr_path,
        ["timestamp_utc", "voltage_v"],
        [
            {"timestamp_utc": utc(10), "voltage_v": "100"},
            {"timestamp_utc": utc(11), "voltage_v": "101"},
            {"timestamp_utc": utc(12), "voltage_v": "102"},
        ],
    )
    original_can = can_path.read_bytes()

    result = MergedCSVWriter().merge(
        can_csv_path=str(can_path),
        nhr_csv_path=str(nhr_path),
        output_path=str(output_path),
        signals=["SignalA"],
    )

    assert result.can_rows_before_nhr == 2
    assert result.can_rows_after_nhr == 1
    assert result.nhr_rows_merged == 3
    assert result.overlap_duration_s == 2.0
    assert can_path.read_bytes() == original_can


def test_merge_failure_preserves_sources_and_existing_destination(tmp_path):
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    output_path = tmp_path / "merged.csv"
    write_csv(can_path, ["timestamp_utc", "SignalA"], [{"timestamp_utc": utc(10), "SignalA": "1"}])
    write_csv(nhr_path, ["timestamp_utc"], [{"timestamp_utc": utc(10)}])
    output_path.write_text("previous-good-output", encoding="utf-8")
    original_can = can_path.read_bytes()
    original_nhr = nhr_path.read_bytes()

    with pytest.raises(MergedCSVError, match="missing selected signal"):
        MergedCSVWriter().merge(
            can_csv_path=str(can_path),
            nhr_csv_path=str(nhr_path),
            output_path=str(output_path),
            signals=["MissingSignal"],
        )

    assert can_path.read_bytes() == original_can
    assert nhr_path.read_bytes() == original_nhr
    assert output_path.read_text(encoding="utf-8") == "previous-good-output"
    assert not list(tmp_path.glob(".merged.csv.*.tmp"))


def test_non_utc_timestamp_is_rejected(tmp_path):
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    write_csv(
        can_path,
        ["timestamp_utc", "SignalA"],
        [{"timestamp_utc": "2026-09-15T08:00:00-04:00", "SignalA": "1"}],
    )
    write_csv(nhr_path, ["timestamp_utc"], [{"timestamp_utc": "2026-09-15T12:00:00Z"}])
    with pytest.raises(MergedCSVError, match="not UTC"):
        MergedCSVWriter().merge(
            can_csv_path=str(can_path),
            nhr_csv_path=str(nhr_path),
            output_path=str(tmp_path / "merged.csv"),
            signals=["SignalA"],
        )


def test_destination_cannot_overwrite_a_source(tmp_path):
    can_path = tmp_path / "can.csv"
    nhr_path = tmp_path / "nhr.csv"
    write_csv(can_path, ["timestamp_utc", "SignalA"], [{"timestamp_utc": utc(10), "SignalA": "1"}])
    write_csv(nhr_path, ["timestamp_utc"], [{"timestamp_utc": utc(10)}])
    original = can_path.read_bytes()
    with pytest.raises(MergedCSVError, match="must not overwrite"):
        MergedCSVWriter().merge(
            can_csv_path=str(can_path),
            nhr_csv_path=str(nhr_path),
            output_path=str(can_path),
            signals=["SignalA"],
        )
    assert can_path.read_bytes() == original


def test_battery_current_uses_nhr_convention_with_delayed_can_samples(tmp_path):
    can_path, nhr_path, output_path = (tmp_path / name for name in ("can.csv", "nhr.csv", "merged.csv"))
    # CAN changes 1 s after NHR at each stage; 5 s medians still describe the same stage.
    currents = [2.0, -3.0, 4.0, -2.0]
    can_rows = [{"timestamp_utc": utc(99), "batteryCurrent": "-2"}]
    nhr_rows = []
    for stage, current in enumerate(currents):
        start = 100 + stage * 5
        if stage:
            can_rows.append({"timestamp_utc": utc(start + 1), "batteryCurrent": str(-current)})
        for second in range(5):
            nhr_rows.append({"timestamp_utc": utc(start + second), "current_a": str(current)})
    can_rows.append({"timestamp_utc": utc(119), "batteryCurrent": "2"})
    write_csv(can_path, ["timestamp_utc", "batteryCurrent"], can_rows)
    write_csv(nhr_path, ["timestamp_utc", "current_a"], nhr_rows)
    original_can = can_path.read_bytes()
    result = MergedCSVWriter().merge(
        can_csv_path=str(can_path), nhr_csv_path=str(nhr_path),
        output_path=str(output_path), signals=["batteryCurrent"],
    )
    rows = list(csv.DictReader(output_path.open(newline="", encoding="utf-8")))
    assert rows[0]["can_batteryCurrent"] == "2.0"
    assert rows[10]["can_batteryCurrent"] == "-3.0"  # one second of CAN latency
    assert rows[11]["can_batteryCurrent"] == "4.0"
    assert result.current_normalization["verification"] == "plausible"
    assert result.current_normalization["can_factor"] == -1
    assert can_path.read_bytes() == original_can


def test_battery_current_contradiction_preserves_existing_output(tmp_path):
    can_path, nhr_path, output_path = (tmp_path / name for name in ("can.csv", "nhr.csv", "merged.csv"))
    write_csv(can_path, ["timestamp_utc", "batteryCurrent"], [
        {"timestamp_utc": utc(second), "batteryCurrent": "2"}
        for second in range(100, 121, 2)
    ])
    write_csv(nhr_path, ["timestamp_utc", "current_a"], [
        {"timestamp_utc": utc(second), "current_a": "2"} for second in range(100, 121)
    ])
    output_path.write_text("prior result", encoding="utf-8")
    with pytest.raises(MergedCSVError, match="contradict"):
        MergedCSVWriter().merge(
            can_csv_path=str(can_path), nhr_csv_path=str(nhr_path),
            output_path=str(output_path), signals=["batteryCurrent"],
        )
    assert output_path.read_text(encoding="utf-8") == "prior result"


def test_battery_current_rest_is_inconclusive_but_normalized(tmp_path):
    can_path, nhr_path, output_path = (tmp_path / name for name in ("can.csv", "nhr.csv", "merged.csv"))
    write_csv(can_path, ["timestamp_utc", "batteryCurrent"], [
        {"timestamp_utc": utc(100), "batteryCurrent": "-0.1"},
        {"timestamp_utc": utc(104), "batteryCurrent": "-0.1"},
    ])
    write_csv(nhr_path, ["timestamp_utc", "current_a"], [
        {"timestamp_utc": utc(second), "current_a": "0.1"} for second in range(100, 105)
    ])
    result = MergedCSVWriter().merge(
        can_csv_path=str(can_path), nhr_csv_path=str(nhr_path),
        output_path=str(output_path), signals=["batteryCurrent"],
    )
    assert result.current_normalization["verification"] == "inconclusive"
    rows = list(csv.DictReader(output_path.open(newline="", encoding="utf-8")))
    assert float(rows[0]["can_batteryCurrent"]) == pytest.approx(0.1)
