#!/usr/bin/env python3
"""Apply `.codewikiignore` files so the code-wiki skill never
reads, describes, or shells out to private / generated / irrelevant paths.

Gitignore-style syntax: `#` comments, blank lines, `*`/`**`/`?` globs, directory rules
(`dir/`), and `!` negation. Last matching rule wins.

Nested like real .gitignore: a file at the repo ROOT applies everywhere; a file inside a
subfolder applies only within that subfolder, with its patterns relative to ITS OWN
directory (not the repo root), and can override (including re-include via `!`) whatever a
parent-directory file said -- but only for paths it actually has a rule about. No matching
rule in the nested file leaves the parent's verdict standing.

This module is the single source of truth for "may the wiki touch this path?", used to
filter filesystem discovery and to derive shell/read deny rules.

Actions:
  active ROOT              exit 0 if any ignore file (root or nested) has >=1 active rule
  list ROOT [--scope P]    print allowed (non-ignored) files under ROOT (or ROOT/P)
  check ROOT PATH...       print "IGNORED <p>" / "OK <p>" per PATH; exit 1 if any ignored
  deny-rules ROOT [--scope P]   print suggested Claude Code deny entries (Read/Bash)
  suggest ROOT [--scope P]      scan for vendor/build/generated paths and print a candidate
                                .codewikiignore body (not written to disk) for the caller to
                                review with the user before creating the file

Always-skipped noise (independent of ignore files): .git, node_modules, .venv, venv,
__pycache__, dist, build, target, .mypy_cache, .pytest_cache.
"""
import argparse
import datetime
import os
import re
from pathlib import Path

IGNORE_NAMES = (".codewikiignore",)
ALWAYS_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__",
               "dist", "build", "target", ".mypy_cache", ".pytest_cache"}

# Heuristics for `suggest`. Grouped so the proposed file reads as reasoned
# categories, not a flat dump. A directory name here only becomes a suggested
# rule if it is actually found in the scanned tree.
SUGGEST_VENDOR_DIRS = {
    "node_modules": "JS/TS dependency tree", "vendor": "vendored dependencies",
    "third_party": "vendored dependencies", "bower_components": "legacy JS dependencies",
    "Pods": "CocoaPods dependencies", ".venv": "Python virtualenv", "venv": "Python virtualenv",
    "env": "Python virtualenv", "virtualenv": "Python virtualenv", ".tox": "tox environments",
    "site-packages": "installed Python packages",
}
SUGGEST_BUILD_DIRS = {
    "dist": "build output", "build": "build output", "out": "build output",
    "bin": "compiled output", "obj": "compiled output", ".next": "Next.js build cache",
    ".nuxt": "Nuxt build cache", ".output": "build output", ".svelte-kit": "SvelteKit build cache",
    "target": "Rust/JVM build output", ".gradle": "Gradle cache", ".turbo": "Turborepo cache",
    ".parcel-cache": "Parcel cache", "coverage": "test coverage reports",
    ".nyc_output": "test coverage reports", "DerivedData": "Xcode build output",
    ".angular": "Angular build cache",
}
SUGGEST_TOOLING_DIRS = {
    "__pycache__": "Python bytecode cache", ".mypy_cache": "mypy cache",
    ".pytest_cache": "pytest cache", ".cache": "generic cache", ".idea": "IDE settings",
    ".vs": "IDE settings",
}
SUGGEST_GENERATED_DIR_NAMES = {"generated": "generated code", "gen": "generated code",
                                "__generated__": "generated code", "autogen": "generated code"}
SUGGEST_REVIEW_DIRS = {"__snapshots__": "test snapshot fixtures", "fixtures": "test fixtures",
                        "testdata": "test fixtures", "cassettes": "recorded HTTP fixtures"}

