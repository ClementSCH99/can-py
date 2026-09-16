# NHR-RT x CAN-PY POC V2

This integration is optional. CAN-PY remains responsible for CAN acquisition,
DBC decoding, source timestamps, CAN-source health, and orchestration. NHR-RT
remains the sole owner of the NHR hardware and safety actions.

## POC snapshot contract

The source ID defaults to `bms-poc-v2`. The initial mapping is derived from
`dbc/6.44.4.0.dbc`:

| DBC signal | Snapshot signal | DBC unit |
| --- | --- | --- |
| `minCellTemp` | `MinCellTemp` | `degC` |
| `maxCellTemp` | `MaxCellTemp` | `degC` |
| `minCellV` | `MinCellVolt` | `V` |
| `maxCellV` | `MaxCellVolt` | `V` |

The four signals form one complete snapshot. CAN-PY waits until every value is
available, then uses the oldest contributing CAN timestamp. The forwarding
worker republishes the latest complete snapshot at 5 Hz. A slow signal keeps
its original timestamp; publication does not make it appear newer.

CAN-PY marks the snapshot `stale` once the oldest contributing value is older
than `signal_max_age_s`, which defaults to 2.5 seconds. If the required BMS
messages remain absent for a second complete freshness window, it confirms a
communication-loss fault and publishes `health=fault` after 5.0 seconds. A new
complete snapshot clears the condition.

The NHR workflow must independently use the same exact signal names and units,
and an approved `max_age_s` of 2.5 seconds for this POC. No NHR profile
or workflow is changed by this integration.

## Enabling the forwarder

Forwarding remains disabled unless both `service_url` and `instrument_id` are
configured and a DBC file is selected.

Expose the local NHR-RT client package to the CAN-PY 64-bit environment. From
the CAN-PY repository, set this in every PowerShell console used for the POC:

```powershell
$env:PYTHONPATH = (Resolve-Path ..\nhr-rt\src).Path
.\.venv\Scripts\python.exe -c "from nhr9300 import NHRServiceClient; print('NHR client ready')"
```

This avoids changing either repository. An editable `pip install` requires the
Python build tooling to be installed in the CAN-PY environment and is not a POC
prerequisite.

Confirm that the new options are available:

```powershell
.\.venv\Scripts\python.exe -m canpy.capture --help
```

### Passive integration test with the NHR simulator

This is the recommended first test with a real CAN bus. It exercises the real
CAN adapter, DBC and forwarding path while the NHR side remains simulated and
cannot command physical NHR hardware.

In a first PowerShell console, start the NHR-RT simulator service:

```powershell
Set-Location ..\nhr-rt
.\.venv32\Scripts\nhr9300-service.exe `
  --config .\examples\service.simulator.json
```

The example instrument ID is `sim-1`. Leave that console open.

In a second console, start the read-only NHR monitor:

```powershell
Set-Location ..\nhr-rt
.\.venv64\Scripts\nhr9300-monitor.exe `
  --service-url http://127.0.0.1:9300 `
  --instrument-id sim-1 `
  --port 9400
```

Open `http://127.0.0.1:9400` locally.

In a third console, from CAN-PY, start a bounded capture. Replace `COM3` if the
adapter is not auto-detected on that port:

```powershell
.\.venv\Scripts\python.exe -m canpy.capture `
  --mode duration `
  --duration 60 `
  --port COM3 `
  --dbc dbc/6.44.4.0.dbc `
  --log csv,json `
  --output-dir data/poc-v2 `
  --nhr-url http://127.0.0.1:9300 `
  --nhr-instrument sim-1 `
  --nhr-source-id bms-poc-v2 `
  --nhr-rate 5 `
  --nhr-signal-max-age 2.5 `
  --nhr-communication-loss-fault-after 5
```

The worker performs `configuration()` and initializes one
`ExternalSnapshotPublisher`. Its bounded queue drops the oldest queued snapshot
when full. HTTP work and retry delays stay outside the CAN receive, decode, and
recording path. The capture result reports failure if forwarding was requested
but never succeeded; CAN evidence is still closed normally.

At the end of the capture, check that `Snapshots sent` is greater than zero,
that `API rejections` is zero and that no forwarding error is reported. The CSV
remains the CAN evidence source.

### Normal post-test CAN/NHR merge

The normal operator path intentionally separates acquisition from the derived
merge:

1. Start CAN-PY with the operator profile and keep snapshot forwarding active.
2. Start the workflow from NHR-RT and retain its exact `run_id`.
3. Wait for NHR-RT to reach a terminal state and finalize its evidence.
4. Close CAN-PY normally with Ctrl+C.
5. Run the explicit merge command with the CAN manifest and exact run ID.

```powershell
python -m canpy.capture --profile configs/canpy/bms-nhr-poc-v2.yaml
```

`can.serial_port` is `null` in this profile. CAN-PY therefore discovers the
available adapter/COM port; `--port COMx` remains an explicit SLCAN fallback.

Then:

```powershell
python -m canpy.tools.merge_nhr_csv `
  --can-manifest data/poc-v2/can_capture_YYYYMMDD_HHMMSS.manifest.json `
  --nhr-run-id REPLACE_WITH_EXACT_RUN_ID
