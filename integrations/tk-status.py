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
  tk-status.py --stdin-json    # read the CLI's session JSON on stdin
  tk-status.py --stdin-json --multiline   # vertical checklist

Flags
-----
  --stdin-json   take the session JSON a CLI feeds its status line on stdin.
                 The working directory comes from it, and so does everything
                 the host would otherwise have shown in the bar it replaced:
                 model, quota buckets, context window.
  --multiline    render the whole list, one task per line, instead of a
                 single compacted line. Only for hosts that accept several
                 lines (Claude Code, Antigravity CLI); tmux status-right and
                 a p10k segment are one line by construction.
  --color / --no-color   force ANSI on or off. Default: on in --multiline,
                 off otherwise, because tmux and starship apply their own and
                 would print raw escapes. TK_STATUS_COLOR=1/0 and NO_COLOR
                 override the default too.
  --selftest     run the built-in assertions and print "ok".

Why isatty() is not the test: a status line command is a child process whose
stdout the host captures and then paints itself, so isatty() is false exactly
where color works. Inside a captured agent session it is false too, and there
color would be noise. The flag is the only honest signal.

Output, one line: "<model> | <quota> | <ctx> | <done>/<total> <mark> <task>
<duration>" - the session segments only when a session JSON supplied them.
Multiline: that same segment as a header, then one line per task, windowed
around the active one past 8 tasks so the list never grows without bound.
Empty output, exit 0, when there is nothing to show.
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
ELLIPSIS_ASCII = "..."
ELLIPSIS_UTF8 = "⋯"
SEP_ASCII = "|"
SEP_UTF8 = "│"

# One line has room for one subject. Kept for the single-line render only;
# --multiline truncates at the terminal width instead, which is the whole
# point of having a second line.
MAX_LABEL = 40

# Past this many tasks the list is windowed: a fixed number of lines around
# the active task, plus a count of what was folded away at each end. A status
# line repaints in place, but a screen is still finite.
WINDOW_AFTER = 8
WINDOW_BEFORE_ACTIVE = 2
WINDOW_AFTER_ACTIVE = 3

DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
RESET = "\033[0m"
TASK_COLOR = {"todo": DIM, "doing": YELLOW, "done": GREEN}

# Antigravity CLI names its quota buckets by provider; the 5h window and the
# weekly one are the two that gate the session. A host that sends neither
# simply gets no quota segment.
QUOTA_BUCKETS = [
    ("gemini-5h", "5h"), ("3p-5h", "5h"),
    ("gemini-weekly", "W"), ("3p-weekly", "W"),
]


def parse_args(argv):
    opts = {"stdin_json": False, "multiline": False, "color": None,
            "selftest": False, "path": None}
    for a in argv:
        if a == "--stdin-json":
            opts["stdin_json"] = True
        elif a == "--multiline":
            opts["multiline"] = True
        elif a == "--color":
            opts["color"] = True
        elif a == "--no-color":
            opts["color"] = False
        elif a == "--selftest":
            opts["selftest"] = True
        elif not a.startswith("-") and opts["path"] is None:
            opts["path"] = a
    return opts


def read_session():
    """The host's session JSON, or {} when there is none or it is unusable."""
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def session_cwd(session):
    cwd = session.get("cwd")
    if isinstance(cwd, str) and cwd:
        return cwd
    workspace = session.get("workspace")
    if isinstance(workspace, dict):
        cwd = workspace.get("current_dir")
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


def resolve_cwd(opts, session):
    if opts["stdin_json"]:
        return session_cwd(session)
    if opts["path"]:
        return opts["path"]
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
    # Mirror tk's state_path(): TICKMARK_SESSION splits the list so parallel
    # agents in one checkout don't share it. A status line that ignores the
    # split reads a file that isn't there and renders nothing - which is
    # exactly the setup where it matters most.
    name = hashlib.sha1(root.encode("utf-8")).hexdigest()[:16]
    session = os.environ.get("TICKMARK_SESSION") or ""
    if session:
        name += "-" + hashlib.sha1(session.encode("utf-8")).hexdigest()[:8]
    name += ".json"
    try:
        with open(os.path.join(STORE, name), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, list) else None


