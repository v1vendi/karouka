#!/usr/bin/env python3
"""Runs the display-list census (KR_DEBUG_CENSUS, src/engine/DisplayListCensus.cpp) over the pages
tools/dev.sh check renders and prints docs/COMMAND-LIST.md's karouka column.

    tools/dev.sh census                 # builds, runs every check page, prints the tables
    tools/dev.sh census --input         # each page with its karouka-check-input
    tools/dev.sh census tests/canvas_2d # only these pages (a path, or NAME under pages/)
    python3 tools/census.py --from-logs DIR   # only aggregates the logs a run left in DIR

Each page runs once headless in karouka_viewer for --frames frames (default 60) with KR_DEBUG=1 and
KR_DEBUG_CENSUS=1, which log one `census commands: ...` line before each frame the view rasterizes
(a frame that changed nothing isn't rasterized, so a static page logs one or two). Its stderr goes to
OUT/logs/<page>.log. The default pages are check's: pages/demo/*.html, pages/demo/*/index.html and
pages/tests/*.html. Like the measurement the doc reports, a page runs without its scripted input
unless --input is given.

It prints, per command and per feature the census counts, how many pages use it and the most in one
frame on any page (the doc's "pages using it (max per frame)"), naming the pages when there are at
most three; the drawing commands no page used (from ENUMERATE_DISPLAY_LIST_COMMANDS in
--commands-header, without the compositor metadata ones); the pages with the most commands in one
frame; and which pages the command-list stages S3 and S4 (docs/COMMAND-LIST.md, Cost of (b)) cover
completely, with what each other page needs. OUT/census.json (or --json FILE) keeps the page order
and each page's maxima; --from-logs prints the same tables from a run's logs without running anything.

Exits 1 when a run fails or logs no census, 2 on bad arguments. Counts, not timings: machine load
only moves an animated page's phase.
"""

import argparse
import concurrent.futures
import json
import os
import re
import shlex
import subprocess
import sys

KR_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkout_dirs  # noqa: E402

CENSUS = re.compile(r"census commands:(.*)$")
FIELD = re.compile(r"(\w+)=(\d+)")

# What stages S3 (rects, rounded rects, rings, lines, scrollbars, carets, affine transforms, scissor
# clips, opacity layers, images, linear gradients) and S4 (glyphs) translate. A page is covered when
# it uses no other command and no other nonzero feature.
SUBSET_COMMANDS = {
    "FillRect", "FillRectWithRoundedCorners", "FillRoundedRectRing", "DrawLine", "PaintScrollBar",
    "PaintCaret", "DrawScaledDecodedImageFrame", "PaintLinearGradient", "DrawGlyphRun",
}
SUBSET_FEATURES = {"glyphs", "clips", "transforms", "matrices", "layers", "opacity"}
# The compositor metadata commands execute_command_bytes never plays (DisplayListCommand.h).
METADATA_PREFIX = "Compositor"


def page_name(path):
    """PATH relative to pages/ without .html; an index.html is its directory (demo/NAME/index.html is demo/NAME)."""
    rel = os.path.relpath(os.path.abspath(path), os.path.join(KR_ROOT, "pages"))
    if rel.startswith(".."):
        rel = os.path.abspath(path)
    stem, ext = os.path.splitext(rel)
    if ext == ".html" and os.path.basename(stem) == "index":
        stem = os.path.dirname(stem)
    return stem


def check_pages():
    """The pages tools/dev.sh check renders: demo_pages, then pages/tests/*.html."""
    pages = []
    demo = os.path.join(KR_ROOT, "pages", "demo")
    pages += sorted(os.path.join(demo, f) for f in os.listdir(demo) if f.endswith(".html"))
    pages += sorted(os.path.join(demo, d, "index.html") for d in os.listdir(demo)
                    if os.path.isfile(os.path.join(demo, d, "index.html")))
    tests = os.path.join(KR_ROOT, "pages", "tests")
    pages += sorted(os.path.join(tests, f) for f in os.listdir(tests) if f.endswith(".html"))
    return pages


def resolve_page(arg):
    """A path as given, a directory's index.html, or NAME under pages/ (tests/canvas_2d, demo/trellis_page)."""
    for candidate in (arg, os.path.join(KR_ROOT, "pages", arg), os.path.join(KR_ROOT, "pages", arg + ".html")):
        if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "index.html")):
            return os.path.join(candidate, "index.html")
        if os.path.isfile(candidate):
            return candidate
    print(f"census: no page {arg}", file=sys.stderr)
    sys.exit(2)


def log_file(out, name):
    return os.path.join(out, "logs", name.replace(os.sep, "+") + ".log")


def drawing_commands(header):
    """The non-metadata commands ENUMERATE_DISPLAY_LIST_COMMANDS lists in HEADER, or None."""
    try:
        text = open(header).read()
    except OSError:
        return None
    match = re.search(r"#define ENUMERATE_DISPLAY_LIST_COMMANDS\(V\)(.*?)\n\s*\n", text, re.S)
    if not match:
        return None
    names = re.findall(r"V\(\s*(\w+)\s*,", match.group(1))
    return [n for n in names if not n.startswith(METADATA_PREFIX)]


