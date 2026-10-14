#!/usr/bin/env python3
"""Runs Ladybird's own Tests/LibWeb Text and Ref tests that touch images through karouka_viewer.

    tools/libweb_tests.py --viewer PATH --out DIR [--kind text|ref|both] [--gc-stress] [--jobs N]
                          [--frames N] [--timeout S] [--only REL]... [--list] [--save NAME]
                          [--saved-dir DIR] [--keep-saved-days N] [--known FILE] [--write-known]
    tools/libweb_tests.py [--saved-dir DIR] --compare A B
    tools/libweb_tests.py --preflight [--saved-dir DIR] [flags]

Ladybird's runner (test-web) needs WebContent and LibWebView, which don't build against karouka's
pruned LibWeb (tools/dev.sh, ladybird()), so this runs the tests in karouka_viewer instead.
`tools/dev.sh libweb [flags]` builds and runs it from a snapshot of the build, with --viewer and --out
($KR_BUILD/libweb/<checkout>) filled in. By hand, run it on a snapshot: --viewer
.../check/<checkout>-<hash>/build/bin/karouka_viewer (KR_RESOURCE_ROOT is set to the snapshot's res).

It copies Tests/LibWeb's Text, Ref, Layout, Screenshot and Assets into DIR/libweb and puts a stand-in
`internals` in front of Text/input/include.js and wpt-import's testharnessreport.js:
signalTestIsDone console.logs the viewer's --testharness marker, so the viewer prints the test's
output and stops; gc()/gcAsync() allocate past LibGC's threshold (a collection, LIBGC_LOG_LEVEL=1
shows it); `headless` is true; any other member logs KR_MISSING_INTERNALS and is undefined.
--gc-stress also collects once after the harness loads and on every animation frame. Ref pages load
neither file, so under --gc-stress each Ref test page and its reference gets the same collections from
an inline script of its own, first in <head>, which defines no `internals`: a page that branches on it
renders as without --gc-stress.

Picked: tests whose source has <img, new Image(, createElement("img"), HTMLImageElement, <picture,
image-set( or <input type=image. Text tests compare the printed output with Text/expected; Ref tests
render the test and its <link rel=match> reference at 800x600 on the software backend and compare
them with tools/pngdiff.py (PASS_TOL: within 16 per channel on 0.5% of pixels).

Statuses: PASS, FAIL, NEEDS_INTERNALS:<members> (uses internals karouka doesn't have, an echo server
(echoServer: no networking), or a pruned interface (pruned-<name>); a failing Ref test whose page
calls internals.<member>, since Ref pages get no stand-in), NO_REPORT, CRASH(rc), WALL_TIMEOUT.
Results go to DIR/results-<kind>[-gc].json, which the next run replaces; --save NAME also writes them
to SAVED/NAME.json (--saved-dir, default DIR/../saved: shared by every checkout's runs) and refuses,
before running, a NAME already there. --preflight checks the flags and that NAME, then exits without
running: tools/dev.sh libweb runs it before it builds. --compare A B prints tests whose status
differs; A and B are results files or saved NAMEs.

Cleanup, before each run: saved runs older than --keep-saved-days (default 14) are deleted, and so is
another checkout's output directory next to DIR whose checkout is gone (its .lock names the checkout,
root=, and the pid that last held it, which must be gone too; tools/checkout_dirs.py).

Ratchet: tests/libweb/known_failures.txt (--known FILE) lists the tests allowed not to pass, one
`<kind> <test> <STATUS>  # why` per line, STATUS being the status up to its first `:` or `(`
(FAIL, NEEDS_INTERNALS, NO_REPORT, CRASH, WALL_TIMEOUT). The run exits 1 when a test not listed
doesn't pass (PASS_TOL passes), a listed one passes or ends with another STATUS, or a listed test of
a kind (and --only set) the run covered wasn't run; each is printed. --write-known rewrites the file
from this run instead, keeping the reasons of entries still failing and the entries the run didn't
cover. --gc-stress checks against the same file: GC pressure changes no test's status.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import time

import checkout_dirs

KR_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNGDIFF = os.path.join(KR_ROOT, "tools", "pngdiff.py")
KNOWN = os.path.join(KR_ROOT, "tests", "libweb", "known_failures.txt")
KNOWN_HEADER = [
    "# Ladybird Tests/LibWeb image tests karouka is allowed not to pass: tools/libweb_tests.py's ratchet",
    "# (tools/dev.sh libweb; rules in its docstring). `<kind> <test> <STATUS>  # why`: that test may end",
    "# with STATUS. A test not listed must pass; a listed one that passes, ends with another STATUS or",
    "# isn't run fails the run: update or delete its line (--write-known rewrites the file from a run).",
    "# Causes, by test: docs/ENGINE.md (Ladybird's image tests).",
    "",
]
PASSING = ("PASS", "PASS_TOL")
IMG = re.compile(r"<img|new Image\(|createElement\(\s*['\"]img['\"]\s*\)|HTMLImageElement|<picture|image-set\("
                 r"|<input[^>]+type=['\"]?image")
SKIP_DIRS = re.compile(r"(^|/)(support|resources|common|images|_wpttools)(/|$)")

# Allocates past LibGC's threshold, so the next allocation collects (LIBGC_LOG_LEVEL=1 shows it).
GC_BODY = "let keep = null; for (let i = 0; i < 250000; ++i) keep = { i }; return keep ? undefined : undefined;"
SHIM = r"""// karouka tools/libweb_tests.py: a stand-in `internals` that reports through --testharness.
globalThis.internals = new Proxy({
    headless: true,
    signalTestIsDone(text) { console.log("karouka-testharness-report\n" + text); },
    spoofCurrentURL(url) {},
    setTestTimeout(ms) {},
    gc() { GC_BODY },
    gcAsync() { this.gc(); return new Promise(resolve => setTimeout(resolve, 0)); },
}, {
    get(target, prop, receiver) {
        if (prop in target) return Reflect.get(target, prop, receiver);
        if (typeof prop === "symbol" || prop === "then" || prop === "toJSON" || prop === "getEchoServerPort") return undefined;
        console.log("KR_MISSING_INTERNALS " + String(prop));
        return undefined;
    },
});
""".replace("GC_BODY", GC_BODY)
STRESS = """setTimeout(() => internals.gc(), 0);
(function frame() { internals.gc(); requestAnimationFrame(frame); })();
"""
# STRESS for a Ref page, without `internals`: run_ref greps the page for `internals.` calls, and a page
# that checks for internals must take the path it takes without --gc-stress.
REF_STRESS = ("(function () { function collect() { %s }\n"
              "setTimeout(collect, 0);\n"
              "(function frame() { collect(); requestAnimationFrame(frame); })(); })();\n" % GC_BODY)
DOCTYPE = re.compile(rb"<!doctype[^>]*>", re.I)

def default_tests_dir():
    # Git worktrees share the main checkout's Ladybird tree (docs/BUILDING.md, Build layout).
    common = subprocess.run(["git", "-C", KR_ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True).stdout.strip()
    main_root = os.path.dirname(common) if common else KR_ROOT
    return os.path.join(main_root, "third_party", "ladybird", "Tests", "LibWeb")


def make_copy(src, root, gc_stress):
    if os.path.isdir(root):
        shutil.rmtree(root)
    os.makedirs(root)
    for part in ("Text", "Ref", "Layout", "Screenshot", "Assets"):
        shutil.copytree(os.path.join(src, part), os.path.join(root, part), symlinks=True)
    prefix = SHIM + (STRESS if gc_stress else "")
    include = os.path.join(root, "Text/input/include.js")
    text = open(include).read()
    text = text.replace("if (globalThis.internals === undefined) {", "if (false) {", 1)
    text = text.replace('throw new Error("window.internals must be exposed to use HTTPTestServer");',
                        'console.log("KR_MISSING_INTERNALS echoServer"); '
                        'throw new Error("window.internals must be exposed to use HTTPTestServer");', 1)
    open(include, "w").write(prefix + text)
    report = os.path.join(root, "Text/input/wpt-import/resources/testharnessreport.js")
    text = open(report).read()
    open(report, "w").write(prefix + text)
    if gc_stress:
        for page in sorted({path for rel, reference in ref_tests(root)
                            for path in (os.path.join(root, "Ref/input", rel), reference)}):
            stress_ref_page(page)


def stress_ref_page(path):
    # karouka parses every page it loads as HTML (Web::Embedder::load_html_in_place), .xht and .svg
    # too. After the doctype, since before it the page would render in quirks mode; the parser puts a
    # script that comes before any content first in <head>.
    data = open(path, "rb").read()
    doctype = DOCTYPE.search(data)
    at = doctype.end() if doctype else 0
    open(path, "wb").write(data[:at] + f"<script>{REF_STRESS}</script>".encode() + data[at:])

def read(path):
    return open(path, encoding="utf-8", errors="replace").read()


def text_tests(root):
    base = os.path.join(root, "Text/input")
    found = []
    for directory, _, files in os.walk(base):
        if SKIP_DIRS.search(os.path.relpath(directory, base)):
            continue
        for name in files:
            if not name.endswith((".html", ".htm", ".xhtml", ".svg")):
                continue
            rel = os.path.relpath(os.path.join(directory, name), base)
            if os.path.exists(expected_path(root, rel)) and IMG.search(read(os.path.join(directory, name))):
                found.append(rel)
    return sorted(found)


def expected_path(root, rel):
    return os.path.join(root, "Text/expected", os.path.splitext(rel)[0] + ".txt")


def ref_tests(root):
    base = os.path.join(root, "Ref/input")
    found = []
    for directory, _, files in os.walk(base):
        for name in files:
            if not name.endswith((".html", ".htm", ".xhtml", ".svg")):
                continue
            source = read(os.path.join(directory, name))
            link = re.search(r"<link[^>]+rel=['\"]?match['\"]?[^>]*>", source)
            href = link and re.search(r"href=['\"]([^'\"]+)['\"]", link.group(0))
            if href and IMG.search(source):
                found.append((os.path.relpath(os.path.join(directory, name), base),
                              os.path.normpath(os.path.join(directory, href.group(1)))))
    return sorted(found)


def viewer_command(args, page, extra):
    return [args.viewer, page, "--headless", "--backend", "software", "--size", "800x600", "--scale", "1",
            "--doc-root", os.path.join(args.root, "Text/input/wpt-import"), "--font-hinting", "none"] + extra


def run_text(args, rel):
    command = viewer_command(args, os.path.join(args.root, "Text/input", rel),
                             ["--frames", str(args.frames), "--testharness", "--verbose"])
    try:
        run = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=args.timeout)
    except subprocess.TimeoutExpired:
        return "WALL_TIMEOUT", ""
    missing = set(re.findall(r"KR_MISSING_INTERNALS (\S+)", run.stderr))
    if "'internals' is not defined" in run.stderr:
        missing.add("inline-internals")
    missing |= {"pruned-" + name for name in re.findall(r"ReferenceError: '(\w+)' is not defined", run.stderr)
                if name != "internals"}
    needs = "NEEDS_INTERNALS:" + ",".join(sorted(missing))
    if run.returncode not in (0, 1, 3):
        return f"CRASH({run.returncode})", run.stderr[-2000:]
    if run.returncode == 3:
        return (needs if missing else "NO_REPORT"), run.stderr[-1500:]
    if run.stdout.rstrip() == read(expected_path(args.root, rel)).rstrip():
        return "PASS", ""
    return (needs if missing else "FAIL"), run.stdout


def run_ref(args, item):
    rel, reference = item
    pngs = {}
    for name, page in (("test", os.path.join(args.root, "Ref/input", rel)), ("ref", reference)):
        png = os.path.join(args.out, "ref", f"{rel.replace('/', '__')}.{name}.png")
        try:
            run = subprocess.run(viewer_command(args, page, ["--frames", "60", "--capture", png]),
                                 capture_output=True, text=True, errors="replace", timeout=args.timeout)
        except subprocess.TimeoutExpired:
            return "WALL_TIMEOUT", ""
        if run.returncode not in (0, 1) or not os.path.exists(png):
            return f"CRASH({run.returncode},{name})", run.stderr[-1500:]
        pngs[name] = png
    exact = subprocess.run([sys.executable, PNGDIFF, pngs["ref"], pngs["test"]], capture_output=True, text=True)
    if exact.returncode == 0:
        return "PASS", ""
    tolerant = subprocess.run([sys.executable, PNGDIFF, "--tolerance", "16:0.5", pngs["ref"], pngs["test"]],
                              capture_output=True, text=True)
    if tolerant.returncode == 0:
        return "PASS_TOL", ""
    # Ref pages get no stand-in internals: one that sets state through it (zoom, color scheme,
    # force dark) renders without that state.
    missing = sorted(set(re.findall(r"internals\.(\w+)", read(os.path.join(args.root, "Ref/input", rel)))))
    status = "NEEDS_INTERNALS:" + ",".join(missing) if missing else "FAIL"
    return status, (exact.stdout + exact.stderr).strip()[:400]


def status_class(status):
    return re.split(r"[:(]", status, maxsplit=1)[0]


def load_known(path):
    """(kind, test) -> (STATUS, reason), or None when there's no file."""
    if not os.path.exists(path):
        return None
    known = {}
    for number, line in enumerate(open(path, encoding="utf-8"), 1):
        entry, _, reason = line.partition("#")
        if not entry.strip():
            continue
        fields = entry.split()
        if len(fields) != 3 or fields[0] not in ("text", "ref"):
            sys.exit(f"{path}:{number}: expected `<kind> <test> <STATUS>  # why`, got: {line.rstrip()}")
        known[(fields[0], fields[1])] = (fields[2], reason.strip())
    return known


