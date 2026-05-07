# 🗺️ CAN-PY: 3-Phase Implementation Roadmap

**Last Updated**: Phase 1.3 Steps 1.3.2-1.3.3 Complete (May 7, 2026)  
**Status**: ✅ QueryFilter + CsvRepository Complete → Moving to Phase 1.3.4  
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

---

## 📝 Session Notes: April 23-24, 2026 (Phase 1.3 Refinement)

**Focus**: Design validation and step reordering for Phase 1.3

**Key Decisions Made**:
1. **Filepath storage in CsvRepository**: Store filepath for lazy-streaming reads ✅
2. **Format standardization**: All storage backends use CANFrame format (canonical representation) ✅
3. **Data conversion strategy**: Auto-detect types for parsed signals (try float, else string) ✅
4. **CsvRepository architecture**: Align with CSVWriter format, but DO NOT wrap CSVWriter
   - Reason: CSVWriter is write-only with managed lifecycle; CsvRepository needs bidirectional control
   - Solution: Replicate ~20 lines of write logic, add independent read logic
5. **Step reordering** (see below): Build QueryFilter before CsvRepository
   - Reason: CsvRepository depends on QueryFilter.matches() for filtering
   - Benefit: No mocks/TODOs, clearer dependency order, professional practice

**Architecture Insight**:
- Writers (Phase 1.1) and Repository (Phase 1.3) are **separate systems**
- Writers: Format-specific output from capture (write-only, streaming)
- Repository: Bidirectional data access for queries (read + write, lazy)
- CsvRepository aligns with CSVWriter format (same columns, types) but doesn't couple to it

---

## 🏗️ Current Phase (Next to Implement)

### Phase 1.3 — Data Access Layer (Repository Pattern)

**STEP REORDERING NOTE**: Steps 1.3.2 and 1.3.3 have been reordered below to respect dependency order:
- Step 1.3.2 now builds QueryFilter (dependency)
- Step 1.3.3 now builds CsvRepository (depends on QueryFilter)
- This avoids mock objects and follows professional best practice (build dependencies first)

#### Goals
Introduce an abstraction layer between the application and data storage so that:
1. Capture writes go through a unified interface (not directly to writer objects)
2. Data can be **read back** and **queried** without knowing the underlying format
3. The same interface can later support CSV, SQLite, Parquet, or any new backend
4. Large files can be read lazily (streaming/chunked) instead of loading into memory

This is the critical enabler for Phase 2 visualization — you can't plot data you can't query.

#### Why Now?
- Writers currently handle **write-only** operations. There is no way to read captured data back.
- Phase 2 (visualization) requires querying captured data by CAN ID, time range, and signal name.
- Building the Repository Pattern now means Phase 2 can focus on queries and plots, not plumbing.
- The writer system (Phase 1.1) and config system (Phase 1.2) are stable foundations to build on.

#### Steps

##### Step 1.3.1 — Define the Abstract Repository Interface ✅

**STATUS**: Completed April 17, 2026

- 🎯 **Objective**: Create `canpy/storage/repository.py` with an abstract `BaseRepository` class that defines the contract for all storage backends.
- 🧠 **Concept to learn**: Repository Pattern — separates domain logic from data access. The application talks to an interface, not a specific storage engine. This is the same pattern used in Django ORM, SQLAlchemy, and most enterprise applications.
- 📌 **Deliverables**:
  - ✅ `src/canpy/storage/__init__.py` — exports CANFrame, BaseRepository
  - ✅ `src/canpy/storage/frame.py` — frozen CANFrame dataclass
  - ✅ `src/canpy/storage/repository.py` — BaseRepository interface with abstract methods
  - ✅ `tests/storage/test_frame.py` — 40+ tests covering structure, immutability, equality
  - ✅ `tests/storage/test_repository.py` — 8+ tests validating interface enforcement
  - ✅ All tests passing

##### Step 1.3.2 — Build Query Filter Object (REORDERED)

**STATUS**: Completed May 7, 2026

**REORDERING NOTE**: This step moved from 1.3.3 to 1.3.2 to respect dependency order (CsvRepository depends on QueryFilter).

