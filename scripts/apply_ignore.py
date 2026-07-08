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

Always-skipped noise (independent of ignore files): .git, node_modules, .venv, venv,
__pycache__, dist, build, target, .mypy_cache, .pytest_cache.
"""
import argparse
import os
import re
from pathlib import Path

IGNORE_NAMES = (".codewikiignore",)
ALWAYS_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__",
               "dist", "build", "target", ".mypy_cache", ".pytest_cache"}


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


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply nested .codewikiignore files for the code-wiki skill.")
    ap.add_argument("action", choices=["active", "list", "check", "deny-rules"])
    ap.add_argument("root")
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--scope", default=None, help="Restrict list/deny-rules to this path (relative to root or absolute)")
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
