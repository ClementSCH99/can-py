import yaml
import os
from typing import Optional

from pathlib import Path
PACKAGE_DIR = Path(__file__).parent
DEFAULT_YAML = PACKAGE_DIR / "defaults.yaml"

class ConfigManager:
    def __init__(self):
        self._settings = {}
        self._locked = False
    
    def _validate_bitrate(self, value: int) -> int:
        if not isinstance(value, int) or value <= 0:
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
        if not isinstance(value, str) or not value:
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
        valid_formats = {'csv', 'json'}
        for fmt in value:
            if fmt not in valid_formats:
                raise ValueError(f"Invalid log format: {fmt}. Valid options are: {valid_formats}")
        return value
    
    def _validate_filters(self, value: list[int]) -> list[int]:
        if value is None or value == []:
            return value
        
        if not isinstance(value, list):
            raise ValueError(f"Invalid filters: {value}. Must be a list of filter definitions.")
        for item in value:
            if not isinstance(item, int) or item < 0:
                raise ValueError(f"Invalid filter CAN ID: {item}. Must be a non-negative integer.")
        return value

    def _validate_nhr_settings(self, value: dict) -> dict:
        if not isinstance(value, dict):
            raise ValueError("Invalid NHR settings: expected a mapping")
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
                not isinstance(item, (int, float)) or item <= 0
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
        with open(filepath, "r") as f:
            yaml_settings = yaml.safe_load(f)
        return yaml_settings
    
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
        if 'can' in settings and 'bitrate' in settings['can']:
            self._validate_bitrate(settings['can']['bitrate'])

        if 'capture' in settings and 'mode' in settings['capture']:
            self._validate_capture_mode(settings['capture']['mode'])

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
        user_settings = self._load_yaml(filepath)
        user_settings = self.validate_settings(user_settings)
        self._settings = self._deep_merge(self._settings, user_settings)
    
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
        if name in ('_settings', '_locked'):
            super().__setattr__(name, value)
            return
        
        # Block changes to settings after lock
        if self._locked:
            raise AttributeError(f"Cannot modify locked configuration: '{name}'")
        
        super().__setattr__(name, value)
