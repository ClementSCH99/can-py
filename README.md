# CAN Data Capture Tool

A Python tool to capture raw CAN data from a CANable Z pro+ device and save it to CSV/JSON files with optional DBC signal parsing.

## Features

- 🔌 **CANable Z pro+ Support**: Works with SLCAN protocol
- 📊 **Multiple Output Formats**: CSV, JSON, and human-readable TXT
- 🔍 **DBC Parsing**: Optional CAN signal decoding from DBC files
- ⏱️ **Flexible Capture Modes**: 
  - Duration-based (capture for N seconds)
  - Count-based (capture N frames)
  - Continuous (until user stops)
- 📈 **Real-time Console Display**: View frames as they're captured
- ⚙️ **Configurable**: Bitrate, port, and output settings

## Project Documentation

- [ROADMAP.md](ROADMAP.md) — current phase, completed work, and future direction
- [docs/WORKFLOW.md](docs/WORKFLOW.md) — guided learning and implementation workflow
- [docs/BRANCHING.md](docs/BRANCHING.md) — branch roles and release gates
- [docs/NHR_RT_POC_V2.md](docs/NHR_RT_POC_V2.md) — NHR-RT forwarding setup, operation and monitoring

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

To run the compact-format benchmark, install its optional Parquet dependency:
```bash
pip install -e ".[benchmark]"
```

2. Drivers (Windows):
   - CANable Z pro+ may need USB-to-Serial drivers
   - Download from: https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers

## Quick Start

### Basic Usage

Capture 60 seconds of CAN data:
```bash
python -m canpy.capture --duration 60
```

### With DBC Parsing

If you have a DBC file (e.g., `dbc/6.44.4.0.dbc`), capture and decode signals:
```bash
python -m canpy.capture --duration 60 --dbc dbc/6.44.4.0.dbc --log csv
```

### Capture Specific Number of Frames

```bash
python -m canpy.capture --count 500 --dbc dbc/6.44.4.0.dbc --log csv,json
```

### Daily CAN/NHR operator path

Start CAN capture and snapshot forwarding from the versioned operator profile:

```powershell
python -m canpy.capture --profile configs/canpy/bms-nhr-poc-v2.yaml
```

The profile leaves `can.serial_port: null`, so CAN-PY discovers the adapter and
port automatically. Use `--port COMx` only when an explicit SLCAN override is
needed.

After NHR-RT has reached a terminal state and finalized the exact retained
`run_id`, close CAN-PY normally with Ctrl+C. CAN-PY writes and prints the path
of `can_capture_<timestamp>.manifest.json`. Then run:


```powershell
python -m canpy.tools.merge_nhr_csv `
  --can-manifest data/poc-v2/can_capture_YYYYMMDD_HHMMSS.manifest.json `
  --nhr-run-id REPLACE_WITH_EXACT_RUN_ID
```

The profile defines CAN capture, forwarding identity and merge defaults; it
never contains an NHR run ID, workflow profile/digest, physical authorization
or battery limits. The immutable CAN manifest describes only closed CAN source
files. NHR-RT's own manifest remains authoritative for its workflow evidence.
The merged CSV and adjacent `.report.json` are separate derived products and do
not mutate either manifest.

The default profile selects the finalized NHR `sequence` artifact, including
post-sequence rest. Expert overrides support `session`, `sequence`, and
`stage --nhr-stage-index N`. The historical detailed merge arguments remain
available in `--help`. Capture-time `--merged-csv` is retained temporarily as
an advanced compatibility mode and emits a deprecation warning; it is not the
normal physical workflow. CAN-PY never starts/stops an NHR workflow and never
falls back to the continuous surveillance CSV.

See [docs/MERGE_NHR_CSV.md](docs/MERGE_NHR_CSV.md) for the full reference,
scope procedures and migration from the historical long form.

### Specify Serial Port

If auto-detection fails, specify the COM port:
```bash
python -m canpy.capture --duration 60 --port COM3 --dbc dbc/6.44.4.0.dbc
```

### Filter by CAN ID

Capture only specific CAN message IDs:
```bash
# Single CAN ID
python -m canpy.capture --duration 60 --filter-can-id 0x123 --log csv

# Multiple CAN IDs (hex format)
python -m canpy.capture --duration 60 --filter-can-id 0x123,0x456,0x789 --log csv

# Multiple CAN IDs (decimal format)
python -m canpy.capture --duration 60 --filter-can-id 291,1110,1945 --log csv

# Mix with DBC parsing
python -m canpy.capture --duration 60 --dbc dbc/6.44.4.0.dbc --filter-can-id 0x100,0x200 --log csv,json
```

