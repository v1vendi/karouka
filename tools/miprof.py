#!/usr/bin/env python3
"""Report karouka_miprof snapshots (src/tools/miprof.cpp): what kmalloc (mimalloc) holds per phase,
per mimalloc heap and per call site, and what a span of phases added.

    tools/dev.sh mem --attribute            # runs the viewer with the interposer, then this
    python3 tools/miprof.py DIR [--from load] [--to render-0] [--top 25] [--depth 3]

Sizes are mimalloc usable sizes (the size class), so they add up to what the heap pages hold.
"committed" is what mimalloc's own page walk (mi_heap_visit_blocks) reports per heap: bytes of
pages it has handed out to size classes, used or not; the difference is free space in those pages.
"""

import argparse
import bisect
import collections
import glob
import os
import re
import subprocess
import sys

# Rust v0 symbols (LibWeb's libweb_rust) need llvm-cxxfilt; atos demangles only C++.
DEMANGLER = next((p for p in ("/opt/homebrew/opt/llvm/bin/llvm-cxxfilt", "llvm-cxxfilt") if os.path.exists(p)), "c++filt")

# Frames that say where memory is, not who wanted it: the allocator, AK containers and smart
# pointers, the standard library.
NOISE = re.compile(
    r"^(ak_k|kmalloc|kcalloc|krealloc|kfree|operator new|mi_|std::|__|AK::(?!Detail::)|AK::Detail::|"
    r"Gfx::Path|GC::Heap::allocate|GC::Cell|_platform_|swift_|alloc::|core::|hashbrown::|smallvec::|"
    r"ladybird_alloc|rust_alloc|__rust)"
)


def load(directory):
    snapshots = []
    for path in sorted(glob.glob(os.path.join(directory, "[0-9][0-9]-*.tsv"))):
        snap = {"images": [], "heaps": {}, "areas": collections.defaultdict(list), "sites": {}, "dirty": [], "pagesize": 16384}
        with open(path) as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                kind = parts[0]
                if kind == "phase":
                    snap["phase"] = parts[1]
                elif kind == "process":
                    snap["process"] = [int(v) for v in parts[1:]]
                elif kind == "image":
                    snap["images"].append((int(parts[1], 16), parts[2]))
                elif kind == "heap":
                    snap["heaps"][int(parts[1])] = parts[3] if len(parts) > 3 else "visited"
                elif kind == "area":
                    heap, block, used, committed, reserved, full = (int(v) for v in parts[1:7])
                    snap["areas"][heap].append((block, used, committed, reserved, full, int(parts[7], 16)))
                elif kind == "pagesize":
                    snap["pagesize"] = int(parts[1])
                elif kind == "freedpage":
                    snap.setdefault("freedpages", {})[int(parts[1], 16)] = (int(parts[2]), parts[3] == "1")
                elif kind == "crossfree":
                    snap["crossfree"] = int(parts[1])
                elif kind == "livepage":
                    snap.setdefault("livepages", {})[int(parts[1], 16)] = (int(parts[2]), int(parts[3]))
                elif kind == "dirty":
                    snap["dirty"].append((int(parts[1], 16), int(parts[2])))
                elif kind == "site":
                    sid, heap, live, live_n, total, total_n = (int(v) for v in parts[1:7])
                    frames = tuple(int(a, 16) for a in parts[7].split(",")) if len(parts) > 7 and parts[7] else ()
                    snap["sites"][sid] = (heap, live, live_n, total, total_n, frames)
        snapshots.append(snap)
    return snapshots


class Symbolizer:
    def __init__(self, images):
        self.images = sorted(images)
        self.bases = [b for b, _ in self.images]
        self.cache = {}

    def image_of(self, address):
        i = bisect.bisect_right(self.bases, address) - 1
        return self.images[i] if i >= 0 else (0, "?")

    def resolve(self, addresses):
        pending = collections.defaultdict(list)
        for a in addresses:
            if a not in self.cache:
                pending[self.image_of(a)].append(a)
        for (base, path), addrs in pending.items():
            names = []
            if os.path.exists(path):
                out = subprocess.run(["atos", "-o", path, "-l", hex(base)] + [hex(a - 1) for a in addrs],
                                     capture_output=True, text=True).stdout.splitlines()
                names = out if len(out) == len(addrs) else []
            if names:
                names = subprocess.run([DEMANGLER], input="\n".join(names), capture_output=True, text=True).stdout.splitlines() or names
            for i, a in enumerate(addrs):
                name = names[i] if names else hex(a)
                name = re.sub(r" \(in [^)]*\)", "", name)
                name = re.sub(r" \+ \d+$", "", name)
                name = re.sub(r" \([^()]*:\d+\)$", "", name)
                self.cache[a] = (simplify(name), os.path.basename(path))
        return [self.cache[a] for a in addresses]


