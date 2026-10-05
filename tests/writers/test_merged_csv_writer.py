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


def test_power_and_setpoints_follow_nhr_convention_without_changing_sources(tmp_path):
    can_path, nhr_path, output = (tmp_path / name for name in ("can.csv", "nhr.csv", "merged.csv"))
    write_csv(can_path, ["timestamp_utc", "maxChargePower", "maxDischargePower"], [
        {"timestamp_utc": utc(100), "maxChargePower": "", "maxDischargePower": ""},
        {"timestamp_utc": utc(101), "maxChargePower": "-17.125", "maxDischargePower": "44.4375"},
        {"timestamp_utc": utc(106), "maxChargePower": "0", "maxDischargePower": "0"},
    ])
    fields = ["timestamp_utc", "state", "setpoint_current_a", "setpoint_power_w", "setpoint_voltage_v", "power_w"]
    write_csv(nhr_path, fields, [
        {"timestamp_utc": utc(100+i), "state": state,
         "setpoint_current_a": "0" if i == 6 else "32",
         "setpoint_power_w": "0" if i == 6 else "3500",
         "setpoint_voltage_v": "103.2", "power_w": "-123"}
        for i, state in enumerate(["charge", "charge", "discharge", "off", "standby", "battery_emulation", "charge"])
    ])
    originals = (can_path.read_bytes(), nhr_path.read_bytes())
    result = MergedCSVWriter().merge(can_csv_path=str(can_path), nhr_csv_path=str(nhr_path),
                                    output_path=str(output), signals=["maxChargePower", "maxDischargePower"])
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["can_maxChargePower"] == ""
    assert rows[0]["can_maxChargePower_status"] == "missing"
    assert float(rows[1]["can_maxChargePower"]) == 17125
    assert float(rows[1]["can_maxDischargePower"]) == -44437.5
    assert float(rows[1]["nhr_setpoint_current_a"]) == 32
    assert float(rows[2]["nhr_setpoint_current_a"]) == -32
    assert float(rows[2]["nhr_setpoint_power_w"]) == -3500
    assert float(rows[2]["nhr_setpoint_voltage_v"]) == 103.2
    for row in rows[3:6]:
        assert all(row["nhr_"+f] == "" for f in fields[2:5])
    assert rows[4]["can_maxChargePower_status"] == "stale"
    assert rows[4]["can_maxChargePower_age_s"] == "3.000000"
    assert rows[6]["can_maxChargePower"] == "0.0"
    assert rows[6]["nhr_setpoint_current_a"] == "0.0"
    assert all(row["nhr_power_w"] == "-123" for row in rows)
    assert result.normalization["signals"]["can_maxChargePower"]["output_unit"] == "W"
    assert result.normalization["setpoints"]["blanked_rows"] == 3
    assert result.normalization["setpoints"]["unsupported_states"] == {"battery_emulation": 1}
    assert (can_path.read_bytes(), nhr_path.read_bytes()) == originals


@pytest.mark.parametrize("signal,value", [
    ("maxChargePower", "1"), ("maxDischargePower", "-1"),
    ("maxChargePower", "nan"), ("maxDischargePower", "inf"),
    ("maxChargePower", "bad"), ("maxDischargePower", "1e308"),
])
def test_invalid_power_preserves_sources_and_previous_output(tmp_path, signal, value):
    can_path, nhr_path, output = (tmp_path / name for name in ("can.csv", "nhr.csv", "merged.csv"))
    write_csv(can_path, ["timestamp_utc", signal], [{"timestamp_utc": utc(100), signal: value}])
    write_csv(nhr_path, ["timestamp_utc"], [{"timestamp_utc": utc(100)}])
    output.write_text("previous result", encoding="utf-8")
    originals = (can_path.read_bytes(), nhr_path.read_bytes())
    with pytest.raises(MergedCSVError):
        MergedCSVWriter().merge(can_csv_path=str(can_path), nhr_csv_path=str(nhr_path),
                                output_path=str(output), signals=[signal])
    assert (can_path.read_bytes(), nhr_path.read_bytes()) == originals
    assert output.read_text(encoding="utf-8") == "previous result"
    assert not list(tmp_path.glob(".merged.csv.*.tmp"))


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "bad"])
def test_invalid_active_setpoint_is_rejected(tmp_path, value):
    can_path, nhr_path = tmp_path / "can.csv", tmp_path / "nhr.csv"
    write_csv(can_path, ["timestamp_utc", "SignalA"], [{"timestamp_utc": utc(100), "SignalA": "1"}])
    write_csv(nhr_path, ["timestamp_utc", "state", "setpoint_current_a"],
              [{"timestamp_utc": utc(100), "state": "discharge", "setpoint_current_a": value}])
    with pytest.raises(MergedCSVError):
        MergedCSVWriter().merge(can_csv_path=str(can_path), nhr_csv_path=str(nhr_path),
                                output_path=str(tmp_path / "merged.csv"), signals=["SignalA"])


def test_setpoints_require_state_but_allow_missing_active_values(tmp_path):
    can_path, nhr_path, output = (tmp_path / name for name in ("can.csv", "nhr.csv", "merged.csv"))
    write_csv(can_path, ["timestamp_utc", "SignalA"], [
        {"timestamp_utc": utc(100), "SignalA": "1"},
        {"timestamp_utc": utc(101), "SignalA": "2"},
    ])
    write_csv(nhr_path, ["timestamp_utc", "setpoint_current_a"],
              [{"timestamp_utc": utc(100), "setpoint_current_a": "1"}])
    with pytest.raises(MergedCSVError, match="missing state"):
        MergedCSVWriter().merge(can_csv_path=str(can_path), nhr_csv_path=str(nhr_path),
                                output_path=str(output), signals=["SignalA"])
    write_csv(nhr_path, ["timestamp_utc", "state", "setpoint_current_a"], [
        {"timestamp_utc": utc(100), "state": "charge", "setpoint_current_a": ""},
        {"timestamp_utc": utc(101), "state": "off", "setpoint_current_a": "unused"},
    ])
    MergedCSVWriter().merge(can_csv_path=str(can_path), nhr_csv_path=str(nhr_path),
                            output_path=str(output), signals=["SignalA"])
    with output.open(newline="", encoding="utf-8") as handle:
        assert all(row["nhr_setpoint_current_a"] == "" for row in csv.DictReader(handle))
