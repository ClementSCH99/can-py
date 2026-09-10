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
  --log csv `
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
