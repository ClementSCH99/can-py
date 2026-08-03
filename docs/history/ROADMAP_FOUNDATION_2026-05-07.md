# Archived roadmap — Foundation cycle through May 7, 2026

**Last Updated**: Phase 1.3 Complete, Phase 1.4 Ready (May 7, 2026)  
**Status**: ✅ Phase 1.3 Complete → Next: Phase 1.4 Step 1.4.1  
**Always Maintains**: 2-phase lookahead buffer

---

## 📊 Project Vision

Transform CAN-PY from a capture-only tool into a **scalable, extensible data acquisition and analysis platform** supporting:
- **Multiple data formats** (CSV, JSON, Parquet, HDF5, database)
- **Data visualization** (plots, dashboards, real-time monitoring)
- **Test equipment integration** (hardware control, synchronized capture)
- **Enterprise patterns** (plugins, configuration management, validation)

**Core Principle**: Each phase builds the foundation for the next without rework.

---

## ✅ Completed Phases

### Phase 1.1 — Plugin Architecture & Writer Registry ✅

**Completed**: April 14, 2026

**Summary**:
Built an extensible writer system using Factory + Registry + Decorator patterns, proving the Open/Closed Principle by adding an ExampleWriter with zero changes to `capture.py`.

**Completed Deliverables**:
- `canpy/writers/registry.py` — WriterFactory with registration validation
- `canpy/writers/csv_writer.py` — Single-responsibility CSVWriter
- `canpy/writers/json_writer.py` — Single-responsibility JSONWriter
- `canpy/writers/example_writer.py` — Extensibility proof (dummy writer)
- `canpy/writers/base.py` — BaseOutputWriter abstract interface
- `capture.py` refactored to use WriterFactory loop (one writer per format)
- Test suite: 16/16 tests passing

**Design Patterns Implemented**:
- Factory Pattern (WriterFactory.create())
- Registry Pattern (format_name → writer_class mapping)
- Decorator Pattern (@WriterFactory.register())
- Abstract Base Class Pattern (BaseOutputWriter)
- Dependency Injection (factory loop in capture.py)

**Key Learnings**:
- SOLID Principles in practice — Open/Closed Principle is powerful for extensibility
- Test organization matters: separate mechanism tests from integration tests
- Professional Python packaging with `src/` layout enables clean imports
- Decorator-based registration is elegant but requires understanding of class-level side effects

---

### Phase 1.2 — Configuration Management Layer ✅

**Completed**: April 16, 2026

**Summary**:
Built a centralized ConfigManager with a 4-level precedence chain (YAML defaults → user config file → environment variables → CLI args). Configuration is immutable after validation, preventing accidental runtime mutations.

**Completed Deliverables**:
- `canpy/config/manager.py` — ConfigManager with load/validate/lock lifecycle
- `canpy/config/defaults.yaml` — Default settings (interface, bitrate, capture mode, output, DBC)
- `capture.py` refactored to accept ConfigManager via dependency injection
- Comprehensive validation: bitrate, capture mode, output directory, DBC file existence, output formats, CAN ID filters
- Config immutability after `validate_config()` (prevents post-validation mutations)
- Integration tests covering defaults, env overrides, args overrides, locking, and validation

**Design Patterns Implemented**:
- Strategy Pattern (multiple config sources with consistent interface)
- Layered Configuration (4-level precedence chain)
- Immutable Object Pattern (lock after validation)
- Dependency Injection (ConfigManager injected into CANCapture)

**Key Learnings**:
- Configuration precedence chains are critical — users expect CLI to override everything
- Immutability after validation prevents entire classes of subtle bugs
- Environment variable overrides are essential for CI/CD and deployment flexibility
- Validation should give actionable warnings (e.g., "uncommon bitrate" vs. just rejecting)
- Separating config loading from config validation makes testing much easier

---

### Phase 1.3 — Data Access Layer (Repository Pattern) ✅

**Completed**: May 7, 2026

**Summary**:
Established the first read-side data access layer around a canonical `CANFrame` model. Captured CSV data can now be reopened, queried lazily through `QueryFilter`, and consumed through a repository abstraction without changing the capture write loop.

