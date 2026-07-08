#!/usr/bin/env python3
"""Build a single self-contained index.html wiki (left sidebar nav + Mermaid diagrams)
from a directory of Markdown section files.

Stdlib only -- no pip installs, no network needed to *build*. Mermaid is loaded in
the browser from a CDN by default; pass --mermaid-src to point at a local copy for
fully offline viewing.

The sidebar has up to three levels: group (e.g. "Modules") -> page (e.g. a module)
-> the page's own "##" subsections, which auto-expand for the page you're viewing.

Expected content layout (any missing file is simply skipped):
    <dir>/README.md            -> "Overview"
    <dir>/architecture.md      -> "Architecture"
    <dir>/getting-started.md   -> "Getting Started"
    <dir>/modules/*.md         -> "Modules" group (one entry each)
    <dir>/diagrams/class-diagram.md, sequences.md -> "Diagrams" group
    <dir>/api.md               -> "API"

Usage:
    python build_html_wiki.py <content-dir> --title "My Project" [--out <dir>/index.html]
                              [--mermaid-src ./mermaid.min.js]
"""
import argparse
import html
import re
import sys
from pathlib import Path

SECTION_ANCHORS = {
    "README.md": "overview",
    "architecture.md": "architecture",
    "getting-started.md": "getting-started",
    "class-diagram.md": "class-diagram",
    "sequences.md": "sequences",
    "api.md": "api",
}
SECTION_LABELS = {
    "class-diagram": "Class Diagram",
    "sequences": "Sequence Diagrams",
    "api": "API Reference",
}


def slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"[\s_]+", "-", s) or "section"


# ---------------------------------------------------------------------------
# Inline markdown
# ---------------------------------------------------------------------------
def _remap_link(url: str, module_names: set) -> str:
    if url.startswith("#") or url.startswith(("http://", "https://", "mailto:")):
        return url
    frag = ""
    if "#" in url:
        url, frag = url.split("#", 1)
    if not url.endswith(".md"):
        return url + (f"#{frag}" if frag else "")
    base = url.rsplit("/", 1)[-1]
    if base in SECTION_ANCHORS:
        return "#" + SECTION_ANCHORS[base]
    name = base[:-3]
    if name in module_names:
        return "#module-" + name
    return "#" + slug(name)


def inline(text: str, module_names: set) -> str:
    codes = []

    def _stash(m):
        codes.append(m.group(1))
        return f"\x00C{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _stash, text)
    text = html.escape(text, quote=False)

    def _link(m):
        label, url = m.group(1), _remap_link(m.group(2), module_names)
        return f'<a href="{html.escape(url, quote=True)}">{label}</a>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\x00C(\d+)\x00", lambda m: f"<code>{html.escape(codes[int(m.group(1))], quote=False)}</code>", text)
    return text


