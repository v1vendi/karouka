#!/usr/bin/env python3
"""Runs the vendored WPT subsets on karouka and reports the pass rates.

    tools/dev.sh wpt [--suite all|reftest|dom] [--filter SUBSTRING]... [--jobs N] [--verbose]
    tools/wpt.py --viewer PATH [same options] [--root DIR] [--out DIR] [--write-known]

Two suites, each with its own ratchet: `reftest` (this docstring) and `dom`, testharness.js documents
(dom/nodes/, css-scroll-snap, cssom-view, innerText, html/semantics/scripting-1, transform-hit-testing)
scored per subtest against tests/wpt/known_failures_dom.txt (tools/wpt_dom.py's docstring).
--suite all (the default) runs both; the run fails when either does. --filter applies to both; it must
match a document of one of them. Given more than once, a document runs when it matches any of them, and
each must match one (dev.sh check runs tests/wpt/check_filters.txt in one process, so its first
viewer launches and the corpus walk are paid once).

The corpus is this repo's `third_party/wpt/`, a vendored subset of upstream WPT (the vendored tree is the
subset, nothing is filtered at run time) pinned by tests/wpt/corpus.pin, byte for byte
(tools/wpt_vendor.sh --check verifies it). $KR_WPT_ROOT / --root point it elsewhere. The rules:

- A test is an .html/.htm/.xht/.xhtml file outside any `support/` or `reference/` directory that carries
  a <link rel=match> or <link rel=mismatch>. Its references resolve against the test's URL; a
  root-relative href (`/css/...`) against the corpus root.
- Every document renders alone, in its own `karouka_viewer --headless --backend software` process, at
  800x600 (wptrunner's viewport), scale 1, after --frames frames (default 30, as dev.sh check). `--doc-root` serves root-relative loads (`/fonts/ahem.css`) from the
  corpus root, as wptserve would. `--font-hinting none` turns off CoreGraphics' font smoothing, which
  otherwise dilates glyphs ~1px past their outlines (an Ahem glyph past its em box).
- A test passes when it equals any one of its match references and none of its mismatch references.
  Equal is exact, unless the test declares <meta name=fuzzy>, read with wptrunner's two-sided rule. A
  document that fails to render, or a reference that doesn't exist, makes the test an error.

The ratchet is tests/wpt/known_failures.txt (one corpus-relative path per line, `# reason` after it):
a test not listed must pass, a listed one must not (remove it when it passes), so dev.sh wpt exits 1
on either. A listed path the corpus no longer has is only warned about (a re-vendor, or a --root
elsewhere, can drop tests). --write-known rewrites the file from this run, keeping existing reasons.

Captures and results.tsv (test, outcome, detail) go to --out (dev.sh wpt: $KR_BUILD/wpt/<checkout>).
--prune-checkouts (dev.sh wpt passes it) first deletes the other output directories next to --out, when
that is in a `wpt` directory, of checkouts that are gone, never a live checkout's (tools/checkout_dirs.py, orphans included: the
directories of runs before their lock named the checkout).
"""

import argparse
import concurrent.futures
import html.parser
import os
import re
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkout_dirs  # noqa: E402
import pngdiff  # noqa: E402
import wpt_dom  # noqa: E402

WIDTH, HEIGHT = 800, 600
EXTENSIONS = (".html", ".htm", ".xht", ".xhtml")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWN_FAILURES = os.path.join(REPO, "tests", "wpt", "known_failures.txt")


# ---------------------------------------------------------------- discovery


class Scan(html.parser.HTMLParser):
    """Collects rel=match/mismatch links and <meta name=fuzzy> contents, in tree order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = []  # (kind, href)
        self.fuzzy = []  # raw content strings

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "link":
            rel = a.get("rel", "").strip().lower()
            href = a.get("href", "").strip()
            if rel in ("match", "mismatch") and href:
                self.refs.append((rel, href))
        elif tag == "meta" and a.get("name", "").strip().lower() == "fuzzy":
            self.fuzzy.append(a.get("content", ""))

    handle_startendtag = handle_starttag


def is_support_only(relative):
    return any(part in ("support", "reference") for part in relative.split("/"))


def matches(relative, substrings):
    """Whether a corpus-relative path passes --filter: any of its substrings, or no filter at all."""
    return not substrings or any(s in relative for s in substrings)


def discover(root, substrings):
    tests = []
    for directory, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            if not name.endswith(EXTENSIONS):
                continue
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            if is_support_only(relative) or not matches(relative, substrings):
                continue
            with open(path, "rb") as f:
                text = f.read().decode("utf-8", "replace")
            scan = Scan()
            try:
                scan.feed(text)
                scan.close()
            except Exception:  # an unparsable document is not a test we can read
                continue
            if scan.refs:
                tests.append((relative, scan.refs, scan.fuzzy))
    tests.sort()
    return tests


def resolve(root, test_relative, href):
    """A reference's corpus-relative path, or None when it points outside the corpus."""
    href = urllib.parse.urldefrag(href)[0].split("?")[0]
    if href.startswith("/"):
        relative = href.lstrip("/")
    else:
        relative = os.path.normpath(os.path.join(os.path.dirname(test_relative), urllib.parse.unquote(href)))
    relative = relative.replace(os.sep, "/")
    if relative.startswith("../"):
        return None
    return relative


