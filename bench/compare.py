#!/usr/bin/env python3
"""Benchmark karouka on a fixed set of pages with one harness: karouka alone, or two karouka builds
against each other (A/B).

Modes:
  default       karouka alone (--karouka-only, accepted for compatibility, is the same).
  --ab A B      two karouka builds, each its own karouka_viewer + libkarouka.dylib. A and B are
                directories holding both files, names of builds saved with `tools/dev.sh bench
                --save NAME` (under $KAROUKA_BENCH_BUILDS), or `current` (--karouka-viewer and the
                libkarouka.dylib its rpath finds; from dev.sh, a snapshot of the build). Each viewer
                gets DYLD_LIBRARY_PATH=<its dir>, then $KAROUKA_BENCH_LIB when set; a saved viewer's
                rpath still points at the shared build's lib/, which holds whatever was built last,
                so before timing anything each side is run once with DYLD_PRINT_LIBRARIES and must
                load libkarouka.dylib, and every other dylib its dir holds, from its own dir. A save
                from dev.sh holds the vcpkg and Skia dylibs too (libmimalloc among them), so
                an A/B of a change in one of them needs no hand-made DYLD_LIBRARY_PATH copies; an
                older save without them takes those from $KAROUKA_BENCH_LIB, the same on both sides.
                Each side's build.txt (for `current`, $KAROUKA_CURRENT_BUILD_INFO from dev.sh) names
                the Ladybird tree it was built from; when A's and B's differ it warns: the
                dylib links Ladybird in, so the deltas include every patch one side had and the other
                didn't (patch 0032 once showed up as ~3 MB on every page, an RSS skew).
                --same-ladybird turns that warning into a refusal: exit 1 before anything
                runs when the trees differ or either side's can't be told (no build info).
  Both print a summary table and write DIR/summary.md; their default --out is
  bench/results/karouka or bench/results/ab.

Every viewer runs headless (offscreen Metal, unpaced: each frame is update + render + GPU wait),
at the same size and scale, for the same number of frames, one after the other, never in
parallel. Every (build, page, scenario) runs --runs times, the builds interleaved run by run,
and the median is reported.

Measured from outside the process, identically for every build (wait4's rusage, as
/usr/bin/time -l reports it, read here directly: /usr/bin/time is SIP-protected, so dyld strips
DYLD_* from it and from the viewer it starts, which the A/B mode needs):
  wall time, CPU time (user+sys), CPU % of one core, peak RSS (max resident set size),
  and time per frame = wall / frames.
Per-frame cost comes from the viewer's own frame-loop line where it prints one:
  frame-loop engine=E page=P frames=N wall_s=W cpu_s=C cpu_pct=X frame_p50=A frame_p95=B cpu_p50=D cpu_p95=E
  the frame loop after the first frame (N = frames - 1), timed in process: wall clock and
  getrusage (user + sys, every thread) from the end of frame 0 to the end of the last frame, and
  each of those frames' wall and CPU ms. ms/frame = W / N and CPU ms/frame = C / N, with p50/p95.
  karouka_viewer prints it under --stats; without one, the per-frame figures fall back to
  (run - startup) / (frames - 1) of the process times above, a difference of two medians each with
  ~1 ms resolution (results.json: per_frame_source).
The paced scenario runs the viewer headless with --fps 60 for --paced-frames frames: each
frame waits for its 16.67 ms slot in real time, so CPU % at 60 fps is the frame loop's cpu_s / wall_s,
measured, where the unpaced scenarios can only derive it (CPU ms/frame x 60). No memory run for it.
paced_long is the same at --paced-long-frames frames (default 1200: 20 s a run), for a busy
page's frame p95, which 120 frames hardly sample. It adds minutes, so it runs only when named:
--scenario paced_long. Its figures are a scenario of their own in results.json and summary.md.
Pages: PAGES (name, page); animated_churn is LibWeb's animated-image decode, a busy page
for frame p95 and RSS A/Bs.
Measured inside the viewer (--stats) and reported where available: frame p50/p95,
update/record/raster/gpu p50, and the frames it rendered of the run's (`rendered`).
karouka_viewer times kr_view_render (`raster`, which only submits) and its own commit +
waitUntilCompleted (`gpu`) separately; render_p50_ms is raster_p50 + gpu_p50 of the same run (a sum
of medians, not the median of per-frame sums). With --engine-gpu, kr_view_render waits itself and
gpu is 0, so the sum is still the whole frame.
Shader cache: every run of a page reads and writes that page's own
file, DIR/shader-cache/<engine>/<page>.bin (--shader-cache), not the viewer's machine-wide
~/Library/Caches/karouka/skia-shaders.bin, whose warm list is whatever page last ran on the machine,
so startup and first-frame figures would depend on the bench's previous page or the last
`dev.sh run`. Before a page's first timed run the file is removed and remade by one untimed run of
the page (--frames frames, as steady), so every timed run is a second launch of an app that has shown
this page before, and the same in every bench. A 1-frame KR_DEBUG run on a copy of that file then
reads its `shader cache: N programs from ..., M precompiled` line into results.json (shader_cache:
programs, precompiled), printed as the page's `shader cache` line and, per page and engine, listed
in summary.md.
Memory by subsystem: one more run per page
and scenario, not timed, with --memory-stats, which prints kr_system_memory_usage's bytes per tag at
the end of the run (GC heap live/allocated, GPU cache, display lists, decoded images, font cache,
malloc total, surfaces). Its walk of the VM regions takes tens of ms, so it stays out of the timed
runs. Printed next to that run's peak RSS; --no-memory skips it.

Load: before each timed run it waits, polling, for the 1-minute load average to fall to
--max-load (default half the logical cores), out of one --load-wait budget for the whole bench
(default 120 s); once that is spent, runs start at whatever the load is. Every run records the load
it started at, and summary.md gives their spread and says how many started above --max-load.
summary.md also gives each row's per-run coefficient of variation (stdev / mean over the runs; a
per-frame row without a frame-loop line takes each run minus the startup median, a difference of two
noisy medians) and flags rows above 10%. CPU ms/frame leads the table:
it moves less with load than wall ms/frame, which includes time spent waiting for a core.

Usage:
  bench/compare.py [--runs 3] [--frames 600] [--size 1280x720] [--only PAGE] [--scenario S]
                   [--karouka-viewer PATH] [--out DIR] [--no-memory]
                   [--max-load L] [--load-wait SECONDS] [--paced-frames 120]
                   [--paced-long-frames 1200]
                   [--karouka-only | --ab A B [--same-ladybird]] [--no-captures]
Writes DIR/results.json, DIR/captures/*.png and DIR/summary.md.
"""

