# tests/config/test_manager_integration.py
"""
Integration tests for ConfigManager
Tests configuration precedence: YAML defaults → environment → CLI args
"""

import os
import argparse
import pytest
from pathlib import Path
from canpy.config.manager import ConfigManager


class TestConfigManagerDefaults:
    """Test default configuration loading from YAML"""
    
    def test_defaults_load_successfully(self):
        """Verify defaults are loaded from YAML"""
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        cfg.validate_config()
        
        assert cfg.get_setting('can', 'bitrate') == 500000
        assert cfg.get_setting('can', 'interface') == 'slcan'
        assert cfg.get_setting('capture', 'mode') == 'continuous'
        assert cfg.get_setting('output', 'directory') == 'data'
        assert cfg.get_setting('output', 'formats') == []
        assert cfg.get_setting('dbc', 'file') is None
        assert cfg.get_setting('dbc', 'filter') is None


class TestConfigManagerEnvOverrides:
    """Test environment variable overrides"""
    
    def test_env_overrides_defaults_bitrate(self):
        """Verify environment variables override YAML defaults"""
        os.environ['CAN_BITRATE'] = '250000'
        try:
            cfg = ConfigManager()
            cfg.load_defaults_conf()
            cfg.load_env_conf()
            cfg.validate_config()
            
            assert cfg.get_setting('can', 'bitrate') == 250000
        finally:
            del os.environ['CAN_BITRATE']
    
    def test_env_overrides_defaults_multiple(self):
        """Verify multiple environment variables override"""
        os.environ['CAN_BITRATE'] = '125000'
        os.environ['CAPTURE_MODE'] = 'duration'
        try:
            cfg = ConfigManager()
            cfg.load_defaults_conf()
            cfg.load_env_conf()
            cfg.validate_config()
            
            assert cfg.get_setting('can', 'bitrate') == 125000
            assert cfg.get_setting('capture', 'mode') == 'duration'
        finally:
            del os.environ['CAN_BITRATE']
            del os.environ['CAPTURE_MODE']
    
    def test_missing_env_vars_use_defaults(self):
        """Verify missing environment variables don't break config"""
        # Clear any CAN_* env vars
        for key in list(os.environ.keys()):
            if key.startswith('CAN_') or key.startswith('CAPTURE_'):
                del os.environ[key]
        
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        cfg.load_env_conf()
        cfg.validate_config()
        
        assert cfg.get_setting('can', 'bitrate') == 500000


class TestConfigManagerArgsOverrides:
    """Test CLI argument overrides"""
    
    def test_args_override_defaults(self):
        """Verify CLI arguments override defaults"""
        args = argparse.Namespace(
            interface=None,
            bitrate=1000000,
            port=None,
            mode=None,
            duration=None,
            count=None,
            no_console=False,
            show_parsed=False,
            output_dir=None,
            log=None,
            dbc=None,
            filter_can_id=None
        )
        
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        cfg.load_args_conf(args)
        cfg.validate_config()
        
        assert cfg.get_setting('can', 'bitrate') == 1000000
    
    def test_args_override_env(self):
        """Verify CLI arguments override environment variables"""
        os.environ['CAN_BITRATE'] = '250000'
        try:
            args = argparse.Namespace(
                interface=None,
                bitrate=1000000,  # User passes this
                port=None,
                mode=None,
                duration=None,
                count=None,
                no_console=False,
                show_parsed=False,
                output_dir=None,
                log=None,
                dbc=None,
                filter_can_id=None
            )
            
            cfg = ConfigManager()
            cfg.load_defaults_conf()
            cfg.load_env_conf()
            cfg.load_args_conf(args)
            cfg.validate_config()
            
            # CLI wins over environment
            assert cfg.get_setting('can', 'bitrate') == 1000000
        finally:
            del os.environ['CAN_BITRATE']
    
    def test_full_precedence_chain(self):
        """Verify full precedence: YAML → env → CLI"""
        os.environ['CAPTURE_MODE'] = 'duration'
        try:
            args = argparse.Namespace(
                interface=None,
                bitrate=None,  # Not specified, uses env or YAML
                port=None,
                mode='count',  # CLI overrides env
                duration=None,
                count=None,
                no_console=False,
                show_parsed=False,
                output_dir=None,
                log=None,
                dbc=None,
                filter_can_id=None
            )
            
            cfg = ConfigManager()
            cfg.load_defaults_conf()
            cfg.load_env_conf()
            cfg.load_args_conf(args)
            cfg.validate_config()
            
            assert cfg.get_setting('capture', 'mode') == 'count'  # CLI wins
            assert cfg.get_setting('can', 'bitrate') == 500000  # YAML used
        finally:
            del os.environ['CAPTURE_MODE']