# ---------------------------------------------------------------------------
# Block markdown -> HTML. Returns (html, subheadings) where subheadings are the
# page's "##" headings (id + label), used to build the third nav level.
# ---------------------------------------------------------------------------
def md_to_html(md: str, module_names: set, section_id: str):
    lines = md.replace("\r\n", "\n").split("\n")
    out, subs, seen = [], [], {}
    i, n = 0, len(lines)
    para = []

    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(para).strip(), module_names) + "</p>")
            para.clear()

    while i < n:
        line = lines[i]

        fence = re.match(r"^(`{3,})\s*([\w-]*)\s*$", line)
        if fence:
            flush_para()
            marker, lang = fence.group(1), fence.group(2).lower()
            i += 1
            body = []
            while i < n and not re.match(rf"^`{{{len(marker)},}}\s*$", lines[i]):
                body.append(lines[i])
                i += 1
            i += 1
            code = html.escape("\n".join(body), quote=False)
            if lang == "mermaid":
                out.append(f'<pre class="mermaid">{code}</pre>')
            else:
                cls = f' class="language-{lang}"' if lang else ""
                out.append(f"<pre><code{cls}>{code}</code></pre>")
            continue

        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            flush_para()
            level = len(h.group(1))
            text = h.group(2).strip()
            if level == 2:
                base = f"{section_id}--{slug(text)}"
                if base in seen:
                    seen[base] += 1
                    hid = f"{base}-{seen[base]}"
                else:
                    seen[base] = 0
                    hid = base
                subs.append({"id": hid, "label": re.sub(r"`", "", text)})
                out.append(f'<h2 id="{hid}">{inline(text, module_names)}</h2>')
            else:
                out.append(f"<h{level}>{inline(text, module_names)}</h{level}>")
            i += 1
            continue

        if "|" in line and i + 1 < n and re.match(r"^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$", lines[i + 1]) and "|" in lines[i + 1]:
            flush_para()

            def cells(row):
                row = row.strip()
                row = row[1:] if row.startswith("|") else row
                row = row[:-1] if row.endswith("|") else row
                return [c.strip() for c in row.split("|")]

            header = cells(line)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(cells(lines[i]))
                i += 1
            thead = "".join(f"<th>{inline(c, module_names)}</th>" for c in header)
            tbody = "".join("<tr>" + "".join(f"<td>{inline(c, module_names)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>")
            continue

        if re.match(r"^>\s?", line):
            flush_para()
            quote = []
            while i < n and re.match(r"^>\s?", lines[i]):
                quote.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>" + inline(" ".join(quote).strip(), module_names) + "</blockquote>")
            continue

        lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if lm:
            flush_para()
            ordered = bool(re.match(r"\d+\.", lm.group(2)))
            tag = "ol" if ordered else "ul"
            items = []
            while i < n:
                m2 = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if not m2:
                    break
                items.append(inline(m2.group(3).strip(), module_names))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{it}</li>" for it in items) + f"</{tag}>")
            continue

        if not line.strip():
            flush_para()
            i += 1
            continue

        para.append(line)
        i += 1

    flush_para()
    return "\n".join(out), subs


# ---------------------------------------------------------------------------
# Section discovery
# ---------------------------------------------------------------------------
def first_heading(md: str, fallback: str) -> str:
    for ln in md.split("\n"):
        m = re.match(r"^#\s+(.*)$", ln)
        if m:
            t = m.group(1).strip()
            b = re.search(r"`([^`]+)`", t)
            return b.group(1) if b else t
    return fallback


def discover(content: Path):
    module_files = sorted((content / "modules").glob("*.md")) if (content / "modules").is_dir() else []
    module_names = {p.stem for p in module_files}
    sections = []

    def add(path: Path, sid: str, label: str, group):
        if path.is_file():
            sections.append({"id": sid, "label": label, "group": group, "md": path.read_text(encoding="utf-8")})

    add(content / "README.md", "overview", "Overview", None)
    add(content / "architecture.md", "architecture", "Architecture", None)
    add(content / "getting-started.md", "getting-started", "Getting Started", None)
    for p in module_files:
        sections.append({
            "id": "module-" + p.stem,
            "label": first_heading(p.read_text(encoding="utf-8"), p.stem),
            "group": "Modules",
            "md": p.read_text(encoding="utf-8"),
        })
    for fname, sid in (("diagrams/class-diagram.md", "class-diagram"), ("diagrams/sequences.md", "sequences")):
        add(content / fname, sid, SECTION_LABELS[sid], "Diagrams")
    add(content / "api.md", "api", "API Reference", None)
    return sections, module_names


# ---------------------------------------------------------------------------
# Assemble page (3-level nav)
# ---------------------------------------------------------------------------
def _nav_item(s) -> str:
    kids = "".join(
        f'<a class="nav-sublink" href="#{k["id"]}" data-target="{k["id"]}">{html.escape(k["label"])}</a>'
        for k in s.get("subs", [])
    )
    children = f'<div class="nav-children">{kids}</div>' if kids else ""
    return (f'<div class="nav-item" data-section="{s["id"]}">'
            f'<a class="nav-link" href="#{s["id"]}" data-target="{s["id"]}">{html.escape(s["label"])}</a>'
            f"{children}</div>")


def build_nav(sections) -> str:
    parts = ['<nav id="nav">']
    i = 0
    while i < len(sections):
        s = sections[i]
        if s["group"]:
            group = s["group"]
            parts.append(f'<div class="nav-group"><div class="nav-group-title">{html.escape(group)}</div>')
            while i < len(sections) and sections[i]["group"] == group:
                parts.append(_nav_item(sections[i]))
                i += 1
            parts.append("</div>")
        else:
            parts.append(_nav_item(s))
            i += 1
    parts.append("</nav>")
    return "\n".join(parts)


def build_html(title: str, sections, module_names, mermaid_src: str, subtitle: str = "") -> str:
    body = []
    for s in sections:
        shtml, subs = md_to_html(s["md"], module_names, s["id"])
        s["subs"] = subs
        body.append(f'<section id="{s["id"]}">\n{shtml}\n</section>')
    content_html = "\n".join(body)
    nav = build_nav(sections)  # after subs populated

    if mermaid_src.endswith(".js"):
        mermaid_script = (
            f'<script src="{html.escape(mermaid_src, quote=True)}"></script>\n'
            "<script>mermaid.initialize({startOnLoad:true, theme:'neutral', securityLevel:'loose'});</script>"
        )
    else:
        mermaid_script = (
            '<script type="module">\n'
            f"import mermaid from '{mermaid_src}';\n"
            "mermaid.initialize({startOnLoad:true, theme:'neutral', securityLevel:'loose'});\n"
            "</script>"
        )
    esc_title = html.escape(title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc_title} — Wiki</title>
<style>
:root {{
  --bg:#ffffff; --fg:#1f2328; --muted:#59636e; --line:#d1d9e0;
  --sidebar:#f6f8fa; --accent:#0969da; --code-bg:#f6f8fa;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0d1117; --fg:#e6edf3; --muted:#9198a1; --line:#30363d;
           --sidebar:#010409; --accent:#4493f8; --code-bg:#161b22; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
        color:var(--fg); background:var(--bg); }}
#sidebar {{ position:fixed; top:0; left:0; bottom:0; width:290px; background:var(--sidebar);
            border-right:1px solid var(--line); overflow-y:auto; padding:20px 0; }}
