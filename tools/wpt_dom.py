"""The testharness.js half of tools/wpt.py: the dom suite, run on karouka.

The documents: every .html under dom/nodes/ and html/dom/elements/the-innertext-and-outertext-properties/,
every .html under html/semantics/scripting-1/ outside its */support/ and */resources/, and, under
css/css-scroll-snap/, css/cssom-view/ and the one file css/css-transforms/transform-hit-testing.html, the
.html documents that load /resources/testharness.js and carry no rel="match"/"mismatch" (SUBSET below). They run as testharness.js, scored per subtest. Each
runs alone in `karouka_viewer --testharness --headless --backend software --no-render` at 800x600,
scale 1, for at most --dom-frames frames of page clock (default 3600: 60 s, so the harness's own 10 s
timeout fires inside it); the viewer serves its own testharnessreport.js and stops at the frame the
report arrived in. The outcome:

- a document that prints no report, reports no subtests, or reports a harness status other than OK is a
  whole-file error (key: the corpus-relative path), and its subtests aren't counted;
- otherwise each subtest is keyed `path::name` (trailing blanks trimmed) and passes on PASS only.

The ratchet is tests/wpt/known_failures_dom.txt: one key per line, `# reason` after it, `\\#` for a `#`
inside a subtest name. A key not listed must pass (or, for a path, must not error), a listed one must
not; a listed key nothing in this run produced is stale and fails too, unless --filter left its
document out.

testharness.js and the two scroll helpers (dom/events/scrolling/scroll_support.js,
css/cssom-view/support/scroll-behavior.js) load from --doc-root, the vendored copies in the corpus.
"""

import concurrent.futures
import os
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWN_FAILURES_DOM = os.path.join(REPO, "tests", "wpt", "known_failures_dom.txt")
# The subset, in order: (corpus path, css rule, skip). A directory is walked recursively for .html
# files; the css rule keeps only documents that load testharness.js and carry no rel="match"/"mismatch";
# scripting-1 skips support/ and resources/ below its top level (the relative path must contain
# "/support/", so a top-level support/ would be walked).
SUBSET = (
    ("dom/nodes", False, None),
    ("css/css-scroll-snap", True, None),
    ("css/cssom-view", True, None),
    ("html/dom/elements/the-innertext-and-outertext-properties", False, None),
    ("html/semantics/scripting-1", False, lambda rel: "/support/" in rel or "/resources/" in rel),
    ("css/css-transforms/transform-hit-testing.html", True, None),
)
SUBSET_NAMES = ", ".join(d + ("" if d.endswith(".html") else "/") for d, _, _ in SUBSET)
WIDTH, HEIGHT = 800, 600

KNOWN_HEADER = [
    "# WPT testharness.js subtests karouka is allowed to fail: tools/wpt.py's dom suite ratchet,",
    "# over the dom suite's subset of third_party/wpt/ (documents and rules: tools/wpt_dom.py's docstring).",
    "# `<path>::<subtest name>` lets that subtest fail; `<path>` lets the whole file error (no report, no",
    "# subtests, or a harness status other than OK). A key not listed must pass; a listed key that passes",
    "# or that nothing produced fails the run too: delete its line. `\\#` is a literal # in a name.",
    "",
]


def is_css_testharness_doc(path):
    """Whether a css/ document is in the suite: it loads testharness.js and isn't a reftest (by bytes)."""
    try:
        with open(path, "rb") as f:
            text = f.read()
    except OSError:
        return False
    return b"/resources/testharness.js" in text and b'rel="match"' not in text and b'rel="mismatch"' not in text


def discover(root, substrings):
    """The dom suite's documents (SUBSET), corpus-relative."""
    documents = []

    def consider(path, css):
        if not path.endswith(".html"):
            return
        relative = os.path.relpath(path, root).replace(os.sep, "/")
        if substrings and not any(s in relative for s in substrings):
            return
        if css and not is_css_testharness_doc(path):
            return
        documents.append(relative)

    def walk(subdir, css=False, skip=None):
        base = os.path.join(root, subdir)
        for directory, dirs, files in os.walk(base):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(directory, name)
                if skip and skip(os.path.relpath(path, base).replace(os.sep, "/")):
                    continue
                consider(path, css)

    for subdir, css, skip in SUBSET:
        if subdir.endswith(".html"):
            if os.path.isfile(os.path.join(root, subdir)):
                consider(os.path.join(root, subdir), css)
        else:
            walk(subdir, css, skip)
    return sorted(set(documents))


