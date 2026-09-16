import hashlib
import os
import re
import yaml
from typing import Optional

from pathlib import Path
PACKAGE_DIR = Path(__file__).parent
DEFAULT_YAML = PACKAGE_DIR / "defaults.yaml"

class ConfigManager:
    def __init__(self):
        self._settings = {}
        self._locked = False
        self._profile_path = None
        self._profile_configured_path = None
        self._profile_sha256 = None
    
    def _validate_bitrate(self, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"Invalid CAN bitrate: {value}. Must be a positive integer.")
    
        common_bitrates = {125000, 250000, 500000, 1000000}
        if value not in common_bitrates:
            print(f"[WARNING] Uncommon CAN bitrate: {value}. Common bitrates are: {common_bitrates}")
        return value
    
    def _validate_capture_mode(self, value: str) -> str:
        valid_modes = {'duration', 'count', 'continuous'}
        if value not in valid_modes:
            raise ValueError(f"Invalid capture mode: {value}. Valid options are: {valid_modes}")
        return value
    
    def _validate_output_directory(self, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Invalid output directory: {value}. Must be a non-empty string.")
        return value
    
    def _validate_dbc_file(self, value: str) -> str:
        if value is None:
            return value
        if not isinstance(value, str) or not value:
            raise ValueError(f"Invalid DBC file path: {value}. Must be a non-empty string.")
        if not os.path.isfile(value):
            raise ValueError(f"DBC file does not exist: {value}")
        return value
    
    def _validate_output_format(self, value: list[str]) -> list[str]:
        if value is None or value == []:
            return value
        if not isinstance(value, list):
            raise ValueError("Invalid output formats: expected a list")
        valid_formats = {'csv', 'json'}
        for fmt in value:
            if fmt not in valid_formats:
                raise ValueError(f"Invalid log format: {fmt}. Valid options are: {valid_formats}")
        return value

    def _validate_merge_settings(self, value: dict) -> dict:
        if not isinstance(value, dict):
            raise ValueError("Invalid merge settings: expected a mapping")
        allowed = {'default_scope', 'can_stale_after_s', 'signals'}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError("Unknown merge setting(s): " + ", ".join(unknown))
        scope = value.get('default_scope')
        if scope is not None and scope not in {'session', 'sequence', 'stage'}:
            raise ValueError(
                "Invalid merge default_scope: expected session, sequence, or stage"
            )
        stale = value.get('can_stale_after_s')
        if stale is not None and (
            isinstance(stale, bool)
            or not isinstance(stale, (int, float))
            or stale <= 0
        ):
            raise ValueError("Invalid merge can_stale_after_s: expected a positive number")
        signals = value.get('signals')
        if signals is not None:
            if not isinstance(signals, list) or not signals:
                raise ValueError("Invalid merge signals: expected a non-empty list")
            for signal in signals:
                if (
                    not isinstance(signal, str)
                    or not signal.strip()
                    or signal != signal.strip()
                    or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", signal) is None
                ):
                    raise ValueError(f"Invalid merge signal name: {signal!r}")
            if len(signals) != len(set(signals)):
                raise ValueError("Invalid merge signals: duplicate names are not allowed")
        return value

    @staticmethod
    def _validate_profile_contract(settings: dict) -> None:
        if not isinstance(settings, dict):
            raise ValueError("Configuration YAML must contain a mapping")
        allowed_top = {
            'schema_version', 'name', 'can', 'capture', 'output', 'dbc', 'nhr', 'merge'
        }
        forbidden = {
            'run_id', 'nhr_run_id', 'nhr_csv', 'runtime', 'physical_authorization',
            'battery_limits', 'workflow_profile', 'workflow_digest',
        }
        forbidden_top = sorted(set(settings) & forbidden)
        if forbidden_top:
            raise ValueError(
                "Forbidden runtime/NHR workflow field in CAN-PY profile: "
                + ", ".join(forbidden_top)
            )
        unknown = sorted(set(settings) - allowed_top)
        if unknown:
            raise ValueError("Unknown profile section(s): " + ", ".join(unknown))
        if 'schema_version' in settings and settings['schema_version'] != 1:
            raise ValueError("Profile schema_version must be 1")
        if 'name' in settings and (
            not isinstance(settings['name'], str) or not settings['name'].strip()
        ):
            raise ValueError("Profile name must be a non-empty string")
        def visit(node, prefix=""):
            if isinstance(node, dict):
                for key, item in node.items():
                    if key in forbidden:
                        raise ValueError(
                            f"Forbidden runtime/NHR workflow field in CAN-PY profile: "
                            f"{prefix}{key}"
                        )
                    visit(item, f"{prefix}{key}.")
            elif isinstance(node, list):
                for item in node:
                    visit(item, prefix)

        visit(settings)
    
    def _validate_filters(self, value: list[int]) -> list[int]:
        if value is None or value == []:
            return value
        
        if not isinstance(value, list):
            raise ValueError(f"Invalid filters: {value}. Must be a list of filter definitions.")
        for item in value:
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise ValueError(f"Invalid filter CAN ID: {item}. Must be a non-negative integer.")
        return value

    def _validate_nhr_settings(self, value: dict) -> dict:
        if not isinstance(value, dict):
            raise ValueError("Invalid NHR settings: expected a mapping")
        allowed = {
            'service_url', 'instrument_id', 'source_id', 'publish_rate_hz',
            'signal_max_age_s', 'communication_loss_fault_after_s',
            'queue_size', 'timeout_s',
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError("Unknown NHR setting(s): " + ", ".join(unknown))
        for key in ('service_url', 'instrument_id', 'source_id'):
            item = value.get(key)
            if item is not None and (not isinstance(item, str) or not item.strip()):
                raise ValueError(f"Invalid NHR {key}: expected a non-empty string")
        for key in (
            'publish_rate_hz',
            'signal_max_age_s',
            'communication_loss_fault_after_s',
            'timeout_s',
        ):
            item = value.get(key)
            if item is not None and (
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or item <= 0
            ):
                raise ValueError(f"Invalid NHR {key}: expected a positive number")
        queue_size = value.get('queue_size')
        if queue_size is not None and (
            isinstance(queue_size, bool)
            or not isinstance(queue_size, int)
            or queue_size <= 0
        ):
            raise ValueError("Invalid NHR queue_size: expected a positive integer")
        return value


    def _load_yaml(self, filepath: Path) -> dict:
        with open(filepath, "r", encoding="utf-8") as f:
            yaml_settings = yaml.safe_load(f)
        return yaml_settings if yaml_settings is not None else {}
    
    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

        
    def validate_settings(self, settings: dict) -> dict:
        """Validate settings and raise exceptions for invalid values."""
        if not isinstance(settings, dict):
            raise ValueError("Configuration must be a mapping")
        section_keys = {
            'can': {'interface', 'bitrate', 'serial_port'},
            'capture': {'mode', 'duration', 'count', 'no_console', 'show_parsed'},
            'output': {'directory', 'formats'},
            'dbc': {'file', 'filter'},
        }
        for section, allowed in section_keys.items():
            if section in settings:
                if not isinstance(settings[section], dict):
                    raise ValueError(f"Invalid {section} settings: expected a mapping")
                unknown = sorted(set(settings[section]) - allowed)
                if unknown:
                    raise ValueError(
                        f"Unknown {section} setting(s): " + ", ".join(unknown)
                    )
        if 'can' in settings:
            for key in ('interface', 'serial_port'):
                item = settings['can'].get(key)
                if item is not None and (not isinstance(item, str) or not item.strip()):
                    raise ValueError(f"Invalid CAN {key}: expected a non-empty string")
        if 'can' in settings and 'bitrate' in settings['can']:
            self._validate_bitrate(settings['can']['bitrate'])

        if 'capture' in settings and 'mode' in settings['capture']:
            self._validate_capture_mode(settings['capture']['mode'])
        if 'capture' in settings:
            capture = settings['capture']
            for key in ('duration', 'count'):
                item = capture.get(key)
                if item is not None and (
                    isinstance(item, bool) or not isinstance(item, int)
                ):
                    raise ValueError(f"Invalid capture {key}: expected an integer or null")
            for key in ('no_console', 'show_parsed'):
                item = capture.get(key)
                if item is not None and not isinstance(item, bool):
                    raise ValueError(f"Invalid capture {key}: expected a boolean")

        if 'output' in settings and 'directory' in settings['output']:
            self._validate_output_directory(settings['output']['directory'])
        if 'output' in settings and 'formats' in settings['output']:
            self._validate_output_format(settings['output']['formats'])

        if 'dbc' in settings and 'file' in settings['dbc']:
            self._validate_dbc_file(settings['dbc']['file'])
        if 'dbc' in settings and 'filter' in settings['dbc']:
            self._validate_filters(settings['dbc']['filter'])
        if 'nhr' in settings:
            self._validate_nhr_settings(settings['nhr'])
        if 'merge' in settings:
            self._validate_merge_settings(settings['merge'])
        
        return settings
    
    def validate_config(self) -> None:
        """Final validation and lock configuration"""
        # Check required sections exist
        required_sections = {'can', 'capture', 'output'}
        for section in required_sections:
            if section not in self._settings:
                raise ValueError(f"Missing required section: {section}")
        
        # Validate entire config once more
        self.validate_settings(self._settings)

        nhr = self._settings.get('nhr', {})
        has_url = bool(nhr.get('service_url'))
        has_instrument = bool(nhr.get('instrument_id'))
        if has_url != has_instrument:
            raise ValueError(
                "NHR service_url and instrument_id must be configured together"
            )
        if has_url and not self._settings.get('dbc', {}).get('file'):
            raise ValueError("NHR external snapshot forwarding requires a DBC file")
        signal_max_age_s = nhr.get('signal_max_age_s')
        communication_loss_s = nhr.get('communication_loss_fault_after_s')
        if (
            signal_max_age_s is not None
            and communication_loss_s is not None
            and communication_loss_s <= signal_max_age_s
        ):
            raise ValueError(
                "NHR communication_loss_fault_after_s must be greater than "
                "signal_max_age_s"
            )
        
        # Lock it
        self._locked = True
    

    def load_defaults_conf(self) -> None:
        defaults = self._load_yaml(DEFAULT_YAML)
        defaults = self.validate_settings(defaults)
        self._settings = self._deep_merge(self._settings, defaults)

    def load_user_conf(self, filepath: Path) -> None:
        filepath = Path(filepath)
        user_settings = self._load_yaml(filepath)
        self._validate_profile_contract(user_settings)
        user_settings = self.validate_settings(user_settings)
        self._settings = self._deep_merge(self._settings, user_settings)
        self._profile_configured_path = filepath.as_posix()
        self._profile_path = filepath.resolve()
        self._profile_sha256 = hashlib.sha256(filepath.read_bytes()).hexdigest()
    
    def load_env_conf(self) -> None:
        """Load from environment variables (CAN_*, CAPTURE_*, OUTPUT_*, DBC_*)"""
        # Map environment variable name → (section, key)
        env_mapping = {
            'CAN_BITRATE': ('can', 'bitrate', int),
            'CAN_INTERFACE': ('can', 'interface', str),
            'CAPTURE_MODE': ('capture', 'mode', str),
            'OUTPUT_DIR': ('output', 'directory', str),
            'DBC_FILE': ('dbc', 'file', str),
            'NHR_SERVICE_URL': ('nhr', 'service_url', str),
            'NHR_INSTRUMENT_ID': ('nhr', 'instrument_id', str),
            'NHR_SOURCE_ID': ('nhr', 'source_id', str),
            'NHR_SIGNAL_MAX_AGE_S': ('nhr', 'signal_max_age_s', float),
            'NHR_COMMUNICATION_LOSS_FAULT_AFTER_S': (
                'nhr', 'communication_loss_fault_after_s', float
            ),
            'MERGE_DEFAULT_SCOPE': ('merge', 'default_scope', str),
            'MERGE_CAN_STALE_AFTER_S': ('merge', 'can_stale_after_s', float),
        }
        
        env_settings = {}
        for env_var, (section, key, dtype) in env_mapping.items():
            value = os.getenv(env_var)
            if value is not None:
                if section not in env_settings:
                    env_settings[section] = {}
                # Convert to correct type (int for bitrate, str for others)
                env_settings[section][key] = dtype(value)
        
        if env_settings:
            self.validate_settings(env_settings)
            self._settings = self._deep_merge(self._settings, env_settings)
    
    def load_args_conf(self, args) -> None:
        """Load from argparse Namespace (only non-None values)"""

        args_mapping = {
            'interface': ('can', 'interface', str),
            'bitrate': ('can', 'bitrate', int),
            'port': ('can', 'serial_port', str),

            'mode': ('capture', 'mode', str),
            'duration': ('capture', 'duration', int),
            'count': ('capture', 'count', int),
            'no_console': ('capture', 'no_console', bool),
            'show_parsed': ('capture', 'show_parsed', bool),

            'output_dir': ('output', 'directory', str),
            'log': ('output', 'formats', list[str]),

            'dbc': ('dbc', 'file', str),
            'filter_can_id': ('dbc', 'filter', list),

            'nhr_url': ('nhr', 'service_url', str),
            'nhr_instrument': ('nhr', 'instrument_id', str),
            'nhr_source_id': ('nhr', 'source_id', str),
            'nhr_rate': ('nhr', 'publish_rate_hz', float),
            'nhr_signal_max_age': ('nhr', 'signal_max_age_s', float),
            'nhr_communication_loss_fault_after': (
                'nhr', 'communication_loss_fault_after_s', float
            ),
            'nhr_queue_size': ('nhr', 'queue_size', int),
            'nhr_timeout': ('nhr', 'timeout_s', float),
        }

        args_settings = {}
        for arg_name, (section, key, dtype) in args_mapping.items():
            value = getattr(args, arg_name, None)
            if value is not None and value is not False:  # Only include if value is set and not False (for bool flags)
                if section not in args_settings:
                    args_settings[section] = {}
                args_settings[section][key] = dtype(value)
        
        if args_settings:
            self.validate_settings(args_settings)
            self._settings = self._deep_merge(self._settings, args_settings)


    def get_section(self, name: Optional[str] = None) -> dict:
        """Get a specific section of the configuration or the entire config if no name is provided."""
        if name:
            if name not in self._settings:
                raise KeyError(f"Configuration section '{name}' not found.")
            return self._settings.get(name, {})    
        return self._settings

    @property
    def profile_path(self) -> Optional[Path]:
        return self._profile_path

    @property
    def profile_sha256(self) -> Optional[str]:
        return self._profile_sha256

    @property
    def profile_configured_path(self) -> Optional[str]:
        return self._profile_configured_path
    
    # TODO: Add type hints for return values and parameters
    def get_setting(self, section: str, key: str):
        """Get a specific setting from a section."""
        if section not in self._settings:
            raise KeyError(f"Configuration section '{section}' not found.")
        if key not in self._settings[section]:
            raise KeyError(f"Setting '{key}' not found in section '{section}'.")
        return self._settings[section][key]
    
    def __getattr__(self, name):
        if name in self._settings:
            return self._settings[name]
        raise AttributeError(f"Configuration section '{name}' not found.")
    
    # TODO: This only works for new attributes, not for modifying existing ones. We need a locking mechanism to prevent modifications after validation.
    def __setattr__(self, name, value):
        # Allow internal attributes (_settings, _locked) to be set during init
        if name in (
            '_settings', '_locked', '_profile_path', '_profile_configured_path',
            '_profile_sha256'
        ):
            super().__setattr__(name, value)
            return
        
        # Block changes to settings after lock
        if self._locked:
            raise AttributeError(f"Cannot modify locked configuration: '{name}'")
        
        super().__setattr__(name, value)