class TestConfigManagerLocking:
    """Test configuration immutability"""

    def test_can_modify_before_lock(self):
        """Verify config can be modified before validation"""
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        # Should not raise before validate_config()
        cfg._settings['can']['bitrate'] = 250000
        assert cfg.get_setting('can', 'bitrate') == 250000
    
    def test_config_prevents_new_attributes_after_lock(self):
        """Verify config prevents setting new attributes after validation"""
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        cfg.validate_config()
        
        # Attempt to add a new attribute should fail
        with pytest.raises(AttributeError):
            cfg.new_key = "cannot add this"
    
    # TODO: After adding a proper locking mechanism, we should also test that modifying existing settings raises an error after validation.


class TestConfigManagerValidation:
    """Test validation logic"""
    
    def test_validation_rejects_invalid_bitrate(self):
        """Verify validation catches invalid bitrate"""
        args = argparse.Namespace(
            interface=None,
            bitrate=-100,  # Invalid!
            port=None,
            mode=None,
            duration=None,
            count=None,
            no_console=False,
            show_parsed=False,
            output_dir=None,
            log=None,
            dbc=None,
            filter_can_id=None
        )
        
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        
        with pytest.raises(ValueError, match="Must be a positive integer"):
            cfg.load_args_conf(args)
    
    def test_validation_rejects_invalid_capture_mode(self):
        """Verify validation catches invalid capture mode"""
        args = argparse.Namespace(
            interface=None,
            bitrate=None,
            port=None,
            mode='invalid_mode',  # Invalid!
            duration=None,
            count=None,
            no_console=False,
            show_parsed=False,
            output_dir=None,
            log=None,
            dbc=None,
            filter_can_id=None
        )
        
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        
        with pytest.raises(ValueError, match="Valid options are"):
            cfg.load_args_conf(args)
    
    def test_validation_rejects_invalid_log_format(self):
        """Verify validation catches invalid log format"""
        args = argparse.Namespace(
            interface=None,
            bitrate=None,
            port=None,
            mode=None,
            duration=None,
            count=None,
            no_console=False,
            show_parsed=False,
            output_dir=None,
            log=['csv', 'invalid_format'],  # Invalid format!
            dbc=None,
            filter_can_id=None
        )
        
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        
        with pytest.raises(ValueError, match="Invalid log format"):
            cfg.load_args_conf(args)
    
    def test_validation_rejects_invalid_filter_can_ids(self):
        """Verify validation catches invalid CAN ID filters"""
        args = argparse.Namespace(
            interface=None,
            bitrate=None,
            port=None,
            mode=None,
            duration=None,
            count=None,
            no_console=False,
            show_parsed=False,
            output_dir=None,
            log=None,
            dbc=None,
            filter_can_id=[-1]  # Negative ID invalid!
        )
        
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        
        with pytest.raises(ValueError, match="non-negative integer"):
            cfg.load_args_conf(args)


class TestConfigManagerComplexArgs:
    """Test pre-parsed complex arguments"""
    
    def test_parsed_log_formats_accepted(self):
        """Verify pre-parsed log formats are accepted"""
        args = argparse.Namespace(
            interface=None,
            bitrate=None,
            port=None,
            mode=None,
            duration=None,
            count=None,
            no_console=False,
            show_parsed=False,
            output_dir=None,
            log=['csv', 'json'],  # Pre-parsed in main()
            dbc=None,
            filter_can_id=None
        )
        
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        cfg.load_args_conf(args)
        cfg.validate_config()
        
        assert cfg.get_setting('output', 'formats') == ['csv', 'json']
    
    def test_parsed_filter_can_ids_accepted(self):
        """Verify pre-parsed CAN ID filters are accepted"""
        args = argparse.Namespace(
            interface=None,
            bitrate=None,
            port=None,
            mode=None,
            duration=None,
            count=None,
            no_console=False,
            show_parsed=False,
            output_dir=None,
            log=None,
            dbc=None,
            filter_can_id=[0x123, 0x456]  # Pre-parsed in main()
        )
        
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        cfg.load_args_conf(args)
        cfg.validate_config()
        
        assert cfg.get_setting('dbc', 'filter') == [0x123, 0x456]
    
    def test_parsed_single_log_format(self):
        """Verify single pre-parsed log format works"""
        args = argparse.Namespace(
            interface=None,
            bitrate=None,
            port=None,
            mode=None,
            duration=None,
            count=None,
            no_console=False,
            show_parsed=False,
            output_dir=None,
            log=['csv'],  # Single format
            dbc=None,
            filter_can_id=None
        )
        
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        cfg.load_args_conf(args)
        cfg.validate_config()
        
        assert cfg.get_setting('output', 'formats') == ['csv']


