#!/usr/bin/env python3
"""Record libkarouka's linker order file: the functions a page runs, in the order it first
runs them, so the linker lays them out together at the start of __text.

    tools/dev.sh orderfile                  # builds, records, writes src/libkarouka.order
    tools/dev.sh orderfile --stats          # only reports how the current image's touched functions lie
    tools/dev.sh orderfile --stats --tests  # the demo pages, then pages/tests pages with scripted input

Each page runs once headless in karouka_viewer with libkarouka_ordertrace.dylib inserted
(src/tools/ordertrace.cpp), which reports the image address of every function the first time any
thread enters it. The link map (libkarouka.map, written by every link) names the function at each
address and its object file. The order file lists the empty page first (start-up, load, the first
frame, then the rest of its frames, as `# phase` comments mark), then what each further page adds.
Each further page replays scripted input: its own <meta name="karouka-check-input"> when
it declares one, else --input (DEMO_INPUT: the wheel scroll, mouse move, click and key presses check's
layout gates replay on the demo pages), so the input paths are recorded. Its window also resigns key
halfway through its frames and becomes key again in the next (karouka_viewer --blur/--focus),
as a windowed host's does, so kr_view_set_focused and the unfocused paint it brings are recorded,
unless its own input changes focus. The empty page runs without either, as tools/dev.sh mem does.
A static function whose name occurs in more than one object is written as `leaf.o:name`, as ld's
-order_file takes it; the linker ignores names the image no longer has.

Data too: with KR_ORDERTRACE_DATA the tracer also reports the first reads of the data in
__TEXT,__const, __TEXT,__cstring and __DATA_CONST,__const (vtables, typeinfo, string literals,
Rust constants), and the order file lists the named ones after the functions, so the linker gathers
them at the start of their sections too. ld (ld-prime) ignores order file lines for literals (quoted
C strings) and can't name the merged 4/8/16-byte literals (the map's `anon`), so those go to
src/libkarouka_literals.c instead: top-level asm that defines the same literals again, in the order
they were first read. That object is first on libkarouka's link line, and ld keeps the first copy of
equal literals, so the read ones lie together at the start of __cstring and __const. A literal the
image no longer has is dead-stripped. The data trace still misses some first reads (a read by a
libSystem routine called from outside libkarouka can't be stepped over, and its page stays open for
~10 us), and what it misses depends on the layout, so a regeneration keeps the data and literals the
previous files listed after the ones it traced (--fresh drops them): a datum read once stays hot. Unnamed data that isn't a literal
is a section's `ltmpN` atom: its start up to the object's first symbol there (C++ jump tables and string arrays, Rust's
private constants). ld takes it as `leaf.o:ltmpN` when no other object shares the leaf; one that can't be
named stays where it is. Data is traced when writing, and with --stats only given --data; --unplaced also lists the
data ld can't place and, per touched page of each section, whether its atoms are listed in the order file.

--stats prints, per page, how many functions ran and how many 16 KiB __text pages they span: the
part of libkarouka's code a page can't avoid making resident. With --warn-pages N it also exits 3
when the empty page's code spans more than N pages: the order file has gone stale (tools/dev.sh
check).
"""

STALE = 3  # exit status for --warn-pages

import argparse
import bisect
import collections
import os
import re
import struct
import subprocess
import sys
import tempfile

PAGE = 16384
# The data sections the tracer closes and the order file orders.
DATA_SECTIONS = {("__TEXT", "__const"), ("__TEXT", "__cstring"), ("__DATA_CONST", "__const")}


