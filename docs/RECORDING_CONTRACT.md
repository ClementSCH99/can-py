# CAN Recording Contract

**Status:** Draft accepted for Phase 2, Step 2.1

This note defines what CAN-PY must preserve before a compact recording format
is selected. It describes requirements, not a storage-format decision.

## Roles of the recorded data

A test session has three distinct data roles:

1. **Canonical CAN source** — the most precise, trustworthy CAN record.
2. **External sources** — for example, the acquisition CSV owned by `nhr-rt`.
3. **Derived outputs** — decoded CSV exports and the resampled CAN-NHR merged
   CSV used for routine analysis.

Derived outputs are convenient and may be much smaller than the CAN source.
They do not replace the canonical CAN or NHR sources.

## In-memory CAN frame

`CANFrame` remains the central in-memory representation. Its accepted logical
fields are:

| Field | Required | Meaning |
|---|---:|---|
| `timestamp_utc` | yes | UTC time assigned by the CAN-PY host when the frame is received |
| `source_timestamp` | yes | Original timestamp supplied by `python-can` or the CAN adapter |
| `can_id` | yes | Numeric arbitration identifier |
| `dlc` | yes | Data Length Code reported for the frame |
| `data` | yes | Raw payload bytes |
| `is_extended` | yes | Distinguishes an 11-bit standard ID from a 29-bit extended ID |
| `is_remote` | yes | Distinguishes a Remote Transmission Request from a data frame |
| `is_error` | yes | Identifies an error frame |
| `parsed_signals` | no | Signal values decoded from the raw frame using a DBC |

`source_timestamp` is preserved as received. It must not be assumed to share a
clock with NHR data. `timestamp_utc` is the common timestamp used to correlate
CAN and NHR recordings.

## Canonical persistence

The canonical recording must preserve every required raw field above except
`parsed_signals`.

Decoded signals may exist on `CANFrame` for display, live processing, and
exports, but they are derived data. Omitting them from the canonical recording
avoids repeatedly storing values that can be regenerated from:

- the raw CAN frame;
- the exact DBC associated with the session.

The canonical recording therefore remains technically inspectable as IDs and
raw bytes, but it is not expected to expose engineering signal names and values
without a decoding/export step.

## Session metadata

Session metadata should live in one small companion file rather than being
repeated for every frame. The exact session layout belongs to Step 2.3, but the
minimum metadata contract is:

- session identifier;
- UTC start time and, when available, UTC end time;
- final state such as `completed`, `interrupted`, or `failed`;
- CAN interface, channel, bitrate, and active CAN-ID filter;
- CAN-PY version;
- DBC path and SHA-256 checksum when a DBC is used;
- canonical CAN recording path and frame count;
- each external tool used during the session;
- for `nhr-rt`, the service/instrument identity and acquisition CSV path;
- paths to derived outputs such as decoded CSV or merged CSV.

The checksum detects whether the DBC has changed. A later session-layout
decision will determine whether the session also stores a DBC snapshot.

## Interruption behavior

No software can guarantee recovery from every physical disk or filesystem
failure. CAN-PY's required recoverability is:

- every fully committed record or block before the interruption remains
  readable;
- an incomplete final record or block is detectable and can be ignored;
- losing a small number of the newest, uncommitted frames is acceptable;
- an incomplete tail must not make earlier data unreadable;
- derived-output failure must never delete or overwrite the source recordings.

Streaming remains required. A candidate format may use small controlled buffers
only when it preserves this recovery behavior.

## Size target

A reduction of at least 50% relative to the smaller current text recording is
the desired target, not an absolute acceptance threshold.

The selected format should minimize size as far as practical while preserving:

- every required raw field;
- interruption recovery;
- sustainable write throughput;
- reliable decoding and export.

## Step 2.1 baseline

The existing CSV and NDJSON writers are measured before either is changed.
Both writers receive the exact same ordered frames.

The baseline records:

- input description;
- frame count;
- file size in bytes;
- measured write duration;
- frames written per second;
- bytes written per frame;
- whether the output can be read back as the expected number of complete
  records.

Use a small representative NDJSON capture when available:

```powershell
python -m canpy.tools.recording_baseline `
  --input-ndjson path\to\small_representative_capture.ndjson `
  --output-dir data\recording_baseline
```

A deterministic synthetic input is available to validate the procedure, but it
is not operational evidence:

```powershell
python -m canpy.tools.recording_baseline `
  --synthetic-frames 10000 `
  --output-dir data\recording_baseline
```

The tool overwrites only its own `baseline_csv.csv` and
`baseline_json.ndjson` files. It does not remove the output directory or other
files in it.

No compact format will be selected from synthetic results alone.

## Recorded baseline

### Representative input

Measured on August 3, 2026 using the first 100,000 frames from:

```text
can_capture_20260803_085603.ndjson
```

The source was produced by the operational `exp/NHR9300` worktree. The selected
frames cover 143.760 seconds and include the parsed signals written by the
current capture path.

### Results

| Current writer | Frames | Capture duration | Size | Bytes/frame | Write time | Write rate | Readback |
|---|---:|---:|---:|---:|---:|---:|---|
| CSV | 100,000 | 143.760 s | 31,729,673 B | 317.30 | 6.8969 s | 14,499.2 frames/s | 100,000 records |
| NDJSON | 100,000 | 143.760 s | 52,330,781 B | 523.31 | 6.6150 s | 15,117.2 frames/s | 100,000 records |

These are local single-run measurements, not stable performance guarantees.
Format comparisons in Step 2.2 should use repeated measurements where small
throughput differences affect the decision.

### Contract limitations found

The current CSV writer is smaller partly because it does not preserve all fields
in the accepted contract. In particular, `dev` currently writes one generic
`timestamp` and omits `is_extended`, `is_remote`, and `is_error`.

The current NDJSON writer preserves the full parser dictionary, but also repeats
decoded signals. Its size therefore includes data that the future canonical
recording is allowed to omit.

The baseline describes current behavior; it does not establish either writer as
a valid canonical format.
