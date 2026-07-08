# Lifecycle, scope, and idempotence

This file holds the exact mechanics for scoping to a monorepo component, the `init`/`update`
lifecycle, the no-op skip, surgical updates, and the state file. `SKILL.md` references it.

## Scope: one component inside a (possibly monorepo) repo

Git is repository-wide, but a wiki targets **one folder**. Three variables:

- `REPO_ROOT` — `git rev-parse --show-toplevel` (where `.git` lives; the whole monorepo).
- `SCOPE` — the component folder to document (absolute). Whole-repo runs use `SCOPE=REPO_ROOT`.
- `SCOPE_REL` — `SCOPE` relative to `REPO_ROOT` (e.g. `packages/api`; `.` for whole-repo).

Rules:
- Document **only** files under `SCOPE`. Siblings in the monorepo are out of scope; if the
  component imports from a sibling, note it as an external dependency (by path) — don't document it.
- The wiki is written **inside the component**: `WIKI_DIR = SCOPE/wiki` (repo-relative `WIKI_REL`).
  Each component gets its own self-contained wiki; nothing is written at the monorepo root.
- **Every git command runs at the repo root but is path-filtered to the component** — this is the
  whole point: "git touches the monorepo, we only need the folder."

```bash
REPO_ROOT=$(git -C . rev-parse --show-toplevel 2>/dev/null || pwd)
SCOPE=$(cd "$TARGET_FOLDER" && pwd)                 # TARGET_FOLDER defaults to cwd
SCOPE_REL=$(realpath --relative-to="$REPO_ROOT" "$SCOPE")   # "." means whole repo
WIKI_DIR="$SCOPE/wiki"; WIKI_REL="${SCOPE_REL%/}/wiki"; WIKI_REL="${WIKI_REL#./}"
```

## Scoped git evidence (init and update)

All read-only, all path-filtered to `SCOPE_REL` so a huge monorepo history stays relevant:

```bash
git -C "$REPO_ROOT" --no-pager rev-parse HEAD
git -C "$REPO_ROOT" --no-pager status --short -- "$SCOPE_REL"
git -C "$REPO_ROOT" --no-pager diff --name-status HEAD -- "$SCOPE_REL"
# history:
#   init (or update w/o prior gitHead):
git -C "$REPO_ROOT" --no-pager log -n 20 --oneline -- "$SCOPE_REL"
#   update with a recorded gitHead:
git -C "$REPO_ROOT" --no-pager log "$GITHEAD"..HEAD --name-status --oneline -- "$SCOPE_REL"
```

Not a git repo → degrade gracefully: use filesystem timestamps + source inspection.

## Lifecycle: init | update | auto

- **auto** (default when unspecified): if `WIKI_DIR/.codewiki-state.json` exists → `update`, else `init`.
  `test -f "$WIKI_DIR/.codewiki-state.json" && echo update || echo init`
- **init** — build the wiki for the component from scratch (see `SKILL.md` steps).
- **update** — maintain an existing component wiki (below). Depth defaults to the recorded `depth`
  unless the user overrides.

## Update: no-op check (run first, update mode, no extra instruction)

Read `WIKI_DIR/.codewiki-state.json` for `gitHead` and `content_hash`. Compute:

```bash
DIRTY=$(git -C "$REPO_ROOT" --no-pager status --short -- "$SCOPE_REL" | grep -v " $WIKI_REL/")
HEAD=$(git -C "$REPO_ROOT" --no-pager rev-parse HEAD)
CHANGED=""; [ "$HEAD" != "$GITHEAD" ] && \
  CHANGED=$(git -C "$REPO_ROOT" --no-pager diff --name-only "$GITHEAD"..HEAD -- "$SCOPE_REL" | grep -v "^$WIKI_REL/")
HASH=$(find "$WIKI_DIR" -type f -not -name .codewiki-state.json -not -name index.html -print0 \
        2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum)
```