#sidebar .brand {{ font-weight:700; font-size:15px; padding:0 20px 2px; }}
#sidebar .subtitle {{ font-size:12px; color:var(--muted); padding:0 20px 12px; }}
#filter {{ width:calc(100% - 40px); margin:0 20px 12px; padding:7px 10px; border:1px solid var(--line);
           border-radius:6px; background:var(--bg); color:var(--fg); font-size:13px; }}
.nav-group-title {{ padding:12px 20px 4px; font-size:11px; text-transform:uppercase;
                    letter-spacing:.06em; color:var(--muted); font-weight:700; }}
.nav-link {{ display:block; padding:5px 20px; color:var(--fg); text-decoration:none; font-size:14px;
             border-left:2px solid transparent; }}
.nav-group .nav-link {{ padding-left:34px; font-size:13.5px; }}
.nav-link:hover, .nav-sublink:hover {{ background:rgba(127,127,127,.12); }}
.nav-link.active {{ color:var(--accent); border-left-color:var(--accent); font-weight:600; }}
.nav-children {{ display:none; }}
.nav-item.expanded > .nav-children, #nav.filtering .nav-children {{ display:block; }}
.nav-sublink {{ display:block; padding:3px 20px 3px 44px; color:var(--muted); text-decoration:none;
                font-size:12.5px; border-left:2px solid transparent; }}