- 🎯 **Objective**: Create `canpy/storage/query.py` with a `QueryFilter` class that encapsulates filter parameters, so repository methods accept a single structured object instead of many keyword arguments.
- 🧠 **Concept to learn**: Value Object / Parameter Object pattern — when a function takes many related parameters, bundle them into an object. This makes the API cleaner and the filters composable (e.g., "CAN ID 0x123 AND time > 10s").
- ⚖️ **Tradeoffs**:
  - **When to introduce this**: Building QueryFilter first (before CsvRepository) avoids mock objects and clarifies what the repository needs.
  - **Dataclass vs. builder pattern**: A simple `dataclass` with optional fields is the right choice — easy to construct, easy to test, no magic.
  - **Validation in filter vs. in repository**: Validate in the filter object itself (e.g., `start_time < end_time`). The repository should trust the filter is valid.
- 📌 **Implementation guidance**:
  - Create `src/canpy/storage/query.py`
  - Use `@dataclass` with all fields optional (defaulting to `None` = no filter)
  - Fields: `can_ids: Optional[List[int]]`, `time_start: Optional[float]`, `time_end: Optional[float]`, `limit: Optional[int]`
  - Add a `matches(frame: CANFrame) -> bool` method that checks all non-None fields against a frame
  - Validation in `__post_init__`: ensure `time_start < time_end` if both provided
  - Write tests for the filter object independently — it's pure logic, no I/O needed

**Completed Deliverables**:
- `src/canpy/storage/query.py` — `QueryFilter` value object with roadmap-aligned fields (`can_ids`, `time_start`, `time_end`, `limit`)
- `src/canpy/storage/repository.py` — convenience time-range API aligned to `time_start` / `time_end`
- `tests/storage/test_query.py` — unit tests updated to validate the roadmap contract and matching behavior
- Query validation remains inside the filter object, so repositories can trust a valid filter instance

##### Step 1.3.3 — Implement CSV Repository (REORDERED)

**STATUS**: Completed May 7, 2026

**REORDERING NOTE**: This step moved from 1.3.2 to 1.3.3 to depend on QueryFilter (built in 1.3.2).

- 🎯 **Objective**: Create `canpy/storage/csv_repository.py` that implements `BaseRepository` for CSV files — both writing frames and reading them back with filtering.
- 🧠 **Concept to learn**: Adapter Pattern (align with existing format), Generator Pattern (lazy loading), Context Managers (resource cleanup), Type Conversion (CSV strings → native types).
- ⚖️ **Architecture Decision**:
  - **NOT wrapping CSVWriter**: CsvRepository is **independent** because:
    - CSVWriter is write-only and manages its own lifecycle
    - CsvRepository needs bidirectional control (both reads and writes)
    - Wrapping would create awkward coupling and lifecycle conflicts
  - **Aligning format**: CsvRepository uses the **same CSV format** as CSVWriter (timestamp, can_id, dlc, data_hex, + dynamic signal columns)
  - **Replicating write logic**: The write logic is ~20 lines of csv.DictWriter code (acceptable duplication)
  - **Adding read logic**: New capability (generator-based lazy reading)
- ⚖️ **Tradeoffs**:
  - **Load-all vs. lazy streaming reads**: For large captures (millions of frames), use generator-based streaming. Generators work for small files with no performance penalty.
  - **In-memory index vs. scan-every-time**: Start without an index (linear scan). Optimize only if profiling shows it's needed (Phase 2).
  - **Dynamic headers vs. memory usage**: Full in-memory buffering would preserve dynamic signal columns but scales poorly for large files. The implemented solution stages frames to a temporary file during writes, then emits the final CSV with the complete header on close. This keeps memory bounded without introducing a more complex header-rewrite system.
- 📌 **Implementation guidance**:
  - Create `src/canpy/storage/csv_repository.py`
  - **Write path**: `save_frame(frame: CANFrame)`
    - Convert CANFrame to CSV row format
    - Use csv.DictWriter (mirrors CSVWriter approach)
    - Initialize headers on first write
  - **Read path**: `get_frames(query_filter: QueryFilter)` → Generator[CANFrame]
    - Use csv.DictReader (lazy by default)
    - For each row: convert CSV strings → CANFrame native types
    - Filter: `if query_filter.matches(frame)` then `yield frame`
    - Type conversions:
      - `timestamp`: `float(row['timestamp'])`
      - `can_id`: `int(row['can_id'], 16)` (hex string → int)
      - `dlc`: `int(row['dlc'])`
      - `data`: `bytes.fromhex(row['data_hex'])`
      - `parsed_signals`: Auto-detect (try float, else string)
  - **Lifecycle**: `open()` class method, `close()` method, context manager support (`__enter__`, `__exit__`)
  - **File path**: Store filepath for lazy reads (enables streaming from same file multiple times)

