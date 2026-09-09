#!/usr/bin/env python3
"""tk-status - read a tickmark list for a status line, without running tk or git.

Reads roots.json and the project's state file directly from the tickmark
store, so a status line can repaint every second at zero real cost. Never
shells out, never raises: on a missing store, an empty list or corrupt JSON
it prints nothing and exits 0, because a status line showing a traceback is
worse than no status line at all.

Usage
-----
  tk-status.py                 # cwd = $PWD or the process cwd
  tk-status.py <path>          # cwd = <path>
  tk-status.py --stdin-json    # cwd = .cwd (or .workspace.current_dir) of a
                                # JSON object read from stdin (Claude Code's
                                # statusLine contract)

Output: "<done>/<total> <mark> <current task> <duration>", truncated, or just
"<done>/<total>" once every task is done. The duration is how long the task
has been in progress, and is absent on a task that is not in progress or that
was started by a tk old enough not to record it. Empty output, exit 0, when
there is nothing to show. See integrations/README.md for how to wire this
into a given status line.
"""
import hashlib
import json
import os
import sys
import time

HOME = os.path.expanduser("~")
XDG = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")
STORE = os.environ.get("TICKMARK_STORE") or os.path.join(XDG, "tickmark")

MARK_ASCII = {"todo": "o", "doing": ">", "done": "x"}
MARK_UTF8 = {"todo": "○", "doing": "▸", "done": "✔"}

MAX_LABEL = 40


def resolve_cwd():
    argv = sys.argv[1:]
    if "--stdin-json" in argv:
        try:
            data = json.load(sys.stdin)
        except (ValueError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        return data.get("cwd") or data.get("workspace", {}).get("current_dir")
    for a in argv:
        if not a.startswith("-"):
            return a
    return os.environ.get("PWD") or os.getcwd()


def resolve_root(cwd):
    """roots.json maps a cwd tk was run from to its project root. Walk cwd
    upward through that map so a status line repainting from a subdirectory
    of where tk was invoked still finds the list, without ever calling git.
    """
    try:
        with open(os.path.join(STORE, "roots.json"), encoding="utf-8") as f:
            roots = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(roots, dict):
        return None
    path = os.path.normpath(cwd)
    while True:
        root = roots.get(path)
        if isinstance(root, str):
            return root
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent


def load_tasks(root):
    name = hashlib.sha1(root.encode("utf-8")).hexdigest()[:16] + ".json"
    try:
        with open(os.path.join(STORE, name), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, list) else None


def use_ascii():
    if os.environ.get("TK_STATUS_ASCII") == "1":
        return True
    locale = (os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE")
              or os.environ.get("LANG") or "")
    return "utf-8" not in locale.lower() and "utf8" not in locale.lower()


def elapsed(since, now):
    """Same short duration tk prints. Duplicated on purpose: this file never
    imports tk, so that a status line repainting every second costs one open()
    and nothing else. Any value that is not a usable number reads as "no
    duration" — a status line must never be the thing that shows an error.
    """
    if isinstance(since, bool) or not isinstance(since, (int, float)):
        return ""
    try:
        seconds = int(now - since)
    except (ValueError, OverflowError):
        return ""
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm%02ds" % (seconds // 60, seconds % 60)
    if seconds < 86400:
        return "%dh%02dm" % (seconds // 3600, seconds % 3600 // 60)
    return "%dd%02dh" % (seconds // 86400, seconds % 86400 // 3600)


def render(tasks, now=None):
    if not tasks:
        return ""
    marks = MARK_ASCII if use_ascii() else MARK_UTF8
    done = sum(1 for t in tasks if isinstance(t, dict) and t.get("s") == "done")
    total = len(tasks)
    current = next((t for t in tasks if isinstance(t, dict) and t.get("s") == "doing"), None)
    if current is None:
        current = next((t for t in tasks if isinstance(t, dict) and t.get("s") == "todo"), None)
    if current is None:
        return "%d/%d" % (done, total)
    label = str(current.get("t", ""))
    if len(label) > MAX_LABEL:
        label = label[: MAX_LABEL - 1] + "…"
    out = "%d/%d %s %s" % (done, total, marks[current.get("s", "todo")], label)
    if current.get("s") == "doing":
        duration = elapsed(current.get("since"),
                           time.time() if now is None else now)
        if duration:
            out += " " + duration
    return out


def main():
    cwd = resolve_cwd()
    if not cwd:
        return 0
    # tk records roots.json keys via Python's os.getcwd(), which resolves
    # symlinks (e.g. macOS /tmp -> /private/tmp). $PWD and CLI args don't,
    # so normalize the same way or the lookup silently misses.
    cwd = os.path.realpath(cwd)
    root = resolve_root(cwd)
    if not root:
        return 0
    tasks = load_tasks(root)
    if not tasks:
        return 0
    out = render(tasks)
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
