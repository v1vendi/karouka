#!/usr/bin/env python3
"""What libkarouka and the dylibs it loads are made of, by size.

    tools/bundle_size.py                # dylib closure, libkarouka by library, LibWeb by area
    tools/bundle_size.py --top 60       # longer lists
    tools/bundle_size.py --section __TEXT,__cstring   # attribute another libkarouka section
    tools/bundle_size.py --rust web_rust              # one Rust staticlib's code by module
    tools/bundle_size.py --dylib Build/release/karouka/package/<checkout>/lib/libkarouka.dylib
                                                      # head the report with a packaged (stripped) copy

Reads only what the last build left: libkarouka.dylib, its link map (libkarouka.map, written by
every link) and the vcpkg dylibs. It doesn't build; run `tools/dev.sh build` first.

libkarouka's bytes are attributed to the object file the map names for each symbol. Under ThinLTO
code inlined into another object counts there, and a Rust generic counts in the crate that
instantiated it, so a subsystem's figure is approximate (within a few percent of its sources).
LibWeb's generated bindings (Bindings/<Interface>.cpp) are counted with the area whose directory
holds <Interface>.idl. The dylib closure follows @rpath/@loader_path load commands from
libkarouka; system frameworks are left out (they live in the shared cache).
"""

import argparse
import collections
import glob
import os
import re
import subprocess
import sys


def default_build_dir():
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    return os.path.join(os.path.dirname(common), "third_party/ladybird/Build/release")


def load_map(path):
    objects, sections, symbols = {}, [], []
    mode = None
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("# Object files:"):
                mode = "o"
            elif line.startswith("# Sections:"):
                mode = "s"
            elif line.startswith("# Symbols:"):
                mode = "y"
            elif line.startswith("# Dead Stripped"):
                break
            elif line.startswith("#"):
                continue
            elif mode == "o":
                m = re.match(r"\[\s*(\d+)\] (.*)", line.rstrip())
                objects[int(m.group(1))] = m.group(2)
            elif mode == "s":
                addr, size, seg, sect = line.split()
                sections.append((int(addr, 16), int(addr, 16) + int(size, 16), f"{seg},{sect}"))
            elif mode == "y":
                m = re.match(r"0x([0-9A-F]+)\s+0x([0-9A-F]+)\s+\[\s*(\d+)\] (.*)", line)
                if m:
                    symbols.append((int(m.group(1), 16), int(m.group(2), 16), int(m.group(3)), m.group(4)))
    return objects, sections, symbols


def section_of(sections, addr):
    for start, end, name in sections:
        if start <= addr < end:
            return name
    return None


def idl_areas(ladybird):
    areas = {}
    base = os.path.join(ladybird, "Libraries/LibWeb")
    for path in glob.glob(base + "/**/*.idl", recursive=True):
        areas[os.path.basename(path)[:-4]] = os.path.relpath(path, base).split("/")[0]
    return areas


def classify(path, areas):
    """(library, area) of an object file named in the map."""
    m = re.search(r"/([^/]+)\.dir/(.*)\.o$", path)
    if m:
        lib, parts = m.group(1), m.group(2).split("/")
        area = parts[0] if len(parts) > 1 else "(top)"
        if lib == "LibWeb" and area == "Bindings":
            area = areas.get(os.path.basename(parts[-1])[:-4], "(bindings infrastructure)")
        if lib == "LibJS" and area == "Runtime" and len(parts) > 2:
            area = "Runtime/" + parts[1]
        return lib, area
    m = re.search(r"/lib(\w+)\.a\[\d+\]\(([^)]*)\)", path)
    if m:
        crate = m.group(2).split("-")[0].split(".")[0]
        if "rust" in m.group(1):
            return "rust:" + m.group(1).replace("lib", "", 1), crate
        return "static:" + m.group(1), crate
    return "other", os.path.basename(path)


def size_m(path, segment="__TEXT"):
    out = subprocess.run(["size", "-m", path], capture_output=True, text=True).stdout
    text_seg = re.search(rf"Segment {segment}: (\d+)", out)
    text = re.search(r"Section __text: (\d+)", out)
    return int(text_seg.group(1)) if text_seg else 0, int(text.group(1)) if text else 0