import argparse
import datetime
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (name, page).
PAGES = [
    ("sashimi", "pages/demo/sashimi_page.html"),
    ("showcase", "pages/demo/showcase_page.html"),
    ("animations", "pages/demo/animations_page.html"),
    ("demo", "pages/demo/demo_page.html"),
    ("hud", "pages/demo/hud_page.html"),
    ("trellis", "pages/demo/trellis_page.html"),
    ("text", "pages/tests/text.html"),
    # LibWeb's animated-image decode, a busy page.
    ("animated_churn", "pages/tests/animated_churn.html"),
]

# Scenario -> extra flags for the viewer.
SCENARIOS = {
    # One frame: process start, engine init, page load, first render. Subtracted from the
    # others to get the per-frame cost.
    "startup": ["__frames=1"],
    "steady": [],
    "scroll": ["--scroll", "0,20@60..540"],
    # Paced to 60 fps of real time (--paced-frames frames), so CPU % at 60 fps is measured.
    "paced": ["__frames=paced", "--fps", "60"],
    # The same for --paced-long-frames frames; only when named (OPT_IN_SCENARIOS).
    "paced_long": ["__frames=paced_long", "--fps", "60"],
}
# Scenarios that run only when --scenario names them: they add minutes to a bench.
OPT_IN_SCENARIOS = {"paced_long"}
# Scenarios paced to real time: no memory run.
PACED_SCENARIOS = {"paced", "paced_long"}

# A row whose per-run coefficient of variation is above this is flagged in summary.md.
NOISY_CV = 0.10


class LoadGate:
    """Before each timed run, wait (polling) for the 1-minute load average to fall to
    max_load, out of one budget for the whole bench. The old gate retook a sample once, right away,
    when the load had been above 12: the 1-minute average hardly moves in the second a run takes, so
    the retake ran at the same load. The average lags (its time constant is a minute) and counts the
    bench's own runs, so the default limit leaves half the cores' worth of room."""

    def __init__(self, max_load, budget_s):
        self.max_load, self.budget_s, self.waited_s, self.spent_noted = max_load, budget_s, 0.0, False

    def wait(self):
        start = time.monotonic()
        noted = False
        while (load := os.getloadavg()[0]) > self.max_load:
            if self.waited_s + time.monotonic() - start >= self.budget_s:
                if not self.spent_noted and self.budget_s > 0:
                    print(f"WARN --load-wait budget ({self.budget_s:.0f} s) spent: runs now start at whatever "
                          f"the load is (now {load:.1f}, --max-load {self.max_load:g})", flush=True)
                self.spent_noted = True
                break
            if not noted:
                print(f"load {load:.1f} > --max-load {self.max_load:g}: waiting", flush=True)
                noted = True
            time.sleep(2)
        waited = time.monotonic() - start
        self.waited_s += waited
        return waited


def parse_frame_loop(stdout):
    """The viewer's `frame-loop ...` line (the first view's) -> loop_* fields, {} when it
    printed none or its loop had no frames (a one-frame run)."""
    m = re.search(r"^frame-loop (.*)$", stdout, re.M)
    if not m:
        return {}
    fields = dict(kv.split("=", 1) for kv in m.group(1).split() if "=" in kv)
    try:
        frames = int(fields["frames"])
        wall, cpu = float(fields["wall_s"]), float(fields["cpu_s"])
    except (KeyError, ValueError):
        return {}
    if frames <= 0 or wall <= 0:
        return {}
    result = {"loop_frames": frames, "loop_wall_s": wall, "loop_cpu_s": cpu,
              "loop_ms_per_frame": wall * 1000 / frames, "loop_cpu_ms_per_frame": cpu * 1000 / frames,
              "loop_cpu_pct": 100 * cpu / wall}
    for k in ("frame_p50", "frame_p95", "cpu_p50", "cpu_p95"):
        if k in fields:
            result[f"loop_{k}_ms"] = float(fields[k])
    return result


