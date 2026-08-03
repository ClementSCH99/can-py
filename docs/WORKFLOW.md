# CAN-PY Learning and Development Workflow

## Purpose

CAN-PY is both:

- an operational tool used during real tests;
- a guided software-development project.

The workflow must therefore produce useful increments without removing the
learner from the important design and coding decisions.

This document defines **how we work**. `ROADMAP.md` defines **what comes next**,
and `docs/BRANCHING.md` defines **where changes are developed and promoted**.

---

## Working principles

### 1. Operational need sets the order

Architecture is introduced to solve a real problem or prepare the next known
step. A useful vertical feature may take priority over a broad cleanup.

Deferred design work is recorded in the roadmap. It is not silently discarded.

### 2. Understand before generating

Before implementation, the learner should be able to explain:

- the problem being solved;
- the important constraint;
- the proposed boundary or contract;
- the main tradeoff;
- what evidence will show that the step works.

The goal is understanding, not manually typing every repetitive line.

### 3. The learner owns the important reasoning

The learner normally owns or co-implements:

- domain rules;
- safety-sensitive boundaries;
- data and timestamp semantics;
- public interfaces;
- the core algorithm or design concept being learned;
- acceptance of tradeoffs.

### 4. The LLM may remove boilerplate

After the design is understood and the scope is agreed, the LLM may implement:

- repetitive CLI or configuration wiring;
- fixtures and test-data builders;
- straightforward adapters;
- package exports;
- repetitive validation cases;
- documentation updates;
- mechanical refactors already decided together.

The LLM should not quietly replace the learning task, invent adjacent features,
or rewrite a working design without explaining why.

### 5. Small accepted steps

Each roadmap step should finish with a reviewable result. A step is not complete
only because code exists.

Completion requires:

- agreed behavior;
- proportionate automated tests;
- a readable diff;
- relevant documentation;
- operational evidence when hardware or real data matters;
- explicit user acceptance.

---

## Step-by-step cycle

Every implementation step follows the same cycle.

### Stage A — Step context

The LLM presents:

- current phase and step;
- why the step matters now;
- concepts to learn;
- known constraints and safety boundaries;
- what is explicitly out of scope.

No implementation begins while the problem or scope is materially ambiguous.

### Stage B — Design together

The learner and LLM define:

- inputs and outputs;
- ownership and lifecycle;
- error behavior;
- acceptance tests;
- one or more options when a real tradeoff exists.

The LLM makes a recommendation and explains it. The learner is not forced to
choose between unexplained alternatives.

### Stage C — Divide the work

Before editing, state clearly:

- **Learner task:** the part intended to build understanding;
- **LLM task:** boilerplate or mechanical work it may implement;
- **Joint task:** code or design to review together.

The division may change from one step to another.

### Stage D — Implement a focused increment

Implementation stays within the current step.

Rules:

- prefer the smallest functional slice;
- keep code explicit and lightly commented;
- do not add speculative improvements;
- preserve unrelated user changes;
- do not commit or push without explicit approval.

### Stage E — Review and explain

The review checks:

- alignment with the step contract;
- correctness and failure behavior;
- clarity for a newer developer;
- unnecessary complexity;
- future risks that are relevant but not necessarily fixed now.

When the learner wrote the core code, the LLM first explains issues and offers
hints. It does not automatically replace the solution.

### Stage F — Validate

Validation is proportional to risk:

- unit tests for local behavior;
- integration tests for boundaries;
- round-trip or fixture tests for data formats;
- manual commands for CLI behavior;
- bench evidence for hardware-dependent behavior.

A software test is not described as hardware validation.

### Stage G — Close the step

The closeout records:

- what was delivered;
- what was learned;
- test and operational evidence;
- accepted limitations;
- follow-up items;
- whether the roadmap should advance or change.

The user decides when the step is accepted and whether a commit or promotion is
appropriate.

---

## Collaboration modes

These are conversational modes, not separate tools.

### Explore

Use when the problem or desired behavior is not yet clear.

Expected output:

- observations;
- concise options;
- recommendation;
- questions that materially affect the design.

No code changes unless explicitly requested.

### Guided implementation

Use for normal roadmap work.

Expected behavior:

- teach the current concept;
- agree on the contract;
- divide learner and LLM tasks;
- implement only the agreed portion;
- validate together.

### Review

Use after the learner writes code.

Expected behavior:

- review against the current step;
- identify correctness problems before style issues;
- explain why an issue matters;
- prefer hints for the learning portion;
- state whether the step is ready to close.

### Operational fix

Use when a real test is blocked or data is at risk.

Expected behavior:

- keep the fix narrow;
- work in the operational branch described in `docs/BRANCHING.md`;
- preserve safety boundaries;
- document what must later be ported into `dev`;
- do not turn the urgent fix into an unplanned redesign.

---

## Safety and scope boundaries

### NHR

CAN-PY consumes measurements from the separate `nhr-rt` service. Unless a new
safety stage is explicitly reviewed and authorized, CAN-PY does not:

- arm equipment;
- change state, limits, or setpoints;
- start a routine;
- energize a test;
- bypass interlocks or protections.

Stopping an observation worker follows:

1. signal the stop event;
2. join the worker;
3. disconnect only after the worker has ended.

### Recording requests

When the user asks for writing or logging, it means writing captured data to a
file such as CSV. It does not authorize writes to equipment configuration or
state.

### Git

The LLM may inspect branches, diffs, and history during normal work. It does not
commit, push, merge, rebase, tag, or delete branches without explicit user
approval.

---

## Documentation responsibilities

| Document | Responsibility |
|---|---|
| `ROADMAP.md` | Current direction, completed phases, detailed current phase, future buffer |
| `docs/WORKFLOW.md` | Learning and implementation method |
| `docs/BRANCHING.md` | Branch roles, integration path, and release gates |
| `README.md` | Installation and operator-facing usage |
| Focused design note | Only when a decision cannot remain concise in the roadmap |

Avoid creating a new design document for every discussion. A separate note is
justified when it contains durable evidence, a decision with meaningful
tradeoffs, or an operational contract used by multiple phases.

---

## Expected step handoff

At the beginning of a step:

```text
Phase:
Step:
Operational goal:
Concept to learn:
In scope:
Out of scope:
Learner task:
LLM task:
Validation:
```

At the end of a step:

```text
Status:
Delivered:
Evidence:
What was learned:
Known limitations:
Next decision:
Commit/push authorization:
```

These templates are guides. They should keep the work clear without making a
small change feel bureaucratic.