# ---------------------------------------------------------------- fuzzy (wptrunner's rule)


def parse_bound(text):
    text = text.strip()
    if "-" not in text:
        return (0, int(text)) if text.isdigit() else None
    lo, hi = (t.strip() for t in text.split("-", 1))
    if not (lo.isdigit() and hi.isdigit()) or int(lo) > int(hi):
        return None
    return int(lo), int(hi)


def parse_component(text, name):
    text = text.strip()
    if "=" in text:
        key, value = text.split("=", 1)
        return parse_bound(value) if key.strip() == name else None
    return parse_bound(text)


def parse_fuzzy(content):
    """(href or '', (channel_lo, channel_hi), (pixels_lo, pixels_hi)), or None when not understood."""
    rest, href = content.strip(), ""
    colon, semi = rest.find(":"), rest.find(";")
    if colon >= 0 and (semi < 0 or colon < semi):
        head = rest[:colon].strip()
        if head and parse_component(head, "maxDifference") is None:
            href, rest = head, rest[colon + 1 :].strip()
    if ";" not in rest:
        return None
    first, second = rest.split(";", 1)
    channel, pixels = parse_component(first, "maxDifference"), parse_component(second, "totalPixels")
    if channel is None or pixels is None:
        return None
    return href, channel, pixels


def fuzzy_for(entries, href):
    fallback = None
    for entry_href, channel, pixels in entries:
        if entry_href == href:
            return channel, pixels
        if not entry_href and fallback is None:
            fallback = (channel, pixels)
    return fallback


def fuzzy_equal(max_delta, differing, allowance):
    if allowance is None:
        return differing == 0
    (clo, chi), (plo, phi) = allowance
    if differing == 0 and plo == 0:
        return True
    if max_delta == 0 and clo == 0:
        return True
    return clo <= max_delta <= chi and plo <= differing <= phi


# ---------------------------------------------------------------- rendering and comparison


def capture_path(out, relative):
    return os.path.join(out, "captures", relative + ".png")


def render(viewer, root, out, relative, frames, timeout, extra):
    """Renders one corpus document; returns None or an error string."""
    png = capture_path(out, relative)
    os.makedirs(os.path.dirname(png), exist_ok=True)
    if os.path.exists(png):
        os.remove(png)
    command = [viewer, os.path.join(root, relative), "--headless", "--backend", "software",
               "--size", f"{WIDTH}x{HEIGHT}", "--scale", "1", "--frames", str(frames),
               "--capture", png, "--doc-root", root, "--font-hinting", "none"] + extra
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"render of {relative} timed out after {timeout}s"
    if result.returncode != 0 or not os.path.exists(png):
        tail = result.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        return f"render of {relative} failed (exit {result.returncode}): {tail[0][:160]}"
    return None


def judge(root, out, relative, refs, fuzzy_raw, render_errors):
    """('ok'|'fail'|'error', detail)."""
    if relative in render_errors:
        return "error", render_errors[relative]
    fuzzy, warnings = [], []
    for raw in fuzzy_raw:
        entry = parse_fuzzy(raw)
        if entry is None:
            warnings.append(f'unparsed <meta name=fuzzy content="{raw}">')
        else:
            fuzzy.append(entry)
    has_match, any_match, mismatch_ok, details = False, False, True, []
    for kind, href in refs:
        ref = resolve(root, relative, href)
        if ref is None or not os.path.isfile(os.path.join(root, ref)):
            return "error", f"reference {href} is not in the corpus"
        if ref in render_errors:
            return "error", render_errors[ref]
        size_mismatch, max_delta, differing = pngdiff.compare(capture_path(out, relative), capture_path(out, ref))
        allowance = fuzzy_for(fuzzy, href)
        equal = not size_mismatch and fuzzy_equal(max_delta, differing, allowance)
        measured = f"{differing} px differ, max channel delta {max_delta}"
        if allowance is not None:
            (clo, chi), (plo, phi) = allowance
            measured += f" (fuzzy allows {clo}-{chi};{plo}-{phi})"
        if kind == "match":
            has_match = True
            any_match = any_match or equal
            if not equal:
                details.append(f"expected to match {href}: {measured}")
        elif equal:
            mismatch_ok = False
            details.insert(0, f"expected to mismatch {href}, did not")
    passed = (not has_match or any_match) and mismatch_ok
    detail = "; ".join(warnings + ([] if passed else details[:1]))
    return ("ok" if passed else "fail"), detail