```

The command obtains the closed CAN CSV, service URL, instrument, signals,
default scope/stale threshold and default destination from the CAN manifest.
It polls only that exact run through `workflow_run()`, requires a terminal state
and `recording.finalized == true`, then validates the selected
`session-evidence.json` artifact's identity, role, size and SHA-256. It never
uses `runtime.acquisition.evidence_path` and never discovers a latest run.

Expert overrides are `--nhr-scope`, `--nhr-stage-index`, `--signals`,
`--signals-file`, `--can-stale-after`, `--output`, timeout and polling interval.
`sequence` selects the executed workflow including post-sequence rest;
`session` selects canonical complete-session evidence; `stage` requires one
unique non-negative stage index. Every explicit override is printed.

Expected outputs are:

- `can_capture_<timestamp>.csv`: CAN source CSV;
- `can_capture_<timestamp>.ndjson`: CAN source JSON when `--log csv,json` is used;
- `can_capture_<timestamp>.manifest.json`: immutable CAN capture manifest;
- the acquisition CSV owned by `nhr-rt`;
- `merged_capture_<timestamp>.csv`: derived CAN/NHR analysis table;
- `merged_capture_<timestamp>.report.json`: separate derived merge report.

If the merge fails, source files remain unchanged, no partial merged CSV is
retained and the capture command exits with failure. If the selected NHR run is
still active or `finalizing`, CAN-PY waits without sending a stop request. If no
run ID is retained by the capture profile: Ctrl+C closes CAN normally, writes
the immutable CAN manifest and prints an exact minimal command containing
`REPLACE_WITH_EXACT_RUN_ID`. CAN-PY never substitutes
`runtime.acquisition.evidence_path`, because that path is continuous service
surveillance rather than workflow evidence.

The command reports CAN and NHR UTC start/end, overlap duration, CAN rows before
and after the NHR window, and merged NHR rows. A zero-overlap merge is rejected.
The destination is written through a same-directory temporary file and replaced
atomically only after complete success.

For a physical workflow, keep CAN-PY publishing until the NHR workflow reaches
a terminal state whenever the operating procedure allows it; ending CAN-PY
first intentionally makes the external source stale and can trigger the
NHR-RT-owned controlled-stop interlock. CAN-PY does not start or stop workflows.

The historical detailed form remains available temporarily for migration:

```powershell
.\.venv\Scripts\python.exe -m canpy.tools.merge_nhr_csv `
  --can-csv data/poc-v2/can_capture_YYYYMMDD_HHMMSS.csv `
  --nhr-url http://127.0.0.1:9300 `
  --nhr-instrument nhr-79503 `
  --nhr-run-id REPLACE_WITH_EXACT_RUN_ID `
  --nhr-scope session `
  --output data/poc-v2/merged_capture_YYYYMMDD_HHMMSS.csv `
  --signals minCellTemp,maxCellTemp,minCellV,maxCellV
```

The capture-time `--merged-csv` options also remain temporarily, but they are an
advanced/deprecated special case for an already-known run ID. They emit a clear
warning, are removed from the main procedure, and are not the normal physical
workflow. Capture never waits for NHR-RT unless that mode was explicitly asked.

The CAN-PY profile configures CAN, output, DBC, forwarding identity and merge
defaults. It must not contain an NHR run ID, NHR CSV path/runtime state,
physical authorization, battery limits, or NHR workflow profile/digest. The CAN
manifest describes closed CAN evidence. NHR-RT's profile and manifest remain
separate authorities. The merged CSV/report are derived and replace neither.

### Monitoring coverage

The NHR-RT monitor refreshes its read-only runtime view at 1 Hz. For this
integration it shows:

- service and acquisition health;
- aggregate external-source status;
- configured interlock results, including safe/stale state and age;
- workflow state.

The current monitor does not provide a dedicated table of all four raw CAN
snapshot values, nor the raw source sequence and health. Before external
interlock rules are configured, it reports the aggregate external-source state
as inactive. During the passive test, use the CAN-PY decoded console output for
the four values, the NHR monitor for aggregate source/service health, and the
API check below for exact source age, sequence, health and rejection state.
Once approved workflow rules exist, their evaluated values appear in the
monitor's interlock results.

For an exact API-level check, run this from the CAN-PY environment while both
processes are active:

```powershell
.\.venv\Scripts\python.exe -c "from nhr9300 import NHRServiceClient; import pprint; pprint.pp(NHRServiceClient('http://127.0.0.1:9300').interlocks('sim-1'))"
```

Under `external_sources.sources`, verify `source_id`, increasing `sequence`,
`health`, `age_s`, and an empty `last_rejection`.

### Physical NHR readiness gate

Successful passive testing does not authorize an energized test. Before using
the physical NHR service with active external interlocks, the NHR workflow must
define and approve the four rules, engineering thresholds, `max_age_s=2.5`,
scope (`pre_start`, `runtime`, or `both`), workflow digest and controlled-stop
behavior. The physical test procedure and each energizing run require their own
approval and operator confirmation.

## Scope boundary

This POC excludes dynamic SoP/M6, hardware tests, NHR-RT code or profile
changes, workflow start/stop orchestration, and physical-safety conclusions.
