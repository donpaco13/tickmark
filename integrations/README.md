# Status line integrations

`tk-status.py` is the shared engine behind every status line adapter below. It reads
`roots.json` and the project's state file straight from the tickmark store —
it never runs `git` or `tk`, so a status line can repaint every second at
effectively zero cost. On a missing store, an unknown directory, an empty
list or corrupt JSON it prints nothing and exits `0`: a status line showing a
traceback is worse than no status line.

## What it renders

Multiline by default, which is the view intended for an agent status area:

```
Gemini 3.8 Flash │ 5h 72% (reset 3h24m) │ W 92% │ ctx 11% │ 2/5
✔ 1 Define the trial experience  2m30s
✔ 2 Build the signup flow  6m12s
▸ 3 Check the empty state  43s
○ 4 Test the upgrade path
○ 5 Prepare release notes
```

Use `--compact` for a one-line shell segment such as tmux, starship or
powerlevel10k:

```
2/5 ▸ Check the empty state 43s
```

The header carries what the host's own status line was showing, read from the
session JSON on stdin (`--stdin-json`): model
name, quota buckets, context window, then the task counter. Adopting tk
should not cost you the quota reading you steer the session by. A host that
sends no quota gets no quota segment, and the header disappears entirely
when there is no session JSON at all.

Durations come from the store: how long the running task has been running,
and how long each finished one took. A list written by an older `tk` carries
neither and simply shows none.

**Past 8 tasks** the list is windowed — the two tasks before the active one,
the active one, the three after, and a count of what was folded away at each
end:

```
6/14
⋯ +4 done
✔ 5 Review the product copy  2m08s
✔ 6 Update the release notes  2m25s
▸ 7 [Scanner] Scan the product sources  43s
○ 8 Review the matches
○ 9 Prepare the report
○ 10 Publish the summary
⋯ +4 todo
```

A long list stays a fixed nine lines. `[Scanner]` is the `agent` field, shown
only when the store has one.

## Flags

| Flag | Effect |
|---|---|
| `--stdin-json` | Read the session JSON the CLI feeds its status line. The working directory comes from it (`cwd`, or `workspace.current_dir`), and so do the header segments. |
| `--multiline` | Explicitly request the default full progress list. |
| `--compact` | Render one line for tmux, starship and powerlevel10k. |
| `--color` / `--no-color` | Force ANSI on or off. |
| `<path>` | Use this directory instead of `$PWD`. |

Color is **on** in multiline mode and off in compact mode, because tmux and
starship apply their own and would print raw escape codes. `TK_STATUS_COLOR=1`
or `=0` overrides that, and `NO_COLOR` turns it off everywhere. `isatty()` is
deliberately not the test: a status line command is a child process whose
output the host captures and repaints, so `isatty()` is false exactly where
color works.

Quota percentages are what is **left**, and they are colored on that scale:
green above 50%, yellow under 25%, bold red under 10%, with the time before
the bucket refills. The context percentage is what is **used**.

Set `TK_STATUS_ASCII=1` to force the `o`/`>`/`x` marks; otherwise the script
uses them when stdout reports a non-UTF-8 encoding.

## Wiring it up

`TICKMARK_STORE` and `TICKMARK_SESSION` have to reach the status line process
too, not only the agent: the script reads the files `tk` writes and finds them
the same way. `TICKMARK_ROOT` does not: the script never resolves a root
itself. It looks the working directory up in `roots.json`, and `tk` records
every directory it ran from against the pinned root, so a pinned list is still
found from wherever the CLI wandered off to.

Every snippet points at `tk-status.py` by absolute path. `install.sh` only
installs `tk` itself, not this folder, so either keep your clone of this repo
around and point at `integrations/tk-status.py` inside it, or copy
`tk-status.py` next to the `tk` binary (`~/.local/bin` by default).

These adapters are for shells, prompts and CLIs without a progress view that
is already visible to the person watching. They add Tickmark to the host's
status area and do not replace a native task view.

### 1. Antigravity CLI (`agy`)

Same contract, and its payload also carries `quota` and `terminal_width`, so
the header shows the 5h and weekly buckets. In
`~/.gemini/antigravity-cli/settings.json`:

```json
{
  "statusLine": {
    "command": "python3 /absolute/path/to/tickmark/integrations/tk-status.py --stdin-json",
    "enabled": true
  }
}
```

On Windows, point `command` at `python` rather than `python3`. The script
forces its own stdout to UTF-8, so the marks and accented subjects survive a
console still on code page 1252; if the stream refuses UTF-8 it falls back to
ASCII marks rather than going blank.

### 2. starship

starship runs a custom module's command in the shell's current directory, so
no `--stdin-json` or path argument is needed. Paste into
`~/.config/starship.toml`, then add `${custom.tk}` to your `format` string:

```toml
[custom.tk]
command = "python3 /absolute/path/to/tickmark/integrations/tk-status.py --compact"
when = true
shell = ["sh", "-c"]
```

### 3. tmux

`#()` in tmux runs a shell command; nesting `#{pane_current_path}` gives it
the active pane's directory instead of tmux's own. Paste into `~/.tmux.conf`:

```tmux
set -g status-right '#(cd #{pane_current_path} && python3 /absolute/path/to/tickmark/integrations/tk-status.py --compact) | %H:%M'
```

(`%H:%M` is a placeholder for whatever you already have in `status-right` —
keep your existing content and just prepend the `#(...)` part.)

### 4. powerlevel10k

p10k segments are zsh functions, not command strings, so this is the one
integration with its own file: `p10k-segment.zsh` defines `prompt_tk`. Source
it from `~/.p10k.zsh` (near the top, before `POWERLEVEL9K_LEFT_PROMPT_ELEMENTS`
is used) and add `tk` to that array:

```zsh
source /absolute/path/to/tickmark/integrations/p10k-segment.zsh
typeset -g POWERLEVEL9K_LEFT_PROMPT_ELEMENTS+=(tk)
```

By default the function looks for the engine at `~/.local/bin/tk-status.py`
(next to where `install.sh` puts `tk`); set `TK_STATUS_PY` to override.

## Testing notes

`python3 tk-status.py --selftest` runs the built-in assertions: compact output
remains stable, the store's new `elapsed_seconds` and `agent` fields are additive, both quota
buckets and the context window reach the header, each color threshold fires,
the window past 8 tasks folds the right counts, and malformed tasks are ignored
instead of causing a traceback.

Beyond that, every render above is a real run against a populated store. The
failure paths were run too — absent store, unknown directory, corrupt
`roots.json`, corrupt state file, state that is an object instead of a list,
empty list, empty stdin, stdin that is not JSON, stdin that is a JSON array,
and a session JSON whose `model`, `quota` and `context_window` are the wrong
types. All print nothing (or just the task line) and exit `0`. The
non-UTF-8 fallback was checked with `LC_ALL=C PYTHONIOENCODING=ascii:replace`.

The session JSON shape is taken from the host as it ships, not guessed:
Antigravity CLI's
(`model.display_name`, `quota["gemini-5h"|"3p-5h"].remaining_fraction` and
`.reset_in_seconds`, `context_window.total_input_tokens` /
`.context_window_size`, `terminal_width`). Unknown keys are ignored and
missing ones drop their segment, so a host that renames one degrades to the
plain task line instead of breaking. The p10k function was verified in zsh
with a stubbed `p10k` command, and the tmux snippet by running the exact
`sh -c "cd <dir> && ..."` command `#()` expands to — neither tool is
installed in the environment this was built in.
