#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAN Data Capture Tool
Reads CAN frames from CANable Z pro+ device and saves to CSV/JSON with optional DBC parsing
"""

import sys
import logging
import os
from typing import Optional
from pathlib import Path

# Suppress python-can debug messages BEFORE importing can
# Decision (Phase 1.1): Keep logging suppressed by default for clean console output.
# Future (Phase 1.2): Add --verbose flag in ConfigManager to allow debug logs on user request.
logging.basicConfig(level=logging.CRITICAL)
logging.getLogger('can').setLevel(logging.CRITICAL)

# Set UTF-8 encoding for console output
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

import time
import argparse
from datetime import datetime

from canpy import CANParser
from canpy import WriterFactory
from canpy import ConfigManager


class CANCapture:
    """Capture and process CAN data"""
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize CAN capture
        
        Args:
            config_manager: Instance of ConfigManager containing configuration settings
        """
        self.config_manager = config_manager
        self.parser = None
        self.writers = {}

        self.bus = None

    def connect(self) -> bool:
        """Connect to CAN bus via CandleLight or SLCAN device"""
        try:
            print(f"Scanning for CAN adapters...")
            
            # Try auto-detection first
            try:
                import can
                configs = can.interface.detect_available_configs()
                
                # Filter for cantact (CandleLight) devices
                cantact_configs = [c for c in configs if c.get('interface') == 'cantact']
                
                if cantact_configs:
                    config = cantact_configs[0]
                    print(f"Found CandleLight adapter: {config}")
                    
                    # Extract channel number from format "ch:0"
                    channel = config.get('channel', '0')
                    if ':' in str(channel):
                        channel = str(channel).split(':')[1]
                    
                    self.bus = can.interface.Bus(
                        interface='cantact',
                        channel=channel,
                        bitrate=self.config_manager.get_setting('can', 'bitrate'),
                        timeout=1.0
                    )
                    print(f"[OK] Connected via CandleLight USB adapter")
                    return True
            except Exception as e:
                print(f"[INFO] Auto-detection attempt: {e}")
            
            # Fallback: Try specific cantact connection
            try:
                print(f"Trying CandleLight direct connection...")
                self.bus = can.interface.Bus(
                    interface='cantact',
                    channel='0',
                    bitrate=self.config_manager.get_setting('can', 'bitrate'),
                    timeout=1.0
                )
                print(f"[OK] Connected to CandleLight adapter (channel 0)")
                return True
            except Exception as e:
                print(f"[INFO] CandleLight direct failed: {e}")
            
            # Fallback: Try SLCAN if serial port is specified
            if self.config_manager.get_setting('can', 'serial_port'):
                serial_port = self.config_manager.get_setting('can', 'serial_port')
                print(f"Trying SLCAN on port {serial_port}...")
                self.bus = can.interface.Bus(
                    interface='slcan',
                    channel=serial_port,
                    bitrate=self.config_manager.get_setting('can', 'bitrate'),
                    timeout=1.0
                )
                print(f"[OK] Connected via SLCAN on {serial_port}")
                return True
            
            print("[OK] Connected to CAN bus")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to connect: {e}")
            print("\nTroubleshooting:")
            print("1. Ensure CandleLight USB adapter is connected")
            print("2. For Linux/Mac: Install can-utils (candump should work)")
            print("3. For Windows: May need additional drivers")
            print("\nDiagnostics:")
            print("- Run: python test_canable.py")
            print("- Check Device Manager for 'CandleLight USB to CAN adapter'")
            return False
    
    def _matches_filter(self, can_id_decimal: int) -> bool:
        """
        Check if a CAN ID matches the filter
        
        Args:
            can_id_decimal: CAN ID in decimal format
            
        Returns:
            True if no filter is set or if CAN ID matches filter
        """
        filter_can_ids = self.config_manager.get_setting('dbc', 'filter') or []
        if not filter_can_ids:
            return True
        return can_id_decimal in filter_can_ids
    
    def capture(self) -> bool:
        """
        Capture CAN frames
        """
        if not self.bus:
            print("[ERROR] Not connected to CAN bus")
            return False
        
        # Initialize parser with DBC if provided
        dbc_file = self.config_manager.get_setting('dbc', 'file')
        if dbc_file:
            self.parser = CANParser(dbc_file)
            expected_signals = self.parser.get_expected_signals()
        else:
            self.parser = CANParser(None)
            expected_signals = None
        
        # Initialize writer if formats specified
        log_formats = self.config_manager.get_setting('output', 'formats')
        output_dir = self.config_manager.get_setting('output', 'directory')
        if log_formats:
            for format in log_formats:
                writer = WriterFactory.create(format,
                                              output_dir=output_dir,
                                              expected_signals=expected_signals)
                writer.start_streaming()
                self.writers[format] = writer
        
        # Initialize the capture mode
        mode = self.config_manager.get_setting('capture', 'mode') or 'continuous'
        duration = self.config_manager.get_setting('capture', 'duration')
        count = self.config_manager.get_setting('capture', 'count')

        if mode == 'duration':
            if not duration:
                raise ValueError("Duration mode selected but no duration specified. Set capture duration with --duration")
            if duration and duration <= 0:
                raise ValueError("Duration must be a positive integer")
            if count:
                print("[WARNING] Count specified but duration mode selected. Duration will take precedence.")
            
            print(f"Capturing for {duration} seconds...")

        elif mode == 'count':
            if not count:
                raise ValueError("Count mode selected but no count specified. Set capture count with --count")
            if count and count <= 0:
                raise ValueError("Count must be a positive integer")
            if duration:
                print("[WARNING] Duration specified but count mode selected. Count will take precedence.")
            
            print(f"Capturing {count} frames...")

        elif mode == 'continuous':
            if duration or count:
                print("[WARNING] Duration or count specified but continuous mode selected. Continuous mode will ignore these settings.")

            print("Capturing continuously (press Ctrl+C to stop)...")
        
        # Initialize CAN ID filter
        filter_can_ids = self.config_manager.get_setting('dbc', 'filter') or []
        if filter_can_ids:
            filter_ids_hex = [f"0x{cid:03X}" for cid in sorted(filter_can_ids)]
            print(f"CAN ID Filter: {', '.join(filter_ids_hex)}")
        
        # Initialize log formats
        log_formats = self.config_manager.get_setting('output', 'formats')
        if log_formats:
            print(f"Logging to: {', '.join(log_formats).upper()}")
        else:
            print("Output: Console only (like candump)")
        
        
        print("\n" + "=" * 80)
        print("Starting CAN capture...")
        print("=" * 80)

        start_time = time.time()
        frame_count = 0
        last_stats_time = start_time
        
        try:
            while True:
                # Check duration
                if mode == 'duration' and (time.time() - start_time) > duration:
                    print(f"\n[OK] Duration limit reached ({duration}s)")
                    break
                
                # Check count
                if mode == 'count' and frame_count >= count:
                    print(f"\n[OK] Frame count limit reached ({count} frames)")
                    break
                
                # Read message
                msg = self.bus.recv(timeout=1.0)
                if msg is None:
                    continue
                
                # Parse frame
                frame_data = self.parser.parse_frame(msg)
                
                # Apply CAN ID filter
                if not self._matches_filter(frame_data['can_id_dec']):
                    continue
                
                frame_count += 1
                
                # Stream to files if enabled
                if self.writers:
                    for writer in self.writers.values():
                        try:
                            writer.write_frame(frame_data)
                        except Exception as e:
                            print(f"[ERROR] Failed to write frame to {writer}: {e}")
                
                # Display in console
                self._print_frame(frame_data, frame_count)
                
                # Print stats periodically for long captures
                current_time = time.time()
                if self.writers and (current_time - last_stats_time) > 10:
                    stats = next(iter(self.writers.values())).get_stats()
                    fps = stats['fps']
                    elapsed = stats['elapsed_seconds']
                    print(f"[INFO] {elapsed:.1f}s | {frame_count} frames | {fps:.1f} fps")
                    last_stats_time = current_time
        
        except KeyboardInterrupt:
            print(f"\n[OK] Capture stopped by user")
        
        except Exception as e:
            # Safely print error without Unicode issues
            error_msg = str(e).replace('\u2713', 'OK').replace('\u2717', 'ERROR')
            print(f"\n[ERROR] Capture error: {error_msg}")
            return False
        
        finally:
            # Close streaming writers if active
            if self.writers:
                for writer in self.writers.values():
                    writer.stop_streaming()
            self.disconnect()
        
        print(f"\n{'=' * 80}")
        print(f"Capture complete: {frame_count} frames captured")
        print(f"{'=' * 80}\n")
        
        return True
    
    def _print_frame(self, frame_data, frame_num) -> None:
        """Print frame to console"""
        if self.config_manager.get_setting('capture', 'no_console'):
            return
        
        timestamp = datetime.fromtimestamp(frame_data['timestamp']).strftime("%H:%M:%S.%f")[:-3]
        print(f"[{frame_num:5d}] {timestamp} | ID: {frame_data['can_id']:>4s} | "
              f"DLC: {frame_data['dlc']} | Data: {frame_data['data_hex']}", end='')
        
        if frame_data.get('parsed') and self.config_manager.get_setting('capture', 'show_parsed'):
            signals = frame_data['parsed']
            signal_str = ' | '.join(f"{k}={v}" for k, v in signals.items())
            print(f" | Signals: {signal_str}")
        else:
            print()
    
    def disconnect(self) -> None:
        """Disconnect from CAN bus"""
        if self.bus:
            try:
                self.bus.shutdown()
                print("[OK] Disconnected from CAN bus")
            except:
                pass


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='CAN data capture tool - reads from CANable Z pro+ device',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
USAGE:
  By default, frames are printed to console:
  
  # Capture mode (default: continuous until Ctrl+C, or specify duration/count)
  python can_capture.py --duration 30
  
  # Capture and parse signals (requires DBC)
  python can_capture.py --duration 60 --dbc car.dbc
  
  # Save to files (CSV, JSON, or both)
  python can_capture.py --duration 30 --log csv,json --dbc car.dbc
  
  # Continuous capture (press Ctrl+C to stop)
  python can_capture.py --dbc car.dbc --log json
  
  # Filter by CAN ID
  python can_capture.py --duration 30 --filter-can-id 0x123
  
  # Filter by multiple CAN IDs
  python can_capture.py --duration 30 --filter-can-id 0x123,0x456,0x789

  # Load specific user config file
  python can_capture.py --config my_config.yaml
        '''
    )
    
    # CAN settings
    parser.add_argument(
        '--interface', default=None,
        help='CAN interface to use (e.g., cantact, slcan)'
    )
    parser.add_argument(
        '--bitrate', type=int, default=None,
        help='CAN bitrate in bps (default: 500000)'
    )
    parser.add_argument(
        '--port', default=None,
        help='Serial port for CANable device (e.g., COM3, /dev/ttyUSB0)'
    )

    # Capture settings
    parser.add_argument(
        '--mode', default=None, choices=['duration', 'count', 'continuous'],
        help='Capture mode: continuous (default), duration, or count'
    )
    parser.add_argument(
        '--duration', type=int, default=None,
        help='Capture duration in seconds'
    )
    parser.add_argument(
        '--count', type=int, default=None,
        help='Number of frames to capture'
    )
    parser.add_argument(
        '--no-console', action='store_true',
        help='Disable console output'
    )
    parser.add_argument(
        '--show-parsed', action='store_true',
        help='Show parsed signal values in console (requires DBC)'
    )

    # Output settings
    parser.add_argument(
        '--output-dir', default=None,
        help='Output directory for files (default: data)'
    )
    parser.add_argument(
        '--log', default=None,
        help='Log to files in formats: csv,json,txt (comma-separated, no spaces)'
    )

    # DBC settings
    parser.add_argument(
        '--dbc', default=None,
        help='Path to DBC file for signal decoding'
    )

    # Other settings
    parser.add_argument(
        '--filter-can-id', default=None,
        help='Filter by CAN ID(s): comma-separated hex values (e.g., 0x123,0x456 or 0x123)'
    )
    parser.add_argument(
        '--config', default=None,
        help='Path to user config YAML file (optional). Auto-detects ./user_config.yaml if not provided'
    )

    args = parser.parse_args()

    # Pre-process complex arguments
    if args.filter_can_id:
        try:
            filter_can_ids = []
            for can_id_str in args.filter_can_id.split(','):
                # Parse hex or decimal
                if can_id_str.lower().startswith('0x'):
                    can_id = int(can_id_str, 16)
                else:
                    can_id = int(can_id_str)
                filter_can_ids.append(can_id)
            args.filter_can_id = filter_can_ids
        except ValueError:
            print(f"[ERROR] Invalid CAN ID filter format: {args.filter_can_id}")
            print("Expected format: comma-separated hex values (e.g., 0x123,0x456)")
            return 1
    
    if args.log:
        try:
            log_formats = []
            for fmt in args.log.split(','):
                fmt = fmt.strip().lower()
                log_formats.append(fmt)
            args.log = log_formats
        except Exception as e:
            print(f"[ERROR] Invalid log format: {args.log}")
            print("Expected format: comma-separated values (e.g., csv,json)")
            return 1

    # Update config
    try:
        config_manager = ConfigManager()
        config_manager.load_defaults_conf()
        if args.config:
            config_manager.load_user_conf(Path(args.config))
            print(f"[OK] Loaded user config from {args.config}")
        else:
            if Path('user_config.yaml').exists():
                config_manager.load_user_conf(Path('user_config.yaml'))  # Auto-detect user config file
                print(f"[OK] Loaded user config from ./user_config.yaml")
        config_manager.load_env_conf()
        config_manager.load_args_conf(args)
        config_manager.validate_config()
    except Exception as e:
        print(f"[ERROR] Configuration error: {e}")
        return 1
    
    # Create capturer
    capturer = CANCapture(config_manager)
    
    # Connect and capture
    if not capturer.connect():
        return 1
    
    if not capturer.capture():
        return 1
    
    print("[OK] Done!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
