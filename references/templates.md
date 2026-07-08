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