def write_whole(path, text):
    """Writes PATH whole (a temporary file renamed over it): dev.sh orderfile runs without the build
    lock, so a build of this checkout may link against the file meanwhile."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def parse_map(path):
    """{address: (name, size, object)} for every symbol in __TEXT,__text, a Counter of names, and the
    data sections' symbols: {"segment,section": (start, end, [(address, size, name, object)])}."""
    objects = {}
    symbols = {}
    names = collections.Counter()
    text = None
    data = {}
    section = None
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("#"):
                if line.rstrip().endswith(":"):  # "# Symbols:", not its column titles
                    section = line[2:].strip()
                continue
            if section == "Object files:":
                m = re.match(r"\[\s*(\d+)\]\s+(.*)$", line)
                if m:
                    objects[int(m[1])] = m[2]
            elif section == "Sections:":
                parts = line.split()
                if len(parts) == 4 and parts[2] == "__TEXT" and parts[3] == "__text":
                    start = int(parts[0], 16)
                    text = (start, start + int(parts[1], 16))
                elif len(parts) == 4 and (parts[2], parts[3]) in DATA_SECTIONS:
                    start = int(parts[0], 16)
                    data[parts[2] + "," + parts[3]] = (start, start + int(parts[1], 16), [])
            elif section == "Symbols:":
                m = re.match(r"0x([0-9A-F]+)\t0x([0-9A-F]+)\t\[\s*(\d+)\] (.*)$", line)
                if not m:
                    continue
                address = int(m[1], 16)
                if not text or not (text[0] <= address < text[1]):
                    for start, end, atoms in data.values():
                        if start <= address < end:
                            atoms.append((address, int(m[2], 16), m[4], objects.get(int(m[3]), "")))
                    continue
                name = m[4]
                names[name] += 1
                if address not in symbols:
                    symbols[address] = (name, int(m[2], 16), objects.get(int(m[3]), ""))
    for _, _, atoms in data.values():
        atoms.sort()
        names.update(atom[2] for atom in atoms)
    # How many objects share each leaf: an `ltmp` atom is named only by its object's leaf.
    names.update(("leaf", object_leaf(path)) for path in objects.values())
    return symbols, names, data


def page_name(path):
    # A page's file name, or for an index.html its directory's name (pages/demo/NAME/index.html is NAME).
    name = os.path.basename(path)
    return os.path.basename(os.path.dirname(os.path.abspath(path))) if name == "index.html" else name


def object_leaf(path):
    # "dir/libfoo.a[12](bar.o)" for an archive member, else a path.
    m = re.search(r"\(([^()]+)\)$", path)
    return m[1] if m else os.path.basename(path)


def order_entry(name, obj):
    # ld matches a ThinLTO-promoted local ("name.llvm.<hash>") by its name without the suffix.
    name = re.sub(r"\.llvm\.\d+$", "", name)
    return "%s:%s" % (object_leaf(obj), name)


def data_atom(data, address):
    """(section, atom) holding the image address, or None."""
    for section, (start, end, atoms) in data.items():
        if start <= address < end:
            i = bisect.bisect_right(atoms, (address, float("inf"))) - 1
            if i >= 0 and atoms[i][0] <= address < atoms[i][0] + max(atoms[i][1], 1):
                return section, atoms[i]
    return None


LITERAL_SECTIONS = {4: "__literal4,4byte_literals", 8: "__literal8,8byte_literals", 16: "__literal16,16byte_literals"}


def data_entry(name, size, address, obj, names):
    """("order", line) for a named datum, ("literal", section) for one ld coalesces by content, or
    None for one that can't be placed. A name the image has once is written bare: ld doesn't find
    a local datum by object leaf when several objects share the leaf (Intrinsics.cpp.o, Node.cpp.o)."""
    if name.startswith("literal string: "):
        return ("literal", "__cstring,cstring_literals")
    if name == "anon":
        return ("literal", LITERAL_SECTIONS[size]) if size in LITERAL_SECTIONS and address % size == 0 else None
    if name.startswith("ltmp"):
        # A section's start up to its object's first symbol there: private data the assembler left
        # unnamed (C++ switch tables and string arrays, Rust's `anon` constants that share an atom).
        # ld-prime takes it as `leaf.o:ltmpN`, as long as no other object has the same leaf.
        return ("order", order_entry(name, obj)) if names[("leaf", object_leaf(obj))] == 1 else None
    return ("order", re.sub(r"\.llvm\.\d+$", "", name) if names[name] == 1 else order_entry(name, obj))


def read_text(dylib):
    """(vmaddr, fileoff, bytes) of the image's __TEXT segment."""
    with open(dylib, "rb") as f:
        image = f.read()
    magic, _, _, _, ncmds, _, _, _ = struct.unpack_from("<IiiIIIII", image, 0)
    if magic != 0xFEEDFACF:
        sys.exit("orderfile: %s isn't a 64-bit Mach-O image" % dylib)
    offset = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", image, offset)
        if cmd == 0x19:  # LC_SEGMENT_64
            segname = image[offset + 8:offset + 24].rstrip(b"\0")
            vmaddr, _, fileoff, _ = struct.unpack_from("<QQQQ", image, offset + 24)
            if segname == b"__TEXT":
                return vmaddr, fileoff, image
        offset += size
    sys.exit("orderfile: %s has no __TEXT segment" % dylib)


