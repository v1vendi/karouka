#!/usr/bin/env python3
"""Same local page (page/bench.html) in karouka (headless and windowed), Ladybird, Electron, Tauri
and TinyJS. Build the engines first with setup.sh; both write to the work dir (default
bench/engines/.work, or $KR_ENGINES_WORK). README.md says what is measured and what isn't.

Per run, measured from outside the process the same way for every engine:
  startup_ms     spawn -> the page's `first_frame` marker (load + two animation frames)
  startup_cpu_ms CPU (user+sys) of the whole process tree up to that marker
  ff_mem_mb      summed phys_footprint of the tree at the marker
  steady         10 s of rAF-driven DOM updates (capped at 60/s): CPU % of one core, CPU ms per
                 update, peak summed footprint and RSS, fps and frame-interval p95 as the page saw them
  js_ms, dom_ms  the page's fixed synchronous workload (performance.now inside the page)
The process tree is the launched process and every descendant, plus (for WKWebView hosts) the
com.apple.WebKit.* XPC processes that appear after launch: launchd starts those, not the app.
WindowServer's compositing of windowed engines is not counted.

  python3 -I bench/engines/perfcmp.py --runs 7 --max-load 5
"""

import argparse, ctypes, json, os, re, signal, statistics, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DIR = os.path.join(HERE, "page")
PAGE = os.path.join(PAGE_DIR, "bench.html")
WORK = os.path.abspath(os.environ.get("KR_ENGINES_WORK") or os.path.join(HERE, ".work"))

libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)


class RUsageV4(ctypes.Structure):
    _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(f"f{i}", ctypes.c_uint64) for i in range(35)]


class Timebase(ctypes.Structure):
    _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]


tb = Timebase()
libc.mach_timebase_info(ctypes.byref(tb))
TICK_NS = tb.numer / tb.denom
libc.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(RUsageV4)]
libc.proc_listallpids.argtypes = [ctypes.c_void_p, ctypes.c_int]


def rusage(pid):
    """(cpu_ns, phys_footprint, resident) or None."""
    ru = RUsageV4()
    if libc.proc_pid_rusage(pid, 4, ctypes.byref(ru)) != 0:
        return None
    return ((ru.f0 + ru.f1) * TICK_NS, ru.f7, ru.f6)


def all_procs():
    """{pid: (ppid, command)} from ps (once per sample; cheap enough at 10 Hz)."""
    out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True, text=True).stdout
    procs = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3:
            procs[int(parts[0])] = (int(parts[1]), parts[2])
    return procs


def webkit_pids(procs):
    return {p for p, (_, c) in procs.items() if "com.apple.WebKit." in c}


def tree(root, procs):
    kids = {}
    for p, (pp, _) in procs.items():
        kids.setdefault(pp, []).append(p)
    out, stack = set(), [root]
    while stack:
        p = stack.pop()
        if p in out:
            continue
        out.add(p)
        stack.extend(kids.get(p, []))
    return out


def load1():
    return os.getloadavg()[0]


def idle_seconds():
    """Seconds since the last keyboard or mouse input (IOHIDSystem's HIDIdleTime)."""
    out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, text=True).stdout
    m = re.search(r'"HIDIdleTime" = (\d+)', out)
    return int(m.group(1)) / 1e9 if m else float("inf")


def engines(args):
    k = os.path.join(WORK, "karouka-snap")
    lb = os.path.expanduser(args.ladybird)
    return {
        "karouka": dict(mode="headless (offscreen Metal)", webkit=False, marks="stdout",
                        argv=[f"{k}/bin/karouka_viewer", PAGE, "--headless", "--size", "1280x720", "--frames", "4000",
                              "--fps", "60", "--real-time", "--host-log", "info",
                              "--shader-cache", os.path.join(args.out, "karouka-shaders.bin")],
                        env={"KR_RESOURCE_ROOT": f"{k}/res"}),
        # The same snapshot's viewer in its own window (CAMetalLayer, frames on the window's display link).
        "karouka-window": dict(mode="window 1280x720 (CAMetalLayer)", webkit=False, marks="stdout",
                               argv=[f"{k}/bin/karouka_viewer", PAGE, "--size", "1280x720", "--real-time", "--host-log", "info",
                                     "--shader-cache", os.path.join(args.out, "karouka-window-shaders.bin")],
                               env={"KR_RESOURCE_ROOT": f"{k}/res"}),
        "ladybird": dict(mode="headless", webkit=False, marks="stdout",
                         argv=[lb, "--headless=manual", "--window-width", "1280", "--window-height", "720",
                               "--profile-path", os.path.join(WORK, "ladybird-profile"), "file://" + PAGE], env={}),
        "electron": dict(mode="window 1280x720", webkit=False, marks="stdout",
                         argv=[os.path.join(WORK, "electron/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"),
                               os.path.join(WORK, "electron")], env={"BENCH_DIR": PAGE_DIR}),
        "tauri": dict(mode="window 1280x720 (WKWebView)", webkit=True, marks="stdout",
                      argv=[os.path.join(WORK, "tauri-target/release/bench-tauri")], env={"BENCH_DIR": PAGE_DIR}),
        "tinyjs": dict(mode="window 1280x720 (WKWebView)", webkit=True, marks="file",
                       argv=[os.path.join(WORK, "tinyjs/dist/benchtiny")], env={}),
    }