def simplify(name):
    # Drops template arguments, parameters and return types: Web::CSS::StyleComputer::compute_style.
    # A Rust "<Type as Trait>::method" or "<Type>::method" becomes "Type::method".
    if name.startswith("<"):
        depth = 0
        for i, ch in enumerate(name):
            depth += ch == "<"
            depth -= ch == ">"
            if depth == 0:
                inner = name[1:i].split(" as ")[0]
                name = inner + name[i + 1:]
                break
    name = re.sub(r"::h[0-9a-f]{16}$", "", name)
    out, depth = [], 0
    for ch in name:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    name = "".join(out).strip()
    name = re.sub(r"^.* (?=[\w:~]+$)", "", name)  # a leading return type
    return name.replace("::::", "::")


def mb(n):
    return f"{n / 1048576:7.2f}"


def heap_summary(snap):
    rows = {}
    for heap, areas in snap["areas"].items():
        committed = sum(a[2] for a in areas)
        used = sum(a[0] * a[1] for a in areas)
        rows[heap] = (committed, used, len(areas))
    return rows


def phase_lines(directory):
    """The viewer's --mem-phases-heap lines (phases.log, written by dev.sh mem --attribute): phase ->
    {key: MB} for each key=value field."""
    phases = {}
    try:
        with open(os.path.join(directory, "phases.log")) as f:
            for line in f:
                parts = line.split()
                if len(parts) > 2 and parts[0] == "karouka-mem-phase" and "kmalloc_mb=" in line:
                    phases[parts[1]] = {k: float(v) for k, _, v in (p.partition("=") for p in parts[2:]) if v}
    except (OSError, ValueError):
        return {}
    return phases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--from", dest="start", default="load")
    ap.add_argument("--to", dest="end", default=None, help="default: render-0, else the last phase")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--depth", type=int, default=3, help="caller frames shown per site group")
    ap.add_argument("--sort", choices=("live", "alloc"), default="live",
                    help="order the subsystem and caller tables by live MB added or by MB allocated (churn)")
    args = ap.parse_args()

    snaps = load(args.dir)
    if not snaps:
        sys.exit(f"miprof.py: no snapshots in {args.dir}")
    phases = [s["phase"] for s in snaps]
    end = args.end or ("render-0" if "render-0" in phases else phases[-1])
    a, b = snaps[phases.index(args.start)], snaps[phases.index(end)]

    # Live bytes and mimalloc pages per phase.
    print("\nphase           live_mb  sites   committed_mb  used_mb  pages  (mimalloc heaps, all)")
    for s in snaps:
        live = sum(v[1] for v in s["sites"].values())
        hs = heap_summary(s)
        print(f"{s['phase']:<14} {mb(live)} {len(s['sites']):6d}  {mb(sum(h[0] for h in hs.values()))}     "
              f"{mb(sum(h[1] for h in hs.values()))} {sum(h[2] for h in hs.values()):6d}")

    # Memory the phase lines count apart from kmalloc's call sites.
    lines = phase_lines(args.dir)
    if args.start in lines and end in lines and "canvas_mb" in lines[end]:
        print(f"\n{args.start} -> {end}, from the phase lines (kr_system_memory_usage):")
        print(f"  canvas  {lines[args.start]['canvas_mb']:.2f} -> {lines[end]['canvas_mb']:.2f} MB  2D canvas surfaces, 2 a canvas "
              "(Metal textures; on KR_BACKEND_SOFTWARE kmalloc, under Gfx::Bitmap's call sites below)")

    # Where tag 240's dirty pages are: holding live blocks (by the heap of the page's first block;
    # "walked" = inside a page area mi_heap_visit_blocks reported for this thread's heaps), in a
    # segment's first 64 KiB slice (mimalloc's segment header and slice map), or holding no live
    # block at all: freed memory mimalloc has not purged (or decommitted) yet. never_held_mb is the
    # part of empty_mb no recorded block was ever freed on: free-list extension past what was used.
    print("\nphase          dirty_mb  live_pages_mb  (live_kb_on_them)  meta_mb  empty_mb  empty_in_walked_mb  never_held_mb  segs  (VM tag 240)")
    for s in snaps:
        page = s["pagesize"]
        ranges = sorted((ar[5], ar[5] + ar[2]) for areas in s["areas"].values() for ar in areas)
        starts = [r[0] for r in ranges]
        live_pages = s.get("livepages", {})
        freed = s.get("freedpages", {})
        holding = meta = empty = empty_walked = never_held = live_on = 0
        segments = set()
        s["dirty_by_heap"] = collections.Counter()
        for start, count in s["dirty"]:
            for i in range(count):
                addr = start + i * page
                segments.add(addr >> 25)
                j = bisect.bisect_right(starts, addr) - 1
                walked = j >= 0 and addr < ranges[j][1]
                if addr in live_pages:
                    holding += page
                    live_on += live_pages[addr][0]
                    s["dirty_by_heap"][live_pages[addr][1]] += page
                elif addr & ((1 << 25) - 1) < 65536:
                    meta += page
                else:
                    empty += page
                    empty_walked += page if walked else 0
                    never_held += page if addr not in freed else 0
                    s.setdefault("empty_pages", []).append((addr, walked))
        print(f"{s['phase']:<14} {mb(holding + meta + empty)}       {mb(holding)}  ({live_on / 1024:8.0f})   {mb(meta)} {mb(empty)}            {mb(empty_walked)}       {mb(never_held)}  {len(segments):5d}")

    print(f"\nper heap at {end}: live MB (call-site records), dirty MB of pages holding its blocks")
    per_heap = collections.Counter()
    for site in b["sites"].values():
        per_heap[site[0]] += site[1]
    heap_sites = collections.defaultdict(list)
    for site in b["sites"].values():
        heap_sites[site[0]].append(site)
    for heap, live in sorted(per_heap.items()):
        # Name the heap by the callers of its biggest sites (the partition is not recorded).
        top = sorted(heap_sites[heap], key=lambda v: -v[3])[:3]
        addrs = sorted({f for v in top for f in v[5][:12]})
        names = dict(zip(addrs, Symbolizer(b["images"]).resolve(addrs)))
        hint = "; ".join(next((names[f][0] for f in v[5][:12] if not NOISE.match(names[f][0])), "?") for v in top)
        print(f"  heap {heap:2d}  {mb(live)}  {mb(b['dirty_by_heap'].get(heap, 0))}  {b['heaps'].get(heap, '?'):12}  {hint[:150]}")

    ha, hb = heap_summary(a), heap_summary(b)
    print(f"\nper heap, {args.start} -> {end}: committed MB (used MB, pages)")
    for heap in sorted(set(ha) | set(hb)):
        ca, ua, pa = ha.get(heap, (0, 0, 0))
        cb, ub, pb = hb.get(heap, (0, 0, 0))
        print(f"  heap {heap:2d}  {mb(ca)} ({mb(ua).strip()}, {pa}) -> {mb(cb)} ({mb(ub).strip()}, {pb})")

    # What the span added, per site.
    delta = {}
    for sid, site in b["sites"].items():
        before = a["sites"].get(sid, (0, 0, 0, 0, 0, ()))
        d_live = site[1] - before[1]
        d_total = site[3] - before[3]
        if d_live or d_total:
            delta[sid] = (site[0], d_live, site[2] - before[2], d_total, site[5])
    symbolizer = Symbolizer(b["images"])
    addresses = sorted({f for v in delta.values() for f in v[4]})
    resolved = dict(zip(addresses, symbolizer.resolve(addresses)))

    def owner(frames, depth):
        names = [resolved[f][0] for f in frames]
        meaningful = [n for n in names if not NOISE.match(n)]
        return " < ".join(meaningful[:depth]) if meaningful else (names[0] if names else "?")

    def subsystem(frames):
        for f in frames:
            n = resolved[f][0]
            if NOISE.match(n):
                continue
            m = re.match(r"^((?:libweb_rust::\w+(?:::\w+)?)|(?:Web|JS|Gfx|Core|GC|Karouka|Unicode|URL|Media|TextCodec|Crypto|Regex|Compositing|Wasm|IPC)(?:::[A-Za-z]+)?)", n)
            return m.group(1) if m else n.split("::")[0]
        return "?"

    total_live = sum(v[1] for v in delta.values())
    total_alloc = sum(v[3] for v in delta.values())
    print(f"\n{args.start} -> {end}: live {mb(total_live).strip()} MB added in {len(delta)} call sites; "
          f"{mb(total_alloc).strip()} MB allocated in the span (freed or not)")

    for title, key in (("by subsystem (first non-AK frame's namespace)", lambda v: subsystem(v[4])),
                       ("by caller (first non-AK frames)", lambda v: owner(v[4], args.depth))):
        groups = collections.defaultdict(lambda: [0, 0, 0])
        for v in delta.values():
            g = groups[key(v)]
            g[0] += v[1]
            g[1] += v[2]
            g[2] += v[3]
        print(f"\n{title}: live MB added, blocks, MB allocated")
        for name, (live, n, alloc) in sorted(groups.items(), key=lambda kv: -kv[1][2 if args.sort == "alloc" else 0])[:args.top]:
            print(f"  {mb(live)} {n:8d} {mb(alloc)}  {name}")

    # mimalloc gives each thread its own 32 MiB segments, so a segment's live blocks name the
    # thread (heaps) that dirtied its empty pages too.
    print(f"\nsegments (32 MiB) at {args.start} -> {end}: dirty MB, of it holding no live block, heaps with blocks there")
    for s_ in (a, b):
        page = s_["pagesize"]
        seg = collections.defaultdict(lambda: [0, 0, set()])
        lp = s_.get("livepages", {})
        for start, count in s_["dirty"]:
            for i in range(count):
                addr = start + i * page
                e = seg[addr >> 25]
                e[0] += page
                if addr in lp:
                    e[2].add(lp[addr][1])
                else:
                    e[1] += page
        s_["segments"] = seg
    for key in sorted(set(a["segments"]) | set(b["segments"])):
        da, ea, _ = a["segments"].get(key, (0, 0, set()))
        db, eb, hs = b["segments"].get(key, (0, 0, set()))
        print(f"  {key << 25:#014x}  {mb(da)} -> {mb(db)}   empty {mb(ea)} -> {mb(eb)}   heaps {sorted(hs)}")

    # The walked heaps' pages by block size: what mimalloc has extended its free lists over
    # (committed = capacity * block size; mimalloc extends by at least 4 blocks at a time, 32 in MI_SECURE builds)
    # against what is in use.
    buckets = collections.defaultdict(lambda: [0, 0, 0])
    for heap, areas in b["areas"].items():
        for block, used, committed, _, _, _ in areas:
            key = block if block <= 1024 else 1 << (block - 1).bit_length()
            buckets[key][0] += committed
            buckets[key][1] += used * block
            buckets[key][2] += 1
    print(f"\nwalked heaps at {end} by block size (<=1 KiB exact, else rounded up to a power of two): pages, committed MB, used MB, unused MB")
    for key in sorted(buckets):
        c, u, n = buckets[key]
        if c - u >= 32 * 1024:
            print(f"  {key:8d} {n:4d} {mb(c)} {mb(u)} {mb(c - u)}")
    print(f"  total         {mb(sum(v[0] for v in buckets.values()))} {mb(sum(v[1] for v in buckets.values()))} "
          f"{mb(sum(v[0] - v[1] for v in buckets.values()))}")

    # Dirty pages the span added that hold no live block, by the last block freed on them.
    before = {addr for addr, _ in a.get("empty_pages", [])}
    page = b["pagesize"]
    freed = b.get("freedpages", {})
    sites_needed = {freed[addr][0] for addr, _ in b.get("empty_pages", []) if addr not in before and addr in freed}
    extra = sorted({f for sid in sites_needed for f in b["sites"][sid][5]} - set(resolved))
    resolved.update(zip(extra, symbolizer.resolve(extra)))
    groups = collections.defaultdict(lambda: [0, 0])
    for addr, walked in b.get("empty_pages", []):
        if addr in before:
            continue
        if addr not in freed:
            key = ("never held a recorded block", "-", "")
        else:
            sid, cross = freed[addr]
            site = b["sites"][sid]
            key = (owner(site[5], args.depth), f"heap {site[0]}", "freed by another thread" if cross else "")
        groups[key][0] += page
        groups[key][1] += page if walked else 0
    total = sum(g[0] for g in groups.values())
    print(f"\n{args.start} -> {end}: {mb(total).strip()} MB of new dirty pages hold no live block "
          f"(cross-thread frees so far: {mb(b.get('crossfree', 0)).strip()} MB); by the last block freed on them: MB, MB in this thread's heap pages")
    for (name, heap, cross), (n, walked) in sorted(groups.items(), key=lambda kv: -kv[1][0])[:args.top]:
        print(f"  {mb(n)} {mb(walked)}  {heap:8} {cross:24} {name}")


if __name__ == "__main__":
    main()
