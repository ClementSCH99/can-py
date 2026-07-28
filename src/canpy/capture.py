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

import canpy.config as config
from canpy import CANParser
from canpy import WriterFactory
from canpy.nhr import NHRMeasurementStream, NHRStreamError


class CANCapture:
    """Capture and process CAN data"""
    
    def __init__(
        self,
        dbc_file=None,
        bitrate=500000,
        serial_port=None,
        log_formats=None,
        filter_can_ids=None,
        nhr_stream=None,
        nhr_ready_timeout_s=10.0,
    ):
        """
        Initialize CAN capture
        
        Args:
            dbc_file: Path to DBC file (optional)
            bitrate: CAN bus bitrate in bps
            serial_port: Serial port for SLCAN device
            log_formats: List of formats for streaming ('csv', 'json'), None for console-only
            filter_can_ids: List of CAN IDs to filter by (optional)
            nhr_stream: Optional read-only NHR measurement stream
            nhr_ready_timeout_s: Maximum wait for the first NHR measurement
        """
        self.dbc_file = dbc_file
        self.bitrate = bitrate
        self.serial_port = serial_port
        self.bus = None
        self.parser = None
        self.frames = []  # Only used if not streaming
        self.log_formats = log_formats
        self.writer = None  # StreamingOutputWriter if log_formats is set
        self.writers = {}
        self.output_dir: Optional[str] = 'data'
        self.filter_can_ids = filter_can_ids or []  # List of CAN IDs to filter by
        self.nhr_stream = nhr_stream
        self.nhr_ready_timeout_s = nhr_ready_timeout_s
        self._last_nhr_status_time = 0.0
    
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
                        bitrate=self.bitrate,
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
                    bitrate=self.bitrate,
                    timeout=1.0
                )
                print(f"[OK] Connected to CandleLight adapter (channel 0)")
                return True
            except Exception as e:
                print(f"[INFO] CandleLight direct failed: {e}")
            
            # Fallback: Try SLCAN if serial port is specified
            if self.serial_port:
                print(f"Trying SLCAN on port {self.serial_port}...")
                self.bus = can.interface.Bus(
                    interface='slcan',
                    channel=self.serial_port,
                    bitrate=self.bitrate,
                    timeout=1.0
                )
                print(f"[OK] Connected via SLCAN on {self.serial_port}")
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
        if not self.filter_can_ids:
            return True
        return can_id_decimal in self.filter_can_ids
    
    def capture(self, duration=None, count=None) -> bool:
        """
        Capture CAN frames
        
        Args:
            duration: Capture for N seconds (None for inf)
            count: Capture N frames (None for inf)
        """
        if not self.bus:
            print("[ERROR] Not connected to CAN bus")
            return False

        if self.nhr_stream is not None:
            try:
                print(
                    f"[INFO] Waiting for first NHR measurement "
                    f"({self.nhr_stream.instrument_id})..."
                )
                self.nhr_stream.start(timeout_s=self.nhr_ready_timeout_s)
                measurement = self.nhr_stream.latest()
                statistics = self.nhr_stream.statistics()
                print(
                    f"[OK] NHR stream ready after "
                    f"{statistics.first_sample_delay_s:.2f}s | "
                    f"{measurement.voltage_v:.3f} V | "
                    f"{measurement.current_a:.3f} A | "
                    f"{measurement.power_w:.3f} W"
                )
            except NHRStreamError as exc:
                print(f"[ERROR] Could not start NHR observation: {exc}")
                self.disconnect()
                return False
        
        # Initialize parser with DBC if provided
        if self.dbc_file:
            self.parser = CANParser(self.dbc_file)
            expected_signals = self.parser.get_expected_signals()
        else:
            self.parser = CANParser(None)
            expected_signals = None
        
        # Initialize streaming writer if formats specified
        if self.log_formats:
            if self.output_dir is None:
                self.output_dir = 'data'
            for format in self.log_formats:
                writer = WriterFactory.create(format,
                                              output_dir=self.output_dir,
                                              expected_signals=expected_signals)
                writer.start_streaming()
                self.writers[format] = writer
        
        print("\n" + "=" * 80)
        print("Starting CAN capture...")
        print("=" * 80)
        
        if duration:
            print(f"Capturing for {duration} seconds...")
        elif count:
            print(f"Capturing {count} frames...")
        else:
            print("Capturing continuously (press Ctrl+C to stop)...")
        
        if self.filter_can_ids:
            filter_ids_hex = [f"0x{cid:03X}" for cid in sorted(self.filter_can_ids)]
            print(f"CAN ID Filter: {', '.join(filter_ids_hex)}")
        
        if self.log_formats:
            print(f"Logging to: {', '.join(self.log_formats).upper()}")
        else:
            print("Output: Console only (like candump)")
        
        
        start_time = time.time()
        frame_count = 0
        last_stats_time = start_time
        
        try:
            while True:
                # Check duration
                if duration and (time.time() - start_time) > duration:
                    print(f"\n[OK] Duration limit reached ({duration}s)")
                    break
                
                # Check count
                if count and frame_count >= count:
                    print(f"\n[OK] Frame count limit reached ({count} frames)")
                    break
                
                # Read message
                msg = self.bus.recv(timeout=1.0)
                if msg is None:
                    self._print_nhr_status()
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
                else:
                    # Keep in memory only if not streaming (short recordings)
                    self.frames.append(frame_data)
                
                # Display in console
                self._print_frame(frame_data, frame_count)
                self._print_nhr_status()
                
                # Print stats periodically for long captures
                current_time = time.time()
                if self.writers and (current_time - last_stats_time) > 10:
                    # Design (Phase 1.1): All writers get the same frames at the same FPS.
                    # Stats are identical across writers, so reporting first writer is sufficient.
                    # Future Enhancement (Phase 2): Multi-writer aggregation if writers operate independently.
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
            # Close streaming writers and NHR stream if active
            if self.writers:
                for writer in self.writers.values():
                    writer.stop_streaming()
            if self.nhr_stream is not None:
                self.nhr_stream.stop()
                self._print_nhr_summary()
            self.disconnect()
        
        print(f"\n{'=' * 80}")
        print(f"Capture complete: {frame_count} frames captured")
        print(f"{'=' * 80}\n")
        
        return True

    def _print_nhr_status(self) -> None:
        """Periodically show the newest read-only NHR measurement."""
        if self.nhr_stream is None:
            return
        now = time.time()
        if now - self._last_nhr_status_time < 5.0:
            return
        self._last_nhr_status_time = now

        measurement = self.nhr_stream.latest()
        if measurement is None:
            detail = self.nhr_stream.error or "waiting for first measurement"
            print(f"[NHR] {detail}")
            return

        freshness = (
            f"STALE ({measurement.age_seconds():.1f}s old)"
            if self.nhr_stream.is_stale()
            else f"fresh ({measurement.age_seconds():.1f}s old)"
        )
        temperature = (
            "n/a"
            if measurement.temperature_c is None
            else f"{measurement.temperature_c:.1f} C"
        )
        print(
            f"[NHR] {measurement.voltage_v:.3f} V | "
            f"{measurement.current_a:.3f} A | "
            f"{measurement.power_w:.3f} W | "
            f"{temperature} | {freshness}"
            + (
                f" | ERROR: {self.nhr_stream.error}"
                if self.nhr_stream.error
                else ""
            )
        )

    def _print_nhr_summary(self) -> None:
        """Report NHR stream completeness without discarding the CAN capture."""
        statistics = self.nhr_stream.statistics()
        rate = (
            "n/a"
            if statistics.observed_rate_hz is None
            else f"{statistics.observed_rate_hz:.2f} Hz"
        )
        first_delay = (
            "n/a"
            if statistics.first_sample_delay_s is None
            else f"{statistics.first_sample_delay_s:.2f} s"
        )
        stale = self.nhr_stream.is_stale()
        print("\nNHR stream summary:")
        print(f"  Samples received: {statistics.received_count}")
        print(f"  First sample delay: {first_delay}")
        print(f"  Observed rate: {rate}")
        print(f"  Local queue drops: {statistics.dropped_count}")
        print(f"  Final sample stale: {'yes' if stale else 'no'}")
        if statistics.error:
            print(
                f"[WARNING] CAN capture was preserved, but the NHR stream "
                f"was incomplete: {statistics.error}"
            )
        else:
            print("  Stream error: none")
    
    def _print_frame(self, frame_data, frame_num) -> None:
        """Print frame to console"""
        if not config.SHOW_CONSOLE:
            return
        
        timestamp = datetime.fromtimestamp(frame_data['timestamp']).strftime("%H:%M:%S.%f")[:-3]
        print(f"[{frame_num:5d}] {timestamp} | ID: {frame_data['can_id']:>4s} | "
              f"DLC: {frame_data['dlc']} | Data: {frame_data['data_hex']}", end='')
        
        if frame_data.get('parsed') and config.SHOW_PARSED:
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
  By default, frames are printed to console (like candump):
  
  # Capture to console (30 seconds)
  python can_capture.py --duration 30
  
  # Capture and parse signals (requires DBC)
  python can_capture.py --duration 60 --dbc car.dbc
  
  # Save to files (CSV, JSON, or both)
  python can_capture.py --duration 30 --log csv,json --dbc car.dbc
  
  # Long recordings (3+ hours with streaming)
  python can_capture.py --dbc car.dbc --log csv
  
  # Continuous capture (press Ctrl+C to stop)
  python can_capture.py --dbc car.dbc --log json
  
  # Filter by CAN ID
  python can_capture.py --duration 30 --filter-can-id 0x123
  
  # Filter by multiple CAN IDs
  python can_capture.py --duration 30 --filter-can-id 0x123,0x456,0x789
        '''
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
        '--port', default=None,
        help='Serial port for CANable device (e.g., COM3, /dev/ttyUSB0)'
    )
    parser.add_argument(
        '--dbc', default=None,
        help='Path to DBC file for signal decoding'
    )
    parser.add_argument(
        '--bitrate', type=int, default=500000,
        help='CAN bitrate in bps (default: 500000)'
    )
    parser.add_argument(
        '--log', default=None,
        help='Log to files in formats: csv,json,txt (comma-separated, no spaces)'
    )
    parser.add_argument(
        '--output-dir', default='data',
        help='Output directory for files (default: data)'
    )
    parser.add_argument(
        '--no-console', action='store_true',
        help='Disable console output'
    )
    parser.add_argument(
        '--filter-can-id', default=None,
        help='Filter by CAN ID(s): comma-separated hex values (e.g., 0x123,0x456 or 0x123)'
    )
    parser.add_argument(
        '--nhr-url', default=None,
        help='Local nhr-rt service URL (requires --nhr-instrument)'
    )
    parser.add_argument(
        '--nhr-instrument', default=None,
        help='NHR instrument ID configured in nhr-rt (requires --nhr-url)'
    )
    parser.add_argument(
        '--nhr-ready-timeout', type=float, default=10.0,
        help='Seconds to wait for the first valid NHR measurement (default: 10)'
    )
    
    args = parser.parse_args()

    if bool(args.nhr_url) != bool(args.nhr_instrument):
        print("[ERROR] --nhr-url and --nhr-instrument must be supplied together")
        return 1
    if args.nhr_ready_timeout <= 0:
        print("[ERROR] --nhr-ready-timeout must be positive")
        return 1
    
    # Validate DBC file if provided
    if args.dbc and not Path(args.dbc).exists():
        print(f"[ERROR] DBC file not found: {args.dbc}")
        return 1
    
    # Parse log formats
    log_formats = None
    if args.log:
        log_formats = [fmt.strip() for fmt in args.log.split(',')]
        # Validate formats
        valid_formats = {'csv', 'json', 'txt'}
        for fmt in log_formats:
            if fmt not in valid_formats:
                print(f"[ERROR] Invalid log format '{fmt}'. Valid: csv, json, txt")
                return 1
    
    # Parse CAN ID filter
    filter_can_ids = []
    if args.filter_can_id:
        try:
            can_id_strs = [s.strip() for s in args.filter_can_id.split(',')]
            for can_id_str in can_id_strs:
                # Parse hex or decimal
                if can_id_str.lower().startswith('0x'):
                    can_id = int(can_id_str, 16)
                else:
                    can_id = int(can_id_str)
                filter_can_ids.append(can_id)
        except ValueError as e:
            print(f"[ERROR] Invalid CAN ID format: {args.filter_can_id}")
            print(f"  Use hex format (e.g., 0x123) or decimal (e.g., 291)")
            return 1
    
    nhr_stream = None
    if args.nhr_url and args.nhr_instrument:
        nhr_stream = NHRMeasurementStream(
            instrument_id=args.nhr_instrument,
            base_url=args.nhr_url,
        )

    # Create capturer
    capturer = CANCapture(
        dbc_file=args.dbc,
        bitrate=args.bitrate,
        serial_port=args.port,
        log_formats=log_formats,
        filter_can_ids=filter_can_ids,
        nhr_stream=nhr_stream,
        nhr_ready_timeout_s=args.nhr_ready_timeout,
    )
    
    # Set output directory
    capturer.output_dir = args.output_dir
    
    # Update config for console output
    config.OUTPUT_DIR = args.output_dir
    config.SHOW_CONSOLE = not args.no_console
    
    # Connect and capture
    if not capturer.connect():
        return 1
    
    if not capturer.capture(duration=args.duration, count=args.count):
        return 1
    
    print("[OK] Done!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