def use_ascii():
    if os.environ.get("TK_STATUS_ASCII") == "1":
        return True
    encoding = getattr(sys.stdout, "encoding", None) or ""
    if encoding and "utf" not in encoding.replace("-", "").lower():
        return True
    locale = (os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE")
              or os.environ.get("LANG") or "")
    if not locale:
        # Windows consoles carry no LANG; the stdout encoding above already
        # decided, and reconfigure() has made it UTF-8 whenever it could.
        return not encoding
    return "utf-8" not in locale.lower() and "utf8" not in locale.lower()


def use_color(opts):
    if os.environ.get("NO_COLOR") is not None:
        return False
    env = os.environ.get("TK_STATUS_COLOR")
    if env in ("0", "1"):
        return env == "1"
    if opts["color"] is not None:
        return opts["color"]
    return opts["multiline"]


def paint(text, color, on):
    return color + text + RESET if on and color else text


def number(value):
    """A JSON number that is really a number. Booleans are not."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def elapsed(since, now):
    """Same short duration tk prints. Duplicated on purpose: this file never
    imports tk, so that a status line repainting every second costs one open()
    and nothing else. Any value that is not a usable number reads as "no
    duration" - a status line must never be the thing that shows an error.
    """
    if number(since) is None:
        return ""
    try:
        seconds = int(now - since)
    except (ValueError, OverflowError):
        return ""
    return duration(seconds)


def duration(seconds):
    if number(seconds) is None:
        return ""
    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm%02ds" % (seconds // 60, seconds % 60)
    if seconds < 86400:
        return "%dh%02dm" % (seconds // 3600, seconds % 3600 // 60)
    return "%dd%02dh" % (seconds // 86400, seconds % 86400 // 3600)


def reset_in(seconds):
    """Coarser than elapsed(): nobody plans an afternoon on quota seconds."""
    if number(seconds) is None or seconds <= 0:
        return ""
    minutes = max(0, int(seconds) // 60)
    hours, minutes = minutes // 60, minutes % 60
    if hours >= 24:
        return "%dd%02dh" % (hours // 24, hours % 24)
    if hours:
        return "%dh%02dm" % (hours, minutes)
    return "%dm" % minutes


def quota_color(remaining_pct):
    """Remaining, not used: the bar goes red as the session runs out."""
    if remaining_pct < 10:
        return RED
    if remaining_pct < 25:
        return YELLOW
    if remaining_pct > 50:
        return GREEN
    return ""


def model_name(session):
    model = session.get("model")
    if not isinstance(model, dict):
        return ""
    for key in ("display_name", "id"):
        value = model.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def quota_segments(session, color):
    quota = session.get("quota")
    if not isinstance(quota, dict):
        return []
    out = []
    for key, label in QUOTA_BUCKETS:
        bucket = quota.get(key)
        if not isinstance(bucket, dict):
            continue
        fraction = number(bucket.get("remaining_fraction"))
        if fraction is None:
            continue
        remaining = max(0, min(100, int(round(fraction * 100))))
        text = "%s %d%%" % (label, remaining)
        left = reset_in(bucket.get("reset_in_seconds"))
        if left:
            text += " (reset %s)" % left
        out.append(paint(text, quota_color(remaining), color))
    return out


def context_segment(session):
    ctx = session.get("context_window")
    if not isinstance(ctx, dict):
        return ""
    used = number(ctx.get("total_input_tokens"))
    size = number(ctx.get("context_window_size"))
    if used is not None and size is not None and used > 0 and size > 0:
        pct = int(round(used * 100.0 / size))
    else:
        pct = number(ctx.get("used_percentage"))
        if pct is None:
            return ""
        pct = int(round(pct))
    return "ctx %d%%" % max(0, min(100, pct))


def session_segments(session, color):
    """Everything the host's own bar showed, so adopting tk costs nothing."""
    out = []
    name = model_name(session)
    if name:
        out.append(name)
    out.extend(quota_segments(session, color))
    ctx = context_segment(session)
    if ctx:
        out.append(ctx)
    return out


