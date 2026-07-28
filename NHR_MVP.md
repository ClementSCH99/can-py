# NHR9300 experimental integration

This branch integrates `can-py` with the local HTTP/SSE service provided by
`nhr-rt`. It intentionally does not load IVI-COM and does not control the
cycler.

## Acceptance criteria

- NHR support is disabled unless both NHR CLI options are supplied.
- `can-py` connects through `NHRServiceClient`, never directly through IVI-COM.
- Measurements are consumed in a dedicated background thread.
- The in-memory backlog is bounded and retains the newest measurements.
- Voltage, current, power, temperature and UTC timestamp are validated.
- The latest measurement can be identified as stale.
- A missing client package, unavailable service, invalid response or broken
  stream produces an actionable error.
- The NHR stream is stopped when CAN capture finishes or fails.
- The integration exposes no arm, setpoint, routine or energizing operation.
- The existing CAN-only CLI and tests remain compatible.

## Running the MVP

Start the 32-bit service from `nhr-rt`:

```powershell
.\.venv32\Scripts\nhr9300-service.exe `
  --config .\examples\service.hardware.example.json
```

Install only its client package into the `can-py` environment:

```powershell
python -m pip install -e "C:\path\to\nhr-rt" --no-build-isolation
```

Then add NHR observation to an ordinary CAN capture:

```powershell
python -m canpy.capture --duration 60 --log csv `
  --nhr-url http://127.0.0.1:9300 `
  --nhr-instrument nhr-79503
```

`nhr-rt` remains responsible for its own NHR CSV. The experimental MVP only
shows the newest NHR values and their freshness alongside the CAN session.