**Completed Deliverables**:
- `canpy/storage/frame.py` — immutable `CANFrame` value object
- `canpy/storage/repository.py` — `BaseRepository` contract with convenience query helpers
- `canpy/storage/query.py` — `QueryFilter` with construction-time validation
- `canpy/storage/csv_repository.py` — CSV repository with lazy reads, context manager support, and explicit cleanup on open-time validation failures
- `canpy/__init__.py` and `canpy/storage/__init__.py` — public repository exports
- Integration coverage for `CSVWriter` → `CsvRepository` → `QueryFilter`
- Validation result: full suite passing (`179` tests)

**Key Learnings**:
- Query objects should reject invalid inputs at construction time, not during iteration
- Resource cleanup should be explicit on error paths, even when the runtime may hide the issue temporarily
- Adding the read-side repository without refactoring the write path kept the phase focused and low-risk

---
---

## 📝 Session Notes: May 7, 2026 (Phase 1.3 Closeout)

**Focus**: Close Phase 1.3, resolve audit findings, and prepare Phase 1.4.

**Key Decisions Made**:
1. `QueryFilter` now validates numeric time bounds during construction, so repositories can trust filter objects. ✅
2. `CsvRepository.open()` now closes file handles explicitly if CSV header validation fails. ✅
3. Phase 1.3 ends as a read-side integration phase; capture continues writing through writer plugins until Phase 1.5 reorganizes the application boundary. ✅

**Validation Snapshot**:
- `pytest tests -q` → `179 passed`
- Storage path verified end to end: `CSVWriter` → `CsvRepository.open()` → `QueryFilter`

---

## 🏗️ Current Phase (Next to Implement)

### Phase 1.4 — Validation & Error Handling

#### Goals
1. Catch invalid data early with actionable diagnostics instead of delayed runtime failures
2. Define a consistent domain exception model across parser, config, storage, and capture layers
3. Replace internal `print()`-based diagnostics with structured logging without breaking CLI usability
4. Prepare the codebase for richer Phase 2 query and visualization workflows

#### Why Now?
- Phase 1.3 introduced more data boundaries: parser → `CANFrame`, CSV → repository, config → capture.
- Current error handling still mixes raw `ValueError`, `print()`, and module-specific behavior.
- Phase 2 will be much harder to debug if malformed data and context-free errors keep propagating.

#### Steps

##### Step 1.4.1 — Define Domain Exceptions and Logging Boundary

**STATUS**: Next

- 🎯 **Objective**: Create `canpy/exceptions.py` with a small domain exception hierarchy and decide where lower layers raise typed errors versus where the CLI formats user-facing messages.
- 🧠 **Concept to learn**: Error boundaries — lower layers should expose structured failures, while the application boundary decides how to present them.
- ⚖️ **Tradeoffs**:
  - **Custom exceptions vs. raw `ValueError`**: Custom types add maintenance cost but make error handling explicit and extensible.
  - **Centralized logging policy vs. scattered prints**: A logging boundary requires discipline, but it avoids mixing user interaction with library behavior.
- 📌 **Implementation guidance**:
  - Start with a base `CanPyError` plus focused subclasses for config, parser, repository, and validation concerns
  - Update only boundary-facing code paths first; do not refactor unrelated logic in this step
  - Keep existing CLI behavior stable while moving lower layers away from direct printing

##### Step 1.4.2 — Introduce Validation Schemas for Boundary Data

- 🎯 **Objective**: Add `canpy/validation/schemas.py` and validate frame-shaped data at ingress and egress boundaries.
- 🧠 **Concept to learn**: Schema validation — validate external data once at trust boundaries, not repeatedly throughout the system.
- ⚖️ **Tradeoffs**:
  - **Validate everywhere vs. validate at boundaries**: Boundary validation is cheaper and clearer; validating every internal hop adds noise and runtime overhead.
  - **Strict rejection vs. permissive coercion**: Reject obviously broken data, but allow safe normalization where it improves usability.
- 📌 **Implementation guidance**:
  - Validate parser outputs before persistence and repository row conversion before returning `CANFrame`
  - Keep the hot capture loop lean; avoid redundant validation on already-trusted objects
  - Favor explicit field-level errors over generic "invalid frame" messages

##### Step 1.4.3 — Improve Parser and Repository Diagnostics