def parse_line(rest):
    """A census line's commands and features, each {name: count}."""
    sections = rest.split("|")
    commands = {k: int(v) for k, v in FIELD.findall(sections[0])}
    features = {}
    for section in sections[1:]:
        for k, v in FIELD.findall(section):
            features[k] = int(v)
    return commands, features


def parse_log(path):
    """{censuses, commands: {name: max}, features: {name: max}, peak_commands, peak_drawing} for one log."""
    page = {"censuses": 0, "commands": {}, "features": {}, "peak_commands": 0, "peak_drawing": 0}
    feature_order = []
    with open(path, errors="replace") as f:
        for line in f:
            match = CENSUS.search(line)
            if not match:
                continue
            commands, features = parse_line(match.group(1))
            page["censuses"] += 1
            for k, v in commands.items():
                page["commands"][k] = max(page["commands"].get(k, 0), v)
            for k, v in features.items():
                if k not in feature_order:
                    feature_order.append(k)
                page["features"][k] = max(page["features"].get(k, 0), v)
            page["peak_commands"] = max(page["peak_commands"], sum(commands.values()))
            page["peak_drawing"] = max(page["peak_drawing"], sum(
                v for k, v in commands.items() if not k.startswith(METADATA_PREFIX)))
    page["feature_order"] = feature_order
    return page


def run_page(viewer, page, name, out, frames, use_input, timeout):
    """Runs PAGE once; returns (name, exit status or a reason string)."""
    args = [viewer, page, "--headless", "--frames", str(frames)]
    if use_input:
        meta = subprocess.run([viewer, "--print-meta", "karouka-check-input", page],
                              capture_output=True, text=True).stdout.strip()
        args += shlex.split(meta)
    env = dict(os.environ, KR_DEBUG="1", KR_DEBUG_CENSUS="1")
    cache = os.path.join(out, "shader-cache", name.replace(os.sep, "+"))
    os.makedirs(cache, exist_ok=True)
    env.setdefault("KR_SHADER_CACHE_DIR", cache)
    path = log_file(out, name)
    with open(path, "w") as log:
        log.write("$ " + " ".join(shlex.quote(a) for a in args) + "\n")
        log.flush()
        try:
            rc = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                env=env, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            return name, f"timed out after {timeout} s"
    return name, rc


def fmt_pages(names, limit=3):
    return ", ".join(names) if len(names) <= limit else ""