SUGGEST_LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock", "Gemfile.lock",
    "poetry.lock", "Pipfile.lock", "composer.lock", "go.sum", "mix.lock",
}
SUGGEST_GENERATED_GLOBS = [
    ("*.min.js", lambda n: n.endswith(".min.js")),
    ("*.min.css", lambda n: n.endswith(".min.css")),
    ("*_pb2.py", lambda n: n.endswith("_pb2.py")),
    ("*_pb2_grpc.py", lambda n: n.endswith("_pb2_grpc.py")),
    ("*.pb.go", lambda n: n.endswith(".pb.go")),
    ("*.g.dart", lambda n: n.endswith(".g.dart")),
    ("*.designer.cs", lambda n: n.endswith(".designer.cs")),
]
SUGGEST_BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".mp4", ".mov",
                        ".zip", ".tar", ".gz", ".pdf", ".woff", ".woff2", ".ttf", ".otf",
                        ".bin", ".dylib", ".so", ".dll", ".exe", ".class", ".jar", ".wasm"}
SUGGEST_BINARY_DIR_THRESHOLD = 15  # binary files in one dir before flagging it for review


def _translate(pat: str) -> str:
    """Translate a gitignore glob body into a regex body (no anchors)."""
    out, i, n = [], 0, len(pat)
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i:i + 3] == "**/":
                out.append(r"(?:.*/)?"); i += 3; continue
            if pat[i:i + 2] == "**":
                out.append(r".*"); i += 2; continue
            out.append(r"[^/]*"); i += 1; continue
        if c == "?":
            out.append(r"[^/]"); i += 1; continue
        out.append(re.escape(c)); i += 1
    return "".join(out)


class IgnoreFile:
    """Rules from a single ignore file, matched relative to the directory it lives in."""

    def __init__(self, lines, dir_path: Path):
        self.dir_path = dir_path
        self.rules = []        # (compiled_regex, negate, dir_only)
        self.raw_patterns = [] # (pattern_text, negate, dir_only) for deny-rule derivation
        for raw in lines:
            line = raw.rstrip("\n").rstrip()
            if not line or line.startswith("#"):
                continue
            negate = line.startswith("!")
            if negate:
                line = line[1:]
            dir_only = line.endswith("/")
            if dir_only:
                line = line[:-1]
            if not line:
                continue
            anchored = "/" in line
            if line.startswith("/"):
                line = line[1:]
            body = _translate(line)
            prefix = "^" if anchored else r"(?:^|.*/)"
            self.rules.append((re.compile(prefix + body + r"(?:/.*)?$"), negate, dir_only))
            self.raw_patterns.append((line, negate, dir_only))

    def verdict(self, sub_rel: str, as_dir: bool):
        """Return True/False if this file has an opinion on sub_rel (path relative to
        this file's own directory), or None if no rule matched (parent verdict stands)."""
        parts = [p for p in sub_rel.split("/") if p]
        if not parts:
            return None
        matched, ignored = False, None
        for k in range(1, len(parts) + 1):
            prefix = "/".join(parts[:k])
            is_last = k == len(parts)
            final_is_dir = as_dir if is_last else True
            for rx, negate, dir_only in self.rules:
                if dir_only and is_last and not final_is_dir:
                    continue  # a `dir/` rule must not match a file of the same name
                if rx.match(prefix):
                    matched = True
                    ignored = not negate
        return ignored if matched else None

    def has_negation(self) -> bool:
        return any(neg for _, neg, _ in self.rules)


