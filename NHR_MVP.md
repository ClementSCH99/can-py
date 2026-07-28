# NHR9300 experimental integration

This branch integrates `can-py` with the local HTTP/SSE service provided by
`nhr-rt`. It intentionally does not load IVI-COM and does not control the
cycler.

## Acceptance criteria

- NHR support is disabled unless both NHR CLI options are supplied.
- `can-py` connects through `NHRServiceClient`, never directly through IVI-COM.
- Measurements are consumed in a dedicated background thread.
- CAN capture starts only after the first valid NHR measurement is received.
- The in-memory backlog is bounded and retains the newest measurements.
- Voltage, current, power, temperature and UTC timestamp are validated.
- The latest measurement can be identified as stale.
- A missing client package, unavailable service, invalid response or broken
  stream produces an actionable error.
- The NHR stream is stopped when CAN capture finishes or fails.
- A final summary reports first-sample delay, received samples, observed rate,
  local queue drops, freshness and stream errors.
- The integration exposes no arm, setpoint, routine or energizing operation.
- The existing CAN-only CLI and tests remain compatible.

## Running the MVP

Start the 32-bit service from `nhr-rt`:

```powershell
.\.venv32\Scripts\nhr9300-service.exe `
  --config .\examples\service.hardware.example.json
```

Create the `can-py` environment and install its build tooling explicitly. This
keeps editable installs reproducible, including on a machine where a fresh
virtual environment does not already contain `setuptools` or `wheel`:

```powershell
py -3.12 -m venv .venv-main
.\.venv-main\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv-main\Scripts\python.exe -m pip install -e .
.\.venv-main\Scripts\python.exe -m pip install -e `
  "C:\path\to\nhr-rt" --no-build-isolation
```

Then add NHR observation to an ordinary CAN capture:

```powershell
.\.venv-main\Scripts\python.exe -m canpy.capture --duration 60 --log csv `
  --nhr-url http://127.0.0.1:9300 `
  --nhr-instrument nhr-79503
```

The default readiness timeout is 10 seconds. Override it when a real IVI
connection predictably needs longer:

```powershell
--nhr-ready-timeout 20
```

The readiness period occurs before the CAN capture timer starts. A connection
without a valid first measurement fails the requested NHR capture instead of
silently producing a partial beginning.

`nhr-rt` remains responsible for its own NHR CSV. The experimental MVP only
shows the newest NHR values and their freshness alongside the CAN session. At
the end, `can-py` preserves the CAN file even if the NHR stream failed, but
prints a warning that the combined session is incomplete.

The `nhr-rt` service reads its JSON configuration at process startup. Stop and
restart it after changing `rate_hz`; editing the JSON does not reconfigure an
already-running service.
