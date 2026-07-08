---
name: code-wiki
description: "Generate and maintain a browsable wiki for a codebase or for a single component inside a large monorepo — a self-contained HTML site with 3-level sidebar nav, covering an overview, architecture, per-module deep-dives, and Mermaid class + sequence diagrams. Two lifecycle modes (INIT to create, UPDATE to surgically refresh from git changes) crossed with two depth modes (LIGHT overview vs DEEP exhaustive). Use whenever the user asks to document a codebase or component, generate/update a wiki or docs site, write onboarding or reference documentation, or produce architecture/Mermaid diagrams — even without the word 'wiki'. Works on a whole repo, a given path, an uploaded repo, or one folder within a monorepo. Produces reference documentation (what/how; plus why-notes in deep mode)."
---

# Code Wiki

Generate — and later maintain — a wiki for a codebase, rendered as a **single self-contained `index.html`** with a 3-level left-sidebar. Scope can be a whole repo or **one component folder inside a large monorepo**. Content is authored as Markdown (also renders on GitHub); a bundled build script assembles the HTML.

Reference documentation (what/how). In deep mode it adds short git-grounded *why* notes, but it is not a product-strategy narrative.

## When to use

"Document this codebase / this component", "generate a wiki", "update the wiki", "make architecture diagrams", onboarding to a repo or a package within a monorepo.

Do **not** use it for: a single file/function or one endpoint (answer inline); a one-off diagram (produce just that diagram, not a wiki); questions during active development (answer as they come); pure "why"/strategy essays.

## Environment and tools

Standard Claude tools: `bash` (list/search/git/run the build script), `view` (with `view_range`), `create_file`/`str_replace`, and `present_files`. In **Claude Code** the working directory is the target repo and the build script is at `${CLAUDE_SKILL_DIR}/scripts/build_html_wiki.py`. `git` and network may be unavailable — degrade gracefully. Prefer `rg`; the build script is stdlib-only (no pip, no network to build); Mermaid renders from a CDN (`--mermaid-src` for offline).

## Step 1 — Resolve scope (repo root + component)

Git is repo-wide; the wiki targets one folder. See `references/maintenance.md` for the exact commands. In short:

- `REPO_ROOT` = `git rev-parse --show-toplevel`; `SCOPE` = the component folder to document (defaults to the cwd; a whole-repo run sets `SCOPE=REPO_ROOT`); `SCOPE_REL` = `SCOPE` relative to `REPO_ROOT` (`.` for whole-repo).
- Document **only** files under `SCOPE`. Cross-component imports are noted as external deps by path, not documented.
- Output goes **inside the component**: `WIKI_DIR = SCOPE/wiki`. Nothing is written at the monorepo root. In the Claude.ai sandbox, use `/mnt/user-data/outputs/<name>-wiki` instead and `present_files` at the end.
- **All git commands run at `REPO_ROOT` but are path-filtered with `-- "$SCOPE_REL"`** — this is how a huge monorepo's history stays relevant to just the folder.

## Step 1.5 — Load or propose the ignore list (`.codewikiignore`)

If `REPO_ROOT/.codewikiignore` exists with active rules, ignored paths must stay **entirely** out of the run — not read, not shelled to, not described. Gitignore syntax: `#` comments, blank lines, `*`/`**`/`?` globs, directory rules (`dir/`), `!` negation. **Nests like real `.gitignore`**: a file inside a subfolder (e.g. a monorepo component) applies only within that subfolder, with patterns relative to *its own* directory, and can override — including re-include via `!` — whatever a parent-directory file said, but only for paths it has an opinion on; where it's silent, the parent's verdict stands. The bundled `scripts/apply_ignore.py` is the single source of truth and handles this layering automatically:

```bash
IGN="${CLAUDE_SKILL_DIR:-.}/scripts/apply_ignore.py"
if python3 "$IGN" active "$REPO_ROOT"; then
  # the ONLY files you may read/describe under the component (minus the wiki's own output):
  python3 "$IGN" list "$REPO_ROOT" --scope "$SCOPE_REL" | grep -v "^$WIKI_REL/"
fi
```

