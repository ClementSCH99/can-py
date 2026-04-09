"""Output writers for CAN data in various formats with streaming support"""

import csv
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Set


class StreamingOutputWriter:
    """Streaming write support for long-duration captures
    
    Uses frame buffering strategy to collect all unique signals before writing
    CSV headers, preventing column misalignment issues.
    """
    
    def __init__(self, output_dir: str = 'data'):
        """
        Initialize streaming output writer
        
        Args:
            output_dir: Directory to save output files
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate timestamp for filename
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Streaming file handles
        self._csv_file = None
        self._csv_writer = None
        self._fieldnames = None
        self._json_file = None
        self._signal_fields: Set[str] = set()
        self._frame_count = 0
        self._start_time = datetime.now()
        self._filepaths = {}
        
        # Buffer frames to detect all signals before writing header
        self._frame_buffer = []
        self._buffer_size = 10  # Write in batches to detect new signals
        self._header_written = False
    
    def start_streaming(self, formats: List[str], filename: Optional[str] = None):
        """
        Initialize streaming to specified formats
        
        Args:
            formats: List of formats ('csv', 'json', 'txt')
            filename: Custom filename base (without extension)
        """
        if filename is None:
            filename = f"can_capture_{self.timestamp}"
        
        self._filename = filename
        self._formats = formats
        
        # Initialize CSV
        if 'csv' in formats:
            csv_path = os.path.join(self.output_dir, f"{filename}.csv")
            self._csv_file = open(csv_path, 'w', newline='', encoding='utf-8')
            self._filepaths['csv'] = csv_path
        
        # Initialize JSON (newline-delimited format for streaming)
        if 'json' in formats:
            json_path = os.path.join(self.output_dir, f"{filename}.ndjson")
            self._json_file = open(json_path, 'w', encoding='utf-8')
            self._filepaths['json'] = json_path
    
    def write_frame(self, frame: Dict[str, Any]):
        """
        Write a single frame to all active streams
        
        Args:
            frame: Parsed frame dictionary
        """
        self._frame_count += 1
        
        # Write to JSON immediately (no header issues)
        if self._json_file:
            self._write_json_frame(frame)
        
        # For CSV: use buffering to detect all signals before writing header
        if self._csv_file:
            self._handle_csv_frame_buffered(frame)
    
    def _handle_csv_frame_buffered(self, frame: Dict[str, Any]):
        """Handle CSV frame writing with buffering to detect all signals safely"""
        # Build flat row with all signals
        flat_row = {
            'timestamp': frame['timestamp'],
            'can_id': frame['can_id'],
            'dlc': frame['dlc'],
            'data_hex': frame['data_hex'],
        }
        
        # Collect signal names
        if frame.get('parsed'):
            for signal_name, signal_value in frame['parsed'].items():
                self._signal_fields.add(signal_name)
                flat_row[f"signal_{signal_name}"] = signal_value
        
        # Add to buffer
        self._frame_buffer.append(flat_row)
        
        # When buffer is full, flush it with complete headers
        if len(self._frame_buffer) >= self._buffer_size:
            self._flush_csv_buffer()
    
    def _compute_fieldnames(self) -> List[str]:
        """Compute fieldnames based on detected signals"""
        fieldnames = ['timestamp', 'can_id', 'dlc', 'data_hex']
        fieldnames.extend([f"signal_{sig}" for sig in sorted(self._signal_fields)])
        return fieldnames
    
    def _flush_csv_buffer(self):
        """Write all buffered frames to CSV with complete headers"""
        if not self._frame_buffer or not self._csv_file:
            return
        
        fieldnames = self._compute_fieldnames()
        
        # Write header if not yet written
        if not self._header_written:
            self._csv_writer = csv.DictWriter(
                self._csv_file, fieldnames=fieldnames, 
                restval='', extrasaction='ignore'
            )
            self._csv_writer.writeheader()
            self._fieldnames = fieldnames
            self._header_written = True
        
        # Write all buffered rows
        if self._csv_writer:
            for frame in self._frame_buffer:
                self._csv_writer.writerow(frame)
            self._csv_file.flush()
        
        # Clear buffer
        self._frame_buffer = []
    
    def _write_json_frame(self, frame: Dict[str, Any]):
        """Write frame to JSON stream (newline-delimited)"""
        if not self._json_file:
            return
        json_frame = self._make_json_serializable(frame)
        self._json_file.write(json.dumps(json_frame) + '\n')
        self._json_file.flush()
    
    def _make_json_serializable(self, obj):
        """Convert objects to JSON-serializable types"""
        if isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, bytes):
            return obj.hex()
        elif isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        else:
            return str(obj)
    
    def stop_streaming(self):
        """Close all streaming files"""
        # Flush any remaining buffered CSV frames
        if self._csv_file:
            self._flush_csv_buffer()
        
        if self._csv_file:
            self._csv_file.close()
            print(f"[OK] CSV file saved: {self._filepaths['csv']}")
        
        if self._json_file:
            self._json_file.close()
            print(f"[OK] NDJSON file saved: {self._filepaths['json']}")
        
        return self._filepaths
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current capture statistics"""
        elapsed = (datetime.now() - self._start_time).total_seconds()
        fps = self._frame_count / elapsed if elapsed > 0 else 0
        return {
            'frames': self._frame_count,
            'elapsed_seconds': elapsed,
            'fps': fps,
            'formats': self._formats
        }