def kill_tree(pids):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for p in pids:
            try:
                os.kill(p, sig)
            except ProcessLookupError:
                pass
        deadline = time.time() + 3
        while time.time() < deadline and any(rusage(p) for p in pids):
            time.sleep(0.05)


def run_once(name, eng, args, run_idx):
    before_wk = webkit_pids(all_procs()) if eng["webkit"] else set()
    env = dict(os.environ, **eng["env"])
    mark_file = None
    if eng["marks"] == "file":
        mark_file = os.path.join(args.out, f"marks-{name}-{run_idx}.txt")
        if os.path.exists(mark_file):
            os.remove(mark_file)
        env["BENCH_MARK_FILE"] = mark_file
    load = load1()
    t0 = time.monotonic()
    proc = subprocess.Popen(eng["argv"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                            start_new_session=True, text=True, bufsize=1)
    events, lock = {}, threading.Lock()
    cpu_seen = {}  # pid -> max cpu ns seen (keeps the CPU of helpers that exit mid-run)
    samples = []   # (t, cpu_ns_total, footprint_total, rss_total, nprocs)
    stop = threading.Event()
    log = []

    def on_line(line):
        log.append(line)
        m = re.search(r"BENCH (\w+)(.*)", line)
        if m:
            with lock:
                if m.group(1) not in events:
                    events[m.group(1)] = (time.monotonic() - t0, m.group(2).strip(), sample())

    def reader():
        for line in proc.stdout:
            on_line(line.rstrip("\n"))

    def file_reader():
        seen = 0
        while not stop.is_set():
            try:
                with open(mark_file) as f:
                    lines = f.read().splitlines()
                for line in lines[seen:]:
                    on_line(line)
                seen = len(lines)
            except FileNotFoundError:
                pass
            time.sleep(0.005)

    members = set()

    def sample():
        procs = all_procs()
        pids = tree(proc.pid, procs)
        if eng["webkit"]:
            pids |= webkit_pids(procs) - before_wk
        members.update(pids)
        fp = rss = 0
        n = 0
        for p in pids:
            r = rusage(p)
            if r:
                cpu_seen[p] = max(cpu_seen.get(p, 0), r[0])
                fp += r[1]
                rss += r[2]
                n += 1
        s = (time.monotonic() - t0, sum(cpu_seen.values()), fp, rss, n)
        samples.append(s)
        return s

    def sampler():
        while not stop.is_set():
            sample()
            time.sleep(0.1)

    threads = [threading.Thread(target=reader, daemon=True), threading.Thread(target=sampler, daemon=True)]
    if mark_file:
        threads.append(threading.Thread(target=file_reader, daemon=True))
    for t in threads:
        t.start()
    deadline = t0 + args.timeout
    while time.monotonic() < deadline and "done" not in events and proc.poll() is None:
        time.sleep(0.02)
    stop.set()
    final = sample() if proc.poll() is None else None
    procs = all_procs()
    alive = tree(proc.pid, procs) | (members & set(procs))
    kill_tree(alive)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    res = dict(engine=name, run=run_idx, load=round(load, 1), ok="done" in events and "first_frame" in events)
    if not res["ok"]:
        res["log_tail"] = log[-20:]
        return res
    ff_t, ff_args, ff_s = events["first_frame"]
    ss_t, _, ss_s = events["steady_start"]
    dn_t, dn_args, dn_s = events["done"]
    kv = lambda s: {k: float(v) for k, v in re.findall(r"(\w+)=([\d.]+)", s)}
    done = kv(dn_args)
    work = kv(events["work"][1]) if "work" in events else {}
    steady = [s for s in samples if ss_t <= s[0] <= dn_t]
    wall = dn_s[0] - ss_s[0]
    cpu = (dn_s[1] - ss_s[1]) / 1e6
    res.update(
        startup_ms=round(ff_t * 1000, 1),
        page_first_frame_ms=kv(ff_args).get("t"),
        startup_cpu_ms=round(ff_s[1] / 1e6, 1),
        ff_mem_mb=round(ff_s[2] / 2**20, 1),
        js_ms=work.get("js_ms"), dom_ms=work.get("dom_ms"),
        steady_cpu_pct=round(cpu / (wall * 1000) * 100, 1),
        cpu_ms_per_update=round(cpu / max(done.get("updates", 1), 1), 3),
        peak_mem_mb=round(max(s[2] for s in steady + [dn_s]) / 2**20, 1),
        peak_rss_mb=round(max(s[3] for s in steady + [dn_s]) / 2**20, 1),
        end_mem_mb=round(dn_s[2] / 2**20, 1),
        procs=max(s[4] for s in steady + [dn_s]),
        fps=done.get("fps"), updates=done.get("updates"), int_p95=done.get("int_p95"),
        script_p50=done.get("script_p50"),
    )
    return res


def wait_for_load(args, waited, windowed):
    """Waits, out of one --load-wait budget, for the load gate and, before a windowed run, for
    --min-idle seconds without input: a window that opens behind the app in use gets no frames
    (WebKit and the karouka viewer's display link stop for a covered window)."""
    def blocked():
        if args.max_load > 0 and load1() > args.max_load:
            return True
        return windowed and args.min_idle > 0 and idle_seconds() < args.min_idle
    while blocked() and waited < args.load_wait:
        time.sleep(5)
        waited += 5
    return waited


METRICS = [("startup_ms", "startup (ms)"), ("startup_cpu_ms", "startup CPU (ms)"), ("ff_mem_mb", "memory at first frame (MB)"),
           ("js_ms", "JS work (ms)"), ("dom_ms", "DOM work (ms)"), ("steady_cpu_pct", "steady CPU (% of a core)"),
           ("cpu_ms_per_update", "CPU ms / update"), ("peak_mem_mb", "steady peak memory (MB)"),
           ("peak_rss_mb", "steady peak RSS (MB)"), ("procs", "processes"), ("fps", "fps"), ("int_p95", "frame interval p95 (ms)")]


def summarize(results, eng_meta, args):
    names = [n for n in eng_meta if any(r["engine"] == n for r in results)]
    rows = {n: [r for r in results if r["engine"] == n and r["ok"]] for n in names}
    lines = ["| metric | " + " | ".join(names) + " |", "| --- |" + " ---: |" * len(names)]
    for key, label in METRICS:
        cells = []
        for n in names:
            vals = [r[key] for r in rows[n] if r.get(key) is not None]
            if not vals:
                cells.append("—")
                continue
            med = statistics.median(vals)
            cv = statistics.pstdev(vals) / statistics.mean(vals) * 100 if len(vals) > 1 and statistics.mean(vals) else 0
            cell = f"{med:.0f}" if key == "procs" else f"{med:.1f}" if med >= 10 else f"{med:.2f}"
            cells.append(cell + (f" (**{cv:.0f}%**)" if cv > 10 else f" ({cv:.0f}%)"))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    loads = [r["load"] for r in results]
    hdr = [f"Runs per engine: {args.runs} timed (+1 warm-up), interleaved. Medians; per-run CV in parentheses, bold above 10%.",
           f"Load (1-min avg at each run's start): min {min(loads)}, median {statistics.median(loads)}, max {max(loads)}; gate {args.max_load}.",
           "", "| engine | mode | ok runs |", "| --- | --- | ---: |"]
    hdr += [f"| {n} | {eng_meta[n]['mode']} | {len(rows[n])}/{args.runs} |" for n in names]
    return "\n".join(hdr + [""] + lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=7)
    ap.add_argument("--only", action="append")
    ap.add_argument("--max-load", type=float, default=5.0)
    ap.add_argument("--load-wait", type=float, default=8 * 3600, help="total seconds to wait for the load gate")
    ap.add_argument("--min-idle", type=float, default=30,
                    help="seconds without keyboard/mouse input before each windowed run (0: don't wait)")
    ap.add_argument("--timeout", type=float, default=120, help="seconds a run may take before it counts as failed")
    ap.add_argument("--out", default=os.path.join(WORK, "results"))
    ap.add_argument("--ladybird", default="~/ladybird/Build/release/bin/Ladybird.app/Contents/MacOS/Ladybird",
                    help="a Ladybird release build's Ladybird binary")
    args = ap.parse_args()
    args.out = os.path.abspath(args.out)
    os.makedirs(args.out, exist_ok=True)
    meta = engines(args)
    names = [n for n in meta if not args.only or n in args.only]
    results, waited = [], 0
    for rnd in range(args.runs + 1):
        for n in names:
            waited = wait_for_load(args, waited, meta[n]["mode"].startswith("window"))
            r = run_once(n, meta[n], args, rnd)
            tag = "warmup" if rnd == 0 else f"run {rnd}"
            print(f"[{time.strftime('%H:%M:%S')}] {n} {tag}: " + json.dumps({k: v for k, v in r.items() if k not in ('engine', 'log_tail')}), flush=True)
            if not r["ok"]:
                print("  log tail:\n    " + "\n    ".join(r.get("log_tail", [])), flush=True)
            if rnd > 0:
                results.append(r)
            time.sleep(1)
    with open(os.path.join(args.out, "results.json"), "w") as f:
        json.dump(dict(results=results, modes={n: meta[n]["mode"] for n in names}, waited_s=waited), f, indent=1)
    md = summarize(results, {n: meta[n] for n in names}, args)
    with open(os.path.join(args.out, "summary.md"), "w") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    main()
