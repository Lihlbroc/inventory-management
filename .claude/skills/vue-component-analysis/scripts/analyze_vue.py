#!/usr/bin/env python3
"""Static structure scan for Vue single-file components (read-only).

Usage:  python -I analyze_vue.py <dir-or-file> [more paths...] [--json]

Standard library only. It is a heuristic regex scan, not a Vue compiler:
it finds *candidates* for review. Every finding must be confirmed by reading
the code before it is reported as a recommendation.
"""
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Thresholds are deliberately round numbers; they flag "worth a look", not "wrong".
LARGE_SFC_LINES = 400
LARGE_TEMPLATE_LINES = 250


def block(src, tag):
    """Return the inner text of the first <tag>...</tag> block, or ''."""
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", src, re.S)
    return m.group(1) if m else ""


def normalize(text):
    """Strip comments and collapse whitespace so equal code hashes equal."""
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    return re.sub(r"\s+", " ", text).strip()


def digest(text):
    return hashlib.sha1(normalize(text).encode()).hexdigest()[:10]


def extract_functions(script, min_lines=4):
    """Yield (name, body) for `const x = (...) =>`, `function x(...)` forms.

    Finds the matching closing brace by counting braces. This ignores braces
    inside strings/regex/template literals, so a rare miscount is possible;
    that only affects duplicate detection, never correctness of the app.
    `min_lines` lets callers skip tiny helpers (duplicate detection) or keep
    them all (looking up what a template-called function does).
    """
    pat = re.compile(
        r"(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{"
        r"|function\s+(\w+)\s*\([^)]*\)\s*\{"
    )
    for m in pat.finditer(script):
        name = m.group(1) or m.group(2)
        depth, i = 1, m.end()
        while i < len(script) and depth:
            depth += {"{": 1, "}": -1}.get(script[i], 0)
            i += 1
        body = script[m.start():i]
        # Tiny helpers: identical 2-line functions are noise, not reuse.
        if body.count("\n") >= min_lines:
            yield name, body


def css_rules(style):
    """Yield (selector, body) for flat CSS rules; skips @media/@keyframes nests."""
    style = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
    for m in re.finditer(r"([^{}@]+)\{([^{}]*)\}", style):
        selector = " ".join(m.group(1).split())
        if selector:
            yield selector, m.group(2)