def terminal_width(session):
    width = number(session.get("terminal_width"))
    if width is None:
        try:
            width = int(os.environ.get("COLUMNS") or 0)
        except ValueError:
            width = 0
    return int(width) if width and width > 0 else 0


def clip(text, width, ellipsis):
    """Truncate on visible characters. Only ever called on text we built
    ourselves before color was applied, so there are no escapes to miscount.
    """
    if not width or len(text) <= width:
        return text
    if width <= len(ellipsis):
        return text[:width]
    return text[: width - len(ellipsis)] + ellipsis


def task_state(task):
    return task.get("s") if isinstance(task, dict) else None


def active_index(tasks):
    for i, t in enumerate(tasks):
        if task_state(t) == "doing":
            return i
    for i, t in enumerate(tasks):
        if task_state(t) == "todo":
            return i
    return None


def task_duration(task, state, now):
    """A running task counts up from "since"; a finished one shows the
    "elapsed_seconds" tk recorded for it. Either may be missing - an older tk
    wrote neither - and then the line simply carries no duration.
    """
    if state == "doing":
        return elapsed(task.get("since"), now)
    if state == "done":
        return duration(task.get("elapsed_seconds"))
    return ""


def task_text(task, index, state, marks, now):
    label = str(task.get("t", ""))
    agent = task.get("agent")
    if isinstance(agent, str) and agent.strip():
        label = "[%s] %s" % (agent.strip(), label)
    text = "%s %d %s" % (marks[state], index + 1, label)
    span = task_duration(task, state, now)
    if span:
        text += "  " + span
    return text


def window(tasks, active):
    """Indices to render. Whole list while it fits; past WINDOW_AFTER, a band
    around the active task, and the caller reports what was folded away.
    """
    if len(tasks) <= WINDOW_AFTER:
        return 0, len(tasks)
    if active is None:
        active = len(tasks) - 1
    start = max(0, active - WINDOW_BEFORE_ACTIVE)
    end = min(len(tasks), active + WINDOW_AFTER_ACTIVE + 1)
    return start, end


def render(tasks, session=None, multiline=False, color=False, now=None):
    if not tasks:
        return ""
    session = session or {}
    now = time.time() if now is None else now
    ascii_only = use_ascii()
    marks = MARK_ASCII if ascii_only else MARK_UTF8
    ellipsis = ELLIPSIS_ASCII if ascii_only else ELLIPSIS_UTF8
    sep = " %s " % (SEP_ASCII if ascii_only else SEP_UTF8)
    head = session_segments(session, color)
    done = sum(1 for t in tasks if task_state(t) == "done")
    counter = "%d/%d" % (done, len(tasks))
    active = active_index(tasks)

    if not multiline:
        if active is None:
            return sep.join(head + [counter])
        state = task_state(tasks[active])
        label = str(tasks[active].get("t", ""))
        width = terminal_width(session)
        # A host that tells us its width has no reason to be held to 40.
        room = max(MAX_LABEL, width - 30) if width else MAX_LABEL
        line = "%s %s %s" % (counter, marks[state],
                             clip(label, room, "…" if not ascii_only else "..."))
        span = task_duration(tasks[active], state, now)
        if span:
            line += " " + span
        return sep.join(head + [line])

    width = terminal_width(session)
    lines = []
    if head:
        lines.append(sep.join(head + [counter]))
    else:
        lines.append(counter)
    start, end = window(tasks, active)
    if start:
        lines.append(paint("%s +%d done" % (ellipsis, start), DIM, color))
    for i in range(start, end):
        state = task_state(tasks[i])
        if state not in marks:
            continue
        text = clip(task_text(tasks[i], i, state, marks, now), width, ellipsis)
        lines.append(paint(text, TASK_COLOR[state], color))
    if end < len(tasks):
        lines.append(paint("%s +%d todo" % (ellipsis, len(tasks) - end),
                           DIM, color))
    return "\n".join(lines)