def dylib_closure(build):
    vcpkg = os.path.join(build, "vcpkg_installed/arm64-osx-dynamic/lib")
    root = os.path.join(build, "karouka/lib/libkarouka.dylib")
    found, users, queue = {}, collections.defaultdict(set), [root]
    while queue:
        image = queue.pop(0)
        out = subprocess.run(["otool", "-L", image], capture_output=True, text=True).stdout
        for line in out.splitlines()[1:]:
            dep = line.split()[0]
            if not dep.startswith("@"):
                continue
            name = os.path.basename(dep)
            if name == os.path.basename(image):
                continue
            users[name].add(os.path.basename(image))
            if name in found:
                continue
            path = next((p for p in (os.path.join(build, "lib", name), os.path.join(vcpkg, name))
                         if os.path.exists(p)), None)
            found[name] = path
            if path:
                queue.append(path)
    return found, users


def mb(n):
    return f"{n / 1e6:7.2f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build-dir", default=None)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--section", default="__TEXT,__text")
    ap.add_argument("--rust", help="break one Rust staticlib (e.g. web_rust) down by module")
    ap.add_argument("--dylib", help="the libkarouka.dylib the first line sizes: a copy of the build's, "
                    "e.g. tools/dev.sh package's stripped one; the rest still reads the build")
    args = ap.parse_args()
    build = args.build_dir or default_build_dir()
    ladybird = os.path.dirname(os.path.dirname(build))
    lib_path = os.path.join(build, "karouka/lib/libkarouka.dylib")
    objects, sections, symbols = load_map(os.path.join(build, "karouka/libkarouka.map"))
    areas = idl_areas(ladybird)
    obj_class = {i: classify(p, areas) for i, p in objects.items()}
    picked = [(s, o, n) for a, s, o, n in symbols if section_of(sections, a) == args.section]

    if args.rust:
        mine = [(s, n) for s, o, n in picked if obj_class[o][0] == "rust:" + args.rust]
        names = [n[1:] if n.startswith("__R") else n for s, n in mine]
        demangled = subprocess.run(["c++filt", "-n"], input="\n".join(names), capture_output=True,
                                   text=True).stdout.splitlines()
        modules = collections.Counter()
        for (s, _), d in zip(mine, demangled):
            m = re.search(r"([A-Za-z_]\w*(?:::[A-Za-z_]\w*)+)", re.sub(r"\[[0-9a-f]+\]", "", d))
            modules["::".join(m.group(1).split("::")[:3]) if m else d[:40]] += s
        print(f"rust:{args.rust} {args.section}: {mb(sum(modules.values()))} MB")
        for k, v in modules.most_common(args.top):
            print(f"  {mb(v)}  {k}")
        return 0

    head_path = args.dylib or lib_path
    file_size = os.path.getsize(head_path)
    text_seg, text = size_m(head_path)
    linkedit, _ = size_m(head_path, "__LINKEDIT")
    print(f"libkarouka.dylib  file {mb(file_size)} MB  __TEXT {mb(text_seg)}  __text {mb(text)}  "
          f"__LINKEDIT {mb(linkedit)}" + (f"  ({head_path})" if args.dylib else ""))
    found, users = dylib_closure(build)
    rows = []
    for name, path in found.items():
        real = os.path.realpath(path) if path else None
        if not real:
            rows.append((0, 0, 0, name, "(not found)"))
            continue
        seg, txt = size_m(real)
        rows.append((os.path.getsize(real), seg, txt, name, ", ".join(sorted(users[name]))))
    rows.sort(reverse=True)
    print(f"\nDylibs libkarouka loads ({len(rows)}): file / __TEXT / __text MB, loaded by")
    for f, seg, txt, name, by in rows:
        print(f"  {mb(f)} {mb(seg)} {mb(txt)}  {name:30s} {by}")
    print(f"  {mb(sum(r[0] for r in rows))} {mb(sum(r[1] for r in rows))} {mb(sum(r[2] for r in rows))}  total")

    libs, lib_areas = collections.Counter(), collections.Counter()
    for s, o, n in picked:
        lib, area = obj_class[o]
        libs[lib] += s
        lib_areas[(lib, area)] += s
    total = sum(libs.values())
    print(f"\nlibkarouka {args.section} by library: {mb(total)} MB attributed")
    for k, v in libs.most_common(args.top):
        print(f"  {mb(v)} {100 * v / total:5.1f}%  {k}")
    print(f"\nlibkarouka {args.section} by library / area (LibWeb bindings counted with their IDL's area)")
    for (lib, area), v in lib_areas.most_common(args.top * 2):
        print(f"  {mb(v)}  {lib} / {area}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