class TestConfigManagerAccess:
    """Test configuration access methods"""
    
    def test_get_setting_returns_value(self):
        """Verify get_setting retrieves values correctly"""
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        
        assert cfg.get_setting('can', 'bitrate') == 500000
        assert isinstance(cfg.get_setting('output', 'directory'), str)
    
    def test_get_setting_raises_on_missing_section(self):
        """Verify get_setting raises on missing section"""
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        
        with pytest.raises(KeyError):
            cfg.get_setting('nonexistent', 'key')
    
    def test_get_setting_raises_on_missing_key(self):
        """Verify get_setting raises on missing key"""
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        
        with pytest.raises(KeyError):
            cfg.get_setting('can', 'nonexistent_key')
    
    def test_get_section_returns_all_settings(self):
        """Verify get_section returns entire section"""
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        
        can_section = cfg.get_section('can')
        assert 'bitrate' in can_section
        assert 'interface' in can_section


class TestConfigManagerUserConfigFile:
    """Test user config file loading and precedence"""
    
    @pytest.fixture
    def temp_user_config(self, tmp_path):
        """Create a temporary user config file"""
        config_file = tmp_path / "user_config.yaml"
        config_file.write_text("""
can:
  bitrate: 250000
  interface: cantact

capture:
  mode: duration
  duration: 120

output:
  formats: [csv, json]

dbc:
  file: null
  filter: null
""")
        return config_file
    
    def test_user_config_overrides_defaults(self, temp_user_config):
        """Verify user config file overrides defaults"""
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        cfg.load_user_conf(temp_user_config)
        cfg.validate_config()
        
        # User config values override defaults
        assert cfg.get_setting('can', 'bitrate') == 250000
        assert cfg.get_setting('can', 'interface') == 'cantact'
        assert cfg.get_setting('capture', 'duration') == 120
        assert cfg.get_setting('output', 'formats') == ['csv', 'json']
    
    def test_env_overrides_user_config(self, temp_user_config):
        """Verify environment variables override user config"""
        os.environ['CAN_BITRATE'] = '125000'
        try:
            cfg = ConfigManager()
            cfg.load_defaults_conf()
            cfg.load_user_conf(temp_user_config)
            cfg.load_env_conf()
            cfg.validate_config()
            
            # Env var overrides user config
            assert cfg.get_setting('can', 'bitrate') == 125000
            # User config still used for other values
            assert cfg.get_setting('can', 'interface') == 'cantact'
        finally:
            del os.environ['CAN_BITRATE']
    
    def test_cli_args_override_user_config(self, temp_user_config):
        """Verify CLI args override user config file"""
        args = argparse.Namespace(
            interface=None,
            bitrate=1000000,  # Override user config's 250000
            port=None,
            mode=None,
            duration=None,
            count=None,
            no_console=False,
            show_parsed=False,
            output_dir=None,
            log=None,
            dbc=None,
            filter_can_id=None
        )
        
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        cfg.load_user_conf(temp_user_config)
        cfg.load_env_conf()
        cfg.load_args_conf(args)
        cfg.validate_config()
        
        # CLI arg overrides user config
        assert cfg.get_setting('can', 'bitrate') == 1000000
        # User config still used for other values
        assert cfg.get_setting('output', 'formats') == ['csv', 'json']
    
    def test_full_precedence_chain_with_user_config(self, temp_user_config):
        """Verify full precedence: defaults → user_config → env → CLI"""
        os.environ['CAPTURE_MODE'] = 'count'
        try:
            args = argparse.Namespace(
                interface=None,
                bitrate=None,  # Uses user config's 250000
                port=None,
                mode='duration',  # CLI overrides env var
                duration=None,
                count=None,
                no_console=False,
                show_parsed=False,
                output_dir=None,
                log=None,
                dbc=None,
                filter_can_id=None
            )
            
            cfg = ConfigManager()
            cfg.load_defaults_conf()
            cfg.load_user_conf(temp_user_config)
            cfg.load_env_conf()
            cfg.load_args_conf(args)
            cfg.validate_config()
            
            # CLI wins over env
            assert cfg.get_setting('capture', 'mode') == 'duration'
            # User config used over defaults (not overridden)
            assert cfg.get_setting('can', 'bitrate') == 250000
            # User config value preserved
            assert cfg.get_setting('output', 'formats') == ['csv', 'json']
        finally:
            del os.environ['CAPTURE_MODE']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])