def parse_karouka(stdout, frames=None):
    m = re.search(r"^karouka-stats (.*)$", stdout, re.M)
    if not m:
        return parse_frame_loop(stdout)
    fields = dict(kv.split("=", 1) for kv in m.group(1).split())
    keys = {"frame_p50": "frame_p50_ms", "frame_p95": "frame_p95_ms", "update_p50": "update_p50_ms",
            "record_p50": "record_p50_ms", "raster_p50": "raster_p50_ms", "gpu_p50": "gpu_p50_ms",
            "rendered": "frames_rendered"}
    result = {out: float(fields[k]) for k, out in keys.items() if k in fields}
    if "raster_p50_ms" in result:
        # An older viewer prints no gpu field, and its raster already includes the wait.
        result["render_p50_ms"] = result["raster_p50_ms"] + result.get("gpu_p50_ms", 0.0)
    result.update(parse_frame_loop(stdout))
    return result


def parse_karouka_memory(stdout):
    """karouka_viewer --memory-stats: `karouka-memory-usage gc_heap_live_mb=1.23 ...` -> {tag: MB}."""
    m = re.search(r"^karouka-memory-usage (.*)$", stdout, re.M)
    if not m:
        return {}
    fields = dict(kv.split("=", 1) for kv in m.group(1).split())
    return {k[:-3]: float(v) for k, v in fields.items() if k.endswith("_mb")}


def format_memory(memory):
    return " ".join(f"{tag} {mb:.1f}" for tag, mb in memory.items()) + " (MB)"


def run(command, cwd, env=None):
    """Runs command and times it as /usr/bin/time -l would (wall clock around the child, its wait4
    rusage), without exec'ing the SIP-protected /usr/bin/time, which would drop DYLD_* from env."""
    started = datetime.datetime.now()
    load = os.getloadavg()[0]
    with tempfile.TemporaryFile("w+") as out, tempfile.TemporaryFile("w+") as err:
        begin = time.perf_counter()
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=out, stderr=err, text=True)
        watchdog = threading.Timer(900, proc.kill)
        watchdog.start()
        try:
            _, status, usage = os.wait4(proc.pid, 0)
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        finally:
            watchdog.cancel()
        wall = time.perf_counter() - begin
        proc.returncode = os.waitstatus_to_exitcode(status)
        out.seek(0)
        err.seek(0)
        stdout, stderr = out.read(), err.read()
    # macOS reports ru_maxrss in bytes (time -l's "maximum resident set size").
    result = {"wall_s": wall, "cpu_s": usage.ru_utime + usage.ru_stime, "peak_rss_mb": usage.ru_maxrss / 1048576}
    result["exit"] = proc.returncode
    result["load_avg_1m"] = round(load, 2)
    result["started"] = started.isoformat(timespec="seconds")
    if proc.returncode != 0:
        result["error"] = (stderr.strip().splitlines() or ["?"])[-1][:300]
    return result, stdout


SHADER_CACHE_LINE = re.compile(r"shader cache: (\d+) programs from .*?, (\d+) precompiled")