- 🎯 **Objective**: Enrich failures with file path, row, CAN ID, signal, and DBC context so errors are actionable.
- 🧠 **Concept to learn**: Diagnostic design — good error messages reduce debugging time more than clever recovery logic.
- ⚖️ **Tradeoffs**:
  - **Fail-fast vs. skip-and-continue**: Fail-fast is simpler and safer for now; selective recovery can come later once the error model is stable.
  - **Verbose context vs. noisy errors**: Include enough context to debug, but avoid dumping irrelevant internal state.
- 📌 **Implementation guidance**:
  - Repository errors should include file path and row-level context
  - Parser and DBC failures should name the message or signal involved when possible
  - Reuse the domain exception hierarchy instead of inventing one-off messages in each module

##### Step 1.4.4 — Replace Internal Prints with Structured Logging

- 🎯 **Objective**: Move non-user-facing diagnostics to `logging` with consistent levels and module loggers.
- 🧠 **Concept to learn**: Observability — logs are for operators and developers, not for every library call site.
- ⚖️ **Tradeoffs**:
  - **CLI friendliness vs. structured logs**: Keep the CLI readable, but stop using `print()` inside reusable modules for internal state and warnings.
  - **Rich logs vs. minimal setup**: Start simple with level-based logging; avoid building a custom logging framework.
- 📌 **Implementation guidance**:
  - The CLI remains responsible for final user-facing output
  - Lower layers should log context and raise typed exceptions
  - Replace prints incrementally, starting with config, capture, parser, and storage boundary messages

##### Step 1.4.5 — Add Validation and Error-Handling Tests

- 🎯 **Objective**: Add unit and integration tests that lock down exception translation, schema validation, and logging behavior.
- 🧠 **Concept to learn**: Regression protection for boundaries — tests should assert structured behavior, not brittle console text snapshots.
- ⚖️ **Tradeoffs**:
  - **Console snapshot tests vs. behavior tests**: Behavior tests are more stable and more useful for refactors.
  - **Broad integration tests vs. targeted slices**: Prefer targeted tests first, then add one or two boundary integrations where the risk is highest.
- 📌 **Implementation guidance**:
  - Focus first on config, parser, storage, and capture error paths that currently mix raw exceptions and prints
  - Test invalid DLC, malformed CSV rows, missing DBC messages, and logging/exception handoff
  - Keep the new test cases close to the touched modules to preserve fast feedback

---

## 🔮 Future Phases

### Phase 1.5 — Project Reorganization
**High-level goals**:
- Separate CLI concerns from business logic: `capture.py` → `cli/main.py` (entry point) + `capture/engine.py` (logic)
- Reorganize into clear packages: `capture/`, `storage/`, `writers/`, `config/`, `validation/`, `cli/`
- Clean up `capture.py` which currently has too many responsibilities (connection, parsing, filtering, writing, console output, statistics)
- Establish clear `__init__.py` exports for each subpackage
- Remove deprecated `streaming_writer.py` and legacy `config.py`

**Additional refactoring** (discovered in Phase 1.3):
- **Centralize CANFrame class**: Move from `canpy/storage/frame.py` to `canpy/core/frame.py` or `canpy/frame.py`
  - Rationale: Phase 1.3 identified that CANFrame should be the canonical representation across all systems (parser, writers, repository, capture)
  - Current issue: Writers (Phase 1.1) and Repository (Phase 1.3) both work with frame data, but writers use dict while repository uses CANFrame
  - Solution: Move CANFrame to central location, update writers to accept CANFrame as input (like repository does)
  - Benefit: Single source of truth, type safety, consistency
  - Timing: Do in Phase 1.5 after Phase 1.3 complete (avoids refactoring working code mid-phase)
  - Impact: Minimal breaking changes (writers will be more type-safe, cleaner)

### Phase 2 — Data Exploration & Visualization
**High-level goals**:
- Extend repository-backed queries with aggregation and advanced filters
- Add SQLite as the next storage backend and support import from CSV captures
- Generate static and interactive visual outputs from queried data
- Support DataFrame export for analysis workflows

---

## 🎨 PHASE 2: Data Exploration & Visualization

### Overview
Enable understanding of captured data through queries and visual representations.

### Steps (High-Level)