def report(pages, order, drawing, top):
    """The tables, as Markdown lines. PAGES is {name: parse_log(...)}, ORDER the page names in run order."""
    lines = []
    n = len(order)
    commands = sorted({k for p in pages.values() for k in p["commands"]},
                      key=lambda k: (-sum(1 for p in pages.values() if k in p["commands"]), k))
    lines.append(f"## Commands ({n} pages)")
    lines.append("")
    lines.append("| Command | Pages using it (max per frame) | Pages |")
    lines.append("| --- | --- | --- |")
    for k in commands:
        users = [name for name in order if pages[name]["commands"].get(k)]
        peak = max(pages[name]["commands"][k] for name in users)
        detail = ""
        if k == "DrawGlyphRun":
            glyphs = max((pages[name]["features"].get("glyphs", 0) for name in users), default=0)
            detail = f" runs, {glyphs} glyphs"
        lines.append(f"| {k} | {len(users)} ({peak}{detail}) | {fmt_pages(users)} |")
    lines.append("")
    if drawing is not None:
        seen = [k for k in drawing if any(k in p["commands"] for p in pages.values())]
        never = [k for k in drawing if k not in seen]
        lines.append(f"Drawing commands seen: {len(seen)} of {len(drawing)}. "
                     f"Never seen: {', '.join(never) if never else 'none'}.")
    else:
        lines.append("Drawing commands never seen: unknown (no --commands-header).")
    lines.append("")

    features = []
    for name in order:
        for k in pages[name]["feature_order"]:
            if k not in features:
                features.append(k)
    lines.append("## Features")
    lines.append("")
    lines.append("| Feature | Pages using it (max per frame) | Pages |")
    lines.append("| --- | --- | --- |")
    unused = []
    for k in features:
        users = [name for name in order if pages[name]["features"].get(k)]
        if not users:
            unused.append(k)
            continue
        peak = max(pages[name]["features"][k] for name in users)
        lines.append(f"| {k} | {len(users)} ({peak}) | {fmt_pages(users)} |")
    lines.append("")
    lines.append(f"Features no page used: {', '.join(unused) if unused else 'none'}.")
    lines.append("")

    lines.append(f"## Most commands in one frame (top {top})")
    lines.append("")
    lines.append("| Page | Commands | Drawing commands |")
    lines.append("| --- | --- | --- |")
    for name in sorted(order, key=lambda name: (-pages[name]["peak_commands"], name))[:top]:
        lines.append(f"| {name} | {pages[name]['peak_commands']} | {pages[name]['peak_drawing']} |")
    lines.append("")

    misses = {}
    for name in order:
        need = sorted(k for k in pages[name]["commands"] if k not in SUBSET_COMMANDS
                      and not k.startswith(METADATA_PREFIX))
        need += sorted(k for k, v in pages[name]["features"].items() if v and k not in SUBSET_FEATURES)
        if need:
            misses[name] = need
    covered = [name for name in order if name not in misses]
    demo = [name for name in order if name.startswith("demo/")]
    demo_covered = [name for name in covered if name.startswith("demo/")]
    lines.append("## Stages S3 and S4")
    lines.append("")
    lines.append(f"Cover {len(covered)} of {n} pages completely, {len(demo_covered)} of {len(demo)} demo pages"
                 f"{' (' + ', '.join(demo_covered) + ')' if demo_covered else ''}.")
    if misses:
        lines.append("")
        lines.append("| Page | Needs |")
        lines.append("| --- | --- |")
        for name, need in misses.items():
            lines.append(f"| {name} | {', '.join(need)} |")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pages", nargs="*", help="pages (default: the check corpus)")
    parser.add_argument("--viewer", help="karouka_viewer (tools/dev.sh census passes the snapshot's)")
    parser.add_argument("--out", help="output directory: logs/, shader-cache/, census.json")
    parser.add_argument("--from-logs", metavar="DIR", help="aggregate DIR/logs/*.log, run nothing")
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--input", action="store_true", help="give each page its karouka-check-input")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=300, help="seconds per page")
    parser.add_argument("--top", type=int, default=5, help="pages in the most-commands table")
    parser.add_argument("--commands-header", default=os.path.join(
        KR_ROOT, "third_party", "ladybird", "Libraries", "LibCompositing", "DisplayList", "DisplayListCommand.h"))
    parser.add_argument("--json", metavar="FILE", help="also write the per-page maxima as JSON")
    parser.add_argument("--prune-checkouts", action="store_true",
                        help="first delete the census/ output directories of checkouts that are gone")
    args = parser.parse_args()
    if args.frames < 1 or args.jobs < 1:
        parser.error("--frames and --jobs must be at least 1")

    drawing = drawing_commands(args.commands_header)
    if args.from_logs:
        logs = os.path.join(args.from_logs, "logs")
        names = sorted(f[:-4] for f in os.listdir(logs) if f.endswith(".log"))
        order = [n.replace("+", os.sep) for n in names]
        try:  # the run's own page order, which census.json keeps
            with open(os.path.join(args.from_logs, "census.json")) as f:
                run_order = json.load(f)["order"]
            order = [name for name in run_order if name in order] + [n for n in order if n not in run_order]
        except (OSError, ValueError, KeyError):
            pass
        pages = {name: parse_log(log_file(args.from_logs, name)) for name in order}
        failed = []
    else:
        if not args.viewer or not args.out:
            parser.error("--viewer and --out are needed unless --from-logs")
        out = os.path.abspath(args.out)
        if args.prune_checkouts and os.path.basename(os.path.dirname(out)) == "census":
            checkout_dirs.prune(os.path.dirname(out), out, orphans=True)
        paths = [resolve_page(p) for p in args.pages] if args.pages else check_pages()
        order = [page_name(p) for p in paths]
        if len(set(order)) != len(order):
            parser.error("two pages have the same name")
        logs = os.path.join(out, "logs")
        os.makedirs(logs, exist_ok=True)
        for f in os.listdir(logs):
            os.remove(os.path.join(logs, f))
        print(f"census: {len(paths)} pages, {args.frames} frames each, "
              f"{'with' if args.input else 'without'} scripted input, {args.jobs} at a time; logs in {logs}",
              file=sys.stderr)
        failed = []
        with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
            futures = [pool.submit(run_page, args.viewer, p, name, out, args.frames, args.input, args.timeout)
                       for p, name in zip(paths, order)]
            for future in futures:
                name, rc = future.result()
                if rc != 0:
                    failed.append(f"{name}: {'exit ' + str(rc) if isinstance(rc, int) else rc}")
        pages = {name: parse_log(log_file(out, name)) for name in order}
        if args.json is None:
            args.json = os.path.join(out, "census.json")
    failed += [f"{name}: no census line" for name in order if not pages[name]["censuses"] and
               not any(f.startswith(name + ":") for f in failed)]
    measured = [name for name in order if pages[name]["censuses"]]

    print("\n".join(report(pages, measured, drawing, args.top)))
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"order": order, "pages": {name: {k: v for k, v in pages[name].items() if k != "feature_order"}
                                                 for name in order}}, f, indent=1, sort_keys=True)
    if failed:
        print("", file=sys.stderr)
        for line in failed:
            print(f"census: FAILED {line} (see {log_file(args.from_logs or args.out, line.split(':')[0])})",
                  file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
