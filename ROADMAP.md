# 🗺️ CAN-PY: 3-Phase Implementation Roadmap

**Last Updated**: Phase 1.1 Complete (April 14, 2026)  
**Status**: ✅ Phase 1.1 Foundation Complete → Moving to Phase 1.2  
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

## 🏗️ PHASE 1: Foundation & Extensibility

### Overview
Build extensible architecture that supports future growth without architectural rework. Shift from monolithic CLI to plugin-based system.

### Steps

#### **1.1 — Plugin Architecture & Writer Registry** ✅ **COMPLETE**

**Status**: Phase 1.1 is **FINISHED** (April 14, 2026)

**Completed Deliverables**:
- ✅ `canpy/writers/registry.py` — WriterFactory with registration validation
- ✅ `canpy/writers/csv_writer.py` — Single-responsibility CSVWriter
- ✅ `canpy/writers/json_writer.py` — Single-responsibility JSONWriter  
- ✅ `canpy/writers/example_writer.py` — Extensibility proof (dummy writer)
- ✅ `canpy/writers/base.py` — BaseOutputWriter interface (refactored)
- ✅ `capture.py` refactored to use WriterFactory loop (one writer per format)
- ✅ Test suite: 16/16 tests passing
  - Factory registration tests (7 tests)
  - Writer implementation tests (5 tests)
  - Extensibility proof tests (4 tests)

**Key Achievements**:
- **Open/Closed Principle Proven**: ExampleWriter added with ZERO capture.py modifications
- **Factory Pattern**: Decouples capture.py from concrete writer implementations
- **Decorator-based Registration**: New formats auto-register on import via `@WriterFactory.register()`
- **Single Responsibility**: Each writer handles one format only
- **Professional Packaging**: `pyproject.toml` with `src/` layout; proper imports

**Design Patterns Implemented**:
- Factory Pattern (WriterFactory.create())
- Registry Pattern (format_name → writer_class mapping)
- Decorator Pattern (@WriterFactory.register())
- Abstract Base Class Pattern (BaseOutputWriter)
- Dependency Injection (factory loop in capture.py)

**Learning Outcomes**:
- SOLID Principles in practice
- Test organization (mechanism vs. integration tests)
- Professional Python packaging
- Extensible software architecture

**Knowledge Preserved**:
- See: [docs/PHASE4_EXTENSIBILITY.md](./docs/PHASE4_EXTENSIBILITY.md) for architecture explanation

---

#### **1.2 — Configuration Management Layer** ⏭️ **NEXT**

**Learn**: Configuration patterns, environment overrides, YAML/JSON config files  

**Plan**:
- Create `canpy/config/manager.py` — Centralized ConfigManager
- Create `canpy/config/defaults.yaml` — Default settings (bitrate, output dir, etc.)
- Refactor `capture.py` to use ConfigManager instead of argparse
- CLI args override config file settings

**Why**: Settings evolve—hardware specs, visualization options, database URLs—need centralization.

**Design Pattern**: Strategy Pattern (load config from file or environment)

**Estimated Scope**: 3 tasks, ~15 min each (planning included)

---

#### **1.3 — Data Access Layer (Repository Pattern)**
**Learn**: Repository Pattern, Adapter Pattern, lazy loading  
**Build**:
- `canpy/storage/repository.py` — Abstract interface
- `canpy/storage/csv_repository.py` — CSV implementation
- `canpy/storage/query.py` — Filter & aggregate (CAN ID, time, signals)
- Refactor capture to write through repository

**Why**: Query abstraction essential for Phase 2 visualization and Phase 3 test logs.

---

#### **1.4 — Validation & Error Handling**
**Learn**: Data validation, exception hierarchies, error reporting  
**Build**:
- `canpy/validation/schemas.py` — Pydantic models (frame validation)
- `canpy/exceptions.py` — Domain-specific exceptions
- Enhance `parser.py` with detailed validation errors
- Structured logging (replace print statements)

**Dependency**: **Pydantic** (justification: industry standard for validation, auto-generates documentation)

---

#### **1.5 — Project Reorganization**
**Learn**: Package design, responsibility boundaries  
**Build**:
- Reorganize: `capture/`, `storage/`, `writers/`, `processors/`, `config/`, `validation/`, `cli/`
- `capture.py` → `cli/main.py` (entry point)
- Logic → `capture/engine.py` (business logic)
- Clean `__init__.py` exports
- Note from the user: Use this phase to improve capture.py. It has too much responsabilites right now'

---

### ✅ Deliverables & Tests

```bash
# 1.1: Writers self-register & factory creates them
pytest tests/writers/test_registry.py -v

# 1.2: Config loads from YAML + CLI overrides work
pytest tests/config/test_manager.py -v

# 1.3: Repository queries lazily (doesn't load entire file)
pytest tests/storage/test_repository.py -v

# 1.4: Invalid frames caught with meaningful messages
pytest tests/validation/test_schemas.py -v

# 1.5: Reorganized structure works end-to-end
python -m canpy.cli capture --duration 5 --log csv,json
```

**Success Criteria**:
- [ ] New writer format added without modifying existing code ✅ Proves step 1.1
- [ ] Config changes via YAML, no CLI args needed
- [ ] Repository queries CSV without loading entire file into memory
- [ ] Invalid data caught with detailed "why" (not just "error")
- [ ] All tests pass, >80% coverage
- [ ] SOLID principles demonstrated in code reviews

---

## 🎨 PHASE 2: Data Exploration & Visualization

### Overview
Enable understanding of captured data through queries and visual representations.

### Steps

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

### ✅ Deliverables & Tests

```bash
# Queries filter + aggregate correctly
pytest tests/storage/test_queries.py -v

# SQLite backend works, migrations are correct
pytest tests/storage/test_sqlite.py -v

# Visualizations generate without errors
pytest tests/writers/test_visualization_writers.py -v

# End-to-end flow
python -m canpy.cli capture --duration 10 --db vehicle.db
python -m canpy.cli query vehicle.db --signal VehicleSpeed --plot output.png
```

---

## 🔧 PHASE 3: Test Equipment Integration (FUTURE)

### Overview
Connect to hardware and control test scenarios programmatically.

### Steps

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

### ✅ Deliverables & Tests

```bash
pytest tests/hardware/test_hal.py -v
pytest tests/capture/test_async_engine.py -v
pytest tests/scenarios/test_scenario_executor.py -v
```

---

## 📈 Architecture Evolution

```
PHASE 1: Monolithic → Pluggable
├── Writers register themselves
├── Config centralized in YAML
├── Repository abstracts storage
└── Validation schemas catch errors

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
| **Dependency Inversion** | Code changes at boundaries, not core | Factory, Repository, HAL |
| **Open/Closed** | Add features without modifying existing | Plugin system |
| **Separation of Concerns** | Each module has one reason to change | CLI ≠ Parser ≠ Storage |
| **Configuration as Code** | Easy to test different scenarios | YAML + environment overrides |
| **Lazy Evaluation** | Efficient for large datasets | Repository loads frames on demand |
| **Async Patterns** | Enable concurrent operations | Phase 3 capture + equipment |

---

## 📝 Session Updates

After each session, update this section:

**Session 1 Completed** ✅
- Phase 1 Steps: 1.1, 1.2, 1.3, 1.4, 1.5
- Key Decisions Made: [To be filled]
- Unexpected Learnings: [To be filled]
- Next Focus: Phase 2 Step 2.1

---

## 🏁 Success Criteria

**Phase 1 ✅**: New feature added without modifying core logic  
**Phase 2 ✅**: Data visualized and queried  
**Phase 3 ✅**: Hardware controlled and test scenario ran  