def main():
    opts = parse_args(sys.argv[1:])
    if opts["selftest"]:
        return selftest()
    session = read_session() if opts["stdin_json"] else {}
    cwd = resolve_cwd(opts, session)
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
    out = render(tasks, session, opts["multiline"], use_color(opts))
    if out:
        print(out)
    return 0


def selftest():
    """One runnable check: the rendering rules that have a branch in them."""
    os.environ["TK_STATUS_ASCII"] = "1"
    t0 = 1000000
    doing = {"t": "patcher le handler", "s": "doing", "since": t0 - 134}
    plain = [{"t": "lire", "s": "done"}, doing]

    # Single line unchanged when there is no session JSON and no new fields.
    assert render(plain, now=t0) == "1/2 > patcher le handler 2m14s", render(plain, now=t0)
    assert render([{"t": "a", "s": "done"}], now=t0) == "1/1"

    # New store fields are additive, and absent ones change nothing.
    rich = [{"t": "lire", "s": "done", "elapsed_seconds": 150},
            {"t": "ecrire", "s": "doing", "since": t0 - 43, "agent": "Scanner"}]
    out = render(rich, multiline=True, now=t0).split("\n")
    assert out == ["1/2", "x 1 lire  2m30s", "> 2 [Scanner] ecrire  43s"], out

    # Session JSON: model, both quota buckets and context reach the line.
    session = {"model": {"display_name": "Gemini 3.8 Flash"},
               "quota": {"gemini-5h": {"remaining_fraction": 0.72,
                                       "reset_in_seconds": 12240},
                         "gemini-weekly": {"remaining_fraction": 0.92}},
               "context_window": {"total_input_tokens": 21600,
                                  "context_window_size": 200000}}
    line = render(plain, session, now=t0)
    assert line == ("Gemini 3.8 Flash | 5h 72% (reset 3h24m) | W 92% | ctx 11%"
                    " | 1/2 > patcher le handler 2m14s"), line

    # Quota thresholds pick their color, and only when color is on.
    assert quota_color(72) == GREEN and quota_color(20) == YELLOW
    assert quota_color(5) == RED and quota_color(40) == ""
    assert RED in render(plain, {"quota": {"3p-5h": {"remaining_fraction": 0.05}}},
                         color=True, now=t0)
    assert "\033" not in render(plain, {"quota": {"3p-5h": {"remaining_fraction": 0.05}}},
                                now=t0)

    # Past 8 tasks the list is windowed and says what it folded away.
    many = [{"t": "t%d" % i, "s": "done"} for i in range(6)]
    many += [{"t": "t6", "s": "doing", "since": t0}]
    many += [{"t": "t%d" % i, "s": "todo"} for i in range(7, 14)]
    out = render(many, multiline=True, now=t0).split("\n")
    assert out[0] == "6/14" and out[1] == "... +4 done" and out[-1] == "... +4 todo", out
    assert len(out) == 9, out

    # Junk in the store is not a traceback in the bar.
    assert render([{"s": "done"}, "junk", None], now=t0) == "1/3"
    assert render([{"t": "x", "s": "doing", "since": "nope"}], now=t0) == "0/1 > x"
    print("ok")
    return 0


if __name__ == "__main__":
    try:
        # Windows consoles default to a legacy code page, and a status line
        # that raises UnicodeEncodeError just goes blank. Ask for UTF-8; if
        # the stream refuses, use_ascii() reads the encoding and falls back.
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
        sys.exit(main())
    except Exception:
        sys.exit(0)