def analyze_file(path):
    src = path.read_text(encoding="utf-8", errors="replace")
    template, script, style = block(src, "template"), block(src, "script"), block(src, "style")
    lines = lambda s: s.count("\n") + (1 if s.strip() else 0)

    f = {
        "file": str(path),
        "lines": {"total": lines(src), "template": lines(template),
                  "script": lines(script), "style": lines(style)},
        "api_style": ("script-setup" if re.search(r"<script[^>]*\bsetup\b", src)
                      else "setup()" if re.search(r"\bsetup\s*\(", script)
                      else "options" if "export default" in script else "none"),
        "scoped_style": bool(re.search(r"<style[^>]*\bscoped\b", src)),
        "counts": {k: len(re.findall(p, script)) for k, p in {
            "computed": r"\bcomputed\s*\(", "watch": r"\bwatch(?:Effect)?\s*\(",
            "ref": r"\b(?:ref|reactive)\s*\(", "onMounted": r"\bonMounted\s*\(",
            "fetch_calls": r"\bapi\.\w+\(|\bfetch\s*\(|axios\.",
        }.items()},
        "local_imports": re.findall(r"import\s+\w+\s+from\s+['\"](\.[^'\"]+\.vue)['\"]", script),
        "findings": [],
    }
    add = lambda kind, detail: f["findings"].append({"kind": kind, "detail": detail})

    if f["lines"]["total"] > LARGE_SFC_LINES:
        add("large-component", f'{f["lines"]["total"]} lines; look for sub-components/composables to extract')
    if f["lines"]["template"] > LARGE_TEMPLATE_LINES:
        add("large-template", f'{f["lines"]["template"]} template lines; repeated markup is a component candidate')

    # v-for checks. Tags are matched individually so :key is looked up on the same element.
    for tag in re.findall(r"<[\w-]+[^>]*\bv-for=[^>]*>", template, re.S):
        if not re.search(r"(?::|v-bind:)key=", tag):
            add("v-for-no-key", " ".join(tag.split())[:100])
        elif re.search(r":key=\"(?:index|idx|i)\"", tag):
            add("v-for-index-key", " ".join(tag.split())[:100])
        if re.search(r"\bv-if=", tag):
            add("v-if-with-v-for", "filter in a computed instead: " + " ".join(tag.split())[:80])

    # Template calls re-run on every render. Calling a cheap formatter is fine, so only flag
    # calls to local functions whose body loops or filters (e.g. getBacklogByPriority('high')
    # does a .filter each render); those belong in a computed.
    heavy = {n for n, b in extract_functions(script, min_lines=0)
             if re.search(r"\.(filter|sort|reduce|map|find|some|every)\(|\bfor\s*\(", b)}
    seen = set()
    for expr in re.findall(r"\{\{(.*?)\}\}|=\"([^\"]*)\"", template, re.S):
        expr = "".join(expr)
        for name in re.findall(r"(?<![.\w$])([a-zA-Z_]\w*)\(", expr):
            if name in heavy and name not in seen:
                seen.add(name)
                add("heavy-call-in-template", f"{name}(...) loops/filters on every render; use a computed")
    n_inline = len(re.findall(r"@\w[\w.-]*=\"\s*\([^)]*\)\s*=>", template))
    if n_inline:
        add("inline-arrow-handlers", f"{n_inline} inline arrow handler(s); matters mainly inside long v-for lists")

    if re.search(r"deep\s*:\s*true", script):
        add("deep-watcher", "deep: true traverses the whole object on each change; watch a narrower source")
    if f["counts"]["watch"] and f["counts"]["fetch_calls"] and not f["counts"]["computed"]:
        add("watch-fetch-no-computed", "data refetched from watchers with no computed state; check for duplicate requests")
    if f["counts"]["fetch_calls"] >= 6:
        add("many-api-calls", f'{f["counts"]["fetch_calls"]} API call sites in one component; consider a composable')
    if not f["scoped_style"] and style.strip() and "App.vue" not in path.name:
        add("unscoped-style", "styles leak globally; use scoped or move to shared CSS on purpose")
    return f, list(extract_functions(script)), list(css_rules(style))


def collect(paths):
    for p in map(Path, paths):
        if p.is_file() and p.suffix == ".vue":
            yield p
        elif p.is_dir():
            yield from (q for q in sorted(p.rglob("*.vue")) if "node_modules" not in q.parts)


def main(argv):
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")] or ["."]
    files, fn_index, css_index = [], defaultdict(set), defaultdict(set)
    for path in collect(paths):
        f, fns, rules = analyze_file(path)
        files.append(f)
        for name, body in fns:
            fn_index[digest(body)].add((f["file"], name))
        for sel, body in rules:
            css_index[digest(body)].add((f["file"], sel))

    # Reuse candidates: identical bodies appearing in 2+ *different* files.
    spread = lambda idx: [sorted(v) for v in idx.values() if len({x[0] for x in v}) > 1]
    dup_fns = spread(fn_index)
    dup_css = spread(css_index)

    report = {"files": files, "duplicate_functions": dup_fns, "duplicate_css_rules": dup_css}
    if as_json:
        print(json.dumps(report, indent=2))
        return

    print(f"# Vue structure scan: {len(files)} component(s)\n")
    print("| File | Lines (tpl/script/style) | API | computed | watch | API calls | Findings |")
    print("|---|---|---|---|---|---|---|")
    for f in sorted(files, key=lambda x: -x["lines"]["total"]):
        l, c = f["lines"], f["counts"]
        print(f'| {f["file"]} | {l["total"]} ({l["template"]}/{l["script"]}/{l["style"]}) | '
              f'{f["api_style"]} | {c["computed"]} | {c["watch"]} | {c["fetch_calls"]} | {len(f["findings"])} |')
    print("\n## Findings (candidates, verify before reporting)")
    for f in files:
        if f["findings"]:
            print(f'\n### {f["file"]}')
            for x in f["findings"]:
                print(f'- **{x["kind"]}**: {x["detail"]}')
    for title, groups in (("Duplicate functions across files", dup_fns),
                          ("Identical CSS declaration blocks across files", dup_css)):
        if groups:
            print(f"\n## {title}")
            for g in groups[:25]:
                print("- " + "; ".join(f"{a}::{b}" for a, b in g))


if __name__ == "__main__":
    main(sys.argv[1:])