# ---------------------------------------------------------------- ratchet


def load_known(path):
    known = {}
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            entry, _, reason = line.partition("#")
            entry = entry.strip()
            if entry:
                known[entry] = reason.strip()
    return known


def write_known(path, results, known, header):
    lines = list(header)
    # Entries this run didn't test (a --filter run) stay as they are.
    failing = {r: reason for r, reason in (known or {}).items() if r not in results}
    for relative, (outcome, _) in results.items():
        if outcome != "ok":
            failing[relative] = (known or {}).get(relative) or "untriaged, failing at baseline"
    for relative, reason in sorted(failing.items()):
        lines.append(f"{relative}  # {reason}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


KNOWN_HEADER = [
    "# WPT reftests karouka is allowed to fail: tools/wpt.py's ratchet. The corpus is third_party/wpt/,",
    "# a vendored WPT subset pinned by tests/wpt/corpus.pin; see tools/wpt.py's docstring for the rules. A test not listed here must",
    "# pass; a listed test that passes fails the run too: delete its line in the commit that fixed it.",
    "# One corpus-relative path per line, then `# reason`.",
    "",
]

# ---------------------------------------------------------------- main


VENDORED_ROOT = os.path.join(REPO, "third_party", "wpt")
CORPUS_PIN = os.path.join(REPO, "tests", "wpt", "corpus.pin")


def default_root():
    return os.path.realpath(os.environ.get("KR_WPT_ROOT") or VENDORED_ROOT)


def corpus_pin(root):
    """(upstream WPT commit, source commit) the corpus at root was taken from, as far as known."""
    pin = os.path.join(root, "WPT_COMMIT")
    commit = ""
    if os.path.exists(pin):
        m = re.search(r"^commit:\s*(\S+)", open(pin).read(), re.M)
        commit = m.group(1)[:12] if m else ""
    if root == os.path.realpath(VENDORED_ROOT):
        m = re.search(r"^source-commit:\s*(\S+)", open(CORPUS_PIN).read(), re.M) if os.path.exists(CORPUS_PIN) else None
        return commit, (m.group(1)[:10] + " vendored") if m else "vendored, no corpus.pin"
    try:  # a tree read in place (--root / $KR_WPT_ROOT): its checkout's HEAD
        head = subprocess.run(["git", "-C", root, "rev-parse", "--short=10", "HEAD"], capture_output=True,
                              text=True).stdout.strip()
    except OSError:
        head = ""
    return commit, (head + " in place") if head else "in place"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--viewer", required=True)
    parser.add_argument("--root", default=default_root())
    parser.add_argument("--out", default=None)
    parser.add_argument("--filter", action="append", default=[],
                        help="run only documents whose corpus path contains SUBSTRING (repeatable: any of them)")
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("KR_JOBS", "4")))
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--known", default=KNOWN_FAILURES)
    parser.add_argument("--write-known", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--viewer-arg", action="append", default=[],
                        help="pass to every karouka_viewer run (e.g. --viewer-arg=--fallback-font=PATH)")
    parser.add_argument("--suite", choices=("all", "reftest", "dom"), default="all")
    parser.add_argument("--dom-frames", type=int, default=3600)
    parser.add_argument("--known-dom", default=wpt_dom.KNOWN_FAILURES_DOM)
    parser.add_argument("--prune-checkouts", action="store_true",
                        help="first delete the output directories next to --out of checkouts that are gone")
    args = parser.parse_args(argv)
    root = os.path.realpath(args.root)
    out = os.path.abspath(args.out or os.path.join(os.path.dirname(args.viewer), "..", "wpt"))
    jobs = max(1, min(args.jobs, 4))  # at most 4 jobs

    if not os.path.isdir(root):
        print(f"wpt: no WPT corpus at {root} (set KR_WPT_ROOT or --root)", file=sys.stderr)
        return 2
    if args.prune_checkouts and os.path.basename(os.path.dirname(out)) == "wpt":
        checkout_dirs.prune(os.path.dirname(out), out, orphans=True)
    elif args.prune_checkouts:
        print(f"wpt: --prune-checkouts: not pruning, {out} isn't in a wpt/ directory", file=sys.stderr)
    status, found = 0, []
    if args.suite in ("all", "reftest"):
        status, found = reftests(args, root, out, jobs)
        if status in (2, 4):
            return status
    if args.suite in ("all", "dom"):
        extra = [part for arg in args.viewer_arg for part in arg.split("=", 1)]
        dom_status, dom_found = wpt_dom.run(args, args.viewer, root, jobs, extra)
        status, found = max(status, dom_status), found + dom_found
    if not found:
        print(f"wpt: no document matches {' or '.join(map(repr, args.filter))} under {root}" if args.filter else
              f"wpt: no documents under {root}", file=sys.stderr)
        return 4 if args.filter else 2
    unmatched = [f for f in args.filter if not any(f in relative for relative in found)]
    for f in unmatched:
        print(f"wpt: no document matches {f!r} under {root}", file=sys.stderr)
    return 4 if unmatched else status


