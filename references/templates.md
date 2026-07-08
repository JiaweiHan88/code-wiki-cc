# Wiki document templates

Fill these in with real, verified content. Every template is Markdown (the authoring
source); `scripts/build_html_wiki.py` later turns the whole set into the HTML site, so
**write plain Markdown here** and let the build script handle HTML, the sidebar, and
Mermaid rendering. Keep `\`\`\`mermaid` fenced blocks exactly as fenced code — the build
step converts them into live diagrams.

Link style between wiki pages: use the Markdown filename (e.g. `[arch](architecture.md)`,
`[run_loop](modules/run_loop.md)`). The build script rewrites these to in-page anchors,
and they still work as file links when browsing the raw Markdown on GitHub.

---

## README.md

```markdown
# <Project Name>

<One paragraph: what it is and what it's for. Self-contained — assume the reader
does not have the source README open.>

## Key Concepts

- **<Concept>** — <one line>

## Entry Points

- [`path/to/main`](path/to/main) — <what runs when you start it>

## High-Level Architecture

<2-3 sentences. Detail lives in architecture.md.>  See [architecture.md](architecture.md).

## Module Map

| Module | Purpose |
|---|---|
| [`<module>`](modules/<module>.md) | <one-line purpose> |

## Getting Started

See [getting-started.md](getting-started.md).
```

---

## architecture.md

```markdown
# Architecture

<2-3 paragraphs: the shape of the system. What talks to what. Where data enters,
where it exits, where state lives.>

## Components

- **<Component>** — <1-2 sentences>. See [`modules/<module>.md`](modules/<module>.md).

## System Diagram

\`\`\`mermaid
flowchart TD
    User([User]) --> Entry[Entry Point]
    Entry --> Core[Core Engine]
    Core --> DB[(Database)]
    Core --> API{{External API}}
\`\`\`

## Data Flow

1. **<Step>** — `<file>`

## Key Design Decisions

- <Anything load-bearing the reader should know>
```

Mermaid shape semantics: `[]` component · `[()]` database/storage · `{{}}` external
service · `(())` entry/terminal · `-->` sync call · `-.->` async/event. Cap ~20 nodes
per diagram; split if larger. In **deep** mode, add a per-subsystem diagram where a
subsystem is complex enough to warrant its own view.

---

## modules/<module>.md

```markdown
# Module: `<module>`

<1-2 sentence purpose.>

## Responsibilities

- <bullet>

## Key Files

- `<module>/<file>` — <what it does>

## Public API

<Functions/classes/constants other code uses. Show signatures, not full bodies.>

## Internal Structure

<How the module is organized. Where state lives.>

## Dependencies

- **Used by:** <other modules>
- **Uses:** <other modules + external libs>

## Notable Patterns / Gotchas

- <Anything non-obvious>
```

**Deep mode** adds, per module: a **Detailed walkthrough** of the primary code path
(function by function), notable edge cases / error handling, and — where the module is
internally complex — its own small Mermaid diagram.

---

## diagrams/class-diagram.md

```markdown
# Class Diagram

## Core Types

\`\`\`mermaid
classDiagram
    class Agent {
        +string name
        +chat(message) string
    }
    class Tool {
        <<interface>>
        +execute(args) any
    }
    Agent --> Tool : uses
    Tool <|-- TerminalTool
\`\`\`

## Notes

<Lifecycle, threading, anything the diagram can't express.>
```

For classless code (Go, C, function-oriented Python): diagram struct/module
relationships instead, or state plainly that the codebase is not object-oriented and
show the import/ownership graph. **Do not force-fit a class hierarchy that isn't there.**

---

## diagrams/sequences.md

```markdown
# Sequence Diagrams

## Workflow: <Name>

<1 sentence: what this does and when it runs.>

\`\`\`mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Core
    User->>CLI: command
    CLI->>Core: call()
    Core-->>CLI: result
\`\`\`

### Walkthrough

1. **<Step>** — `<file>`
```

Light mode: 2–3 workflows. Deep mode: 4–8, covering the main happy path plus important
error/edge paths. Every participant must be a real component in the code.

---

## getting-started.md

