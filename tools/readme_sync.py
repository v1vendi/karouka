#!/usr/bin/env python3
"""Keeps README.md's lists in step with the tree.

    tools/readme_sync.py                 check, print what differs; exit 1 if anything does
    tools/readme_sync.py --patch-table   print the Patches table for README.md: its rows as they
                                         are, plus a TODO row (from the file name) for each patch
                                         in patches/ladybird/ it lacks, without the rows of
                                         patches that are gone

What it compares:
  - every patches/ladybird/NNNN-*.patch against README's `| \\`NNNN\\` | ... |` rows;
  - every tools/dev.sh subcommand (its `case "$cmd" in` dispatch, minus the `_` internals)
    against the `tools/dev.sh CMD` lines in README's Build command block;
  - every karouka_viewer flag (`arg == "--..."` in src/viewer/main.mm's parse_options) against
    the flags in README's Viewer synopsis block.
Both ways: a README entry the tree no longer has is reported too.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


def section(text, heading):
    """The text from a `## heading` / `### heading` line to the next heading of the same level."""
    level = heading.split(" ", 1)[0]
    match = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^{level} |\Z)", text, re.M | re.S)
    if not match:
        sys.exit(f"readme_sync: README.md has no '{heading}' section")
    return match.group(1)


def first_code_block(text):
    match = re.search(r"^```[a-z]*\n(.*?)^```", text, re.M | re.S)
    return match.group(1) if match else ""


def tree_patches():
    patches = {}
    for path in sorted((ROOT / "patches/ladybird").glob("*.patch")):
        number, _, slug = path.stem.partition("-")
        patches[number] = slug
    return patches


PATCH_ROW = re.compile(r"^\| `(\d{4})` \| (.*) \|$", re.M)


def readme_patch_rows(readme):
    return {m.group(1): m.group(2) for m in PATCH_ROW.finditer(section(readme, "### Patches"))}


def tree_commands():
    text = (ROOT / "tools/dev.sh").read_text()
    dispatch = re.search(r'^case "\$cmd" in\n(.*?)^esac', text, re.M | re.S)
    if not dispatch:
        sys.exit("readme_sync: tools/dev.sh has no `case \"$cmd\" in` dispatch")
    commands = set()
    for match in re.finditer(r"^    ([a-z][a-z|-]*)\)", dispatch.group(1), re.M):
        commands.update(match.group(1).split("|"))
    return commands


def readme_commands(readme):
    block = first_code_block(section(readme, "## Build"))
    return set(re.findall(r"tools/dev\.sh ([a-z][a-z-]*)", block))


def tree_flags():
    text = (ROOT / "src/viewer/main.mm").read_text()
    return set(re.findall(r'arg == "(--[a-z0-9-]+)"', text)) - {"--help"}


def readme_flags(readme):
    block = first_code_block(section(readme, "## Viewer"))
    return set(re.findall(r"(?<![\w-])--[a-z0-9-]+", block))


def describe(slug):
    """A placeholder for a patch README doesn't describe yet: its file name in words."""
    return "TODO: " + slug.replace("-", " ")


def patch_table(readme):
    rows = readme_patch_rows(readme)
    lines = ["| Patch | Why |", "| --- | --- |"]
    for number, slug in tree_patches().items():
        lines.append(f"| `{number}` | {rows.get(number) or describe(slug)} |")
    return "\n".join(lines)


def check(readme):
    problems = []

    def compare(what, tree, listed):
        for name in sorted(tree - listed):
            problems.append(f"README.md lacks {what} {name}")
        for name in sorted(listed - tree):
            problems.append(f"README.md lists {what} {name}, which the tree doesn't have")

    compare("patch", set(tree_patches()), set(readme_patch_rows(readme)))
    compare("dev.sh command", tree_commands(), readme_commands(readme))
    compare("viewer flag", tree_flags(), readme_flags(readme))
    for line in problems:
        print(line)
    if problems:
        print("(tools/readme_sync.py --patch-table prints the patch table with TODO rows to fill in)")
        return 1
    print("README.md lists every patch, dev.sh command and viewer flag in the tree, and nothing else")
    return 0


def main(argv):
    readme = README.read_text()
    if argv == ["--patch-table"]:
        print(patch_table(readme))
        return 0
    if argv in ([], ["--check"]):
        return check(readme)
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
