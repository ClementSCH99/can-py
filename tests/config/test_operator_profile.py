import argparse
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from canpy.capture import main, _print_effective_configuration, _resolve_profile_argument
from canpy.config.manager import ConfigManager


def write_profile(path, dbc_path, extra=""):
    path.write_text(
        f"""schema_version: 1
name: test-profile
can:
  interface: cantact
  bitrate: 250000
capture:
  mode: count
  count: 2
output:
  directory: data/test
  formats: [csv]
dbc:
  file: {dbc_path.as_posix()}
nhr:
  service_url: http://127.0.0.1:9300
  instrument_id: sim-1
  source_id: test-source
merge:
  default_scope: sequence
  can_stale_after_s: 3.0
  signals: [SignalA]
{extra}""",
        encoding="utf-8",
    )


def test_profile_hash_merge_and_full_precedence(tmp_path, monkeypatch):
    dbc = tmp_path / "test.dbc"
    dbc.write_text("VERSION \"test\"", encoding="utf-8")
    profile = tmp_path / "profile.yaml"
    write_profile(profile, dbc)
    monkeypatch.setenv("CAN_BITRATE", "500000")
    args = argparse.Namespace(bitrate=1000000)
    cfg = ConfigManager()
    cfg.load_defaults_conf()
    cfg.load_user_conf(profile)
    cfg.load_env_conf()
    cfg.load_args_conf(args)
    cfg.validate_config()
    assert cfg.get_setting("can", "bitrate") == 1000000
    assert cfg.get_setting("merge", "default_scope") == "sequence"
    assert cfg.profile_sha256 == hashlib.sha256(profile.read_bytes()).hexdigest()


def test_versioned_operator_profile_keeps_serial_port_automatic():
    cfg = ConfigManager()
    cfg.load_defaults_conf()
    cfg.load_user_conf(Path("configs/canpy/bms-nhr-poc-v2.yaml"))
    cfg.validate_config()
    assert cfg.get_setting("can", "serial_port") is None


def test_profile_and_config_alias_conflict_is_clear(tmp_path):
    first = tmp_path / "a.yaml"
    second = tmp_path / "b.yaml"
    with pytest.raises(ValueError, match="cannot reference different"):
        _resolve_profile_argument(str(first), str(second))
    assert _resolve_profile_argument(str(first), str(first)).resolve() == first.resolve()


@pytest.mark.parametrize("option", ["--profile", "--config"])
def test_capture_cli_loads_profile_and_compatibility_alias(tmp_path, option):
    dbc = tmp_path / "test.dbc"
    dbc.write_text("VERSION \"test\"", encoding="utf-8")
    profile = tmp_path / "profile.yaml"
    write_profile(profile, dbc)
    with (
        patch("canpy.capture.ExternalSnapshotForwarder"),
        patch("canpy.capture.CANCapture") as capture_class,
    ):
        capture_class.return_value.connect.return_value = True
        capture_class.return_value.capture.return_value = True
        assert main([option, str(profile)]) == 0
    config = capture_class.call_args.args[0]
    assert config.profile_path == profile.resolve()


def test_capture_cli_rejects_profile_config_conflict(tmp_path, capsys):
    assert main(["--profile", str(tmp_path / "a"), "--config", str(tmp_path / "b")]) == 1
    assert "cannot reference different" in capsys.readouterr().out


@pytest.mark.parametrize(
    "merge, message",
    [
        ("default_scope: latest\n  signals: [SignalA]", "default_scope"),
        ("default_scope: session\n  can_stale_after_s: false\n  signals: [SignalA]", "positive"),
        ("default_scope: session\n  signals: [bad signal]", "signal name"),
    ],
)
def test_invalid_merge_profile_is_rejected(tmp_path, merge, message):
    dbc = tmp_path / "test.dbc"
    dbc.write_text("VERSION \"test\"", encoding="utf-8")
    profile = tmp_path / "profile.yaml"
    write_profile(profile, dbc)
    text = profile.read_text(encoding="utf-8")
    text = text[: text.index("merge:")] + "merge:\n  " + merge + "\n"
    profile.write_text(text, encoding="utf-8")
    cfg = ConfigManager()
    cfg.load_defaults_conf()
    with pytest.raises(ValueError, match=message):
        cfg.load_user_conf(profile)


def test_profile_forbids_runtime_nhr_association(tmp_path):
    dbc = tmp_path / "test.dbc"
    dbc.write_text("VERSION \"test\"", encoding="utf-8")
    profile = tmp_path / "profile.yaml"
    write_profile(profile, dbc, extra="run_id: forbidden\n")
    cfg = ConfigManager()
    cfg.load_defaults_conf()
    with pytest.raises(ValueError, match="Forbidden"):
        cfg.load_user_conf(profile)


def test_effective_summary_includes_profile_and_dbc_hash(tmp_path, capsys):
    dbc = tmp_path / "test.dbc"
    dbc.write_text("VERSION \"test\"", encoding="utf-8")
    profile = tmp_path / "profile.yaml"
    write_profile(profile, dbc)
    cfg = ConfigManager()
    cfg.load_defaults_conf()
    cfg.load_user_conf(profile)
    cfg.validate_config()
    _print_effective_configuration(cfg, ["--bitrate"])
    output = capsys.readouterr().out
    assert cfg.profile_sha256 in output
    assert hashlib.sha256(dbc.read_bytes()).hexdigest() in output
    assert "--bitrate" in output
