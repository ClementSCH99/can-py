# CAN-PY Project Roadmap

**Last updated:** July 30, 2026

**Current phase:** Phase 2 — Operational Recording Footprint

**Project status:** Foundation cycle closed; operational priorities now lead development

---

## Project vision

CAN-PY is a practical CAN data acquisition tool for day-to-day EV test work and
a learning project for developing stronger Python and software-design skills.

The project should:

- capture CAN data reliably during real tests;
- preserve enough timing and configuration context to trust a recording;
- keep recording size manageable during long sessions;
- show the operator what is happening while a test is running;
- support read-only integration with test equipment such as `nhr-rt`;
- make captured data easy to export, query, visualize, and analyze;
- introduce architecture and development concepts progressively, when they
  support a real need.

Safety remains a boundary, not a later feature. CAN-PY may observe NHR
measurements through `nhr-rt`, but it does not gain permission to arm equipment,
change setpoints, start routines, or energize a test.

---

## How this roadmap is organized

The roadmap always keeps:

1. completed phases and their main learnings;
2. one detailed current phase, implemented step by step;
3. at least two future phases at a higher level.

The current phase may be adjusted when field use reveals a more urgent need.
Changing direction is not a failure: the decision and the deferred work must be
recorded explicitly.

Implementation follows [docs/WORKFLOW.md](docs/WORKFLOW.md). Branch roles and
promotion gates are defined in [docs/BRANCHING.md](docs/BRANCHING.md).

---

## Completed phases

### Phase 1 — Software foundation

**Closed:** July 30, 2026

**Reason for closing:** The planned foundation was already sufficient to build
useful vertical features. Real test use exposed two more urgent problems:
recording size and lack of live visibility.

#### Phase 1.1 — Extensible writer architecture

Delivered:

- `BaseOutputWriter`;
- writer factory, registry, and decorator-based registration;
- separate CSV and NDJSON writers;
- proof that a new writer can be added without modifying the capture loop.

Learned:

- Factory, Registry, Decorator, and Dependency Injection patterns;
- Open/Closed Principle;
- package organization using a `src/` layout.

#### Phase 1.2 — Configuration management

Delivered on `dev`:

- centralized `ConfigManager`;
- YAML, user-file, environment, and CLI precedence;
- validation and immutable configuration after startup;
- integration coverage for configuration behavior.

Learned:

- configuration precedence;
- validation at system boundaries;
- dependency injection and immutable runtime settings.

#### Phase 1.3 — Data access layer

Delivered on `dev`:

- immutable `CANFrame`;
- `BaseRepository`, `CsvRepository`, and `QueryFilter`;
- lazy CSV reading and filtered queries;
- end-to-end writer-to-repository tests.

Learned:

- Repository and Query Object patterns;
- lazy iteration;
- explicit resource cleanup;
- value objects and public package APIs.

#### Experimental operational MVP completed in parallel

Delivered on `exp/NHR9300` and currently used from the `can-py-main` worktree:

- opt-in, read-only `nhr-rt` measurement streaming;
- capture start aligned to the first valid NHR measurement;
- host UTC timestamps for CAN/NHR correlation;
- cooperative worker shutdown and bounded reconnection;
- post-capture CAN/NHR merged CSV for selected DBC signals;
- missing-CAN and stream-health diagnostics.

This MVP is a field pilot, not yet a release on the Git `main` branch. Its
proven behavior will later be ported into `dev` through focused integration
work.

#### Foundation work intentionally deferred

The former Phase 1.4 and 1.5 are not abandoned. These concepts move to the
stabilization phase, where they can be applied to the operational architecture:

- domain exceptions and validation schemas;
- structured logging and actionable diagnostics;
- separation of CLI, capture engine, storage, and display concerns;
- one canonical frame model shared by parser, writers, and repositories;
- removal of deprecated modules and clearer package exports.

The complete previous roadmap is preserved in
[docs/history/ROADMAP_FOUNDATION_2026-05-07.md](docs/history/ROADMAP_FOUNDATION_2026-05-07.md).

---

## Current phase

### Phase 2 — Operational recording footprint

#### Outcome

Long captures create one trustworthy, compact session instead of several large,
redundant text files. CSV remains available as an export when a person or
external tool needs it.

#### Why this is first

