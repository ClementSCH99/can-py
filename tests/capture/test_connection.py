from unittest.mock import Mock, patch

from canpy.capture import CANCapture
from canpy.config.manager import ConfigManager


def configuration(*, interface="cantact", serial_port=None):
    config = ConfigManager()
    config.load_defaults_conf()
    config._settings["can"].update(
        {"interface": interface, "serial_port": serial_port, "bitrate": 500000}
    )
    return config


def test_null_serial_port_uses_automatic_adapter_discovery():
    capture = CANCapture(configuration(serial_port=None))
    bus = Mock()
    with (
        patch(
            "can.interface.detect_available_configs",
            return_value=[{"interface": "cantact", "channel": "ch:2"}],
        ) as detect,
        patch("can.interface.Bus", return_value=bus) as open_bus,
    ):
        assert capture.connect() is True

    detect.assert_called_once_with()
    open_bus.assert_called_once_with(
        interface="cantact", channel="2", bitrate=500000, timeout=1.0
    )
    assert capture.bus is bus


def test_explicit_serial_port_bypasses_discovery_and_uses_slcan():
    capture = CANCapture(configuration(serial_port="COM7"))
    bus = Mock()
    with (
        patch("can.interface.detect_available_configs") as detect,
        patch("can.interface.Bus", return_value=bus) as open_bus,
    ):
        assert capture.connect() is True

    detect.assert_not_called()
    open_bus.assert_called_once_with(
        interface="slcan", channel="COM7", bitrate=500000, timeout=1.0
    )


def test_connection_does_not_report_success_without_an_open_bus(capsys):
    capture = CANCapture(configuration(serial_port=None))
    with (
        patch("can.interface.detect_available_configs", return_value=[]),
        patch("can.interface.Bus", side_effect=RuntimeError("not present")),
    ):
        assert capture.connect() is False

    assert capture.bus is None
    assert "No compatible CAN adapter" in capsys.readouterr().out
