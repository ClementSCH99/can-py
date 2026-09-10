# NHR-RT POC V2 passive integration test

- Date: 2026-09-10
- CAN-PY branch: `exp/NHR9300-v2`
- CAN-PY base commit: `c609d96e63f46b48077f7a5800e158056c0afbad`
- NHR-RT commit: `0a305ab`
- CAN adapter: CandleLight / cantact `ch:0`
- DBC: `dbc/6.44.4.0.dbc`
- NHR backend: simulator `sim-1`
- External source: `bms-poc-v2`
- Requested forwarding rate: 5 Hz
- Signal maximum age: 2.5 s
- Communication-loss fault delay: 5.0 s

## Natural bounded run

- Command mode and duration: `duration`, 15 s
- Captured frames: 9,995
- CSV data rows: 9,995
- CSV size: 6,535,733 bytes
- CSV SHA-256: `8A91CA2A86560B0923585E526CD5927AEAD29A8CFFE1D0D0E7CFFB8C9897B3A1`
- Approximate aggregate CAN rate: 666.3 frames/s
- Temperature frames carrying both mapped signals: 15, approximately 1 Hz
- Voltage frames carrying both mapped signals: 150, approximately 10 Hz
- Snapshots offered: 162
- Snapshots accepted by NHR-RT: 65
- Queue drops: 0
- Cadence coalescing: 11
- Ambiguous retries: 0
- API rejections: 0
- Final accepted source sequence: 331
- Final `last_rejection`: null

| Signal | First value | Last value | Unit |
| --- | ---: | ---: | --- |
| MinCellTemp | 23.90625 | 23.921875 | degC |
| MaxCellTemp | 24.046875 | 24.046875 | degC |
| MinCellVolt | 3.69921875 | 3.69921875 | V |
| MaxCellVolt | 3.703125 | 3.703125 | V |

The NHR read-only monitor endpoint returned the external source with sequence
331, `health=ok`, and no rejection. Its aggregate status was `inactive` because
the simulator configuration intentionally contained no external-interlock
workflow rules.

## Preliminary manually stopped run

The preceding run demonstrated 39,400 captured frames, 651 snapshots offered,
267 accepted, zero queue drops and zero API rejections. It was stopped manually
after the CLI revealed that `--duration` alone does not select duration mode.
The interrupt occurred between capture counting and writer submission, leaving
39,399 CSV rows. The documented command now includes `--mode duration`; the
natural bounded run above is the evidence run.

## Evidence boundary

This test validates passive CAN reception, DBC decoding, asynchronous localhost
forwarding, sequence resynchronization, NHR simulator acceptance and read-only
monitor visibility. It did not start a workflow, command an NHR instrument,
energize an output or validate physical stop behavior.
