# Post-test CAN/NHR merge reference

## Normal invocation

After the exact NHR run is terminal and finalized, and after Ctrl+C has closed
CAN-PY and written its manifest:

```powershell
python -m canpy.tools.merge_nhr_csv `
  --can-manifest data/poc-v2/can_capture_YYYYMMDD_HHMMSS.manifest.json `
  --nhr-run-id REPLACE_WITH_EXACT_RUN_ID
```

The command resolves the CAN CSV, NHR service/instrument, signals, scope, stale
threshold and destination from the manifest. It prints every CLI override. It
queries only the exact run ID, waits for active/finalizing states within the
configured timeout, requires terminal state plus `recording.finalized == true`,
and verifies the selected artifact's identity, role, size and SHA-256.

## Scope procedures

The versioned profile defaults to `sequence`, which includes all executed
workflow stages and post-sequence rest:

```powershell
python -m canpy.tools.merge_nhr_csv `
  --can-manifest data/poc-v2/can_capture_YYYYMMDD_HHMMSS.manifest.json `
  --nhr-run-id REPLACE_WITH_EXACT_RUN_ID `
  --nhr-scope sequence
```

Use `session` for the canonical complete run recording:

```powershell
python -m canpy.tools.merge_nhr_csv `
  --can-manifest data/poc-v2/can_capture_YYYYMMDD_HHMMSS.manifest.json `
  --nhr-run-id REPLACE_WITH_EXACT_RUN_ID `
  --nhr-scope session
```

Use `stage` only with one explicit zero-based stage index:

```powershell
python -m canpy.tools.merge_nhr_csv `
  --can-manifest data/poc-v2/can_capture_YYYYMMDD_HHMMSS.manifest.json `
  --nhr-run-id REPLACE_WITH_EXACT_RUN_ID `
  --nhr-scope stage `
  --nhr-stage-index 0
```

An absent or ambiguous stage is rejected and the available indices are shown.

## Expert overrides

`--signals`, `--signals-file`, `--can-stale-after`, `--output`,
`--nhr-finalize-timeout`, and `--nhr-poll-interval` override manifest defaults.
The destination must differ from both sources. CAN/NHR UTC timestamps, required
columns/signals and overlap are validated before the atomic destination replace.

The adjacent `.report.json` records the CAN manifest/capture, exact NHR run and
artifact, scope/stage, hashes/sizes, UTC windows, overlap, row counts, stale
threshold and creation time. It never modifies or replaces either source
manifest.

## Current convention

When `batteryCurrent` is selected (including via
`signals/module_test_live_signals.txt`), `can_batteryCurrent` in the merged CSV
uses the NHR convention: charge positive, discharge negative. It is the negated
CAN source value. `nhr_current_a` remains the measured NHR value, and the source
CSV files are unchanged. Other CAN current-like signals are not transformed.

The merger checks plausibility using fresh CAN values and the median CAN/NHR
currents in 5 s windows. Windows with fewer than three paired rows or either
median below 0.5 A are excluded. At least three comparable windows are needed
to verify the rule. Of those windows, at least 80% must have opposite raw signs,
and the median relative magnitude difference must be at most 20%. A contradiction
rejects the merge; insufficient active data is recorded as `inconclusive` in the
report. The report also records the applied factor, field names and check values.

## Migration from the historical detailed command

The old form remains available temporarily:

```powershell
python -m canpy.tools.merge_nhr_csv `
  --can-csv data/poc-v2/can_capture_YYYYMMDD_HHMMSS.csv `
  --nhr-url http://127.0.0.1:9300 `
  --nhr-instrument nhr-79503 `
  --nhr-run-id REPLACE_WITH_EXACT_RUN_ID `
  --nhr-scope sequence `
  --output data/poc-v2/merged_capture_YYYYMMDD_HHMMSS.csv `
  --signals minCellTemp,maxCellTemp,minCellV,maxCellV
```

Do not mix detailed source/service arguments with `--can-manifest`. The manifest
form is preferred because it removes repeated identities without introducing a
mutable link, latest-run discovery or CAN/NHR orchestrator.

The command never reads the NHR surveillance CSV or
`runtime.acquisition.evidence_path`, and CAN-PY never starts or stops a workflow.
