import argparse

import pytest

from canpy.config.manager import ConfigManager


def test_nhr_defaults_select_approved_poc_policy():
    config = ConfigManager()
    config.load_defaults_conf()

    assert config.get_section("nhr") == {
        "service_url": None,
        "instrument_id": None,
        "source_id": "bms-poc-v2",
        "publish_rate_hz": 5.0,
        "signal_max_age_s": 2.5,
        "communication_loss_fault_after_s": 5.0,
        "queue_size": 16,
        "timeout_s": 1.0,
    }


def test_nhr_cli_values_override_defaults(tmp_path):
    dbc_file = tmp_path / "test.dbc"
    dbc_file.write_text("", encoding="utf-8")
    args = argparse.Namespace(
        dbc=str(dbc_file),
        nhr_url="http://127.0.0.1:9300",
        nhr_instrument="sim-1",
        nhr_source_id="bms-poc-v2",
        nhr_rate=10.0,
        nhr_signal_max_age=2.5,
        nhr_communication_loss_fault_after=6.0,
        nhr_queue_size=8,
        nhr_timeout=0.5,
    )
    config = ConfigManager()
    config.load_defaults_conf()
    config.load_args_conf(args)
    config.validate_config()

    assert config.get_setting("nhr", "publish_rate_hz") == 10.0
    assert config.get_setting("nhr", "signal_max_age_s") == 2.5
    assert (
        config.get_setting("nhr", "communication_loss_fault_after_s") == 6.0
    )
    assert config.get_setting("nhr", "queue_size") == 8


@pytest.mark.parametrize(
    ("service_url", "instrument_id"),
    [
        ("http://127.0.0.1:9300", None),
        (None, "sim-1"),
    ],
)
def test_nhr_url_and_instrument_are_an_atomic_configuration_pair(
    service_url, instrument_id
):
    config = ConfigManager()
    config.load_defaults_conf()
    config._settings["nhr"]["service_url"] = service_url
    config._settings["nhr"]["instrument_id"] = instrument_id

    with pytest.raises(ValueError, match="configured together"):
        config.validate_config()


def test_nhr_forwarding_requires_dbc():
    config = ConfigManager()
    config.load_defaults_conf()
    config._settings["nhr"].update(
        {
            "service_url": "http://127.0.0.1:9300",
            "instrument_id": "sim-1",
        }
    )

    with pytest.raises(ValueError, match="requires a DBC file"):
        config.validate_config()


def test_communication_loss_fault_requires_a_debounce_window():
    config = ConfigManager()
    config.load_defaults_conf()
    config._settings["nhr"].update(
        {
            "signal_max_age_s": 2.5,
            "communication_loss_fault_after_s": 2.5,
        }
    )

    with pytest.raises(ValueError, match="must be greater"):
        config.validate_config()
