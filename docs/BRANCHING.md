# CAN-PY Branching and Promotion Guide

## Purpose

This document separates:

- stable code used as a release;
- ongoing guided development;
- the current NHR field pilot;
- focused feature work.

The objective is safe, understandable promotion—not frequent merging for its
own sake.

---

## Important naming note

The directory name and the Git branch name are not the same thing.

Current worktrees:

| Directory | Current branch | Role |
|---|---|---|
| `can-py` | `dev` | Guided development and integration |
| `can-py-main` | `exp/NHR9300` | Operational NHR field pilot |

The Git branch named `main` does **not** currently contain the NHR MVP.

Always check `git status --short --branch` before editing, testing, committing,
or describing a worktree.

---

## Branch roles

### `main` — Stable release

`main` represents a reviewed version suitable for normal lab use.

It should contain:

- completed, coherent roadmap increments;
- passing automated tests;
- documented operator commands;
- representative operational validation where required.

It should not receive:

- partial learning steps;
- experimental hardware integration;
- unreviewed format migrations;
- direct day-to-day development.

Merging to `main` is important, but only at a release milestone.

### `dev` — Integration and learning

`dev` is the base for roadmap implementation.

It contains:

- completed learning steps that work together;
- features accepted for continued development;
- architecture that is not yet promoted as a stable release.

Normal feature branches start from `dev` and return to `dev` after review.

### `exp/NHR9300` — Field pilot

`exp/NHR9300` supports the current read-only CAN/NHR operational MVP.

Until its behavior is promoted:

- keep it usable for current tests;
- avoid broad refactors;
- accept only required operational fixes or explicitly approved improvements;
- preserve observation-only NHR behavior;
- record fixes that must later be ported to `dev`.

This branch and `dev` diverged from the same older `main`. The NHR branch is not
equivalent to `dev` plus NHR support, so it must not be blindly merged into
`dev`.

### `feat/<topic>` — Focused roadmap work

Create a focused branch from `dev` for a roadmap step when implementation
begins.

Examples:

- `feat/compact-recording`;
- `feat/session-manifest`;
- `feat/live-monitor`;
- `feat/nhr-observation-port`.

A feature branch should normally represent one reviewable roadmap step or one
small group of inseparable steps.

### `fix/<topic>` — Narrow fixes

Use for a focused defect in the branch where the defect matters.

An operational fix made on `exp/NHR9300` should later be:

- reproduced or reviewed against `dev`;
- ported intentionally if still relevant;
- tested against the newer architecture.

Do not assume a commit can always be cherry-picked cleanly.

---

## Normal development path

```text
dev
  └── feat/<roadmap-step>
          ├── guided implementation
          ├── tests and review
          └── accepted integration back to dev

dev
  └── release gate
          └── merge to main
```

Process:

1. Confirm the current roadmap step.
2. Inspect that `dev` is clean and current.
3. Create a focused feature branch only with user approval.
4. Follow `docs/WORKFLOW.md`.
5. Review the diff and run proportionate tests.
6. Obtain explicit approval before commit or push.
7. Integrate into `dev` after the step is accepted.
8. Keep working in `dev` until a release-level outcome is complete.

---

## NHR MVP promotion path

Promotion means porting accepted behavior into the current architecture.

### Gate 1 — Field evidence

Before porting, the pilot should demonstrate:

- a normal representative test;
- a representative long test;
- clean normal stop and operator interruption;
- actionable behavior when CAN traffic is absent;
- actionable behavior when the NHR stream or service is interrupted;
- correct sampled CAN/NHR time correlation;
- raw files retained if the merged output fails;
- no NHR control or energizing behavior.

### Gate 2 — Behavior inventory

List the accepted behavior to preserve, including:

- CLI contract;
- first-valid-NHR start boundary;
- host UTC and adapter timestamp meanings;
- SSE worker lifecycle;
- reconnect and error reporting;
- merged-signal selection and freshness rules;
- raw-file retention.

The inventory is more important than preserving the exact experimental code.

### Gate 3 — Focused port to `dev`

Port through small branches or steps:

1. shared timestamp/frame contract;
2. read-only NHR provider;
3. capture lifecycle integration;
4. session metadata and compact-storage integration;
5. selected-signal merged export;
6. live-view integration.

Each part is reviewed against the accepted behavior and the current `dev`
architecture.

### Gate 4 — Release candidate

The integrated `dev` version must pass:

- the full automated suite;
- compact-recording validation;
- live-monitor validation;
- NHR failure-path tests;
- representative bench validation;
- operator documentation review.

Only then is `dev` a candidate for promotion to `main`.

---

## Promotion to `main`

A merge to `main` should answer yes to all of the following:

- Is the roadmap milestone complete?
- Is the worktree clean and the intended diff understood?
- Do automated tests pass in the supported environment?
- Has hardware-dependent behavior been validated at the correct safety stage?
- Are normal startup, stop, and failure paths documented?
- Can an operator run the feature without development context?
- Are known limitations acceptable and recorded?
- Has the user explicitly approved the commit, push, and merge?

Recommended release actions after approval:

1. merge the accepted `dev` history into `main`;
2. run the final validation from `main`;
3. tag a version;
4. keep `dev` for the next roadmap phase;
5. retain or archive the experimental branch only after its unique behavior is
   present in the stable history.

---

## Conflict and scope rules

- Never solve branch divergence by discarding one side.
- Do not use a broad merge as a substitute for understanding experimental
  behavior.
- Preserve unrelated user changes.
- Do not combine an urgent lab fix with roadmap refactoring.
- Do not delete an experimental branch until its useful behavior and evidence
  are accounted for.
- Do not commit generated captures, credentials, machine-specific paths, or
  large benchmark outputs.
- Prefer a concise decision note when a port intentionally changes behavior.

---

## Quick decision table

| Situation | Work location |
|---|---|
| Current lab test with existing NHR MVP | `exp/NHR9300` worktree |
| New roadmap feature | `feat/<topic>` from `dev` |
| Guided cleanup supporting a current step | Feature branch from `dev` |
| Urgent defect blocking the NHR pilot | Narrow fix on `exp/NHR9300`, then assess port |
| Stable milestone accepted for normal use | Promote tested `dev` to `main` |