def default_reason(result):
    status = result["status"]
    if status.startswith("NEEDS_INTERNALS:"):
        return "needs " + status.split(":", 1)[1]
    return "untriaged"


def write_known(path, results, known, covered):
    entries = {key: value for key, value in (known or {}).items() if not covered(key)}
    for r in results:
        if r["status"] not in PASSING:
            key = (r["kind"], r["test"])
            old_reason = (known or {}).get(key, (None, ""))[1]
            entries[key] = (status_class(r["status"]), old_reason or default_reason(r))
    lines = list(KNOWN_HEADER)
    for (kind, test), (status, reason) in sorted(entries.items()):
        lines.append(f"{kind} {test} {status}  # {reason}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def ratchet(results, known, covered, path):
    """Prints every way this run differs from the known-failures file; returns how many."""
    name = os.path.relpath(path, KR_ROOT) if path.startswith(KR_ROOT + os.sep) else path
    problems = 0
    ran = set()
    for r in results:
        key = (r["kind"], r["test"])
        ran.add(key)
        listed = known.get(key)
        cls = status_class(r["status"])
        if r["status"] in PASSING:
            if listed:
                print(f"ratchet passes now   {r['kind']:4} {r['test']}: listed as {listed[0]}; delete its line")
                problems += 1
        elif not listed:
            print(f"ratchet new failure  {r['kind']:4} {r['test']}: {r['status']}")
            problems += 1
        elif listed[0] != cls:
            print(f"ratchet changed      {r['kind']:4} {r['test']}: {r['status']}, listed as {listed[0]}")
            problems += 1
    for key in sorted(k for k in known if covered(k) and k not in ran):
        print(f"ratchet not run      {key[0]:4} {key[1]}: listed, but this run has no such test; delete its line")
        problems += 1
    if problems:
        print(f"ratchet: {problems} test(s) differ from {name}")
    else:
        print(f"ratchet: every non-passing test is listed in {name} with its status")
    return problems


def saved_path(saved_dir, name):
    if os.sep in name or name.endswith(".json"):
        return name
    return os.path.join(saved_dir, name + ".json")


def prune_saved(saved_dir, days):
    """Deletes saved runs older than DAYS days; prints each."""
    if days <= 0 or not os.path.isdir(saved_dir):
        return
    cutoff = time.time() - days * 86400
    for name in sorted(os.listdir(saved_dir)):
        path = os.path.join(saved_dir, name)
        if name.endswith(".json") and os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            os.remove(path)
            print(f"cleanup: deleted saved run {name} (older than {days} days)")


def compare(a_path, b_path):
    a = {(r["kind"], r["test"]): r["status"] for r in json.load(open(a_path))}
    b = {(r["kind"], r["test"]): r["status"] for r in json.load(open(b_path))}
    differ = [key for key in sorted(set(a) | set(b)) if a.get(key) != b.get(key)]
    for kind, test in differ:
        print(f"{kind:4} {a.get((kind, test), '-'):24} -> {b.get((kind, test), '-'):24} {test}")
    print(f"{len(differ)} of {len(set(a) | set(b))} tests differ")
    return 1 if differ else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--viewer")
    parser.add_argument("--out")
    parser.add_argument("--tests", default=default_tests_dir(), help="Ladybird's Tests/LibWeb")
    parser.add_argument("--kind", choices=("text", "ref", "both"), default="both")
    parser.add_argument("--gc-stress", action="store_true")
    parser.add_argument("--jobs", type=int, default=min(3, int(os.environ.get("KR_JOBS", "4"))))
    parser.add_argument("--frames", type=int, default=3600)
    parser.add_argument("--timeout", type=int, default=150)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"))
    parser.add_argument("--save", metavar="NAME", help="also write the results to SAVED/NAME.json")
    parser.add_argument("--saved-dir", help="where --save writes and --compare finds NAMEs (default OUT/../saved)")
    parser.add_argument("--keep-saved-days", type=int, default=14,
                        help="delete saved runs older than this many days before a run (0: keep all)")
    parser.add_argument("--preflight", action="store_true",
                        help="check the flags and the --save NAME, then exit without running")
    parser.add_argument("--known", default=KNOWN, help="the known-failures file")
    parser.add_argument("--write-known", action="store_true", help="rewrite the known-failures file from this run")
    args = parser.parse_args()
    saved_dir = args.saved_dir or (os.path.join(os.path.dirname(os.path.abspath(args.out)), "saved")
                                   if args.out else os.getcwd())
    if args.compare:
        return compare(*(saved_path(saved_dir, name) for name in args.compare))
    if not args.preflight and (not args.out or (not args.viewer and not args.list)):
        parser.error("--viewer and --out are required")
    save_to = None
    if args.save and not args.list:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", args.save) or args.save.endswith(".json"):
            parser.error("--save NAME: letters, digits, '.', '_' and '-', without .json")
        save_to = os.path.join(saved_dir, args.save + ".json")
        if os.path.exists(save_to):
            parser.error(f"--save {args.save}: {save_to} exists; pick another name or delete it")
    known = load_known(args.known)
    if args.preflight:
        return 0
    if not args.list:
        prune_saved(saved_dir, args.keep_saved_days)
        checkout_dirs.prune(os.path.dirname(os.path.abspath(args.out)), os.path.abspath(args.out))
    args.out = os.path.abspath(args.out)
    args.root = os.path.join(args.out, "libweb-gc" if args.gc_stress else "libweb")
    make_copy(args.tests, args.root, args.gc_stress)
    os.makedirs(os.path.join(args.out, "ref"), exist_ok=True)
    if args.viewer:
        os.environ.setdefault("KR_RESOURCE_ROOT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.viewer))), "res"))
    jobs = []
    if args.kind in ("text", "both"):
        jobs += [("text", rel, rel) for rel in text_tests(args.root)]
    if args.kind in ("ref", "both"):
        jobs += [("ref", item[0], item) for item in ref_tests(args.root)]
    if args.only:
        jobs = [job for job in jobs if job[1] in args.only]
    if args.list:
        for kind, rel, _ in jobs:
            print(kind, rel)
        print(len(jobs), "tests")
        return 0
    results = []
    with cf.ThreadPoolExecutor(max(1, min(args.jobs, 4))) as pool:
        futures = {pool.submit(run_text if kind == "text" else run_ref, args, item): (kind, rel)
                   for kind, rel, item in jobs}
        for future in cf.as_completed(futures):
            kind, rel = futures[future]
            status, detail = future.result()
            results.append({"kind": kind, "test": rel, "status": status, "detail": detail})
            print(f"{kind:4} {status:24} {rel}", flush=True)
    results.sort(key=lambda r: (r["kind"], r["test"]))
    path = os.path.join(args.out, f"results-{args.kind}{'-gc' if args.gc_stress else ''}.json")
    json.dump(results, open(path, "w"), indent=1)
    counts = {}
    for r in results:
        key = (r["kind"], r["status"].split(":")[0])
        counts[key] = counts.get(key, 0) + 1
    for (kind, status), n in sorted(counts.items()):
        print(f"summary {kind} {status} {n}")
    print(f"results: {path}")
    if save_to:
        os.makedirs(os.path.dirname(save_to), exist_ok=True)
        try:
            with open(save_to, "x") as saved, open(path) as run:
                saved.write(run.read())
            print(f"saved: {save_to}")
        except FileExistsError:
            print(f"not saved: {save_to} appeared during the run (another checkout's --save {args.save}); "
                  f"the run is in {path}")

    kinds = ("text", "ref") if args.kind == "both" else (args.kind,)
    only = set(args.only)

    def covered(key):
        return key[0] in kinds and (not only or key[1] in only)

    if args.write_known:
        write_known(args.known, results, known, covered)
        print(f"wrote {args.known}")
        return 0
    if known is None:
        print(f"ratchet: no {args.known}: nothing to check against (--write-known records this run)")
        return 0
    return 1 if ratchet(results, known, covered, args.known) else 0


if __name__ == "__main__":
    sys.exit(main())