.nav-group .nav-sublink {{ padding-left:58px; }}
.nav-sublink.active-sub {{ color:var(--accent); border-left-color:var(--accent); }}
#main {{ margin-left:290px; padding:40px 56px 120px; max-width:900px; }}
section {{ scroll-margin-top:24px; padding-bottom:24px; border-bottom:1px solid var(--line); margin-bottom:24px; }}
section:last-child {{ border-bottom:none; }}
h1 {{ font-size:1.9em; margin:.2em 0 .6em; }}
h2 {{ font-size:1.4em; margin:1.4em 0 .5em; padding-bottom:.2em; border-bottom:1px solid var(--line); scroll-margin-top:24px; }}
h3 {{ font-size:1.15em; margin:1.2em 0 .4em; }}
a {{ color:var(--accent); }}
code {{ background:var(--code-bg); padding:.15em .35em; border-radius:5px; font-size:.88em;
        font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
pre {{ background:var(--code-bg); border:1px solid var(--line); border-radius:8px; padding:14px 16px; overflow:auto; }}
pre code {{ background:none; padding:0; }}
pre.mermaid {{ background:var(--bg); border:1px solid var(--line); text-align:center; }}
table {{ border-collapse:collapse; width:100%; margin:1em 0; font-size:.92em; }}
th,td {{ border:1px solid var(--line); padding:7px 11px; text-align:left; vertical-align:top; }}
th {{ background:var(--sidebar); }}
blockquote {{ margin:1em 0; padding:.4em 1em; border-left:3px solid var(--line); color:var(--muted); }}
ul,ol {{ padding-left:1.5em; }}
@media (max-width:800px) {{
  #sidebar {{ position:static; width:auto; height:auto; border-right:none; border-bottom:1px solid var(--line); }}
  #main {{ margin-left:0; padding:24px 18px 80px; }}
}}
</style>
</head>
<body>
<aside id="sidebar">
  <div class="brand">{esc_title}</div>
  {("<div class=\"subtitle\">" + html.escape(subtitle) + "</div>") if subtitle else ""}
  <input id="filter" type="text" placeholder="Filter…" aria-label="Filter navigation">
  {nav}
</aside>
<main id="main">
{content_html}
</main>
{mermaid_script}
<script>
const secLinks = Object.fromEntries([...document.querySelectorAll('.nav-link')].map(l => [l.dataset.target, l]));
const subLinks = Object.fromEntries([...document.querySelectorAll('.nav-sublink')].map(l => [l.dataset.target, l]));
const secObs = new IntersectionObserver((entries) => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      document.querySelectorAll('.nav-link.active').forEach(l => l.classList.remove('active'));
      document.querySelectorAll('.nav-item.expanded').forEach(n => n.classList.remove('expanded'));
      const link = secLinks[e.target.id];
      if (link) {{ link.classList.add('active'); link.closest('.nav-item')?.classList.add('expanded'); }}
    }}
  }});
}}, {{ rootMargin: '0px 0px -70% 0px', threshold: 0 }});
document.querySelectorAll('main section').forEach(s => secObs.observe(s));
const subObs = new IntersectionObserver((entries) => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      document.querySelectorAll('.nav-sublink.active-sub').forEach(l => l.classList.remove('active-sub'));
      subLinks[e.target.id]?.classList.add('active-sub');
    }}
  }});
}}, {{ rootMargin: '0px 0px -80% 0px', threshold: 0 }});
document.querySelectorAll('main h2[id]').forEach(h => subObs.observe(h));
const nav = document.getElementById('nav');
const filter = document.getElementById('filter');
filter.addEventListener('input', () => {{
  const q = filter.value.toLowerCase().trim();
  nav.classList.toggle('filtering', q.length > 0);
  document.querySelectorAll('.nav-item').forEach(item => {{
    const link = item.querySelector('.nav-link');
    const linkMatch = link.textContent.toLowerCase().includes(q);
    let anySub = false;
    item.querySelectorAll('.nav-sublink').forEach(s => {{
      const m = s.textContent.toLowerCase().includes(q);
      s.style.display = (!q || m || linkMatch) ? '' : 'none';
      if (m) anySub = true;
    }});
    item.style.display = (!q || linkMatch || anySub) ? '' : 'none';
  }});
  document.querySelectorAll('.nav-group').forEach(g => {{
    const any = [...g.querySelectorAll('.nav-item')].some(i => i.style.display !== 'none');
    g.style.display = any ? '' : 'none';
  }});
}});
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a single-file HTML wiki with 3-level sidebar nav from Markdown sections.")
    ap.add_argument("content_dir")
    ap.add_argument("--title", required=True)
    ap.add_argument("--subtitle", default="", help="Optional second line under the title, e.g. a monorepo component path")
    ap.add_argument("--out", default=None)
    ap.add_argument("--mermaid-src", default="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs")
    args = ap.parse_args()

    content = Path(args.content_dir)
    if not content.is_dir():
        print(f"error: {content} is not a directory", file=sys.stderr)
        return 1
    sections, module_names = discover(content)
    if not sections:
        print(f"error: no wiki content (.md files) found in {content}", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else content / "index.html"
    out.write_text(build_html(args.title, sections, module_names, args.mermaid_src, args.subtitle), encoding="utf-8")
    mermaid_count = sum(s["md"].count("```mermaid") for s in sections)
    subtotal = sum(len(s.get("subs", [])) for s in sections)
    print(f"Built {out} — {len(sections)} sections, {subtotal} sub-nav entries, "
          f"{mermaid_count} Mermaid diagrams, {len(module_names)} modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
