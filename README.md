# code-wiki

A Claude skill that **generates and maintains a browsable wiki for a codebase** — or for a single component inside a large monorepo. It writes interlinked Markdown (an overview, architecture, per-module deep-dives, and Mermaid class + sequence diagrams) and assembles it into a single self-contained `index.html` with a three-level sidebar.

It produces *reference* documentation — what the code is and how it works (plus short git-grounded *why* notes in deep mode) — not product-strategy narrative.

## What you get

- **A self-contained HTML site** (`wiki/index.html`): left sidebar with three levels (section → page → the page's subsections), active-link highlighting, a filter box, and dark mode. No server needed — open it with a double-click.
- **Mermaid diagrams**: an architecture flowchart, a class diagram, and sequence diagrams, rendered in the browser.
- **The Markdown source alongside it**, so the same wiki also renders on GitHub and re-runs stay cheap.

## Install (Claude Code)

Skills are loaded from the filesystem — no upload step. Clone (or copy) this repo into a `code-wiki` folder under your skills directory:

```bash
# Personal (available in all your projects)
git clone https://github.com/JiaweiHan88/code-wiki-cc ~/.claude/skills/code-wiki

# …or project-scoped (committed to one repo, shared with the team)
git clone https://github.com/JiaweiHan88/code-wiki-cc .claude/skills/code-wiki
```

Already have the folder locally? Just copy it into place:

```bash
cp -R code-wiki ~/.claude/skills/          # personal
cp -R code-wiki .claude/skills/            # project-scoped
```

You should end up with `~/.claude/skills/code-wiki/SKILL.md`. Then start a **new** Claude Code session — the skill is discovered automatically. Type `/` in a session to see loaded skills.

For Claude.ai, upload the folder as a skill in Settings › Features (Pro/Max/Team/Enterprise with code execution enabled).

## Usage

Just describe what you want; the skill triggers on natural language:

- "Generate a wiki for this codebase."
- "Document the `packages/api` component in depth."
- "Update the wiki." (refreshes only what changed)
- "Draw me an architecture diagram of this repo as a wiki."

If you don't signal a depth it will ask. Two independent dials:

| Dial | Options | Meaning |
|---|---|---|
| Lifecycle | `init` · `update` · `auto` | Create from scratch · surgically refresh from git changes · pick automatically |
| Depth | `light` · `deep` | Top 8–10 modules and core diagrams · every significant module with function-level walkthroughs, more diagrams, `why` notes, and an API reference |

`update` is idempotent: if nothing relevant changed since the last run, it does nothing and says so.

## Monorepo components

Point it at one folder and it documents only that component. Git is repository-wide, so all git evidence (history, change detection) is **path-filtered to the folder** — a change in a sibling package won't touch this component's wiki. The output lives inside the component at `<component>/wiki/`, and the sidebar shows the `repo ▸ component` path.

## Keeping paths out: `.codewikiignore`

Add a `.codewikiignore` at the repository root to keep private, generated, or irrelevant paths out of the run entirely — they are never read, shelled to, described, or treated as changes. Gitignore syntax: `#` comments, blank lines, `*`/`**`/`?` globs, directory rules, and `!` negation.

```gitignore
# private / generated paths
secrets/
*.log
!logs/keep.log
```

**Nests like real `.gitignore`.** A component can keep its own ignore file for rules only it needs, without touching the root:

```
monorepo/
├── .codewikiignore              # applies everywhere, e.g. "*.log"
└── packages/
    ├── api/
    │   ├── .codewikiignore      # applies only inside packages/api/, patterns relative to it
    │   └── secrets/             # -> ignored by packages/api/.codewikiignore's "secrets/"
    └── web/
        └── secrets/             # NOT ignored — api's rule doesn't leak to sibling packages
```

A closer file wins for whatever it has an opinion on (it can even `!`-re-include something the root ignored); where it's silent, the parent file's verdict stands. This mirrors how nested `.gitignore` files actually work in git.

## Files

```
code-wiki/
├── SKILL.md                     # the skill: workflow, modes, scope, safety rules
├── references/
│   ├── templates.md             # per-document Markdown templates + depth notes
│   └── maintenance.md           # scope resolution, init/update lifecycle, no-op, state schema
└── scripts/
    ├── build_html_wiki.py       # Markdown sections → one self-contained index.html
    └── apply_ignore.py          # .codewikiignore matcher (discovery filter + deny-rule generator)
```

## Requirements

- **Python 3** — both scripts are **standard-library only** (no `pip`, no network to build).
- **git** (optional but recommended) — enables history/"why" notes and change-scoped updates; without it the skill degrades to filesystem inspection.
- **A browser with internet** for the diagrams — Mermaid loads from a CDN. For fully offline viewing, vendor `mermaid.min.js` into the wiki folder and pass `--mermaid-src ./mermaid.min.js` to the build script.

## Using the scripts directly

The skill runs these for you, but they work standalone:

```bash
# Build the HTML site from a folder of wiki Markdown
python3 scripts/build_html_wiki.py path/to/wiki --title "my-project" --subtitle "monorepo ▸ packages/api"

# See what an ignore file allows / blocks (root + any nested component files)
python3 scripts/apply_ignore.py list  /path/to/repo --scope packages/api
python3 scripts/apply_ignore.py check /path/to/repo packages/api/secrets/key.pem
python3 scripts/apply_ignore.py deny-rules /path/to/repo --scope packages/api   # entries for .claude/settings.json
```

## Safety

Three stacked layers keep the wiki off things it shouldn't touch: **scope** (only files under the target component), the **ignore list** (`.codewikiignore`), and a built-in **secrets rule** (never read `.env` or credential files). The skill grounds every claim and diagram node in real source — it reads before it writes and does not invent components.
