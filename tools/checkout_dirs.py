"""Deletes the per-checkout output directories under $KR_BUILD (wpt/<checkout>, libweb/<checkout>) of
checkouts that are gone. Every git worktree of this repository shares the main checkout's Ladybird
build dir (docs/BUILDING.md, Build layout), so each one's runs leave a directory there that outlives it.

An output directory DIR has a lock DIR.lock (tools/dev.sh with_lock_at), which records root=, the
checkout, and pid=, the process that last held it. prune(BASE, MINE) deletes each DIR and DIR.lock in
BASE, MINE never, whose root no longer exists and whose pid is gone too. With orphans=True it also
deletes a DIR or DIR.lock that records no root (left before with_lock_at wrote one, or by a run with
its own --out), when DIR's name is the basename of no existing worktree of this repository
(`git worktree list`) and neither it nor anything directly in it changed for ORPHAN_DAYS days; when
git can't list the worktrees, it deletes none of those.
"""
import os
import shutil
import subprocess
import time

ORPHAN_DAYS = 1
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lock_holder(lock):
    """The root= and pid= a lock file records (tools/dev.sh with_lock_at), or {}."""
    try:
        return dict(line.split("=", 1) for line in open(lock).read().splitlines() if "=" in line)
    except OSError:
        return {}


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
    except (ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True
    return True


def live_checkout_names():
    """The basenames of this repository's worktrees (the main checkout too) that exist, or None."""
    try:
        listing = subprocess.run(["git", "-C", REPO, "worktree", "list", "--porcelain"], capture_output=True,
                                 text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    paths = [line[len("worktree "):] for line in listing.splitlines() if line.startswith("worktree ")]
    return {os.path.basename(path) for path in paths if os.path.isdir(path)} or None


def last_change(paths):
    """The newest mtime of PATHS and of the entries directly in those that are directories."""
    newest = 0.0
    for path in paths:
        try:
            newest = max(newest, os.lstat(path).st_mtime)
            if os.path.isdir(path):
                with os.scandir(path) as entries:
                    newest = max([newest] + [entry.stat(follow_symlinks=False).st_mtime for entry in entries])
        except OSError:
            pass
    return newest


def prune(base, mine, orphans=False):
    """Deletes BASE's output directories and locks of checkouts that are gone (module docstring); prints each."""
    if not os.path.isdir(base):
        return
    names = set()
    for entry in os.listdir(base):
        path = os.path.join(base, entry)
        if entry.startswith("."):
            continue
        if entry.endswith(".lock") and os.path.isfile(path):
            names.add(entry[:-len(".lock")])
        elif os.path.isdir(path) and not os.path.islink(path):
            names.add(entry)
    live = False  # not listed yet
    for name in sorted(names):
        directory = os.path.join(base, name)
        lock = directory + ".lock"
        if directory == mine:
            continue
        holder = lock_holder(lock)
        root, pid = holder.get("root", ""), holder.get("pid", "")
        if root:
            if os.path.isdir(root) or pid_alive(pid):
                continue
            why = f"its checkout {root} is gone"
        else:
            if not orphans:
                continue
            if live is False:
                live = live_checkout_names()
            if not live or name in live:
                continue
            if time.time() - last_change([directory, lock]) < ORPHAN_DAYS * 86400:
                continue
            why = f"no lock names its checkout, no worktree is named {name}, unchanged for {ORPHAN_DAYS} day(s)"
        if os.path.isdir(directory):
            shutil.rmtree(directory)
        if os.path.isfile(lock):
            os.remove(lock)
        print(f"cleanup: deleted {directory} ({why})")