A representative run produced approximately 2.43 GB of NDJSON and 1.73 GB of
CSV for the same CAN traffic. More than 4.1 GB was written because two verbose
text representations duplicated the recording.

Before building richer analysis or dashboards, CAN-PY needs an explicit answer
to:

- what is the source of truth for a session;
- which timestamps and metadata must never be lost;
- which files are raw, derived, or temporary;
- how size, write speed, interruption recovery, and exportability are balanced.

---

#### Step 2.1 — Define the recording contract and baseline

**Status:** Accepted and completed on August 3, 2026.

**Objective**

Describe the minimum information required for a trustworthy test session and
measure the current CSV/NDJSON baseline on a small representative capture.

**Concept to learn**

Requirements and acceptance criteria: choose what must be preserved before
choosing a technology.

**Questions to answer**

- Which CAN fields are mandatory?
- How are `timestamp_utc` and `source_timestamp` preserved?
- Is the DBC version or checksum part of the session metadata?
- Which NHR file references belong in the session?
- What file-size reduction is considered useful?
- What must remain readable after an interrupted capture?

**Division of work**

- The learner defines the operational requirements and reviews the session
  contract.
- The LLM may prepare measurement scripts, fixtures, and a comparison table.

**Done when**

- the recording contract is written in the roadmap or a focused design note;
- a repeatable baseline records size, frame count, duration, and write rate;
- no output format has been selected without evidence.

**Working document**

- [CAN recording contract](docs/RECORDING_CONTRACT.md) defines the accepted
  raw-frame, metadata, derived-output, and interruption-recovery requirements.
- The baseline tool replays identical frames through the existing CSV and
  NDJSON writers.
- The operational baseline used 100,000 frames covering 143.760 seconds from
  the August 3 representative capture. Both outputs read back all 100,000
  records; neither current format was selected as the canonical format.

---

#### Step 2.2 — Compare compact-format candidates

**Objective**

Run a focused spike comparing only the realistic candidates:

- compressed BLF for raw CAN frames;
- Parquet for structured records;
- compressed CSV as a low-complexity fallback.

**Concept to learn**

Engineering tradeoffs and proof-of-concept work: a spike answers a decision and
is not automatically production code.

**Tradeoffs to evaluate**

- file size;
- sustained write throughput;
- CPU and memory use;
- preservation of both timestamp domains;
- partial-file behavior after interruption;
- dependency weight and Python compatibility;
- ability to read selected data without loading the whole capture;
- ease of exporting to CSV and merging with NHR data.

**Division of work**

- The learner predicts and explains the tradeoffs, then reviews the results.
- The LLM may write repetitive benchmark adapters and collect measurements.

**Done when**

- results are recorded in one concise decision section;
- one canonical recording format is selected;
- rejected formats and the reason for rejection are documented;
- the choice preserves the accepted timestamp contract.

**Decision**