```markdown
# Getting Started

## Prerequisites

<From manifests + README. Versions where pinned.>

## Installation

\`\`\`bash
<exact commands>
\`\`\`

## First Run

\`\`\`bash
<minimum command to see the system do something useful>
\`\`\`

## Common Workflows

### <Workflow>
\`\`\`bash
<commands>
\`\`\`

## Configuration

- `<config-file>` — <what it controls>

## Where to Go Next

- Architecture: [architecture.md](architecture.md)
```

---

## api.md (library / API server only)

Document the public surface (`__init__` exports, OpenAPI routes, exported types): each
entry with signature, parameters, return type, one-line description, grouped by category.
In **light** mode, write this only if the project is clearly a library or API server. In
**deep** mode, always include it when any public surface exists.

---

# Optional pages (author only when artifacts exist)

**Hard rule for all three pages below: author a page only if concrete artifacts exist in
the codebase — never fabricate.** Detection happens in the scan step (see `SKILL.md`).
If only 1–2 trivial facts exist (e.g. just a `test` script in `package.json` with no test
files), fold them into `getting-started.md` instead of creating a thin page. When a page
is skipped, skip it silently — no placeholder file.

---

## testing.md

```markdown
# Testing

<1-2 sentences: what test harness this codebase uses and the one command to run everything.>

## Harness

- **Runner:** <pytest / jest / go test / ... + version if pinned>
- **Config:** `<pytest.ini / jest.config.ts / ...>` — <what it sets: paths, markers, coverage>

## Test Layout

- `<tests/ or __tests__/ path>` — <what lives here; naming convention, e.g. `test_*.py`>

## Fixtures & Test Data

- `<conftest.py / fixtures/ / factories / snapshot dir>` — <what it provides and who uses it>

## Running Tests

\`\`\`bash
<all tests>
<one file>
<one test by name/pattern>
<with coverage, if configured>
\`\`\`

## Writing a New Test

<Conventions: where the file goes, base classes/helpers to use, how fixtures are pulled in.>

## Gotchas

- <Anything non-obvious: required services, env vars, slow/flaky markers, ordering>
```

**Deep mode** adds: a walkthrough of one representative test (what it exercises and how),
custom assertions/plugins/markers, and notable mocking or snapshot patterns.

---

## debugging.md

```markdown
# Debugging

<1-2 sentences: the fastest way to see what this system is doing.>

## Logging

- <How to raise verbosity: flag / env var / config key> — <where logs go>

## Debug Entry Points

- `<dev server command / REPL / scripts/debug_*.py>` — <what it lets you poke at>

## Debug Flags & Endpoints

- `<DEBUG=1 / feature flag / /debug route>` — <effect>

## Profiling & Inspection

- `<profiler / trace tool / launch.json config>` — <when to reach for it>
```

**Deep mode** adds: a worked walkthrough of debugging one realistic failure (e.g. "a
request returns 500 — where to look, in order").

Every entry must point at a real artifact (a script, a config key, a flag read in code) —
cite the file that implements it.

---

## deployment.md (CI/CD & Deployment)

```markdown
# CI/CD & Deployment

<1-2 sentences: what happens automatically on PR, merge, and release.>

## Pipeline Overview

- **On PR:** <jobs that run>
- **On merge to <branch>:** <jobs>
- **On tag/release:** <jobs>

## Workflows

| File | Trigger | What it does |
|---|---|---|
| `<.github/workflows/ci.yml>` | <push/PR/tag> | <one line> |

## Build Artifacts

- <Docker image / package / binary> — built by <workflow>, published to <where>

## Deployment Targets & Infrastructure

- <k8s manifests / terraform / helm chart paths> — <what they provision>

## Release Process

<How a release actually happens: tagging convention, version bump, manual steps if any.>
```

**Deep mode** adds: a Mermaid flowchart of the pipeline (commit → CI → artifact → deploy)
and failure/rollback notes (what happens when a stage fails, how to roll back).

**Monorepo component scope exception:** CI configs usually live at the repo root, outside
`SCOPE`. You may read root-level CI/deploy configs **read-only** and document **only the
parts that reference the component** (path filters matching `SCOPE_REL`, jobs that build
or test it). Unrelated root jobs stay undocumented. Root files read this way must still
pass `apply_ignore.py check`, and each one gets recorded in the state file's
`external_ci_files` (see `references/maintenance.md`).
