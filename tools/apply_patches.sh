#!/usr/bin/env bash
# Makes the shared Ladybird submodule's working tree equal to its pinned commit with this
# checkout's patches/ladybird/*.patch applied, in order.
#
# The tree is shared by every checkout (the main one and its git worktrees), and a branch may
# rewrite a patch that is already applied, so patches can't be applied incrementally. Instead the
# target tree is built in a scratch index (pinned commit + every patch) and only files whose
# content differs are written, so unchanged files keep their mtimes and ninja rebuilds only what
# actually changed. Files a previous series added and this one doesn't are removed.
#
#   tools/apply_patches.sh           make the tree match this checkout's series (the owner keeps
#                                    its hand edits, see below)
#   tools/apply_patches.sh --check   only list what that would change; exit 1 if anything would
#   tools/apply_patches.sh --reset   make the tree match the series, discarding hand edits too
#
# If another checkout owns the tree (tools/dev.sh own; see env.sh), the tree is left as it is: the
# owner is working on the patch series and its unsaved edits live there. A strict checkout
# (KR_SERIES_STRICT=1) exits KR_OWNED_EXIT instead, and tools/dev.sh waits for the owner to release the tree.
#
# Hand edits. Every apply records the target tree it wrote (KR_APPLIED_FILE). A file that differs
# from that record was edited by hand since; one that still matches it only differs from this
# series because the series changed. The owner's own builds update the second kind and keep the
# first ("kept hand edit"), so the owner can rebuild without losing unsaved edits, and
# still picks up patches it rebases onto. Everyone else (and the owner with --reset, and
# `dev.sh own` taking a tree nobody owned) resets both; the hand edits it discards are labelled.
# With no usable record the owner keeps every difference, and says so.
# Run it through `tools/dev.sh patches` to hold the build lock while it writes.
set -euo pipefail
source "$(dirname "$0")/env.sh"

mode=apply
case "${1:-}" in
    "") ;;
    --check) mode=check ;;
    --reset) mode=reset ;;
    *) echo "usage: $0 [--check | --reset]" >&2; exit 2 ;;
esac

owner="$(kr_tree_owner)"
if [[ "$mode" != check && -n "$owner" && "$owner" != "$KR_ROOT" ]]; then
    if ((KR_SERIES_STRICT)); then
        echo "ladybird tree is owned by $owner; this checkout must build its own series" >&2
        exit "$KR_OWNED_EXIT"
    fi
    echo "ladybird tree is owned by $owner (patch-series work in progress): building against" \
        "its tree, not this checkout's series"
    exit 0
fi
# The owner's plain apply keeps hand edits; --reset and every other checkout discard them.
keep=0
[[ "$mode" == apply && -n "$owner" ]] && keep=1

# The NNNN- prefix is the series order; two patches with one number (two branches each took
# the next free number) have no order but the glob's, so refuse them, before applying any.
dupes="$(cd "$KR_ROOT/patches/ladybird" && for p in *.patch; do echo "${p%%-*}"; done | sort | uniq -d)"
if [[ -n "$dupes" ]]; then
    for n in $dupes; do
        echo "patches/ladybird: more than one patch numbered $n:" \
            $(cd "$KR_ROOT/patches/ladybird" && ls -- "$n"-*.patch) >&2
    done
    echo "renumber the newer one (git mv it to the next free number)" >&2
    exit 1
fi

last="$(kr_applied_tree)"

cd "$KR_LADYBIRD"
index="$(mktemp -t kr-patch-index)"
trap 'rm -f "$index"' EXIT
export GIT_INDEX_FILE="$index"

git read-tree HEAD
for patch in "$KR_ROOT"/patches/ladybird/*.patch; do
    name="$(basename "$patch")"
    if ! git apply --cached "$patch"; then
        echo "FAILED to apply: $name" >&2
        exit 1
    fi
    echo "in series: $name"
done
target="$(git write-tree)"
# The scratch index has no stat data; refresh it so only content differences show below.
git update-index -q --refresh >/dev/null || true

# Paths that differ: those the target tree has that differ from (or are missing in) the working
# tree, then files present in the working tree but in neither the target nor upstream (leftovers
# of patches a previous series added, or files added by hand). Untracked files that aren't from
# patches (Build/) are ignored by the submodule's .gitignore, so only unignored untracked files are
# candidates.
paths=()
while IFS= read -r -d '' path; do
    paths+=("$path")
done < <(git diff-files -z --name-only)
updates=${#paths[@]}
target_files="$(git ls-files)"
while IFS= read -r -d '' path; do
    grep -qxF -- "$path" <<<"$target_files" || paths+=("$path")
done < <(git ls-files -z --others --exclude-standard)

# hand[i]: 1 if paths[i] differs from the last applied tree (edited by hand since), 0 if it still
# matches it (only the series changed), ? without a record. Content only; "missing" on both sides
# counts as a match.
hand=()
if ((${#paths[@]})); then
    if [[ -z "$last" ]]; then
        for path in "${paths[@]}"; do hand+=("?"); done
    else
        last_blobs=() work_blobs=() present=()
        while IFS= read -r line; do
            last_blobs+=("${line%% *}")
        done < <(printf "$last:%s\n" "${paths[@]}" | git cat-file --batch-check='%(objectname)')
        for path in "${paths[@]}"; do
            [[ -f "$path" || -L "$path" ]] && present+=("$path")
        done
        hashes=()
        if ((${#present[@]})); then
            while IFS= read -r line; do hashes+=("$line"); done \
                < <(printf '%s\n' "${present[@]}" | git hash-object --stdin-paths)
        fi
        j=0
        for ((i = 0; i < ${#paths[@]}; i++)); do
            work=missing
            if [[ -f "${paths[i]}" || -L "${paths[i]}" ]]; then
                work="${hashes[j]}"
                j=$((j + 1))
            fi
            lb="${last_blobs[i]}"
            [[ "$lb" == *:* ]] && lb=missing # "<tree>:<path> missing"
            [[ "$work" == "$lb" ]] && hand+=(0) || hand+=(1)
        done
    fi
fi

changed=0 kept=0
for ((i = 0; i < ${#paths[@]}; i++)); do
    path="${paths[i]}"
    if ((i < updates)); then verb=update; else verb=remove; fi
    note=""
    [[ "${hand[i]}" == 1 ]] && note=" (hand edit)"
    if [[ "$mode" == check ]]; then
        echo "would $verb: $path$note"
    elif ((keep)) && [[ "${hand[i]}" != 0 ]]; then
        echo "kept hand edit: $path"
        kept=$((kept + 1))
        continue
    else
        if [[ "$verb" == update ]]; then git checkout-index -f -- "$path"; else rm -f -- "$path"; fi
        [[ -n "$note" ]] && note=" (discarded hand edit)"
        echo "${verb}d: $path$note"
    fi
    changed=$((changed + 1))
done

unset GIT_INDEX_FILE
if [[ "$mode" == check ]]; then
    ((changed == 0)) && echo "ladybird tree matches the series" && exit 0
    echo "ladybird tree differs from the series in $changed file(s)"
    exit 1
fi
kr_record_applied "$target"
if ((kept)); then
    [[ -z "$last" ]] && echo "no record of the last applied series: every difference counts as a" \
        "hand edit. tools/dev.sh patches --reset discards them."
    echo "ladybird tree matches the series ($changed file(s) changed) except $kept hand edit(s)" \
        "kept for its owner, this checkout"
else
    echo "ladybird tree matches the series ($changed file(s) changed)"
fi