def run_one(viewer, root, relative, frames, timeout, extra):
    """(error or None, [(status, name, message)])."""
    command = [viewer, os.path.join(root, relative), "--headless", "--backend", "software", "--no-render",
               "--size", f"{WIDTH}x{HEIGHT}", "--scale", "1", "--frames", str(frames), "--doc-root", root,
               "--testharness"] + extra
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"timed out after {timeout}s", []
    stdout = result.stdout.decode("utf-8", "replace")
    if result.returncode == 3:
        return f"no testharness.js report in {frames} frames (completion never ran)", []
    if result.returncode != 0:
        tail = result.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        return f"viewer exit {result.returncode}: {tail[0][:160]}", []
    harness, subtests = None, []
    for line in stdout.splitlines():
        fields = line.split("\t")
        if fields[0] == "HARNESS" and harness is None:
            harness = (fields[1] if len(fields) > 1 else "", fields[2] if len(fields) > 2 else "")
        elif fields[0] == "SUBTEST" and len(fields) >= 3:
            subtests.append((fields[1], fields[2], fields[3] if len(fields) > 3 else ""))
    if harness is None:
        return "report without a HARNESS line", []
    if not subtests:
        return f"testharness.js completed with zero subtests (harness status {harness[0]})", []
    if harness[0] != "OK":
        return f"testharness.js harness status {harness[0]}" + (f": {harness[1]}" if harness[1] else ""), []
    return None, subtests


def key_of(relative, name):
    return relative + "::" + name.rstrip(" \t")


def load_known(path):
    if not os.path.exists(path):
        return None
    known = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            cut = next((i for i, c in enumerate(line) if c == "#" and (i == 0 or line[i - 1] != "\\")), len(line))
            entry = line[:cut].strip().replace("\\#", "#")
            if entry:
                known[entry] = line[cut + 1 :].strip()
    return known


def write_known(path, outcomes, known, documents):
    """outcomes: key -> (ok, status, detail) for this run; entries of documents not run stay."""
    run = set(documents)
    failing = {k: r for k, r in (known or {}).items() if k.split("::", 1)[0] not in run}
    for key, (ok, status, _) in outcomes.items():
        if not ok:
            failing[key] = (known or {}).get(key) or f"untriaged, {status} at baseline"
    lines = list(KNOWN_HEADER)
    for key, reason in sorted(failing.items()):
        lines.append(f"{key.replace('#', chr(92) + '#')}  # {reason}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run(args, viewer, root, jobs, extra):
    """Runs the suite and prints its report; returns (exit code, the documents run)."""
    documents = discover(root, args.filter)
    if not documents:
        return 0, []
    print(f"wpt dom: {len(documents)} testharness.js documents ({SUBSET_NAMES}), {WIDTH}x{HEIGHT}, "
          f"at most {args.dom_frames} frames, software backend, no render, {jobs} jobs")
    reports = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run_one, viewer, root, d, args.dom_frames, args.timeout, extra): d for d in documents}
        for future in concurrent.futures.as_completed(futures):
            reports[futures[future]] = future.result()

    outcomes = {}  # key -> (ok, status, detail)
    for relative in documents:
        error, subtests = reports[relative]
        if error:
            outcomes[relative] = (False, "ERROR", error)
            continue
        for status, name, message in subtests:
            outcomes[key_of(relative, name)] = (status == "PASS", status, message)

    known_path = args.known_dom
    known = load_known(known_path)
    regressions, newly_passing = [], []
    for key, (ok, status, detail) in outcomes.items():
        listed = known is not None and key in known
        if ok and listed:
            newly_passing.append(key)
            print(f"  ok(!)          {key}: passes now -- remove from known_failures_dom.txt")
        elif ok:
            if args.verbose:
                print(f"  ok             {key}")
        else:
            word = status.lower() if listed or known is None else status
            print(f"  {(word + '(known)') if listed else word:<14} {key}: {detail[:200]}")
            if known is not None and not listed:
                regressions.append(key)
    run_set = set(documents)
    stale = sorted(k for k in (known or {}) if k.split("::", 1)[0] in run_set and k not in outcomes)
    for key in stale:
        print(f"  stale          {key}: listed in known_failures_dom.txt, not reported by this run")

    errors = sum(1 for k in outcomes if "::" not in k)
    subtests = {k: v for k, v in outcomes.items() if "::" in k}
    passed = sum(1 for ok, _, _ in subtests.values() if ok)
    print(f"wpt dom: karouka {passed}/{len(subtests)} subtests passed"
          f" ({100.0 * passed / max(1, len(subtests)):.1f}%) in {len(documents) - errors} documents, "
          f"{errors} whole-file errors")

    if args.write_known:
        write_known(known_path, outcomes, known, documents)
        print(f"wpt dom: wrote {known_path}")
        return 0, documents
    if known is None:
        print(f"wpt dom: no {known_path}: nothing to ratchet against (--write-known records this run)")
        return 0, documents
    if regressions:
        print(f"wpt dom: {len(regressions)} subtest(s)/file(s) outside known_failures_dom.txt failed")
    if newly_passing:
        print(f"wpt dom: {len(newly_passing)} known_failures_dom.txt entr(ies) pass now; delete their lines")
    if stale:
        print(f"wpt dom: {len(stale)} known_failures_dom.txt entr(ies) matched nothing; delete them")
    return (1 if regressions or newly_passing or stale else 0), documents
