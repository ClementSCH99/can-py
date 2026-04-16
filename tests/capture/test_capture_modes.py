"""
Unit tests for CANCapture mode validation logic.
Tests verify that capture mode consistency checks work correctly.
Focus: Validation logic, not full capture loop behavior.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from canpy.config.manager import ConfigManager
from canpy.capture import CANCapture

# TODO: Refactor this whole testing file as AI went crazy on it and it's a mess.
# I'm not sur its the right way of doing it. A bit lost here. Task for later as it works now.

class TestCaptureModeValidation:
    """Test capture mode validation in CANCapture.capture()"""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create a basic ConfigManager"""
        cfg = ConfigManager()
        cfg.load_defaults_conf()
        return cfg
    
    @pytest.fixture
    def capturer(self, mock_config_manager):
        """Create a CANCapture with minimal mocking"""
        cap = CANCapture(mock_config_manager)
        cap.bus = Mock()
        cap.bus.recv = Mock(return_value=None)  # Exit immediately
        cap.parser = Mock()
        cap.writers = {}
        return cap
    
    @staticmethod
    def mock_frame_data():
        """Return a complete mock frame data dictionary"""
        return {
            'can_id_dec': 0x123,
            'can_id': '0x123',
            'dlc': 8,
            'data_hex': '00 01 02 03 04 05 06 07',
            'timestamp': 0.1,
            'parsed': {}
        }
    
    # Duration mode tests
    
    def test_duration_mode_requires_duration_value(self, capturer):
        """Verify duration mode fails if duration is not set"""
        capturer.config_manager._settings['capture']['mode'] = 'duration'
        capturer.config_manager._settings['capture']['duration'] = None
        capturer.config_manager._settings['capture']['count'] = None
        
        with pytest.raises(ValueError, match="Duration mode selected but no duration specified"):
            capturer.capture()
    
    def test_duration_mode_rejects_zero_duration(self, capturer):
        """Verify duration mode treats 0 as not specified"""
        capturer.config_manager._settings['capture']['mode'] = 'duration'
        capturer.config_manager._settings['capture']['duration'] = 0
        capturer.config_manager._settings['capture']['count'] = None
        
        with pytest.raises(ValueError, match="Duration mode selected but no duration specified"):
            capturer.capture()
    
    def test_duration_mode_rejects_negative_duration(self, capturer):
        """Verify duration mode rejects negative values"""
        capturer.config_manager._settings['capture']['mode'] = 'duration'
        capturer.config_manager._settings['capture']['duration'] = -5
        capturer.config_manager._settings['capture']['count'] = None
        
        with pytest.raises(ValueError, match="Duration must be a positive integer"):
            capturer.capture()
    
    # Count mode tests
    
    def test_count_mode_requires_count_value(self, capturer):
        """Verify count mode fails if count is not set"""
        capturer.config_manager._settings['capture']['mode'] = 'count'
        capturer.config_manager._settings['capture']['count'] = None
        capturer.config_manager._settings['capture']['duration'] = None
        
        with pytest.raises(ValueError, match="Count mode selected but no count specified"):
            capturer.capture()
    
    def test_count_mode_rejects_zero_count(self, capturer):
        """Verify count mode treats 0 as not specified"""
        capturer.config_manager._settings['capture']['mode'] = 'count'
        capturer.config_manager._settings['capture']['count'] = 0
        capturer.config_manager._settings['capture']['duration'] = None
        
        with pytest.raises(ValueError, match="Count mode selected but no count specified"):
            capturer.capture()
    
    def test_count_mode_rejects_negative_count(self, capturer):
        """Verify count mode rejects negative values"""
        capturer.config_manager._settings['capture']['mode'] = 'count'
        capturer.config_manager._settings['capture']['count'] = -10
        capturer.config_manager._settings['capture']['duration'] = None
        
        with pytest.raises(ValueError, match="Count must be a positive integer"):
            capturer.capture()
    
    # Valid configurations - Tests that verify error is NOT raised during validation
    # These tests simulate realistic capture behavior with keyboard interrupt after a few frames
    
    def test_duration_mode_accepts_positive_duration(self, capturer):
        """Verify valid duration mode configuration doesn't raise during validation"""
        capturer.config_manager._settings['capture']['mode'] = 'duration'
        capturer.config_manager._settings['capture']['duration'] = 5
        capturer.config_manager._settings['capture']['count'] = None
        
        # Simulate receiving 2 frames then user interrupts with Ctrl+C
        call_count = [0]
        def mock_recv(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise KeyboardInterrupt()
            return Mock()  # Return frame first call
        
        capturer.bus.recv = mock_recv

        with patch('canpy.capture.CANParser') as mock_parser_class:
            mock_parser_inst = MagicMock()
            mock_parser_inst.parse_frame = Mock(return_value=self.mock_frame_data())
            mock_parser_inst.get_expected_signals = Mock(return_value=None)
            mock_parser_class.return_value = mock_parser_inst
            
            with patch.object(capturer, 'disconnect'):
                with patch.object(capturer, '_print_frame'):
                    result = capturer.capture()
        
        assert result is True
    
    def test_count_mode_accepts_positive_count(self, capturer):
        """Verify valid count mode configuration doesn't raise during validation"""
        capturer.config_manager._settings['capture']['mode'] = 'count'
        capturer.config_manager._settings['capture']['count'] = 3
        capturer.config_manager._settings['capture']['duration'] = None

        # Simulate receiving exactly 3 frames (count limit reached)
        frame_count = [0]
        def mock_recv(*args, **kwargs):
            frame_count[0] += 1
            if frame_count[0] <= 3:
                return Mock()
            return None

        capturer.bus.recv = mock_recv

        with patch('canpy.capture.CANParser') as mock_parser_class:
            mock_parser_inst = MagicMock()
            mock_parser_inst.parse_frame = Mock(return_value=self.mock_frame_data())
            mock_parser_inst.get_expected_signals = Mock(return_value=None)
            mock_parser_class.return_value = mock_parser_inst
            
            with patch.object(capturer, 'disconnect'):
                with patch.object(capturer, '_print_frame'):
                    result = capturer.capture()
        
        assert result is True
    
    def test_continuous_mode_valid_configuration(self, capturer):
        """Verify continuous mode with no duration/count is valid"""
        capturer.config_manager._settings['capture']['mode'] = 'continuous'
        capturer.config_manager._settings['capture']['duration'] = None
        capturer.config_manager._settings['capture']['count'] = None
        
        # Simulate receiving messages then user interrupts with Ctrl+C
        call_count = [0]
        def mock_recv(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 3:  # After 3 calls, simulate Ctrl+C
                raise KeyboardInterrupt()
            return Mock()  # Return frame for first 2 calls
        
        capturer.bus.recv = mock_recv

        with patch('canpy.capture.CANParser') as mock_parser_class:
            mock_parser_inst = MagicMock()
            mock_parser_inst.parse_frame = Mock(return_value=self.mock_frame_data())
            mock_parser_inst.get_expected_signals = Mock(return_value=None)
            mock_parser_class.return_value = mock_parser_inst
            
            with patch.object(capturer, 'disconnect'):
                with patch.object(capturer, '_print_frame'):
                    result = capturer.capture()
        
        assert result is True
    
    def test_mode_defaults_to_continuous(self, capturer):
        """Verify mode defaults to continuous when not set"""
        capturer.config_manager._settings['capture']['mode'] = None
        capturer.config_manager._settings['capture']['duration'] = None
        capturer.config_manager._settings['capture']['count'] = None
        
        # Simulate keyboard interrupt after a couple frames
        call_count = [0]
        def mock_recv(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise KeyboardInterrupt()
            return Mock()
        
        capturer.bus.recv = mock_recv

        with patch('canpy.capture.CANParser') as mock_parser_class:
            mock_parser_inst = MagicMock()
            mock_parser_inst.parse_frame = Mock(return_value=self.mock_frame_data())
            mock_parser_inst.get_expected_signals = Mock(return_value=None)
            mock_parser_class.return_value = mock_parser_inst
            
            with patch.object(capturer, 'disconnect'):
                with patch.object(capturer, '_print_frame'):
                    result = capturer.capture()
        
        assert result is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