#### **2.1 — Query & Aggregation Engine**
- Advanced filtering (CAN ID ranges, signal value ranges, time windows)
- Grouping (mean/min/max/count by time bucket)
- Statistics (per-signal over time windows)

#### **2.2 — SQLite Integration**
- Schema design (messages, signals, captures metadata)
- Migrations (handle schema evolution)
- Bulk import from CSV into SQLite
- Query optimization (indexing strategies)

#### **2.3 — Visualization Writers**
- PNG plots (matplotlib) — signal vs. time
- HTML interactive (plotly) — hover, pan, zoom
- Summary reports — signal stats, data quality
- Real-time monitoring

#### **2.4 — Pandas Integration**
- Export queries to DataFrame
- Statistical analysis (correlation, drift)
- Data quality checks (missing frames, duplicates)

---

## 🔧 PHASE 3: Test Equipment Integration (FUTURE)

### Overview
Connect to hardware and control test scenarios programmatically.

### Steps (High-Level)

#### **3.1 — Hardware Abstraction Layer (HAL)**
- Equipment interface (DAQ, power supply, oscilloscope)
- Protocol support (SCPI, proprietary commands)
- Error handling + timeouts

#### **3.2 — Async I/O & Concurrency**
- Async capture + equipment control simultaneously
- Event coordination
- Proper cancellation & cleanup

#### **3.3 — Test Scenario Framework**
- DSL: "Ramp voltage 5V → 20V over 30 seconds, capture signals"
- Validation rules + pass/fail
- Sequential + parallel operations

#### **3.4 — Database Schema Versioning**
- Auto-migrate old captures to new schemas
- Backward compatibility

---

## 📈 Architecture Evolution

```
PHASE 1: Monolithic → Pluggable
├── Writers register themselves (1.1 ✅)
├── Config centralized in YAML (1.2 ✅)
├── Repository abstracts storage (1.3 ✅)
├── Validation schemas catch errors (1.4 ← NEXT)
└── Clean package structure (1.5)

PHASE 2: Add Query & Visualization
├── Queries work across CSV, SQLite, future formats
├── Visualization writers generated from data
├── No changes to Phase 1 architecture
└── Just extends repository with query methods

PHASE 3: Add Hardware & Test Control
├── Async event loop coordinates operations
├── Equipment drivers load via HAL
├── Test scenarios use repository for logging
└── Schema migrations handle evolution
```

---

## 🎓 Key Architectural Principles

| Principle | Why It Matters | Demonstrated In |
|-----------|---|---|
| **Dependency Inversion** | Code changes at boundaries, not core | Factory, ConfigManager, Repository |
| **Open/Closed** | Add features without modifying existing | Plugin system, writer registry |
| **Separation of Concerns** | Each module has one reason to change | CLI ≠ Parser ≠ Storage ≠ Config |
| **Configuration as Code** | Easy to test different scenarios | YAML + environment overrides |
| **Lazy Evaluation** | Efficient for large datasets | Repository loads frames on demand |
| **Immutability** | Prevents subtle runtime bugs | ConfigManager locks after validation |

---

## 📝 Session Updates

**Session 1** ✅ — Phase 1.1 complete (April 14, 2026)
- Built writer plugin architecture with Factory + Registry + Decorator patterns
- 16/16 tests passing
- Open/Closed Principle proven with ExampleWriter

**Session 2** ✅ — Phase 1.2 complete (April 16, 2026)
- Built ConfigManager with 4-level precedence (YAML → user file → env → CLI)
- Immutable config after validation
- capture.py refactored to use dependency-injected ConfigManager
- Comprehensive integration tests (defaults, overrides, locking, validation)

**Session 3** ✅ — Phase 1.3 complete (May 7, 2026)
- Built `CANFrame`, `BaseRepository`, `QueryFilter`, and `CsvRepository`
- Added post-capture CSV read/query integration without refactoring the capture write loop
- Closed audit gaps in `QueryFilter` validation and repository open-time cleanup
- Full suite passing (`179/179`)

---

## 🏁 Success Criteria

**Phase 1 ✅**: New feature added without modifying core logic  
**Phase 2 ✅**: Data visualized and queried  
**Phase 3 ✅**: Hardware controlled and test scenario ran  