**Completed Deliverables**:
- `src/canpy/storage/csv_repository.py` — `CsvRepository` implementation with `create()`, `open()`, `save_frame()`, `get_frames()`, `count()`, and context manager support
- CSV read path aligned to `CSVWriter` output format: `timestamp`, `can_id`, `dlc`, `data_hex`, plus dynamic signal columns
- Disk-backed staging during writes preserves dynamic signal columns without unbounded RAM growth
- `src/canpy/storage/__init__.py` and `src/canpy/__init__.py` — export `CsvRepository`, `BaseRepository`, and `QueryFilter` as promised by Step 1.3.4 guidance
- `tests/storage/test_csv_repository.py` — lossless round-trip tests, filtering tests, edge-case tests, and CSVWriter → CsvRepository integration coverage
- `tests/storage/test_public_exports.py` — verifies the public storage API is available from `canpy`
- Validation result: storage and writer suites passing (`120` tests)

##### Step 1.3.4 — Integrate Repository into Capture Pipeline

- 🎯 **Objective**: Enable reading captured data after capture completes. Add `CsvRepository.open(filepath)` as a post-capture interface (not integrated into capture loop).
- 🧠 **Concept to learn**: Dependency Inversion Principle (DIP) — applications depend on abstractions, not concrete implementations.
- ⚖️ **Integration strategy**:
  - **Keep capture.py write path unchanged**: Writers continue to handle streaming writes (works well, no need to refactor)
  - **Add read-only repository path**: After capture completes, user can open CSV files via `CsvRepository.open(path)` and query them
  - **No breaking changes**: Existing capture functionality untouched
- 📌 **Implementation guidance**:
  - Add `CsvRepository.open(filepath: str)` class method that opens existing CSV file for reading
  - Export from `canpy/__init__.py`: `BaseRepository`, `CsvRepository`, `QueryFilter`
  - Example usage pattern:
    ```python
    repo = CsvRepository.open('data/can_capture_20260424_120000.csv')
    query = QueryFilter(can_ids=[0x123], time_start=10.0)
    for frame in repo.get_frames(query):
        print(frame)
    repo.close()
    ```
  - Write integration test: Create CSV via CSVWriter → Open via CsvRepository → Query and verify

##### Step 1.3.5 — Tests and Validation

- 🎯 **Objective**: Comprehensive test coverage for the storage layer — unit tests for QueryFilter and CsvRepository, integration tests for write→read→query cycle.
- 🧠 **Concept to learn**: Test pyramid — unit tests (fast, isolated) at base, integration tests (slower, real I/O) in middle, end-to-end tests at top.
- 📌 **Test organization**:
  - `tests/storage/test_query.py`: Unit tests for QueryFilter
    - Test filter matching: each condition independently
    - Test validation: `time_start < time_end`
    - Test edge cases: `None` values, empty lists
  - `tests/storage/test_csv_repository.py`: Unit + integration tests
    - Write frames → read back → verify lossless
    - Test filtering: write 100 frames → query specific CAN ID → verify exact subset
    - Test time range: write frames with timestamps 0-100 → query 20-80 → verify bounds
    - Test lazy loading: verify generator doesn't load entire file into memory
    - Test context manager: `with CsvRepository.open(...) as repo:` → auto-close
    - Test edge cases: empty file, single frame, missing parsed signals
  - Use `tempfile.TemporaryDirectory` for file cleanup after tests

---

## 🔮 Future Phases

### Phase 1.4 — Validation & Error Handling
**High-level goals**:
- Introduce Pydantic models for CAN frame validation (`canpy/validation/schemas.py`)
- Create domain-specific exception hierarchy (`canpy/exceptions.py`)
- Enhance `parser.py` with detailed validation errors (malformed frames, DBC mismatches)
- Replace `print()` statements with structured logging (`logging` module)
- Goal: invalid data is caught early with actionable error messages ("Frame 0x3A5 has DLC 4 but message expects DLC 8"), not silent corruption

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
├── Repository abstracts storage (1.3 ← NEXT)
├── Validation schemas catch errors (1.4)
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

---

## 🏁 Success Criteria

**Phase 1 ✅**: New feature added without modifying core logic  
**Phase 2 ✅**: Data visualized and queried  
**Phase 3 ✅**: Hardware controlled and test scenario ran  