## Command Line Options

```
positional arguments:
  None

optional arguments:
  --duration DURATION       Capture duration in seconds
  --count COUNT             Number of frames to capture
  --port PORT              Serial port (e.g., COM3, /dev/ttyUSB0)
  --dbc DBC                Path to DBC file for signal decoding
  --filter-can-id IDS      Filter by CAN ID(s): comma-separated hex values
                           (e.g., 0x123,0x456 or 0x123)
  --bitrate BITRATE        CAN bitrate in bps (default: 500000)
  --output-dir DIR         Output directory (default: data)
  --log FORMAT             Output formats: csv,json,txt (comma-separated)
  --no-console             Disable console output
  -h, --help              Show help message
```

## Configuration

Edit `config.py` to set default values:

```python
CAN_BITRATE = 500000         # 500 kbps
SERIAL_PORT = None           # Auto-detect
DBC_FILE = None              # Path to DBC file
OUTPUT_DIR = 'data'          # Output directory
OUTPUT_FORMAT = ['csv', 'json']
CAPTURE_MODE = 'duration'    # duration, count, continuous
CAPTURE_DURATION = 60        # seconds
SHOW_CONSOLE = True
SHOW_PARSED = True
```

## Output Files

Files are saved to the `data` directory with timestamp:

- `can_capture_20240401_123456.csv` - Tabular format with all signals
- `can_capture_20240401_123456.json` - Detailed JSON with metadata
- `can_capture_20240401_123456.txt` - Human-readable format

### CSV Format

```
timestamp,can_id,dlc,data_hex,signal_RPM,signal_Speed,...
1712057096.123,0x123,8,12 34 56 78 9A BC DE F0,800.0,50.5,...
```

### JSON Format

```json
{
  "metadata": {
    "capture_time": "2024-04-01T12:34:56.123456",
    "frame_count": 1234
  },
  "frames": [
    {
      "timestamp": 1712057096.123,
      "can_id": "0x123",
      "dlc": 8,
      "data_hex": "12 34 56 78 9A BC DE F0",
      "parsed": {
        "RPM": 800.0,
        "Speed": 50.5
      }
    }
  ]
}
```

## Troubleshooting

### Device Not Found

1. **Check connection**: Ensure CANable Z pro+ is connected via USB
2. **Find COM port**: Use Device Manager or Python:
   ```bash
   python -c "import serial.tools.list_ports; [print(p.device, p.description) for p in serial.tools.list_ports.comports()]"
   ```
3. **Install drivers**: Download CP210x drivers from Silicon Labs
4. **Specify port explicitly**: 
   ```bash
   python can_capture.py --port COM3
   ```

### DBC File Not Loading

1. **Check file path**: Ensure DBC file exists and path is correct
2. **Verify format**: Use cantools to test:
   ```bash
   python -c "import cantools; cantools.database.load_file('your.dbc')"
   ```

### No Frames Captured

1. **Check CAN bus**: Ensure CAN bus is active on vehicle/test bench
2. **Verify bitrate**: Default is 500 kbps, use `--bitrate` if different
3. **Console output**: Check if frames appear in console, issue may be in saving

## Examples

### Example 1: Capture vehicle data with DBC parsing

```bash
python can_capture.py --duration 120 --dbc vehicle.dbc --bitrate 500000
```

Captures 2 minutes of CAN data with signal decoding and saves as CSV and JSON.

### Example 2: Continuous monitoring

```bash
python can_capture.py --dbc vehicle.dbc
# Press Ctrl+C to stop
```

### Example 3: Diagnostics - raw data only

```bash
python can_capture.py --count 100 --no-console --log txt
```

Captures 100 frames with no console output, saves as readable text file.

### Example 4: Filter specific CAN IDs

```bash
python can_capture.py --duration 60 --dbc vehicle.dbc --filter-can-id 0x100,0x200,0x300 --log csv
```

Captures data for 60 seconds but only saves messages with CAN IDs 0x100, 0x200, or 0x300, with signal decoding.

## Dependencies

- `python-can`: CAN interface library
- `cantools`: DBC file parser and CAN signal decoder

## License

MIT

## Support

For issues with:
- **CANable device**: See https://canable.io/
- **DBC format**: See https://cantools.readthedocs.io/
- **This tool**: Check README and command help
