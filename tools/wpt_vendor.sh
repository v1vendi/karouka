#!/usr/bin/env bash
# The vendored WPT reftest corpus: third_party/wpt/ is a subset of upstream WPT, copied byte
# for byte from a source repository's third_party/wpt/ at one commit, so a test added upstream doesn't
# change karouka's pass count or break its ratchet (tests/wpt/known_failures.txt) until someone
# re-vendors on purpose. The pin is tests/wpt/corpus.pin: the source commit, the git tree hash of the
# directory there, and the upstream WPT commit (the source's third_party/wpt/WPT_COMMIT).
#
#   tools/wpt_vendor.sh --check
#       the committed third_party/wpt/ is exactly the pinned tree and the working tree matches it.
#       Needs nothing outside this repo (git tree hashes are content hashes).
#   tools/wpt_vendor.sh --from DIR [COMMIT]
#       replace third_party/wpt/ with git repository DIR's third_party/wpt/ at COMMIT (default: the
#       last commit on DIR's HEAD that touched it, so the pin doesn't move for unrelated commits) and
#       rewrite the pin. Only committed files are copied (git archive), never DIR's working tree.
#       Re-run `tools/dev.sh wpt` afterwards: new tests fail the ratchet until they pass or are listed
#       (--write-known), and removed ones are warned about.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="third_party/wpt"
PIN="$REPO/tests/wpt/corpus.pin"

pin_field() { sed -n "s/^$1:[[:space:]]*//p" "$PIN" | head -1; }

if [[ "${1:-}" == "--check" ]]; then
    [[ -f "$PIN" ]] || { echo "wpt_vendor: no $PIN" >&2; exit 2; }
    want="$(pin_field tree)"
    have="$(git -C "$REPO" rev-parse --verify -q "HEAD:$DEST" 2>/dev/null || true)"
    if [[ "$have" != "$want" ]]; then
        echo "wpt_vendor: HEAD:$DEST is ${have:-missing}, pin says $want (re-vendor with tools/wpt_vendor.sh --from DIR)" >&2
        exit 1
    fi
    dirty="$(git -C "$REPO" status --porcelain --untracked-files=all -- "$DEST")"
    if [[ -n "$dirty" ]]; then
        echo "wpt_vendor: $DEST differs from HEAD:" >&2
        echo "$dirty" | head -20 >&2
        exit 1
    fi
    echo "wpt_vendor: $DEST matches the pin (source $(pin_field source-commit | cut -c1-10), tree ${want:0:10}, WPT $(pin_field wpt-commit | cut -c1-12))"
    exit 0
fi

if [[ "${1:-}" != "--from" || -z "${2:-}" ]]; then
    echo "usage: tools/wpt_vendor.sh --check | --from DIR [COMMIT]" >&2
    exit 2
fi
source_repo="$2"
shift 2
commit="${1:-$(git -C "$source_repo" log -1 --format=%H HEAD -- "$DEST")}"
commit="$(git -C "$source_repo" rev-parse --verify "$commit^{commit}")"
tree="$(git -C "$source_repo" rev-parse "$commit:$DEST")"
wpt="$(git -C "$source_repo" show "$commit:$DEST/WPT_COMMIT" | sed -n 's/^commit:[[:space:]]*//p' | head -1)"

rm -rf "${REPO:?}/$DEST"
mkdir -p "$REPO/$DEST"
git -C "$source_repo" archive --format=tar "$commit" "$DEST" | tar -x -C "$REPO" -f -

cat > "$PIN" <<PIN_EOF
# The vendored WPT reftest corpus, third_party/wpt/: a subset of upstream WPT, copied from a
# source repository's third_party/wpt/ at source-commit, byte for byte (git tree \`tree\`). Upstream WPT:
# wpt-commit. Re-vendor with tools/wpt_vendor.sh --from DIR; verify with tools/wpt_vendor.sh --check.
source-commit: $commit
tree: $tree
wpt-commit: $wpt
PIN_EOF

git -C "$REPO" add -A -- "$DEST" "tests/wpt/corpus.pin"
staged="$(cd "$REPO" && git write-tree --prefix="$DEST/" 2>/dev/null || true)"
if [[ "$staged" != "$tree" ]]; then
    echo "wpt_vendor: staged $DEST is tree ${staged:-?}, the source's is $tree (check .gitattributes/.gitignore)" >&2
    exit 1
fi
echo "wpt_vendor: vendored $DEST from ${commit:0:10} (tree ${tree:0:10}, WPT ${wpt:0:12}); staged, commit it"