def discover(root: Path) -> dict:
    """Find every ignore file under root (pruning noise dirs). Returns {abs_dir_str: IgnoreFile}."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ALWAYS_SKIP]
        for name in IGNORE_NAMES:
            fp = Path(dirpath) / name
            if fp.is_file():
                lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
                found[os.path.normpath(dirpath)] = IgnoreFile(lines, Path(dirpath))
                break
    return found


def chain_for(root: Path, target_dir: Path, layers: dict):
    """Ordered list of IgnoreFile layers from root down to target_dir (inclusive)."""
    try:
        rel_parts = target_dir.resolve().relative_to(root.resolve()).parts
    except ValueError:
        rel_parts = ()
    cur = root.resolve()
    chain = []
    for d in (cur, *[cur.joinpath(*rel_parts[:i + 1]) for i in range(len(rel_parts))]):
        layer = layers.get(os.path.normpath(str(d)))
        if layer is not None:
            chain.append(layer)
    return chain


def is_ignored(root: Path, rel_path: str, layers: dict, as_dir: bool = False) -> bool:
    full = root.resolve() / rel_path
    target_dir = full if as_dir else full.parent
    result = False
    for layer in chain_for(root, target_dir, layers):
        sub_rel = os.path.relpath(str(full), str(layer.dir_path.resolve())).replace(os.sep, "/")
        v = layer.verdict(sub_rel, as_dir)
        if v is not None:
            result = v
    return result


def any_negation(layers: dict) -> bool:
    return any(layer.has_negation() for layer in layers.values())


def walk_allowed(root: Path, scope: Path, layers: dict):
    """Yield allowed file paths (relative to root, posix) under scope."""
    neg = any_negation(layers)
    for dirpath, dirnames, filenames in os.walk(scope):
        d = Path(dirpath)
        kept = []
        for name in dirnames:
            if name in ALWAYS_SKIP:
                continue
            sub = d / name
            # Prune an ignored directory only when no ignore file anywhere uses negation
            # (a descendant `!` could otherwise re-include something under it).
            rel = os.path.relpath(str(sub), str(root.resolve())).replace(os.sep, "/")
            if is_ignored(root, rel, layers, as_dir=True) and not neg:
                continue
            kept.append(name)
        dirnames[:] = kept
        for fn in filenames:
            if fn in IGNORE_NAMES:
                continue
            full = d / fn
            rel = os.path.relpath(str(full), str(root.resolve())).replace(os.sep, "/")
            if not is_ignored(root, rel, layers):
                yield rel


def suggest_ignore(root: Path, scope: Path) -> str:
    """Scan `scope` for vendor/build/generated paths and render a candidate
    .codewikiignore body. Pure read-only scan; caller decides whether to write it."""
    recommended = {cat: {} for cat in ("vendor", "build", "tooling", "generated_dir")}
    lockfiles_found = {}        # filename -> example_rel_path
    generated_globs_found = {}  # glob -> (count, example_rel_path)
    review_dirs = {}            # rel_path -> reason
    binary_heavy_dirs = {}      # rel_path -> count

    for dirpath, dirnames, filenames in os.walk(scope):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        keep = []
        binary_count = 0
        for d in list(dirnames):
            rd = f"{rel_dir}/{d}" if rel_dir else d
            if d in ALWAYS_SKIP:
                continue  # already always excluded, no need to suggest it
            matched = False
            for table, cat in ((SUGGEST_VENDOR_DIRS, "vendor"), (SUGGEST_BUILD_DIRS, "build"),
                                (SUGGEST_TOOLING_DIRS, "tooling"),
                                (SUGGEST_GENERATED_DIR_NAMES, "generated_dir")):
                if d in table:
                    recommended[cat].setdefault(d, rd)
                    matched = True
                    break  # don't descend into a dir we're about to suggest excluding
            if matched:
                continue
            if d in SUGGEST_REVIEW_DIRS:
                review_dirs.setdefault(rd, SUGGEST_REVIEW_DIRS[d])
                continue
            keep.append(d)
        dirnames[:] = keep

        for fn in filenames:
            if fn in IGNORE_NAMES:
                continue
            rf = f"{rel_dir}/{fn}" if rel_dir else fn
            if fn in SUGGEST_LOCKFILES:
                lockfiles_found.setdefault(fn, rf)
            for glob, pred in SUGGEST_GENERATED_GLOBS:
                if pred(fn):
                    count, example = generated_globs_found.get(glob, (0, rf))
                    generated_globs_found[glob] = (count + 1, example)
            if os.path.splitext(fn)[1].lower() in SUGGEST_BINARY_EXTS:
                binary_count += 1
        if binary_count >= SUGGEST_BINARY_DIR_THRESHOLD:
            binary_heavy_dirs[rel_dir or "."] = binary_count

    lines = [
        f"# Suggested by code-wiki's directory scan on {datetime.date.today().isoformat()}.",
        "# This file was NOT created automatically — review, edit, then save it as",
        "# .codewikiignore at the repository root (or inside a component for a nested rule).",
        "# Gitignore syntax: '#' comments, blank lines, */**/? globs, 'dir/' rules, '!' negation.",
    ]

    def emit_section(title, items_dict, reason_table):
        if not items_dict:
            return
        lines.append("")
        lines.append(f"# {title}")
        for name in sorted(items_dict):
            reason = reason_table.get(name, "")
            example = items_dict[name]
            lines.append(f"{name}/  # {reason} (e.g. {example})")

    emit_section("Dependency / vendor directories", recommended["vendor"], SUGGEST_VENDOR_DIRS)
    emit_section("Build output", recommended["build"], SUGGEST_BUILD_DIRS)
    emit_section("Tooling caches", recommended["tooling"], SUGGEST_TOOLING_DIRS)
    emit_section("Generated code directories", recommended["generated_dir"], SUGGEST_GENERATED_DIR_NAMES)

    if lockfiles_found:
        lines.append("")
        lines.append("# Lockfiles (noisy, rarely worth documenting)")
        for fn in sorted(lockfiles_found):
            lines.append(fn)

    if generated_globs_found:
        lines.append("")
        lines.append("# Generated code files")
        for glob in sorted(generated_globs_found):
            count, example = generated_globs_found[glob]
            lines.append(f"{glob}  # {count} file(s), e.g. {example}")

    if review_dirs or binary_heavy_dirs:
        lines.append("")
        lines.append("# Consider also excluding (heuristic — commented out, review before enabling):")
        for rd in sorted(review_dirs):
            lines.append(f"# {rd}/  # {review_dirs[rd]}")
        for rd in sorted(binary_heavy_dirs):
            lines.append(f"# {rd}/  # {binary_heavy_dirs[rd]} binary/media files")

    if len(lines) == 4:  # only the header — nothing found
        lines.append("")
        lines.append("# No vendor/build/generated paths were detected under this scope.")

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply nested .codewikiignore files for the code-wiki skill.")
    ap.add_argument("action", choices=["active", "list", "check", "deny-rules", "suggest"])
    ap.add_argument("root")
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--scope", default=None, help="Restrict list/deny-rules/suggest to this path (relative to root or absolute)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    layers = discover(root)

    if args.action == "active":
        return 0 if any(l.rules for l in layers.values()) else 1

    if args.action == "list":
        scope = Path(args.scope) if args.scope else root
        if not scope.is_absolute():
            scope = root / scope
        for p in sorted(walk_allowed(root, scope.resolve(), layers)):
            print(p)
        return 0

    if args.action == "suggest":
        scope = Path(args.scope) if args.scope else root
        if not scope.is_absolute():
            scope = root / scope
        print(suggest_ignore(root, scope.resolve()), end="")
        return 0

    if args.action == "check":
        any_ignored = False
        for p in args.rest:
            rel = p if not os.path.isabs(p) else os.path.relpath(p, root)
            rel = rel.replace(os.sep, "/")
            ig = is_ignored(root, rel, layers)
            any_ignored = any_ignored or ig
            print(f"{'IGNORED' if ig else 'OK'} {rel}")
        return 1 if any_ignored else 0

    if args.action == "deny-rules":
        if not any(l.rules for l in layers.values()):
            return 1
        scope = Path(args.scope) if args.scope else root
        if not scope.is_absolute():
            scope = root / scope
        scope = scope.resolve()
        seen = set()
        for dir_key, layer in sorted(layers.items()):
            layer_dir = layer.dir_path.resolve()
            # Only include layers at/under the requested scope, or ancestors of it (root rules
            # still apply to a scoped run).
            try:
                layer_dir.relative_to(scope)
                under_scope = True
            except ValueError:
                under_scope = False
            try:
                scope.relative_to(layer_dir)
                is_ancestor = True
            except ValueError:
                is_ancestor = False
            if not (under_scope or is_ancestor):
                continue
            rel_dir = os.path.relpath(str(layer_dir), str(root)).replace(os.sep, "/")
            rel_dir = "" if rel_dir == "." else rel_dir + "/"
            for pat, negate, dir_only in layer.raw_patterns:
                if negate:
                    continue  # negations re-include; not expressible as a deny
                glob = rel_dir + pat.lstrip("/")
                glob = f"{glob}/**" if dir_only else glob
                for tool in ("Read", "Bash"):
                    entry = f'"{tool}({glob})"'
                    if entry not in seen:
                        seen.add(entry)
                        print(entry)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