def asm_bytes(data):
    """The bytes as an asm string literal inside a C string literal."""
    out = []
    for b in data:
        c = chr(b)
        if c == '"':
            out.append('\\\\\\"')
        elif c == "\\":
            out.append("\\\\\\\\")
        elif 32 <= b < 127 and c != "?":
            out.append(c)
        else:
            out.append("\\\\%03o" % b)
    return '\\"' + "".join(out) + '\\"'


def previous_literals(path):
    """{section: [asm line]} of an earlier literals file."""
    by_section = collections.OrderedDict()
    section = None
    if not os.path.exists(path):
        return by_section
    with open(path) as f:
        for line in f:
            m = re.match(r'__asm__\("\.section __TEXT,([^"\\]+)', line)
            if m:
                section = m[1]
            elif section and re.match(r'\s+"\.(asciz|byte) ', line):
                by_section.setdefault(section, []).append(line.strip().rstrip(");"))
    return by_section


def write_literals(path, literals, text, previous):
    """src/libkarouka_literals.c: the literals in first-read order, by section, as top-level asm,
    then the previous file's that weren't read this time."""
    vmaddr, fileoff, image = text
    by_section = collections.OrderedDict()
    for section, address, size in literals:
        by_section.setdefault(section, []).append(image[address - vmaddr + fileoff:address - vmaddr + fileoff + size])
    lines = [
        "// libkarouka's hot literals, recorded by tools/dev.sh orderfile with src/libkarouka.order;",
        "// don't edit by hand. Each is a literal an empty page (then each pages/demo page) read, in the order",
        "// it first read it. This object is the first on libkarouka's link line and ld keeps the first copy of",
        "// equal literals, so these lie together at the start of __TEXT,__cstring and __TEXT,__const. Literals",
        "// nothing else defines any more are dead-stripped.",
        "",
        "// clang-format off",
    ]
    # Keep a section the previous file had even when this trace read none of it: the trace sees
    # almost none of the reads of literals this file already packs together, so a run can miss a
    # whole __literalN section.
    for section in previous:
        by_section.setdefault(section, [])
    for section, values in by_section.items():
        size = int(re.search(r"__literal(\d+)", section)[1]) if "__literal" in section else 1
        lines.append('__asm__(".section __TEXT,%s\\n"' % section)
        if size > 1:
            lines.append('        ".p2align %d\\n"' % (size.bit_length() - 1))
        written = []
        for value in values:
            if size == 1:
                written.append('".asciz %s\\n"' % asm_bytes(value.rstrip(b"\0")))
            else:
                written.append('".byte %s\\n"' % ",".join("0x%02x" % b for b in value))
        seen = set(written)
        written += [line for line in previous.get(section, []) if line not in seen and not seen.add(line)]
        lines += ["        " + line for line in written]
        lines[-1] += ");"
    write_whole(path, "\n".join(lines) + "\n")


# The scripted input a further page gets when it declares none: what check's layout gates
# replay on the demo pages (tools/dev.sh check: a wheel scroll, a mouse move across the page, a click,
# down-arrow presses), one after another in a 60-frame run, around the focus toggle at frames 30-31.
DEMO_INPUT = "--scroll 0,20@10..14 --move 50,50:700,500@15x10 --poke 100,100@25 --key 125@33..37"


