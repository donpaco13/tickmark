# Status line integrations

`tk-status.py` is the shared engine behind all four integrations below. It
reads `roots.json` and the project's state file straight from the tickmark
store — it never runs `git` or `tk`, so a status line can repaint every
second at effectively zero cost. On a missing store, an unknown directory,
an empty list or corrupt JSON, it prints nothing and exits `0`: a status
line showing a traceback is worse than no status line.

Output looks like `1/2 ▸ patcher le handler` (current task, truncated at 40
chars), or just `2/2` once every task is done. No color is added — each
target below applies its own. Set `TK_STATUS_ASCII=1` to force the `o`/`>`
fallback if your terminal locale isn't UTF-8 (auto-detected otherwise).

Every snippet below points at `tk-status.py` by absolute path. `install.sh`
only installs `tk` itself, not this folder, so either keep your clone of
this repo around and point at `integrations/tk-status.py` inside it, or
copy `tk-status.py` next to the `tk` binary (`~/.local/bin` by default) and
use that path instead.

## 1. Claude Code

Claude Code's `statusLine` sends session JSON — including `cwd` — on stdin.
Paste into `~/.claude/settings.json` (or a project's `.claude/settings.json`):

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /absolute/path/to/tickmark/integrations/tk-status.py --stdin-json"
  }
}
```

## 2. starship

starship runs a custom module's command in the shell's current directory, so
no `--stdin-json` or path argument is needed. Paste into
`~/.config/starship.toml`, then add `${custom.tk}` to your `format` string:

```toml
[custom.tk]
command = "python3 /absolute/path/to/tickmark/integrations/tk-status.py"
when = true
shell = ["sh", "-c"]
```

## 3. tmux

`#()` in tmux runs a shell command; nesting `#{pane_current_path}` gives it
the active pane's directory instead of tmux's own. Paste into `~/.tmux.conf`:

```tmux
set -g status-right '#(cd #{pane_current_path} && python3 /absolute/path/to/tickmark/integrations/tk-status.py) | %H:%M'
```

(`%H:%M` is a placeholder for whatever you already have in `status-right` —
keep your existing content and just prepend the `#(...)` part.)

## 4. powerlevel10k

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

`tk-status.py` and the tmux/starship snippets were run directly against a
populated store, an empty/missing store, and corrupt `roots.json` and state
files — all print nothing and exit `0` on failure, and print the compact
line on success (verified from the project root and from a subdirectory,
and with a non-UTF-8 locale). The Claude Code path was verified against the
documented `statusLine` stdin schema (both `.cwd` and `.workspace.current_dir`).
The p10k function was verified in zsh with a stubbed `p10k` command (no
powerlevel10k install available in this environment). tmux itself isn't
installed here either, so the tmux snippet was verified by running the exact
`sh -c "cd <dir> && ..."` command tmux's `#()` expands to, not inside a live
tmux session.
