# tickmark

![tk add, tk go 1, tk next updating a live checklist in the terminal](assets/demo.svg)

When an agent has a native task or progress view, use that view. When it does
not, `tk` gives the person watching the session a small, persistent view of
what the agent is doing now and what comes next.

`tk` writes progress to a JSON file. A status line reads that file and repaints
in place, so the checklist stays visible without filling the transcript with
repeated output. It is one Python file, has no dependencies, and runs as a
shell command.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/donpaco13/tickmark/main/packaging/get.sh | sh
```

Or from a clone:

```sh
git clone https://github.com/donpaco13/tickmark
cd tickmark && ./install.sh
```

This copies `tk` to `~/.local/bin`. `install.sh` is a POSIX shell script. On
Windows, run `.\install.ps1` instead — it does the same thing natively, plus a
`tk.cmd` wrapper and the `PATH` entry. If your execution policy blocks it:
`powershell -ExecutionPolicy Bypass -File install.ps1`.

For a CLI without a native progress view, give the agent [`AGENTS.md`](AGENTS.md)
in the instruction file it reads. Known examples are Antigravity CLI (`agy`),
Aider, Amp, Cline CLI and Goose. Check each tool's current documentation for
the exact instruction-file location.

For a CLI with a native progress view, use that native tool and do not install
or append Tickmark instructions. This includes Claude Code, Codex, Continue,
Crush, Droid, Gemini CLI, Kilo Code, opencode, Qwen Code and Roo Code. Cursor
CLI and GitHub Copilot CLI need to be checked against their current UI.

## Commands

| | |
| --- | --- |
| `tk add "<subject>" ...` | add one or more tasks |
| `tk go <n>` | mark task *n* as in progress |
| `tk ok <n> [<n> ...]` | complete one or more tasks |
| `tk next` | complete the current task, start the next |
| `tk rm <n> [<n> ...]` | remove tasks |
| `tk new` | clear the list |
| `tk stats` | how long the finished tasks took |
| `tk` | show the list |
| `tk --json` | show the list as JSON |

Every command reprints the full list, so a single call both records the change
and shows the state. That matters: it's one tool call for the agent instead of
two, which is the difference between an agent that keeps the list up to date and
one that stops bothering.

The step in progress carries how long it has been running, at the end of its own
line: `▸ 2 patch the payment handler  2m14s`. Closing it writes that number down, so
the line still reads `✔ 2 patch the payment handler  2m14s` afterwards, and `tk stats`
adds up what the finished steps took:

```
2 done in 8m42s | median 4m21s | slowest 6m12s
```

The duration adds no line to the output, and it drops out rather than eat into
the subject when the terminal is too narrow for both. The one still counting is
only worth reading in a status line — see above for why.

`tk add` and `tk go` also take `--agent <name>`, for when several sub-agents
work one list at once. The name sits between the number and the subject:

```
▸ 3 [Scanner] Scan the product sources  43s
```

Set `TICKMARK_AGENT` when you launch a sub-agent and it tags its own work with
no flag to pass; `--agent` overrides it call by call.

## Status lines

Where the list is meant to be read, repainted on every prompt redraw. A host
that accepts several lines, such as Antigravity CLI, gets the whole progress
list under its existing status information. Tickmark adds a configurable
segment; it does not replace the host's own task view.

```
Gemini 3.8 Flash │ 5h 72% (reset 3h24m) │ W 92% │ ctx 11% │ 2/5
✔ 1 Define the trial experience  2m30s
✔ 2 Build the signup flow  6m12s
▸ 3 [Reviewer] Check the empty state  43s
○ 4 Test the upgrade path
○ 5 Prepare release notes
```

Past eight tasks it folds to a fixed nine lines: the two before the active task,
the active one, the three after, and a count of what was folded at each end.
tmux and a powerlevel10k segment are one line by construction, so they get the
compact form instead:

```
2/5 ▸ Scan the product sources 43s
```

Ready-made snippets for Antigravity CLI, starship, tmux and powerlevel10k, all
reading `roots.json` directly with no `git`/`tk` call per repaint: see
[`integrations/`](integrations/).

## How it works

State lives in one local JSON file per project, under `~/.local/share/tickmark`
(honours `XDG_DATA_HOME`, override with `TICKMARK_STORE`). The project is the
git root; with no `git` on the `PATH`, the nearest directory at or above you
carrying a `.git`, `pyproject.toml`, `package.json` or `.hg`; failing both, the
working directory. Two repos never share a list.

Several agents working in one checkout share that list. Give each its own by
setting `TICKMARK_SESSION` when you launch it (`TICKMARK_SESSION=$AGENT_ID`);
unlike `TICKMARK_STORE`, it splits only the task file and leaves the shared
`roots.json` index in place, so status lines keep working.

### When the working directory can't be trusted

Both steps of that resolution start from the working directory, and some agent
CLIs have one that moves: a shell command lands in the CLI's own install
directory instead of the checkout. Antigravity CLI does it, and nothing in the
session says when. Once the working directory is wrong, `git rev-parse` answers
for whatever tree is there and the walk up to a marker climbs the wrong branch,
so both fallbacks are wrong together. The agent then opens a second, empty list
halfway through the work, and the status line goes blank.

`TICKMARK_ROOT=/path/to/the/checkout` is the one answer that survives, because
none of it is inferred. Set it where you launch the agent and the list stops
moving. This is a patch over a broken environment, not a preference: if your CLI
keeps its working directory straight, leave it unset.

| Variable | Effect |
| --- | --- |
| `TICKMARK_STORE` | Where state files live. Default `~/.local/share/tickmark`. |
| `TICKMARK_SESSION` | Splits the list so parallel agents in one checkout don't share it. |
| `TICKMARK_AGENT` | Default `--agent` name, so a sub-agent tags its own work. |
| `TICKMARK_ROOT` | Pins the project root when the working directory lies. |

The file is plain JSON on purpose. A status line, a shell prompt or another tool
can read it directly without going through `tk`. A `roots.json` index maps
working directories to project roots, so a status line can find the right list
without shelling out to `git` on every repaint.

Display language follows your shell locale (English, or French when `LANG`
starts with `fr`). Command names and JSON keys never change, so the instructions
you give an agent stay the same either way.

## What this is not

It is **not** a task manager, an issue tracker, or memory for the agent. The
list is a local progress display for the human in the loop and stays on disk
across sessions until you reset it with `tk new`. It does not sync, store the
agent's reasoning, or replace an issue tracker for long-term planning.

## Requirements

Python 3.6+. No packages. macOS, Linux and Windows.

## License

MIT