def seed_shader_cache(viewer, page, cache, frames, size, cwd, env):
    """Remakes CACHE, the page's own shader cache, with one untimed run of the page, then
    reads what the next launch precompiles from it: a 1-frame KR_DEBUG run on a copy, so the probe
    doesn't change the file the timed runs read. -> {programs, precompiled} or {error}."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.unlink(missing_ok=True)
    base = [viewer, page, "--headless", "--size", size, "--scale", "1"]
    seed = subprocess.run([*base, "--frames", str(frames), "--shader-cache", str(cache)], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=900)
    if seed.returncode != 0 or not cache.exists():
        return {"error": f"seed run exit {seed.returncode}, {'no' if not cache.exists() else 'a'} cache file"}
    with tempfile.TemporaryDirectory() as tmp:
        probe_cache = Path(tmp) / cache.name
        probe_cache.write_bytes(cache.read_bytes())
        probe = subprocess.run([*base, "--frames", "1", "--shader-cache", str(probe_cache)], cwd=cwd,
                               env={**(env or os.environ), "KR_DEBUG": "1"}, capture_output=True, text=True, timeout=300)
    match = SHADER_CACHE_LINE.search(probe.stdout + probe.stderr)
    if not match:
        return {"error": f"probe run exit {probe.returncode}, no 'shader cache: N programs' line"}
    return {"programs": int(match.group(1)), "precompiled": int(match.group(2))}


def median_of(runs, key):
    values = [r[key] for r in runs if r.get(key) is not None and r.get("exit") == 0]
    return statistics.median(values) if values else None


def resolve_build(spec, current_viewer, builds_dir):
    """--ab side -> (karouka_viewer, dir holding the libkarouka.dylib it must load)."""
    if spec == "current":
        viewer = Path(current_viewer)
        return viewer, viewer.parent.parent / "lib"
    path = Path(spec)
    if not path.is_dir() and builds_dir and (Path(builds_dir) / spec).is_dir():
        path = Path(builds_dir) / spec
    if not path.is_dir():
        sys.exit(f"--ab: {spec} is not `current`, a directory, or a build saved in {builds_dir or '$KAROUKA_BENCH_BUILDS'}")
    return path / "karouka_viewer", path


def read_build_info(spec, viewer, current_info):
    """--ab side -> {key: value} from its build.txt (dev.sh bench --save) or, for `current`, the file
    dev.sh _bench writes ($KAROUKA_CURRENT_BUILD_INFO); {} when there is none (an old save, compare.py
    run without dev.sh)."""
    if spec == "current":
        if not current_info:
            return {}
        path = Path(current_info)
    else:
        path = Path(viewer).parent / "build.txt"
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    info = dict(line.split(None, 1) for line in lines if len(line.split(None, 1)) == 2)
    # dev.sh's build_info line: `build    ladybird_tree=ID series=match|differs owner=... karouka=...`.
    info.update(field.split("=", 1) for field in info.get("build", "").split() if "=" in field)
    # Older saves have the earlier lines instead: `ladybird ID [(last applied ...)]`, `commit C`.
    if "ladybird_tree" not in info and info.get("ladybird"):
        info["ladybird_tree"] = info["ladybird"].split()[0]
    if "karouka" not in info and info.get("commit"):
        info["karouka"] = info["commit"]
    return info


def build_mismatch(infos):
    """Why an A/B's deltas may not be the change under test, or None. libkarouka.dylib links
    Ladybird in, so two builds from different Ladybird trees (another checkout's patch series, an
    owner's unsaved edits) differ by those patches too: patch 0032 once read as ~3 MB on every page,
    an RSS skew between builds. Different karouka commits are the usual before/after and pass."""
    a, b = infos.get("A", {}), infos.get("B", {})
    missing = [n for n, i in (("A", a), ("B", b)) if i.get("ladybird_tree", "?") == "?"]
    if missing:
        return (f"can't tell whether A and B share a Ladybird tree: no build info for {' and '.join(missing)} "
                "(save both with this tools/dev.sh bench --save)")
    if a["ladybird_tree"] != b["ladybird_tree"]:
        return (f"A and B were built from different Ladybird trees (A {a['ladybird_tree']}, B {b['ladybird_tree']}; "
                f"series A {a.get('series', '?')}, B {b.get('series', '?')}). Unless the change under test is a "
                "Ladybird patch, the deltas include Ladybird changes it didn't make: save both sides from one "
                "checkout, before and after the change")
    return None


def check_loads(viewer, lib_dir, env, page):
    """dyld must take libkarouka.dylib, and every other dylib lib_dir holds (a save's vcpkg
    copies, libmimalloc among them), from lib_dir, not from the viewer's rpath (the shared build)."""
    probe = subprocess.run([str(viewer), page, "--headless", "--frames", "1"], cwd=ROOT, capture_output=True, text=True,
                           env={**env, "DYLD_PRINT_LIBRARIES": "1"}, timeout=300)
    loaded = [l.split()[-1] for l in probe.stderr.splitlines() if l.rstrip().endswith(".dylib")]
    first = [p for p in loaded if p.endswith("/libkarouka.dylib")]
    want = str((lib_dir / "libkarouka.dylib").resolve())
    if not first or Path(first[0]).resolve() != Path(want):
        sys.exit(f"{viewer} loads {first[0] if first else 'no libkarouka.dylib'}, not {want} (exit {probe.returncode})")
    own = {p.name for p in lib_dir.glob("*.dylib")}
    strays = [p for p in loaded if Path(p).name in own and Path(p).resolve().parent != lib_dir.resolve()]
    if strays:
        sys.exit(f"{viewer} loads {strays[0]} although {lib_dir} holds {Path(strays[0]).name} (exit {probe.returncode})")
    held = sorted({Path(p).name for p in loaded if Path(p).resolve().parent == lib_dir.resolve()} - {"libkarouka.dylib"})
    return held


# (label, key, scale, per_frame, loop_key): summary rows. loop_key is the in-process figure from
# the viewer's frame-loop line, used where the run has it; otherwise a per-frame row is
# (run − startup) / (frames − 1) of key, and any other row the median of key.
# CPU ms/frame leads: wall ms/frame also counts time spent waiting for a core.
METRICS = [("CPU ms/frame", "cpu_s", 1000, True, "loop_cpu_ms_per_frame"),
           ("ms/frame", "wall_s", 1000, True, "loop_ms_per_frame"),
           ("CPU %", None, 1, False, "loop_cpu_pct"),
           ("frame p50", "frame_p50_ms", 1, False, "loop_frame_p50_ms"),
           ("frame p95", "frame_p95_ms", 1, False, "loop_frame_p95_ms"),
           ("CPU p50", None, 1, False, "loop_cpu_p50_ms"), ("CPU p95", None, 1, False, "loop_cpu_p95_ms"),
           ("wall ms", "wall_s", 1000, False, None), ("peak RSS MB", "peak_rss_mb", 1, False, None),
           ("update p50", "update_p50_ms", 1, False, None), ("record p50", "record_p50_ms", 1, False, None),
           ("raster+gpu p50", "render_p50_ms", 1, False, None)]


def metric_value(run, startup, key, scale, per_frame, loop_key=None):
    """A summary row's figure from the medians: the frame loop's in-process figure, the
    per-frame cost from process times, or the median itself."""
    if run and loop_key and run.get(loop_key) is not None:
        return run[loop_key]
    if not run or key is None or run.get(key) is None:
        return None
    if not per_frame:
        return run[key] * scale
    if not startup or startup.get(key) is None or run["frames"] <= 1:
        return None
    return max(run[key] - startup[key], 0) * scale / (run["frames"] - 1)


def per_frame_source(run):
    """results.json: where a result's per-frame figures come from."""
    return "frame-loop" if run.get("loop_ms_per_frame") is not None else "process-difference"


def run_cv(run, startup, key, per_frame, loop_key=None):
    """Per-run coefficient of variation (stdev / mean) of a summary row, or None with under two runs.
    The frame loop's in-process figure where every run has one. Otherwise a per-frame row
    takes each run minus the startup median, so the startup's own noise is not in it; a mean at or
    below zero (runs no slower than startup) is all noise and gives inf."""
    if not run:
        return None
    ok = [s for s in run.get("samples", []) if s.get("exit") == 0]
    if loop_key and ok and all(s.get(loop_key) is not None for s in ok):
        key, per_frame = loop_key, False
    if key is None:
        return None
    values = [s[key] for s in ok if s.get(key) is not None]
    if per_frame:
        if not startup or startup.get(key) is None or run["frames"] <= 1:
            return None
        values = [v - startup[key] for v in values]
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    return statistics.stdev(values) / mean if mean > 0 else float("inf")


def annotate_run_cv(results):
    """results.json: each result's per-run CV by summary row label (for later tools)."""
    by_key = {(r["engine"], r["page"], r["scenario"]): r for r in results}
    for r in results:
        startup = by_key.get((r["engine"], r["page"], "startup"))
        cvs = {}
        for label, key, _scale, per_frame, loop_key in METRICS:
            if per_frame and r["scenario"] == "startup":
                continue
            cv = run_cv(r, startup, key, per_frame, loop_key)
            if cv is not None:
                cvs[label] = cv if cv != float("inf") else "inf"
        r["run_cv"] = cvs


def load_lines(results, meta):
    """The load every timed run started at, and how many started above --max-load."""
    loads = [s["load_avg_1m"] for r in results for s in r.get("samples", []) if s.get("load_avg_1m") is not None]
    if not loads:
        return []
    max_load = meta.get("max_load")
    loaded = sum(1 for v in loads if max_load is not None and v > max_load)
    line = (f"Load (1-minute average as each of the {len(loads)} timed runs started): min {min(loads):.1f}, "
            f"median {statistics.median(loads):.1f}, max {max(loads):.1f}")
    if max_load is not None:
        line += (f"; --max-load {max_load:g}, {meta.get('load_waited_s', 0):.0f} s spent waiting for it "
                 f"(budget {meta.get('load_wait_budget_s', 0):.0f} s)")
    lines = [line + ".", ""]
    if loaded:
        lines += [f"**Warning:** {loaded} of {len(loads)} timed runs started above --max-load {max_load:g} "
                  f"(load up to {max(loads):.1f}). Other processes shared the cores: per-run CV of 28–41% has been seen at "
                  "load 10–17. Rerun when the machine is quiet before calling a per-frame change.", ""]
    return lines


def shader_cache_lines(results, names, pages):
    """summary.md's shader cache section: per page and engine, the programs the page's own
    cache file holds and how many of them the next launch precompiles at startup (the 1-frame probe
    seed_shader_cache runs; the same for every scenario of the page, so the first result's is taken).
    [] when no result carries one (an old results.json)."""
    found = {}
    for r in results:
        if r.get("shader_cache"):
            found.setdefault((r["engine"], r["page"]), r["shader_cache"])
    if not found:
        return []
    lines = ["", "Shader cache (each page's own cache file, remade by an untimed run before its first timed run): "
             "programs in the file, and how many a launch precompiles at startup.", "",
             "| Page | " + " | ".join(f"{n} programs | {n} precompiled" for n in names if any((n, p) in found for p in pages)) + " |"]
    shown = [n for n in names if any((n, p) in found for p in pages)]
    lines.append("| --- | " + " | ".join("---: | ---:" for _ in shown) + " |")
    for page in pages:
        cells = []
        for n in shown:
            sc = found.get((n, page), {})
            cells += [str(sc["programs"]), str(sc["precompiled"])] if "programs" in sc else (["—", "—"] if "error" not in sc else [f"error: {sc['error']}", "—"])
        lines.append(f"| {page} | " + " | ".join(cells) + " |")
    return lines


def summary_lines(results, engines, meta):
    """karouka-only / A/B: one table, each metric per engine; with two engines also the ratio, then
    each engine's per-run CV (bold above NOISY_CV)."""
    by_key = {(r["engine"], r["page"], r["scenario"]): r for r in results}
    names = list(engines)
    pages = list(dict.fromkeys(r["page"] for r in results))
    scenarios = [s for s in SCENARIOS if any(r["scenario"] == s for r in results)]

    head = " | ".join(names) + (f" | {names[1]}/{names[0]}" if len(names) == 2 else "") + " | run CV %"
    lines = [f"# karouka bench: {' vs '.join(n if engines[n] == n else f'{n} = {engines[n]}' for n in names)}", "",
             f"{meta['date']}, {meta['machine']}, karouka `{meta['karouka_commit']}`; median of {meta['runs']} runs, "
             f"{meta['frames']} frames ({meta.get('paced_frames', '—')} for paced"
             + (f", {meta.get('paced_long_frames', '—')} for paced_long" if "paced_long" in scenarios else "")
             + f", at 60 fps of real time), {meta['size']}, "
             "headless. ms/frame, CPU ms/frame, CPU % and the frame / CPU p50/p95 come from the viewer's frame-loop line: "
             "the frames after the first, timed in process; without one, ms/frame = (run − startup) / (frames − 1) "
             "of the process times. CPU ms/frame (user+sys) is the headline: wall ms/frame also counts time spent waiting "
             "for a core; paced CPU % is CPU at 60 fps, measured. "
             f"run CV % = stdev / mean over the runs, per engine (per-frame rows: each run − the startup median); "
             f"above {NOISY_CV:.0%} it is bold.", ""]
    for name, info in meta.get("builds", {}).items():
        # read_build_info's keys (the build line's karouka=, ladybird_tree=), not the raw build.txt lines.
        lines.append(f"- {name}: commit `{info.get('karouka', '?')}`, Ladybird tree `{info.get('ladybird_tree', '?')}`, "
                     f"series `{info.get('series', '?')}`" + (f", tree owned by `{info['owner']}`" if info.get("owner", "none") != "none" else ""))
    if meta.get("builds"):
        lines.append("")
    if meta.get("build_warning"):
        lines += [f"**Warning:** {meta['build_warning']}.", ""]
    lines += load_lines(results, meta)
    rows, noisy = [], []
    for page in pages:
        for scenario in scenarios:
            for label, key, scale, per_frame, loop_key in METRICS:
                if scenario == "startup" and per_frame:
                    continue
                runs = [by_key.get((n, page, scenario)) for n in names]
                startups = [by_key.get((n, page, "startup")) for n in names]
                values = [metric_value(r, s, key, scale, per_frame, loop_key) for r, s in zip(runs, startups)]
                if all(v is None for v in values):
                    continue
                cells = ["—" if v is None else f"{v:.3f}" for v in values]
                if len(values) == 2:
                    cells.append(f"{values[1] / values[0]:.3f}" if values[0] and values[1] is not None else "—")
                cvs = [run_cv(r, s, key, per_frame, loop_key) for r, s in zip(runs, startups)]
                cv_cells = []
                for cv in cvs:
                    text = "—" if cv is None else "inf" if cv == float("inf") else f"{cv * 100:.0f}"
                    cv_cells.append(f"**{text}**" if cv is not None and cv > NOISY_CV else text)
                cells.append(" / ".join(cv_cells))
                if any(cv is not None and cv > NOISY_CV for cv in cvs):
                    noisy.append((page, scenario, label))
                rows.append(f"| {page} | {scenario} | {label} | " + " | ".join(cells) + " |")
    headline = [n for n in noisy if n[2] == "CPU ms/frame"]
    if noisy:
        lines += [f"**Warning:** {len(noisy)} of {len(rows)} rows have a per-run CV above {NOISY_CV:.0%}"
                  + (f", {len(headline)} of them CPU ms/frame ({', '.join(f'{p} {s}' for p, s, _ in headline)})" if headline else "")
                  + ". Their medians and ratios are within the noise: rerun with more --runs on a quiet machine, "
                  "and swap the A/B sides, before reading a change into them.", ""]
    lines += [f"| Page | Scenario | Metric | {head} |", "| --- | --- | --- | " + " | ".join("---:" for _ in head.split(" | ")) + " |"]
    lines += rows
    lines += shader_cache_lines(results, names, pages)
    lines += ["", "Process times have 1 ms resolution here (perf_counter, rusage), not time -l's 10 ms; "
              "the frame-loop figures and the in-process p50s come from each viewer's --stats."]
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--paced-frames", type=int, default=120,
                        help="frames of the paced scenario, at 60 fps of real time (default 120: 2 s a run)")
    parser.add_argument("--paced-long-frames", type=int, default=1200,
                        help="frames of the opt-in paced_long scenario (--scenario paced_long), at 60 fps of real "
                             "time (default 1200: 20 s a run)")
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--only", action="append")
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--karouka-viewer", default=os.environ.get("KAROUKA_VIEWER", str(ROOT / "third_party/ladybird/Build/release/karouka/bin/karouka_viewer")))
    parser.add_argument("--out")
    parser.add_argument("--max-load", type=float, default=(os.cpu_count() or 2) / 2,
                        help="before each timed run, wait for the 1-minute load average to fall to this "
                             "(default: half the logical cores); runs that start above it are flagged")
    parser.add_argument("--load-wait", type=float, default=120.0,
                        help="seconds the whole bench may spend waiting for --max-load (default 120)")
    parser.add_argument("--no-memory", action="store_true", help="skip karouka's untimed per-subsystem memory run")
    parser.add_argument("--no-captures", action="store_true", help="skip the one PNG per engine and page")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--karouka-only", action="store_true", help="karouka alone (the default)")
    mode.add_argument("--ab", nargs=2, metavar=("A", "B"), help="two karouka builds: dirs, saved names, or `current`")
    parser.add_argument("--builds-dir", default=os.environ.get("KAROUKA_BENCH_BUILDS"), help="where --ab looks up saved names")
    parser.add_argument("--same-ladybird", action="store_true",
                        help="--ab: exit 1 instead of warning when A and B weren't built from one Ladybird tree (or can't tell)")
    args = parser.parse_args()
    if args.same_ladybird and not args.ab:
        parser.error("--same-ladybird needs --ab")

    # name -> (kind, viewer, cwd, parse, env, label)
    env = dict(os.environ)
    build_infos, mismatch = {}, None
    if args.ab:
        if args.ab[0] == args.ab[1]:
            sys.exit("--ab: A and B are the same build")
        engines, sides = {}, {}
        for name, spec in zip(("A", "B"), args.ab):
            viewer, lib_dir = resolve_build(spec, args.karouka_viewer, args.builds_dir)
            if not viewer.exists() or not (lib_dir / "libkarouka.dylib").exists():
                sys.exit(f"--ab {spec}: needs {viewer} and {lib_dir / 'libkarouka.dylib'}")
            sides[name] = (viewer, lib_dir)
            # $KAROUKA_BENCH_LIB (dev.sh: its snapshot's lib/) after it: a saved viewer takes
            # its libkarouka.dylib from its own dir and the vcpkg and Skia dylibs from the snapshot, not
            # from the shared build another checkout may be rebuilding.
            side_env = {**env, "DYLD_LIBRARY_PATH": ":".join(
                [str(lib_dir.resolve())] + ([os.environ["KAROUKA_BENCH_LIB"]] if os.environ.get("KAROUKA_BENCH_LIB") else []))}
            engines[name] = ("karouka", str(viewer), ROOT, parse_karouka, side_env, spec)
            # dev.sh's file describes its own build, not a --karouka-viewer given by hand.
            current_info = os.environ.get("KAROUKA_CURRENT_BUILD_INFO") if args.karouka_viewer == os.environ.get("KAROUKA_VIEWER") else None
            build_infos[name] = read_build_info(spec, viewer, current_info)
            for key in ("karouka", "ladybird_tree", "series", "owner"):
                if key != "owner" or build_infos[name].get(key, "none") != "none":
                    print(f"{name} {key:13} {build_infos[name].get(key, '?')}", flush=True)
        mismatch = build_mismatch(build_infos)
        if mismatch and args.same_ladybird:
            sys.exit(f"--same-ladybird: {mismatch}")
        if mismatch:
            print(f"WARN {mismatch}", flush=True)
        # Only now run anything: a refused A/B exits before the first viewer starts.
        for name, (viewer, lib_dir) in sides.items():
            held = check_loads(viewer, lib_dir, engines[name][4], PAGES[0][1])
            print(f"{name} loads libkarouka.dylib and {len(held)} more dylib(s) from {lib_dir}"
                  + (f" ({', '.join(d for d in held if 'mimalloc' in d)})" if any('mimalloc' in d for d in held) else ""), flush=True)
        mode_name = "ab"
    else:
        engines = {"karouka": ("karouka", args.karouka_viewer, ROOT, parse_karouka, None, "karouka")}
        mode_name = "karouka"
    for name, (_kind, viewer, *_rest) in engines.items():
        if not Path(viewer).exists():
            sys.exit(f"{name} viewer not found: {viewer}")

    out = Path(args.out or (ROOT / "bench/results" / mode_name))
    (out / "captures").mkdir(parents=True, exist_ok=True)
    pages = [p for p in PAGES if not args.only or p[0] in args.only]
    scenarios = {k: v for k, v in SCENARIOS.items()
                 if (k in args.scenario if args.scenario else k not in OPT_IN_SCENARIOS)}
    results = []
    load_gate = LoadGate(args.max_load, args.load_wait)
    for page_name, karouka_page in pages:
        # Each karouka engine's own shader cache for this page, remade before its first run.
        shader_caches, shader_cache_stats = {}, {}
        for name, (kind, viewer, cwd, _parse, run_env, _label) in engines.items():
            if kind != "karouka":
                continue
            shader_caches[name] = (out / "shader-cache" / name / f"{page_name}.bin").resolve()
            shader_cache_stats[name] = seed_shader_cache(viewer, karouka_page, shader_caches[name], args.frames, args.size, cwd, run_env)
            stats = shader_cache_stats[name]
            print(f"{name:8} {page_name:11} shader cache: " + (stats["error"] if "error" in stats else
                  f"{stats['programs']} programs, {stats['precompiled']} precompiled at startup ({shader_caches[name]})"), flush=True)
        for scenario, flags in scenarios.items():
            frames = args.frames
            if flags and flags[0].startswith("__frames="):
                value = flags[0].split("=")[1]
                frames = {"paced": args.paced_frames, "paced_long": args.paced_long_frames}.get(value) or int(value)
            cmd_flags = [f for f in flags if not f.startswith("__frames=")]
            commands, samples = {}, {name: [] for name in engines}
            for name, (kind, viewer, cwd, parse_stats, run_env, _label) in engines.items():
                page = karouka_page
                commands[name] = [viewer, page, "--headless", "--frames", str(frames), "--size", args.size, "--scale", "1", "--stats", *cmd_flags]
                if name in shader_caches:
                    commands[name] += ["--shader-cache", str(shader_caches[name])]
            # Engines alternate run by run, so a load spike lands on both rather than on one.
            for i in range(args.runs):
                for name, (kind, viewer, cwd, parse_stats, run_env, _label) in engines.items():
                    waited = load_gate.wait()
                    sample, stdout = run(commands[name], cwd, run_env)
                    if waited >= 0.5:
                        sample["load_wait_s"] = round(waited, 1)
                    sample["loaded"] = sample["load_avg_1m"] > args.max_load
                    sample.update(parse_stats(stdout, frames))
                    samples[name].append(sample)
                    print(f"{name:8} {page_name:11} {scenario:7} run {i + 1}: "
                          f"wall {sample.get('wall_s', 0):.2f}s cpu {sample.get('cpu_s', 0):.2f}s "
                          f"rss {sample.get('peak_rss_mb', 0):.0f}MB exit {sample['exit']} "
                          f"load {sample['load_avg_1m']:.1f}{' LOADED' if sample['loaded'] else ''}", flush=True)
            for name, (kind, viewer, cwd, parse_stats, run_env, _label) in engines.items():
                summary = {"engine": name, "page": page_name, "scenario": scenario, "frames": frames, "samples": samples[name]}
                if name in shader_cache_stats:
                    summary["shader_cache"] = shader_cache_stats[name]
                for key in ["wall_s", "cpu_s", "peak_rss_mb", "frame_p50_ms", "frame_p95_ms", "update_p50_ms",
                            "record_p50_ms", "raster_p50_ms", "gpu_p50_ms", "render_p50_ms",
                            "load_avg_1m", "frames_rendered",
                            "loop_frames", "loop_wall_s", "loop_cpu_s", "loop_ms_per_frame", "loop_cpu_ms_per_frame",
                            "loop_cpu_pct", "loop_frame_p50_ms", "loop_frame_p95_ms", "loop_cpu_p50_ms", "loop_cpu_p95_ms"]:
                    summary[key] = median_of(samples[name], key)
                if scenario != "startup":
                    summary["per_frame_source"] = per_frame_source(summary)
                if summary["wall_s"]:
                    summary["ms_per_frame"] = summary["wall_s"] * 1000 / frames
                    summary["cpu_pct"] = 100 * summary["cpu_s"] / summary["wall_s"]
                summary["failed_runs"] = sum(1 for s in samples[name] if s["exit"] != 0)
                summary["loaded_runs"] = sum(1 for s in samples[name] if s.get("loaded"))
                # The paced run does the steady run's work, only slower: no memory run of its own.
                if kind == "karouka" and not args.no_memory and scenario not in PACED_SCENARIOS:
                    sample, stdout = run([*commands[name], "--memory-stats"], cwd, run_env)
                    memory = parse_karouka_memory(stdout)
                    if memory:
                        summary["memory_mb"] = memory
                        summary["memory_peak_rss_mb"] = sample.get("peak_rss_mb")
                        print(f"{name:8} {page_name:11} {scenario:7} memory: rss {sample.get('peak_rss_mb', 0):.0f}MB = "
                              f"{format_memory(memory)}", flush=True)
                    else:
                        print(f"{name:8} {page_name:11} {scenario:7} memory: no karouka-memory-usage line, exit {sample['exit']}", flush=True)
                results.append(summary)

            # One capture per engine per page, from the steady scenario.
            if scenario == "steady" and not args.no_captures:
                for name, (kind, viewer, cwd, _parse, run_env, _label) in engines.items():
                    page = karouka_page
                    capture = out / "captures" / f"{page_name}-{name}.png"
                    cache_flags = ["--shader-cache", str(shader_caches[name])] if name in shader_caches else []
                    subprocess.run([viewer, page, "--headless", "--frames", "60", "--size", args.size, "--scale", "1",
                                    "--capture", str(capture), *cache_flags], cwd=cwd, env=run_env, capture_output=True, timeout=300)

    meta = {
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "machine": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip(),
        "runs": args.runs, "frames": args.frames, "paced_frames": args.paced_frames, "paced_long_frames": args.paced_long_frames, "size": args.size, "mode": mode_name,
        "max_load": args.max_load, "load_wait_budget_s": args.load_wait, "load_waited_s": round(load_gate.waited_s, 1),
        "engines": {name: e[5] for name, e in engines.items()},
        "karouka_commit": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
    }
    if build_infos:
        meta["builds"] = build_infos
        meta["build_warning"] = mismatch
    annotate_run_cv(results)
    (out / "results.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2))
    print(f"wrote {out / 'results.json'}", flush=True)
    lines = summary_lines(results, meta["engines"], meta)
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"wrote {out / 'summary.md'}")

if __name__ == "__main__":
    main()