def focus_toggle(frames):
    # A further page's window loses key halfway through its run and gets it back the next frame.
    return ["--blur", str(frames // 2), "--focus", str(frames // 2 + 1)] if frames >= 2 else []


def page_input(args, page, frames):
    """A further page's input flags: its own <meta name="karouka-check-input"> (read by the viewer's
    meta scan, as tools/dev.sh check_input does), else --input, then the focus toggle unless the
    page's flags already change focus."""
    meta = subprocess.run([args.viewer, "--print-meta", "karouka-check-input", page],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    flags = (meta.stdout.split() if meta.returncode == 0 else []) or args.input.split()
    if "--blur" not in flags and "--focus" not in flags:
        flags += focus_toggle(frames)
    return flags


def trace(args, page, frames, data, extra=()):
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as out:
        out_path = out.name
    env = dict(os.environ, DYLD_INSERT_LIBRARIES=args.tracer, KR_ORDERTRACE_OUT=out_path)
    if data:
        env["KR_ORDERTRACE_DATA"] = "1"
    command = [args.viewer, page, "--headless", "--frames", str(frames), "--mem-phases", *extra]
    run = subprocess.run(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if run.returncode != 0:
        sys.exit("orderfile: %s failed (%d):\n%s" % (" ".join(command), run.returncode, run.stderr))
    events = []
    with open(out_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("# "):
                events.append(("phase", line[2:]))
            elif line.startswith("0x"):
                events.append(("function", int(line, 16)))
            elif line.startswith("data 0x"):
                events.append(("data", int(line[5:], 16)))
    os.unlink(out_path)
    return events


def span_stats(addresses, symbols):
    pages = set()
    size = 0
    for address in addresses:
        length = symbols[address][1] if address in symbols else 4
        size += length
        pages.update(range(address // PAGE, (address + max(length, 1) - 1) // PAGE + 1))
    return size, pages


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--viewer", required=True)
    parser.add_argument("--tracer", required=True, help="libkarouka_ordertrace.dylib")
    parser.add_argument("--map", required=True, help="libkarouka's link map")
    parser.add_argument("--empty", required=True, help="the empty page, recorded first")
    parser.add_argument("--empty-frames", type=int, default=600, help="as tools/dev.sh mem (600)")
    parser.add_argument("--frames", type=int, default=60, help="frames for each further page (60)")
    parser.add_argument("--out", help="the order file to write")
    parser.add_argument("--literals-out", help="the literals source to write (default: next to --out, *_literals.c)")
    parser.add_argument("--dylib", help="libkarouka.dylib, for the literals' bytes (default: lib/ next to --map)")
    parser.add_argument("--stats", action="store_true", help="report only, write nothing")
    parser.add_argument("--data", action="store_true", help="with --stats, trace data reads too (slower)")
    parser.add_argument("--unplaced", action="store_true",
                        help="with --data, list each data atom read that ld can't place")
    parser.add_argument("--fresh", action="store_true", help="drop the data and literals the previous files listed")
    parser.add_argument("--build-info", metavar="FIELDS",
                        help="what was built (tools/dev.sh build_info), written into the header")
    parser.add_argument("--warn-pages", type=int, metavar="N",
                        help="with --stats, exit %d when the empty page spans more than N __text pages" % STALE)
    parser.add_argument("--input", default=DEMO_INPUT, metavar="FLAGS",
                        help="viewer input flags for further pages without a karouka-check-input meta"
                             " (default: %(default)s; '' for none)")
    parser.add_argument("pages", nargs="*", help="further pages, after the empty page")
    args = parser.parse_args()

    symbols, names, data = parse_map(args.map)
    trace_data = args.data or not args.stats
    runs = [(args.empty, args.empty_frames, [])] + [(page, args.frames, page_input(args, page, args.frames)) for page in args.pages]
    lines = []
    seen = set()
    unnamed = 0
    data_lines = []
    data_seen = set()
    data_unordered = 0
    literals = []
    listed = None
    empty_pages = None
    for page, frames, extra in runs:
        events = trace(args, page, frames, trace_data, extra)
        addresses = [value for kind, value in events if kind == "function"]
        size, pages = span_stats(addresses, symbols)
        new = [a for a in addresses if a not in seen]
        if empty_pages is None:
            empty_pages = len(pages)
        print("%-40s %5d functions, %5.2f MB of code on %4d pages of __text (%5.1f MB), %5d new"
              % (page_name(page), len(addresses), size / 1048576, len(pages), len(pages) * PAGE / 1048576, len(new)))
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        label = os.path.relpath(page, root) if os.path.abspath(page).startswith(root + "/") else os.path.basename(page)
        heading = "# page: %s, %d frames%s" % (label, frames, ", input " + " ".join(extra) if extra else "")
        lines.append(heading)
        for kind, value in events:
            if kind == "phase":
                lines.append("# phase: " + value)
                continue
            if kind != "function" or value in seen:
                continue
            seen.add(value)
            if value not in symbols:
                unnamed += 1
                continue
            name, _, obj = symbols[value]
            lines.append(order_entry(name, obj))
        if not trace_data:
            continue
        # The data atoms this page read, and the pages of each section they lie on.
        touched = collections.defaultdict(dict)
        for kind, value in events:
            found = data_atom(data, value) if kind == "data" else None
            if found:
                touched[found[0]].setdefault(found[1][0], found[1])
        report = []
        for section in sorted(touched):
            atoms = touched[section].values()
            pages = set()
            for address, size, _, _ in atoms:
                pages.update(range(address // PAGE, (address + max(size, 1) - 1) // PAGE + 1))
            start, end, _ = data[section]
            report.append("%s %d atoms, %d KB on %d of %d pages" % (section, len(atoms), sum(a[1] for a in atoms) // 1024,
                                                                   len(pages), (end - 1) // PAGE - start // PAGE + 1))
        print("%-40s data: %s" % ("", "; ".join(report)))
        if args.unplaced:
            # Each touched page of each section (from the section's first page) and what its read
            # atoms are: o listed in the order file, n named but not listed, l literal, u unplaced.
            if listed is None:
                listed = set()
                if args.out and os.path.exists(args.out):
                    with open(args.out) as f:
                        listed = {line.strip() for line in f if line.strip() and not line.startswith("#")}
            for section in sorted(touched):
                start = data[section][0] // PAGE
                kinds = collections.defaultdict(collections.Counter)
                for address, size, name, obj in touched[section].values():
                    entry = data_entry(name, size, address, obj, names)
                    kind = "u" if not entry else "l" if entry[0] == "literal" else "o" if entry[1] in listed else "n"
                    kinds[address // PAGE - start][kind] += 1
                print("%-40s %s pages: %s" % ("", section, " ".join(
                    "%d:%s" % (page, ",".join("%s%d" % kv for kv in sorted(kinds[page].items()))) for page in sorted(kinds))))
        data_lines.append(heading)
        for kind, value in events:
            found = data_atom(data, value) if kind == "data" else None
            if not found or found[1][0] in data_seen:
                continue
            address, size, name, obj = found[1]
            data_seen.add(address)
            entry = data_entry(name, size, address, obj, names)
            if entry is None:
                data_unordered += 1
                if args.unplaced:
                    section = data_atom(data, address)[0]
                    print("%-40s unplaced %s 0x%x size %d %s %s" % ("", section, address, size, name, object_leaf(obj)))
            elif entry[0] == "literal":
                literals.append((entry[1], address, size))
            else:
                data_lines.append(entry[1])
    if unnamed:
        print("orderfile: %d entered addresses have no symbol in the link map (left out)" % unnamed)
    if data_unordered:
        print("orderfile: %d data atoms read are unnamed and not literals, which ld can't place (left out)" % data_unordered)
    if args.stats:
        if args.warn_pages is not None and empty_pages > args.warn_pages:
            print("orderfile: the empty page's code spans %d __text pages, over %d: src/libkarouka.order is stale,"
                  " regenerate it with tools/dev.sh orderfile" % (empty_pages, args.warn_pages))
            sys.exit(STALE)
        return
    header = [
        "# libkarouka's function order, recorded by tools/dev.sh orderfile; don't edit by hand.",
        "# Each function appears where a page first ran it. Regenerate after large engine changes:",
        "# names the image no longer has are ignored, functions it gained are laid out after these.",
    ]
    data_header = [
        "# Data: the named data each page first read (__TEXT,__const, __DATA_CONST,__const), in the order",
        "# it first read it; ld moves each to the start of its own section. Literals are in libkarouka_literals.c.",
    ]
    literals_out = args.literals_out or os.path.splitext(args.out)[0] + "_literals.c"
    previous_data = []
    if not args.fresh and os.path.exists(args.out):
        with open(args.out) as f:
            old = f.read().split("\n# Data: ", 1)
        listed = set(data_lines)
        previous_data = [line for line in (old[1].split("\n")[1:] if len(old) > 1 else [])
                         if line and not line.startswith("#") and line not in listed and not listed.add(line)]
        # Keep only the data the image still has: a datum a pruned family took along
        # would otherwise stay listed after every regeneration.
        current = set()
        for _, _, atoms in data.values():
            for _, _, name, obj in atoms:
                current.add(re.sub(r"\.llvm\.\d+$", "", name))
                current.add(order_entry(name, obj))
        stale = [line for line in previous_data if line not in current]
        if stale:
            print("orderfile: %d data the previous file listed are no longer in the image (dropped)" % len(stale))
            previous_data = [line for line in previous_data if line in current]
    if previous_data:
        data_lines += ["# listed before, not read this time"] + previous_data
    previous = {} if args.fresh else previous_literals(literals_out)
    if args.build_info:
        # dev.sh's build_info is one key=value line; should it ever span lines again, each
        # must stay a comment, or ld reads them as symbol names.
        info = args.build_info.strip().splitlines()
        header += ["# recorded on: " + info[0]] + ["#   " + line for line in info[1:]]
    write_whole(args.out, "\n".join(header + lines + data_header + data_lines) + "\n")
    write_literals(literals_out, literals,
                   read_text(args.dylib or os.path.join(os.path.dirname(args.map), "lib", "libkarouka.dylib")), previous)
    print("orderfile: %d functions and %d named data written to %s, %d literals to %s"
          % (len(seen) - unnamed, len(data_lines) - sum(l.startswith("#") for l in data_lines), args.out,
             len(literals), literals_out))


if __name__ == "__main__":
    main()