**No ignore file exists yet anywhere in the chain.** Before scanning, in an interactive session run a one-time proposal instead of silently walking everything:

```bash
python3 "$IGN" suggest "$REPO_ROOT" --scope "$SCOPE_REL"
```

This is a read-only scan (vendor/build/tooling dirs, generated-code files, lockfiles, and — commented out — snapshot/fixture and binary-heavy dirs worth a second look; note that `node_modules`, `.venv`, `dist`, `build`, `target`, etc. are already hardcoded always-skip in the script and won't reappear here). If it reports anything beyond "nothing detected", show the proposed contents to the user and ask (`AskUserQuestion`) how to proceed:
- **Create it as proposed** — write the output verbatim to `REPO_ROOT/.codewikiignore` (or `SCOPE/.codewikiignore` for a component-only scan), then proceed as if it had already existed (reload via `list` above).
- **Let me edit first** — show the text, apply the user's edits, then write it.
- **Skip** — proceed without creating a file; don't ask again for the rest of this run.

In a non-interactive/headless run (no way to ask), skip the proposal and proceed without creating a file — never write `.codewikiignore` without the user confirming its contents.

Rules while an ignore list is active:
- Drive all discovery (`find`/`rg`/`ls`/`view`) from that allowed list. Never `view`/`cat`/`grep`/`git show` a path outside it, even to "verify" — check first with `python3 "$IGN" check "$REPO_ROOT" <path>`.
- **Never describe an ignored path** in any page, and drop ignored paths from git evidence and from the update change-set (see `references/maintenance.md`).
- Hard enforcement for headless/CI: add `python3 "$IGN" deny-rules "$REPO_ROOT" --scope "$SCOPE_REL"` output to the `deny` list in `.claude/settings.json` so the harness blocks reads/exec on those paths regardless. `--scope` includes root-level rules plus any ignore file at or under the component, correctly path-prefixed.
- A component may keep its own `<component>/.codewikiignore` for rules only it needs (e.g. its own `secrets/`) without editing the root file; the root file still applies everywhere as a base layer.

This composes with scope (only under `SCOPE`, minus ignored) and with the secrets rule below (defence in depth).

## Step 2 — Resolve lifecycle × depth

Two independent dials. Ask only if the user gave no signal.

**Lifecycle** (from `references/maintenance.md`): `init` (create), `update` (maintain), or `auto` — if `WIKI_DIR/.codewiki-state.json` exists → update, else init.

**Depth**: signals "quick/light/overview" → light; "deep/thorough/exhaustive" → deep. On update, depth defaults to the recorded value unless overridden.

| Aspect | **Light** | **Deep** |
|---|---|---|
| Modules documented | top 8–10 | all significant (confirm cost if >~20) |
| Per-module depth | purpose, key files, public API, deps, gotchas | + function-by-function walkthrough, edge/error handling, per-module diagram when complex |
| Diagrams | 1 architecture flowchart, 1 class, 2–3 sequences | + per-subsystem flowcharts, 4–8 sequences incl. error paths |
| Git *why* notes | none | short, git-grounded notes on non-obvious design decisions (see Step 3) |
| API reference | only if clearly a library/API server | always when a public surface exists |
| Testing / Debugging / CI-CD pages | when detected: summary-level (harness, commands, pipeline table) | when detected: + representative-test walkthrough, debug walkthrough, pipeline flowchart |

## Step 3 — Scoped git evidence

Run the scoped, read-only git commands in `references/maintenance.md` (status/rev-parse/diff/log, all `-- "$SCOPE_REL"`). Keep the assembled output as the change context. In **deep** mode, use `git log --oneline -- <file>` and selective `blame`/`show` on high-signal files to explain *why* important code exists — but do not paste commit-hash lists into the docs unless a specific commit documents a decision.

## Quick reference

| Step | Action |
|---|---|
| 1 | Resolve `REPO_ROOT`, `SCOPE`, `SCOPE_REL`, `WIKI_DIR` |
| 1.5 | Load `.codewikiignore`; if missing anywhere in the chain, `apply_ignore.py suggest` and ask the user before creating one; if active, restrict discovery to `apply_ignore.py list` and filter git evidence |
| 2 | Resolve lifecycle (init/update/auto) × depth (light/deep) |
| 3 | Collect scoped git evidence |
| 4 | **update**: run the no-op check (`references/maintenance.md`) — stop if nothing changed |
| 5 | Scan the component; pick modules (light 8–10 / deep all significant); detect optional pages (testing / debugging / deployment) |
| 6 | Author/refresh Markdown from `references/templates.md` (update = surgical) |
| 7 | Build HTML: `python3 "${CLAUDE_SKILL_DIR:-.}/scripts/build_html_wiki.py" "$WIKI_DIR" --title "<component>" --subtitle "<repo ▸ scope>"` |
| 8 | Verify; write `WIKI_DIR/.codewiki-state.json` (content hash); report / `present_files` |

## Procedure

### Scan (init) — step 5
Within `SCOPE` only: `ls`, a depth-3 `find`, read manifests and the component README. Skip vendored/generated code and sibling components. Pick modules by import-count (via `rg`), size, README prominence. State the module list before writing on a big component.

**Optional-page detection.** In the same scan, check for the signal artifacts below; each optional page is authored **only when its artifacts exist** (templates and thin-page rule in `references/templates.md`):

- **`testing.md`** — `tests/`, `__tests__/`, `*_test.*`/`*.test.*`/`test_*.py`, `conftest.py`, runner configs (`pytest.ini`, `jest.config.*`, `vitest.config.*`, Go test conventions), `fixtures/`, CI test jobs.
- **`debugging.md`** — `scripts/debug*`, logging config, `DEBUG`/verbosity env flags read in code, dev-server commands, debug endpoints, profiler configs, `.vscode/launch.json`.
- **`deployment.md`** — `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `Dockerfile`/`docker-compose*`, `k8s`/`helm`/`terraform` dirs, `Procfile`, deploy/release scripts.

**CI scope exception (component scans).** CI/deploy configs usually live at `REPO_ROOT`, outside `SCOPE`. For `deployment.md` only, you may read root-level CI/deploy configs read-only and summarize **only the parts that reference the component** (path filters matching `SCOPE_REL`, jobs that build/test/deploy it). They must still pass `apply_ignore.py check`, and each file read this way is recorded in the state file's `external_ci_files`. Nothing else outside `SCOPE` becomes documentable.

### Author (init) or refresh (update) — step 6
Follow `references/templates.md` for each page. **Read source with `view` before writing about it**; verify every claim and diagram node against real code. Write `README.md`, `architecture.md`, `getting-started.md`, `modules/<name>.md`, `diagrams/class-diagram.md`, `diagrams/sequences.md`, and `api.md` per the depth rules, all under `WIKI_DIR` — plus, **only when detected in step 5**, the optional pages `testing.md`, `debugging.md`, and `deployment.md`.

For **update**: run the no-op check first (stop if clean). Otherwise be **surgical** — regenerate only the module pages whose owned source files changed, touch `README`/`architecture` only if the module set or entrypoints changed, preserve accurate prose, and avoid formatting-only churn. Full mechanics in `references/maintenance.md`.

### Build, state, report — steps 7–8
Always rebuild `index.html` from the Markdown (it is derived). Write the state file with the recomputed `content_hash` — on a no-op, do not rewrite it. In the sandbox, `present_files` (lead with `index.html`).

## Secrets and privacy

Never read or document secret values: `.env`, credentials, private keys, tokens. `.env.example`/sample config may be read only if it holds placeholders. If a secret-bearing file is relevant, note only that such configuration exists and where non-sensitive setup belongs — never its contents.

## Subagents for a large component (Claude Code)

When a component is large with several substantial, independent sub-areas, use the Task tool to parallelize **read-only** research: 1–2 subagents by default (3–4 only if the sub-areas are clearly independent). Each gets a narrow brief (e.g. data layer, API surface, integrations) and returns source-grounded findings with paths; the main agent synthesizes and does **all** writes. Subagents never write to `WIKI_DIR`. (No subagents in the single-agent sandbox — proceed directly.)

## Scope control

A full deep wiki for a big component is expensive. Scan to depth 3; skip vendored/generated code (`vendor/`, `third_party/`, `*_pb2.py`, `*.min.js`, lockfiles, build output) and sibling components. For a large component in deep mode, ballpark the cost first and confirm.

## Pitfalls

- **Documenting outside the scope.** Stay under `SCOPE`; sibling monorepo packages are external deps, not content.
- **Unfiltered git in a monorepo.** Always `-- "$SCOPE_REL"`, or the history/diff is dominated by unrelated packages.
- **Skipping the no-op check on update.** Re-running should touch nothing when nothing changed.
- **Non-surgical updates.** Don't rewrite accurate pages or make formatting-only edits.
- **Fabricating components.** Every node/call must exist in source — `view` before writing.
- **Force-fitting a class diagram** onto function-oriented code; document real classes + an import graph instead.
- **Fabricating a testing/debugging/deployment page** when no artifacts exist — detect first (step 5), skip silently when absent; fold 1–2 trivial facts into `getting-started.md` instead of a thin page.
- **Documenting unrelated root CI jobs.** The CI scope exception covers only jobs/path-filters that touch `SCOPE_REL` — not the whole root pipeline.
- **Mermaid:** quote labels with slashes/parens (`A["a / b"]`); `<br>` for line breaks; generics render `~T~`; no `%%{init}%%` blocks (the build script escapes `<>&` inside diagrams for you).
- **Reading secrets.** Never open `.env` or credential files.
- **Touching an ignored path.** When `.codewikiignore` is active, never read/shell/describe a path outside `apply_ignore.py list` — `check` it first if unsure.
- **Writing `.codewikiignore` without asking.** `apply_ignore.py suggest` only prints a candidate; never save it to disk before the user has confirmed (or edited) it.

## Verification

Loop **per file** so failures name the offender:

```bash
# 1. Balanced fences in every Markdown file
for f in "$WIKI_DIR"/*.md "$WIKI_DIR"/diagrams/*.md "$WIKI_DIR"/modules/*.md; do
  [ -f "$f" ] || continue; t=$(grep -c '^```' "$f")
  [ $((t % 2)) -eq 0 ] || echo "UNBALANCED FENCES: $f ($t)"
done
# 2. Core files exist
for f in README.md architecture.md getting-started.md .codewiki-state.json; do
  [ -f "$WIKI_DIR/$f" ] || echo "MISSING: $f"; done
# 3. Module count matches step 5
echo "modules: $(ls "$WIKI_DIR/modules" 2>/dev/null | wc -l)"
# 3b. Optional pages present match detection (absence is fine)
for f in testing.md debugging.md deployment.md; do
  [ -f "$WIKI_DIR/$f" ] && echo "optional page: $f"; done
# 4. HTML built with expected diagram count
[ -f "$WIKI_DIR/index.html" ] && echo "mermaid in html: $(grep -c '<pre class=\"mermaid\">' "$WIKI_DIR/index.html")"
# 5. State scope is correct and git evidence stayed scoped
grep -o '"scope": *"[^"]*"' "$WIKI_DIR/.codewiki-state.json"
```

Spot-check 2–3 referenced source paths resolve, and confirm no path outside `SCOPE` was documented.

## Bundled resources

- `scripts/build_html_wiki.py` — stdlib-only builder → one self-contained `index.html` with a **3-level sidebar** (group → page → the page's `##` subsections, auto-expanding), `--title`/`--subtitle` (subtitle shows the `repo ▸ component` path), active-link highlighting, a filter box, dark-mode, and Mermaid.
- `scripts/apply_ignore.py` — stdlib matcher for `.codewikiignore` (gitignore syntax). `active` (is it on?), `list` (allowed files under a scope), `check` (is a path ignored?), `deny-rules` (Read/Bash deny entries for `.claude/settings.json`), `suggest` (scan for vendor/build/generated paths and print a candidate ignore file when none exists yet — never written without user confirmation). The single source of truth for what the wiki may touch.
- `references/templates.md` — per-document Markdown templates and depth notes. Read before authoring.
- `references/maintenance.md` — scope resolution, scoped git, the init/update lifecycle, the no-op check, surgical-update mechanics, and the state-file schema. Read before Step 1.