Segmented Parquet is selected. Finalized segments provide interruption recovery
during capture and are merged atomically into one final Parquet recording after
a clean stop. Results and rejected alternatives are recorded in
[the recording contract](docs/RECORDING_CONTRACT.md#compact-format-decision).

---

#### Step 2.3 — Define the session layout

**Objective**

Define a small, explicit session structure around the selected format.

**Concept to learn**

Data provenance: raw data, metadata, and derived outputs have different roles.

**Expected direction**

A session should identify:

- the canonical CAN recording;
- the NHR acquisition file when NHR observation is enabled;
- capture start/end times and clock meaning;
- DBC identity;
- active signal selection and CAN filters;
- tool/configuration version;
- derived files such as merged exports.

This does not require a database or a general artifact framework. A directory
and a small manifest are sufficient unless Step 2.2 proves otherwise.

**Done when**

- raw and derived outputs cannot be confused;
- paths remain usable across the `can-py` and `nhr-rt` processes;
- existing raw files are retained if a derived export fails.

---

#### Step 2.4 — Implement the compact writer MVP

**Objective**

Add the selected writer through the existing writer registry and make it usable
for a normal CAN-only capture.

**Concept to learn**

Extending an architecture through an existing abstraction instead of bypassing
it.

**Constraints**

- keep the capture loop simple;
- avoid unbounded in-memory buffering;
- avoid per-frame durability operations unless measurements justify them;
- report the active file and meaningful write failures;
- do not modify NHR control or safety behavior;
- keep the current CSV path available during transition.

**Division of work**

- The learner implements or co-implements the core serialization decisions.
- The LLM may add boilerplate registration, CLI/config wiring, fixtures, and
  repetitive tests after the contract is understood.

**Done when**

- writer unit tests pass;
- a CAN-only integration capture is readable;
- the new output is materially smaller than the baseline;
- stopping normally and with `Ctrl+C` closes the writer cleanly.

---

#### Step 2.5 — Add read and CSV-export compatibility

**Objective**

Read the compact recording through a clear application boundary and export a
selected time range or signal set to CSV.

**Concept to learn**

Canonical storage versus interchange format.

**Tradeoffs**

- extend the current repository abstraction where it fits;
- do not force a raw CAN format into a tabular abstraction if a small adapter is
  clearer;
- avoid rebuilding the future query engine during this step.

**Done when**

- a recorded session can be reopened and sampled;
- CSV is generated on demand rather than always duplicated during capture;
- timestamp and frame round-trip tests pass.

---

#### Step 2.6 — Validate the operational recording

**Objective**

Prove the new recording path on representative bench use before making it the
default.

**Concept to learn**

Release gates and operational validation.

**Minimum validation**

- short known-data capture;
- representative long capture;
- normal stop and operator interruption;
- readable output and correct metadata;
- measured size reduction;
- no regression in CAN-only behavior;
- raw data retained when an export fails;
- documented fallback to the existing CSV writer.

**Phase exit**

Phase 2 closes only after the user reviews the evidence and accepts the format
as the new operational recording path.

---

## Next phase

### Phase 3 — Live test visibility

**Outcome**

The operator can see selected CAN and NHR measurements, data freshness, capture
health, and file growth while a test is running.

**Planned sections**

1. Define the operator view and selected-signal contract.
2. Expose a thread-safe latest-state snapshot independent of file writing.
3. Build a minimal terminal dashboard with a slow, stable refresh rate.
4. Add freshness, missing-data, capture-rate, and disk-growth warnings.
5. Validate visibility during a representative test.
6. Decide from field use whether plots or a browser dashboard are justified.

**Concepts to learn**

- producer/consumer separation;
- state snapshots;
- refresh rate versus acquisition rate;
- operator-focused observability;
- separation of presentation and business logic.

The first target is a useful terminal view, not a full web application.

---

## Following phase

### Phase 4 — MVP integration, architecture, and stable release

**Outcome**

The proven operational features are integrated into `dev` through clear
boundaries and promoted to Git `main` as a stable lab release.

**Planned sections**

1. Review the field evidence and freeze the accepted NHR behavior.
2. Port NHR observation and merged-output behavior into `dev` in focused pieces.
3. Separate CLI, capture engine, storage, NHR provider, and live-view concerns.
4. Move to one canonical frame model.
5. Introduce domain exceptions and boundary validation.
6. Replace reusable-module prints with structured logging while keeping the CLI
   readable.
7. Remove deprecated modules and repair public exports/documentation.
8. Run automated and representative bench validation.
9. Promote `dev` to `main` under the gates in `docs/BRANCHING.md`.

**Concepts retained from the former roadmap**

- separation of concerns;
- domain exception hierarchy;
- schema validation at trust boundaries;
- structured logging;
- clean package organization;
- dependency inversion;
- release discipline.

This phase ports behavior intentionally. It does not blindly merge
`exp/NHR9300` into `dev`.

---

## Longer-term direction

### Phase 5 — Data exploration and visualization

- repository-backed filtering and aggregation;
- DataFrame export;
- static and interactive plots;
- data-quality summaries;
- SQLite only if real query volume justifies it.

### Phase 6 — Test scenario and equipment integration

- read-only equipment providers first;
- explicit hardware abstraction boundaries;
- cancellation and cleanup;
- test-scenario definitions;
- controlled operations only through separately reviewed safety stages.

---

## Release-level success criteria

The next stable `main` release should:

- create compact, trustworthy recording sessions;
- provide useful live visibility;
- preserve raw CAN and NHR source data;
- correlate sources only through compatible UTC timestamps;
- stop workers and writers cleanly;
- keep NHR integration observation-only;
- pass automated tests and representative bench validation;
- have commands and configuration documented for another operator;
- be reviewed and explicitly accepted before commit, push, or promotion.
