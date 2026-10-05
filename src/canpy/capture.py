#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAN Data Capture Tool
Reads CAN frames from CANable Z pro+ device and saves to CSV/JSON with optional DBC parsing
"""

import sys
import logging
import os
import subprocess
from dataclasses import asdict, is_dataclass
from typing import Mapping, Optional
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
import yaml
from datetime import datetime, timezone

from canpy import CANParser
from canpy import WriterFactory
from canpy import ConfigManager
from canpy.capture_manifest import (
    CaptureManifestError,
    build_capture_manifest,
    sha256_file,
    utc_now_text,
    write_json_atomic,
)
from canpy.nhr import (
    BMS_POC_V2_MAPPING,
    ExternalSnapshotAssembler,
    ExternalSnapshotForwarder,
    NHRRecordingEvidenceError,
    read_nhr_workflow_evidence,
)
from canpy.writers import MergedCSVError, MergedCSVWriter, load_signal_file


class CANCapture:
    """Capture and process CAN data"""
    
    def __init__(
        self,
        config_manager: ConfigManager,
        nhr_forwarder=None,
        nhr_snapshot_assembler=None,
        merged_signals=None,
        merged_can_stale_after_s: float = 2.5,
        nhr_run_id: Optional[str] = None,
        nhr_scope: str = "session",
        nhr_stage_index: Optional[int] = None,
        nhr_finalize_timeout_s: float = 60.0,
        merged_output_path: Optional[str] = None,
        nhr_evidence_reader=read_nhr_workflow_evidence,
        cli_overrides=None,
    ):
        """
        Initialize CAN capture
        
        Args:
            config_manager: Instance of ConfigManager containing configuration settings
        """
        self.config_manager = config_manager
        self.parser = None
        self.writers = {}

        self.bus = None
        self.nhr_forwarder = nhr_forwarder
        self.nhr_snapshot_assembler = nhr_snapshot_assembler
        self._nhr_forwarding_error = None
        self.merged_signals = set(merged_signals or [])
        self.merged_can_stale_after_s = merged_can_stale_after_s
        self.nhr_run_id = nhr_run_id
        self.nhr_scope = nhr_scope
        self.nhr_stage_index = nhr_stage_index
        self.nhr_finalize_timeout_s = nhr_finalize_timeout_s
        self.merged_output_path = merged_output_path
        self.nhr_evidence_reader = nhr_evidence_reader
        self._can_csv_path = None
        self._merged_csv_path = None
        self._merged_csv_error = None
        self._can_close_error = None
        self._manifest_error = None
        self._manifest_path = None
        self._source_paths = {}
        self._forwarding_statistics = None
        self.capture_id = f"can_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.cli_overrides = list(cli_overrides or [])

    def connect(self) -> bool:
        """Connect to CAN bus via CandleLight or SLCAN device"""
        try:
            import can

            bitrate = self.config_manager.get_setting('can', 'bitrate')
            preferred_interface = self.config_manager.get_setting('can', 'interface')
            serial_port = self.config_manager.get_setting('can', 'serial_port')

            # An explicit port is an operator override and keeps the historical
            # SLCAN behavior. A null port selects automatic adapter discovery.
            if serial_port:
                print(f"Trying explicit SLCAN port {serial_port}...")
                self.bus = can.interface.Bus(
                    interface='slcan',
                    channel=serial_port,
                    bitrate=bitrate,
                    timeout=1.0,
                )
                print(f"[OK] Connected via SLCAN on {serial_port}")
                return True

            print("Scanning for CAN adapters (serial_port is automatic)...")
            try:
                configs = can.interface.detect_available_configs()
                supported = [
                    config for config in configs
                    if config.get('interface') in {preferred_interface, 'cantact', 'slcan'}
                ]
                supported.sort(
                    key=lambda config: config.get('interface') != preferred_interface
                )
                for config in supported:
                    interface = config.get('interface')
                    channel = config.get('channel', '0' if interface == 'cantact' else None)
                    if channel is None:
                        continue
                    if interface == 'cantact' and ':' in str(channel):
                        channel = str(channel).split(':', 1)[1]
                    print(f"Found {interface} adapter: {config}")
                    try:
                        self.bus = can.interface.Bus(
                            interface=interface,
                            channel=channel,
                            bitrate=bitrate,
                            timeout=1.0,
                        )
                    except Exception as exc:
                        self.bus = None
                        print(f"[INFO] Could not open detected adapter: {exc}")
                        continue
                    else:
                        print(f"[OK] Connected via auto-detected {interface} adapter")
                        return True
            except Exception as e:
                print(f"[INFO] Auto-detection attempt: {e}")

            # Preserve the legacy CandleLight channel-0 fallback for backends
            # that cannot enumerate adapters but can still open the device.
            try:
                print("Trying CandleLight direct connection...")
                self.bus = can.interface.Bus(
                    interface='cantact',
                    channel='0',
                    bitrate=bitrate,
                    timeout=1.0,
                )
                print(f"[OK] Connected to CandleLight adapter (channel 0)")
                return True
            except Exception as e:
                print(f"[INFO] CandleLight direct failed: {e}")

            raise RuntimeError("No compatible CAN adapter could be opened")
            
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

        if self.nhr_snapshot_assembler is not None:
            missing_signals = sorted(
                self.nhr_snapshot_assembler.required_dbc_signals
                - set(expected_signals or [])
            )
            if missing_signals:
                print(
                    "[ERROR] NHR snapshot signal(s) not found in DBC: "
                    + ", ".join(missing_signals)
                )
                self.disconnect()
                return False

        if self.merged_signals:
            missing_signals = sorted(
                self.merged_signals - set(expected_signals or [])
            )
            if missing_signals:
                print(
                    "[ERROR] Merged CAN signal(s) not found in DBC: "
                    + ", ".join(missing_signals)
                )
                self.disconnect()
                return False
        
        # Initialize writer if formats specified
        log_formats = self.config_manager.get_setting('output', 'formats')
        output_dir = self.config_manager.get_setting('output', 'directory')
        if log_formats:
            for format in log_formats:
                writer = WriterFactory.create(format,
                                              output_dir=output_dir,
                                              expected_signals=expected_signals)
                paths = writer.start_streaming(filename=self.capture_id)
                self.writers[format] = writer
                if isinstance(paths, Mapping):
                    for role, source_path in paths.items():
                        self._source_paths[role] = Path(source_path)
                if format == "csv":
                    self._can_csv_path = paths.get("csv")
        
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

        if self.nhr_forwarder is not None:
            try:
                # The service handshake runs in the worker. CAN acquisition
                # never waits for HTTP readiness.
                self.nhr_forwarder.start()
            except Exception as exc:
                self._record_nhr_forwarding_error(exc)

        start_time = time.time()
        started_at_utc = utc_now_text()
        frame_count = 0
        last_stats_time = start_time
        final_state = "completed"
        closure_reason = "completed"
        
        try:
            while True:
                # Check duration
                if mode == 'duration' and (time.time() - start_time) > duration:
                    print(f"\n[OK] Duration limit reached ({duration}s)")
                    closure_reason = "duration_limit"
                    break
                
                # Check count
                if mode == 'count' and frame_count >= count:
                    print(f"\n[OK] Frame count limit reached ({count} frames)")
                    closure_reason = "count_limit"
                    break
                
                # Read message
                msg = self.bus.recv(timeout=1.0)
                if msg is None:
                    continue
                
                # Parse frame
                received_at = datetime.now(timezone.utc)
                frame = self.parser.parse_frame(msg, timestamp_utc=received_at)

                self._forward_nhr_snapshot(frame)
                
                # Apply CAN ID filter
                if not self._matches_filter(frame.can_id):
                    continue
                
                frame_count += 1
                
                # Stream to files if enabled
                if self.writers:
                    for writer in self.writers.values():
                        try:
                            writer.write_frame(frame)
                        except Exception as e:
                            print(f"[ERROR] Failed to write frame to {writer}: {e}")
                            final_state = "failed"
                            closure_reason = "writer_error"
                            raise
                
                # Display in console
                self._print_frame(frame, frame_count)
                
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
            closure_reason = "user_interrupt"
        
        except Exception as e:
            # Safely print error without Unicode issues
            error_msg = str(e).replace('\u2713', 'OK').replace('\u2717', 'ERROR')
            print(f"\n[ERROR] Capture error: {error_msg}")
            final_state = "failed"
            closure_reason = "capture_error"
        
        finally:
            # Close and flush every CAN-owned source before any NHR HTTP wait.
            close_errors = []
            if self.writers:
                for writer in self.writers.values():
                    try:
                        writer.stop_streaming()
                    except Exception as exc:
                        close_errors.append(f"{type(exc).__name__}: {exc}")
            try:
                self.disconnect()
            except Exception as exc:
                close_errors.append(f"{type(exc).__name__}: {exc}")
            if close_errors:
                self._can_close_error = "; ".join(close_errors)
                print(f"[ERROR] One or more CAN sources did not close cleanly: {self._can_close_error}")

            if self.nhr_forwarder is not None:
                try:
                    self.nhr_forwarder.stop()
                except Exception as exc:
                    self._record_nhr_forwarding_error(exc)
                self._print_nhr_forwarding_summary()

            ended_at_utc = utc_now_text()
            if close_errors:
                final_state = "failed"
                closure_reason = "source_close_error"

            if self._source_paths:
                try:
                    self._write_capture_manifest(
                        started_at_utc=started_at_utc,
                        ended_at_utc=ended_at_utc,
                        final_state=final_state,
                        closure_reason=closure_reason,
                        frame_count=frame_count,
                    )
                except (CaptureManifestError, OSError) as exc:
                    self._manifest_error = f"{type(exc).__name__}: {exc}"
                    print(
                        "[ERROR] CAN manifest was not created; all closed CAN "
                        f"sources were preserved: {exc}"
                    )

        if self.merged_signals and self._can_close_error is None and final_state == "completed":
            try:
                if self.nhr_run_id:
                    self._write_merged_csv()
                else:
                    self._print_deferred_merge_command()
            except (MergedCSVError, NHRRecordingEvidenceError, OSError) as exc:
                self._merged_csv_error = f"{type(exc).__name__}: {exc}"
                print(
                    "[ERROR] Merged CSV was not created; source evidence was "
                    f"preserved: {exc}"
                )
        elif self._manifest_path and final_state == "completed":
            self._print_deferred_merge_command()
        
        print(f"\n{'=' * 80}")
        print(f"Capture complete: {frame_count} frames captured")
        print(f"{'=' * 80}\n")
        
        return (
            self._nhr_forwarding_complete()
            and self._merged_csv_error is None
            and self._can_close_error is None
            and self._manifest_error is None
            and final_state == "completed"
        )

    def _write_capture_manifest(
        self,
        *,
        started_at_utc: str,
        ended_at_utc: str,
        final_state: str,
        closure_reason: str,
        frame_count: int,
    ) -> None:
        output_dir = Path(self.config_manager.get_setting('output', 'directory')).resolve()
        manifest_path = output_dir / f"{self.capture_id}.manifest.json"
        settings = self.config_manager.get_section()
        profile = None
        if self.config_manager.profile_path is not None:
            profile = {
                "path": self.config_manager.profile_configured_path,
                "sha256": self.config_manager.profile_sha256,
            }
        dbc_path = settings.get("dbc", {}).get("file")
        dbc = None
        if dbc_path:
            resolved_dbc = Path(dbc_path).resolve()
            dbc = {"path": Path(dbc_path).as_posix(), "sha256": sha256_file(resolved_dbc)}
        nhr = settings.get("nhr", {})
        merge = settings.get("merge", {})
        effective_config = {
            "can": dict(settings.get("can", {})),
            "capture": dict(settings.get("capture", {})),
            "output": dict(settings.get("output", {})),
            "cli_overrides": list(self.cli_overrides),
        }
        payload = build_capture_manifest(
            manifest_path=manifest_path,
            capture_id=self.capture_id,
            started_at_utc=started_at_utc,
            ended_at_utc=ended_at_utc,
            final_state=final_state,
            closure_reason=closure_reason,
            frame_count=frame_count,
            source_paths=sorted(self._source_paths.items()),
            effective_config=effective_config,
            profile=profile,
            dbc=dbc,
            nhr_identity={
                "service_url": nhr.get("service_url"),
                "instrument_id": nhr.get("instrument_id"),
                "source_id": nhr.get("source_id"),
            },
            forwarding_statistics=self._forwarding_statistics,
            merge_defaults={
                "scope": merge.get("default_scope"),
                "can_stale_after_s": merge.get("can_stale_after_s"),
                "signals": list(merge.get("signals", [])),
            },
        )
        write_json_atomic(manifest_path, payload)
        self._manifest_path = str(manifest_path.resolve())
        print(f"[OK] CAN manifest saved: {self._manifest_path}")

    def _write_merged_csv(self) -> None:
        """Create the derived CSV after the CAN writer has been closed."""
        if not self._can_csv_path:
            raise MergedCSVError("CAN CSV path is unavailable")
        if self.nhr_forwarder is None:
            raise MergedCSVError("NHR forwarding is not configured")

        evidence = self.nhr_evidence_reader(
            self.nhr_forwarder.base_url,
            self.nhr_forwarder.instrument_id,
            self.nhr_run_id,
            scope=self.nhr_scope,
            stage_index=self.nhr_stage_index,
            timeout_s=self.nhr_finalize_timeout_s,
        )
        can_path = Path(self._can_csv_path)
        output_path = self._default_merged_output_path()

        result = MergedCSVWriter(
            stale_after_s=self.merged_can_stale_after_s
        ).merge(
            can_csv_path=str(can_path),
            nhr_csv_path=evidence.csv_path,
            output_path=str(output_path),
            signals=sorted(self.merged_signals),
        )
        self._merged_csv_path = result.path
        # Use the same report contract for automatic and explicit postprocessing.
        from canpy.tools.merge_nhr_csv import _write_report

        manifest_path = Path(self._manifest_path) if self._manifest_path else None
        report_path = _write_report({
            "manifest_path": manifest_path,
            "manifest_sha256": sha256_file(manifest_path) if manifest_path else None,
            "capture_id": can_path.stem,
            "nhr_instrument": self.nhr_forwarder.instrument_id,
            "nhr_scope": self.nhr_scope,
            "nhr_stage_index": self.nhr_stage_index,
            "signals": sorted(self.merged_signals),
            "can_stale_after": self.merged_can_stale_after_s,
        }, evidence, result)
        print(f"[OK] Merged CSV saved: {result.path}")
        print(f"[OK] Merge report saved: {report_path}")
        print(f"  NHR run: {evidence.run_id} ({evidence.workflow_state})")
        print(f"  NHR artifact: {evidence.role} ({evidence.csv_path})")
        print(f"  CAN UTC: {result.can_start_utc} -> {result.can_end_utc}")
        print(f"  NHR UTC: {result.nhr_start_utc} -> {result.nhr_end_utc}")
        print(f"  Overlap: {result.overlap_duration_s:.6f} s")
        print(f"  CAN rows before NHR: {result.can_rows_before_nhr}")
        print(f"  CAN rows after NHR: {result.can_rows_after_nhr}")
        print(f"  NHR rows merged: {result.nhr_rows_merged}")

    def _default_merged_output_path(self) -> Path:
        if self.merged_output_path:
            return Path(self.merged_output_path)
        can_path = Path(self._can_csv_path)
        if can_path.name.startswith("can_capture_"):
            output_name = can_path.name.replace("can_capture_", "merged_capture_", 1)
        else:
            output_name = f"merged_{can_path.name}"
        return can_path.with_name(output_name)

    def _print_deferred_merge_command(self) -> None:
        """Print the normal explicit post-test command without contacting NHR-RT."""
        if not self._manifest_path:
            return
        command = [
            sys.executable,
            "-m",
            "canpy.tools.merge_nhr_csv",
            "--can-manifest",
            self._manifest_path,
            "--nhr-run-id",
            "REPLACE_WITH_EXACT_RUN_ID",
        ]
        print(f"[INFO] CAN manifest: {self._manifest_path}")
        print("[INFO] After the exact NHR run is finalized, execute:")
        print(subprocess.list2cmdline(command))

    def _forward_nhr_snapshot(self, frame) -> None:
        """Offer decoded data without allowing NHR failures into CAN capture."""
        if (
            self.nhr_forwarder is None
            or self.nhr_snapshot_assembler is None
            or self._nhr_forwarding_error is not None
        ):
            return
        try:
            snapshot = self.nhr_snapshot_assembler.observe(frame)
            if snapshot is not None:
                self.nhr_forwarder.offer(snapshot)
        except Exception as exc:
            self._record_nhr_forwarding_error(exc)

    def _record_nhr_forwarding_error(self, exc: BaseException) -> None:
        if self._nhr_forwarding_error is None:
            self._nhr_forwarding_error = f"{type(exc).__name__}: {exc}"
            print(
                "[WARNING] NHR forwarding is incomplete; CAN capture continues: "
                f"{self._nhr_forwarding_error}"
            )

    def _nhr_forwarding_complete(self) -> bool:
        if self.nhr_forwarder is None:
            return True
        statistics = self.nhr_forwarder.statistics()
        return (
            self._nhr_forwarding_error is None
            and statistics.sent_count > 0
            and statistics.last_error is None
        )

    def _print_nhr_forwarding_summary(self) -> None:
        statistics = self.nhr_forwarder.statistics()
        if is_dataclass(statistics):
            self._forwarding_statistics = asdict(statistics)
        else:
            self._forwarding_statistics = {
                key: getattr(statistics, key, None)
                for key in (
                    "offered_count", "sent_count", "dropped_count",
                    "coalesced_count", "retry_count", "rejected_count", "last_error",
                )
            }
        print("\nNHR external snapshot summary:")
        print(f"  Snapshots offered: {statistics.offered_count}")
        print(f"  Snapshots sent: {statistics.sent_count}")
        print(f"  Queue drops: {statistics.dropped_count}")
        print(f"  Cadence coalescing: {statistics.coalesced_count}")
        print(f"  Ambiguous retries: {statistics.retry_count}")
        print(f"  API rejections: {statistics.rejected_count}")
        if statistics.last_error:
            print(f"  Last forwarding error: {statistics.last_error}")
    
    def _print_frame(self, frame, frame_num) -> None:
        """Print frame to console"""
        if self.config_manager.get_setting('capture', 'no_console'):
            return
        
        timestamp = frame.timestamp_utc.strftime("%H:%M:%S.%f")[:-3]
        can_id = f"0x{frame.can_id:03X}"
        data_hex = ' '.join(f"{value:02X}" for value in frame.data)
        print(f"[{frame_num:5d}] {timestamp} | ID: {can_id:>4s} | "
              f"DLC: {frame.dlc} | Data: {data_hex}", end='')
        
        if frame.parsed_signals and self.config_manager.get_setting('capture', 'show_parsed'):
            signals = frame.parsed_signals
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


def _resolve_profile_argument(profile: Optional[str], config: Optional[str]) -> Optional[Path]:
    if profile and config and Path(profile).resolve() != Path(config).resolve():
        raise ValueError("--profile and legacy --config cannot reference different files")
    return Path(profile or config) if profile or config else None


def _significant_cli_overrides(args) -> list[str]:
    names = (
        "interface", "bitrate", "port", "mode", "duration", "count",
        "no_console", "show_parsed", "output_dir", "log", "dbc",
        "filter_can_id", "nhr_url", "nhr_instrument", "nhr_source_id",
        "nhr_rate", "nhr_signal_max_age", "nhr_communication_loss_fault_after",
        "nhr_queue_size", "nhr_timeout",
    )
    return [
        "--" + name.replace("_", "-")
        for name in names
        if getattr(args, name, None) not in (None, False)
    ]


def _print_effective_configuration(config_manager: ConfigManager, overrides) -> None:
    settings = config_manager.get_section()
    print("\nEffective CAN-PY configuration:")
    if config_manager.profile_path:
        print(
            f"  Profile: {config_manager.profile_path} "
            f"(sha256:{config_manager.profile_sha256})"
        )
    else:
        print("  Profile: built-in defaults (no profile file)")
    can = settings["can"]
    print(
        f"  CAN: {can.get('interface')} | port={can.get('serial_port')} | "
        f"bitrate={can.get('bitrate')}"
    )
    dbc_path = settings.get("dbc", {}).get("file")
    if dbc_path:
        print(f"  DBC: {Path(dbc_path).resolve()} (sha256:{sha256_file(Path(dbc_path))})")
    else:
        print("  DBC: none")
    output = settings["output"]
    print(f"  Output: {output.get('directory')} | formats={output.get('formats')}")
    nhr = settings.get("nhr", {})
    print(
        f"  NHR: service={nhr.get('service_url')} | "
        f"instrument={nhr.get('instrument_id')} | source={nhr.get('source_id')}"
    )
    merge = settings.get("merge", {})
    print(
        f"  Merge defaults: scope={merge.get('default_scope')} | "
        f"stale={merge.get('can_stale_after_s')} s | "
        f"signals={','.join(merge.get('signals', []))}"
    )
    print(f"  CLI overrides: {', '.join(overrides) if overrides else 'none'}\n")


def main(argv=None):
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CAN capture with an explicit post-test CAN/NHR merge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Daily: python -m canpy.capture --profile configs/canpy/bms-nhr-poc-v2.yaml\n"
            "Ctrl+C is a successful operator closure; the command prints the manifest "
            "and suggested post-test merge."
        ),
    )
    daily = parser.add_argument_group("daily options")
    capture_group = parser.add_argument_group("capture overrides")
    nhr_group = parser.add_argument_group("NHR integration")
    merge_group = parser.add_argument_group("advanced/deprecated capture-time merge")

    daily.add_argument("--profile", default=None, help="Operator profile YAML")
    daily.add_argument("--config", default=None, help="Compatibility alias for --profile")
    capture_group.add_argument("--interface", default=None)
    capture_group.add_argument("--bitrate", type=int, default=None)
    capture_group.add_argument("--port", default=None)
    capture_group.add_argument(
        "--mode", choices=("duration", "count", "continuous"), default=None
    )
    capture_group.add_argument("--duration", type=int, default=None)
    capture_group.add_argument("--count", type=int, default=None)
    capture_group.add_argument("--no-console", action="store_true")
    capture_group.add_argument("--show-parsed", action="store_true")
    capture_group.add_argument("--output-dir", default=None)
    capture_group.add_argument("--log", default=None, help="csv,json")
    capture_group.add_argument("--dbc", default=None)
    capture_group.add_argument("--filter-can-id", default=None)

    nhr_group.add_argument("--nhr-url", default=None)
    nhr_group.add_argument("--nhr-instrument", default=None)
    nhr_group.add_argument("--nhr-source-id", default=None)
    nhr_group.add_argument("--nhr-rate", type=float, default=None)
    nhr_group.add_argument("--nhr-signal-max-age", type=float, default=None)
    nhr_group.add_argument("--nhr-communication-loss-fault-after", type=float, default=None)
    nhr_group.add_argument("--nhr-queue-size", type=int, default=None)
    nhr_group.add_argument("--nhr-timeout", type=float, default=None)

    merge_group.add_argument(
        "--merged-csv", action="store_true",
        help="Advanced/deprecated special case; prefer post-test merge_nhr_csv",
    )
    merge_group.add_argument("--merged-signals", default=None)
    merge_group.add_argument("--merged-signals-file", default=None)
    merge_group.add_argument("--merged-can-stale-after", type=float, default=None)
    merge_group.add_argument("--nhr-run-id", default=None)
    merge_group.add_argument(
        "--nhr-scope", choices=("session", "sequence", "stage"), default=None
    )
    merge_group.add_argument("--nhr-stage-index", type=int, default=None)
    merge_group.add_argument("--nhr-finalize-timeout", type=float, default=60.0)
    merge_group.add_argument("--merged-output", default=None)
    args = parser.parse_args(argv)

    try:
        if args.filter_can_id:
            args.filter_can_id = [int(item, 0) for item in args.filter_can_id.split(",")]
        if args.log:
            args.log = [item.strip().lower() for item in args.log.split(",")]
        profile_path = _resolve_profile_argument(args.profile, args.config)
        config_manager = ConfigManager()
        config_manager.load_defaults_conf()
        if profile_path:
            config_manager.load_user_conf(profile_path)
            print(f"[OK] Loaded operator profile from {profile_path}")
        elif Path("user_config.yaml").exists():
            config_manager.load_user_conf(Path("user_config.yaml"))
            print("[OK] Loaded compatibility profile from ./user_config.yaml")
        config_manager.load_env_conf()
        config_manager.load_args_conf(args)
        config_manager.validate_config()
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(f"[ERROR] Configuration error: {exc}")
        return 1

    overrides = _significant_cli_overrides(args)
    _print_effective_configuration(config_manager, overrides)
    merge_settings = config_manager.get_section("merge")
    nhr_scope = args.nhr_scope or merge_settings["default_scope"]
    stale_after = (
        args.merged_can_stale_after
        if args.merged_can_stale_after is not None
        else merge_settings["can_stale_after_s"]
    )
    merged_signals = set(merge_settings["signals"] if args.merged_csv else [])
    if args.merged_signals:
        merged_signals = {item.strip() for item in args.merged_signals.split(",") if item.strip()}
    if args.merged_signals_file:
        try:
            merged_signals.update(load_signal_file(args.merged_signals_file))
        except MergedCSVError as exc:
            print(f"[ERROR] {exc}")
            return 1

    if stale_after <= 0 or args.nhr_finalize_timeout <= 0:
        print("[ERROR] Merge stale threshold and finalization timeout must be positive")
        return 1
    if nhr_scope == "stage" and (
        args.nhr_stage_index is None or args.nhr_stage_index < 0
    ):
        print("[ERROR] --nhr-stage-index must be non-negative for stage scope")
        return 1
    if nhr_scope != "stage" and args.nhr_stage_index is not None:
        print("[ERROR] --nhr-stage-index is valid only for stage scope")
        return 1
    if not args.merged_csv and (args.merged_signals or args.merged_signals_file):
        print("[ERROR] --merged-signals options require --merged-csv")
        return 1

    nhr_settings = config_manager.get_section("nhr")
    output_settings = config_manager.get_section("output")
    dbc_settings = config_manager.get_section("dbc")
    if args.merged_csv:
        print(
            "[WARNING] --merged-csv is an advanced compatibility mode. The normal "
            "operator workflow is the separate post-test merge command."
        )
        if not nhr_settings.get("service_url") or not nhr_settings.get("instrument_id"):
            print("[ERROR] --merged-csv requires configured NHR service and instrument")
            return 1
        if not dbc_settings.get("file") or "csv" not in output_settings.get("formats", []):
            print("[ERROR] --merged-csv requires an effective DBC and CSV output")
            return 1
        if not merged_signals:
            print("[ERROR] --merged-csv requires selected merge signals")
            return 1

    nhr_forwarder = None
    nhr_snapshot_assembler = None
    if nhr_settings.get("service_url"):
        nhr_forwarder = ExternalSnapshotForwarder(
            instrument_id=nhr_settings["instrument_id"],
            source_id=nhr_settings["source_id"],
            base_url=nhr_settings["service_url"],
            queue_size=nhr_settings["queue_size"],
            publish_rate_hz=nhr_settings["publish_rate_hz"],
            signal_max_age_s=nhr_settings["signal_max_age_s"],
            communication_loss_fault_after_s=nhr_settings[
                "communication_loss_fault_after_s"
            ],
            timeout_s=nhr_settings["timeout_s"],
        )
        nhr_snapshot_assembler = ExternalSnapshotAssembler(BMS_POC_V2_MAPPING)

    capturer = CANCapture(
        config_manager,
        nhr_forwarder=nhr_forwarder,
        nhr_snapshot_assembler=nhr_snapshot_assembler,
        merged_signals=merged_signals if args.merged_csv else None,
        merged_can_stale_after_s=stale_after,
        nhr_run_id=args.nhr_run_id,
        nhr_scope=nhr_scope,
        nhr_stage_index=args.nhr_stage_index,
        nhr_finalize_timeout_s=args.nhr_finalize_timeout,
        merged_output_path=args.merged_output,
        cli_overrides=overrides,
    )
    if not capturer.connect() or not capturer.capture():
        return 1
    print("[OK] Done!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