def reftests(args, root, out, jobs):
    """The reftest suite: (exit code, the tests run). (0, []) when --filter matches none of them."""
    started = time.monotonic()
    tests = discover(root, args.filter)
    if not tests:
        if args.filter and args.suite == "all":
            return 0, []
        print(f"wpt: no reftest matches {' or '.join(map(repr, args.filter))} under {root}" if args.filter else
              f"wpt: no reftest documents under {root}", file=sys.stderr)
        return (4 if args.filter else 2), []

    documents = set()
    for relative, refs, _ in tests:
        documents.add(relative)
        for _, href in refs:
            ref = resolve(root, relative, href)
            if ref is not None and os.path.isfile(os.path.join(root, ref)):
                documents.add(ref)
    commit, head = corpus_pin(root)
    print(f"wpt: {len(tests)} tests, {len(documents)} documents, corpus {root} (WPT {commit}, source {head}), "
          f"{WIDTH}x{HEIGHT}, {args.frames} frames, software backend, {jobs} jobs")

    extra = [part for arg in args.viewer_arg for part in arg.split("=", 1)]
    render_errors = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(render, args.viewer, root, out, d, args.frames, args.timeout, extra): d
                   for d in sorted(documents)}
        for future in concurrent.futures.as_completed(futures):
            error = future.result()
            if error:
                render_errors[futures[future]] = error
    rendered_at = time.monotonic()

    results = {}
    for relative, refs, fuzzy in tests:
        results[relative] = judge(root, out, relative, refs, fuzzy, render_errors)

    known = load_known(args.known)
    regressions, newly_passing = [], []
    for relative, (outcome, detail) in results.items():
        listed = known is not None and relative in known
        if outcome == "ok":
            if listed:
                newly_passing.append(relative)
                print(f"  ok(!)          {relative}: passes now -- remove from known_failures.txt")
            elif args.verbose:
                print(f"  ok             {relative}" + (f": {detail}" if detail else ""))
        else:
            word = outcome if listed or known is None else outcome.upper()
            label = f"{word}(known)" if listed else word
            print(f"  {label:<14} {relative}: {detail}")
            if known is not None and not listed:
                regressions.append(relative)

    with open(os.path.join(out, "results.tsv"), "w") as f:
        for relative, (outcome, detail) in sorted(results.items()):
            f.write(f"{relative}\t{outcome}\t{detail}\n")

    counts = {k: sum(1 for o, _ in results.values() if o == k) for k in ("ok", "fail", "error")}
    total = len(results)
    print(f"wpt: karouka {counts['ok']}/{total} passed ({100.0 * counts['ok'] / total:.1f}%), "
          f"{counts['fail']} failed, {counts['error']} errors "
          f"(render {rendered_at - started:.0f}s, total {time.monotonic() - started:.0f}s; {out}/results.tsv)")

    if args.write_known:
        write_known(args.known, results, known, KNOWN_HEADER)
        print(f"wpt: wrote {args.known}")
        return 0, list(results)
    if known is None:
        print(f"wpt: no {args.known}: nothing to ratchet against (--write-known records this run)")
        return 0, list(results)
    if not args.filter:
        stale = sorted(set(known) - set(results))
        for relative in stale:
            print(f"  warn           {relative}: listed in known_failures.txt, not in the corpus")
    if regressions:
        print(f"wpt: {len(regressions)} test(s) outside known_failures.txt failed")
    if newly_passing:
        print(f"wpt: {len(newly_passing)} test(s) in known_failures.txt pass now; delete their lines")
    return (1 if regressions or newly_passing else 0), list(results)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