**External CI files.** If the state file records `external_ci_files` (root-level CI/deploy configs
documented under the CI scope exception — see `SKILL.md` step 5), also diff those exact paths;
they sit outside `SCOPE_REL`, so the scoped diff above misses them:

```bash
CI_CHANGED=""
[ "$HEAD" != "$GITHEAD" ] && [ -n "$EXTERNAL_CI_FILES" ] && \
  CI_CHANGED=$(git -C "$REPO_ROOT" --no-pager diff --name-only "$GITHEAD"..HEAD -- $EXTERNAL_CI_FILES)
```

Any hit in `CI_CHANGED` defeats the no-op and marks `deployment.md` affected.

**No-op** (skip the whole run, touch nothing) when all hold: `DIRTY` empty, `CHANGED` empty,
`CI_CHANGED` empty, and `HASH` equals the recorded `content_hash`. Report: `wiki already current —
no changes under <SCOPE_REL> since <gitHead>` and stop. Otherwise proceed to a surgical update.

**When `.codewikiignore` is active**, drop ignored paths from both `DIRTY` and `CHANGED` before
judging no-op or building the impact list — a change under an ignored path (e.g. `secrets/`,
generated output) must never trigger an update or be documented. Filter with the bundled matcher:

```bash
CHANGED=$(printf '%s\n' $CHANGED | while read -r p; do \
  python3 "${CLAUDE_SKILL_DIR:-.}/scripts/apply_ignore.py" check "$REPO_ROOT" "$p" \
  | grep -q '^OK ' && echo "$p"; done)
```

## Update: surgical regeneration

1. Collect changed source files = `CHANGED` ∪ (uncommitted paths from `DIRTY`), all under `SCOPE_REL`.
2. Map each changed file to the module page that owns it (a module page's **Key Files** define its
   source set). Build a small impact list: `changed file → affected page → why`.
   Optional pages own their signal files too (in addition to any module page): changed test
   files/runner configs/fixtures → `testing.md`; changed debug scripts/logging config → `debugging.md`;
   changed CI/deploy files (including any hit in `CI_CHANGED`) → `deployment.md`. If the change set
   introduces **new** signal files for an optional page not yet in `optional_pages`, re-run detection
   for that page and author it if warranted.
3. Regenerate **only** affected module pages. Regenerate `README.md`/`architecture.md` only if the
   set of modules or the entrypoints changed. Preserve accurate pages verbatim — prefer replacing a
   stale sentence over rewriting a page. No formatting-only churn.
4. Rebuild `index.html` (the HTML is always fully regenerated from the Markdown — it is derived).
5. Recompute the content hash and write state only if content actually changed.

## State file — `WIKI_DIR/.codewiki-state.json`

```json
{
  "repo_root": "/abs/path/to/monorepo",
  "scope": "packages/api",
  "wiki_dir": "packages/api/wiki",
  "depth": "light | deep",
  "gitHead": "<git rev-parse HEAD, or 'uncommitted'>",
  "updatedAt": "<UTC ISO 8601, e.g. 2026-07-08T12:34:56Z>",
  "generator": "claude code-wiki skill",
  "content_hash": "<sha256 over wiki files, excluding state + index.html>",
  "modules_documented": ["<module>", "..."],
  "optional_pages": ["testing", "deployment"],
  "external_ci_files": [".github/workflows/ci.yml"]
}
```

`optional_pages` lists which of `testing`/`debugging`/`deployment` were generated (update mode
maintains these; re-detect only when new signal files appear in the change set). `external_ci_files`
lists repo-root CI/deploy configs documented under the CI scope exception — repo-relative paths,
used by the no-op check above. Both are `[]` when not applicable.

Get `updatedAt` and `gitHead` from the shell (`date -u +%Y-%m-%dT%H:%M:%SZ`, `git rev-parse HEAD`),
never guessed. On a no-op, do **not** rewrite this file.