class OutputWriter:
    """Batch write CAN capture data (for backward compatibility and short recordings)"""
    
    def __init__(self, output_dir: str = 'data'):
        """
        Initialize output writer
        
        Args:
            output_dir: Directory to save output files
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def write_csv(self, frames: List[Dict[str, Any]], filename: Optional[str] = None) -> Optional[str]:
        """
        Write frames to CSV file
        
        Args:
            frames: List of parsed frame dictionaries
            filename: Custom filename (without extension)
            
        Returns:
            Path to written file
        """
        if not frames:
            print("[WARNING] No frames to write")
            return None
        
        if filename is None:
            filename = f"can_capture_{self.timestamp}"
        
        filepath = os.path.join(self.output_dir, f"{filename}.csv")
        
        # Flatten the data for CSV
        flattened = []
        for frame in frames:
            flat = {
                'timestamp': frame['timestamp'],
                'can_id': frame['can_id'],
                'dlc': frame['dlc'],
                'data_hex': frame['data_hex'],
            }
            
            # Add parsed signals if available
            if frame.get('parsed'):
                for signal_name, value in frame['parsed'].items():
                    flat[f"signal_{signal_name}"] = value
            
            flattened.append(flat)
        
        # Get all unique fieldnames
        fieldnames = ['timestamp', 'can_id', 'dlc', 'data_hex']
        signal_fields = set()
        for frame in flattened:
            signal_fields.update(k for k in frame.keys() if k.startswith('signal_'))
        fieldnames.extend(sorted(signal_fields))
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval='')
            writer.writeheader()
            writer.writerows(flattened)
        
        print(f"[OK] CSV file saved: {filepath}")
        return filepath
    
    def _make_json_serializable(self, obj):
        """Convert objects to JSON-serializable types"""
        if isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, bytes):
            return obj.hex()
        elif isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        else:
            return str(obj)
    
    def write_json(self, frames: List[Dict[str, Any]], filename: Optional[str] = None) -> Optional[str]:
        """
        Write frames to JSON file
        
        Args:
            frames: List of parsed frame dictionaries
            filename: Custom filename (without extension)
            
        Returns:
            Path to written file
        """
        if not frames:
            print("[WARNING] No frames to write")
            return None
        
        if filename is None:
            filename = f"can_capture_{self.timestamp}"
        
        filepath = os.path.join(self.output_dir, f"{filename}.json")
        
        # Convert frames to JSON-serializable format
        serializable_frames = self._make_json_serializable(frames)
        
        output_data = {
            'metadata': {
                'capture_time': datetime.now().isoformat(),
                'frame_count': len(frames),
            },
            'frames': serializable_frames
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"[OK] JSON file saved: {filepath}")
        return filepath
    
    def write_txt(self, frames: List[Dict[str, Any]], filename: Optional[str] = None) -> Optional[str]:
        """
        Write frames to human-readable text file
        
        Args:
            frames: List of parsed frame dictionaries
            filename: Custom filename (without extension)
            
        Returns:
            Path to written file
        """
        if not frames:
            print("[WARNING] No frames to write")
            return None
        
        if filename is None:
            filename = f"can_capture_{self.timestamp}"
        
        filepath = os.path.join(self.output_dir, f"{filename}.txt")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"CAN Data Capture\n")
            f.write(f"Capture Time: {datetime.now().isoformat()}\n")
            f.write(f"Total Frames: {len(frames)}\n")
            f.write("=" * 80 + "\n\n")
            
            for i, frame in enumerate(frames, 1):
                f.write(f"Frame {i}:\n")
                f.write(f"  Timestamp:   {frame['timestamp']}\n")
                f.write(f"  CAN ID:      {frame['can_id']} (dec: {frame['can_id_dec']})\n")
                f.write(f"  DLC:         {frame['dlc']}\n")
                f.write(f"  Data:        {frame['data_hex']}\n")
                
                if frame.get('parsed'):
                    f.write(f"  Signals:\n")
                    for signal_name, value in frame['parsed'].items():
                        f.write(f"    {signal_name}: {value}\n")
                
                f.write("\n")
        
        print(f"[OK] TXT file saved: {filepath}")
        return filepath
