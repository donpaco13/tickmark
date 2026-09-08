# tickmark

![tk add, tk go 1, tk next updating a live checklist in the terminal](assets/demo.svg)

You can't tell where your agent is. It's mid-task, the terminal is a wall of
scrolling text, and the only status update arrives as a summary once the work
is already done. Agents that ship a native todo tool don't have this problem:
they render a live checklist you can glance at. Most agents don't ship one.

`tk` gives them one anyway. No API, no daemon, no plugin system: one Python
file with no dependencies, called as a shell command.

## Install

```sh
git clone https://github.com/donpaco13/tickmark
cd tickmark && ./install.sh
```

This copies `tk` to `~/.local/bin` and tells you which agent instruction files
it found. Then append [`AGENTS.md`](AGENTS.md) to the one your agent reads:

| Agent | Instruction file |
| --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` or `./CLAUDE.md` |
| Codex | `~/.codex/AGENTS.md` or `./AGENTS.md` |
| opencode | `~/.config/opencode/AGENTS.md` |
| Gemini CLI | `~/.gemini/GEMINI.md` |
| Crush | `~/.config/crush/CRUSH.md` |
| anything else | whatever file it loads at startup |

That's the whole integration. The agent already knows how to run shell
commands — it just needs to be told that this one exists.

## Commands

| | |
| --- | --- |
| `tk add "<subject>" ...` | add one or more tasks |
| `tk go <n>` | mark task *n* as in progress |
| `tk ok <n> [<n> ...]` | complete one or more tasks |
| `tk next` | complete the current task, start the next |
| `tk rm <n> [<n> ...]` | remove tasks |
| `tk new` | clear the list |
| `tk` | show the list |
| `tk --json` | show the list as JSON |

Every command reprints the full list, so a single call both records the change
and shows the state. That matters: it's one tool call for the agent instead of
two, which is the difference between an agent that keeps the list up to date and
one that stops bothering.

## How it works

State lives in one JSON file per project, under `~/.local/share/tickmark`
(honours `XDG_DATA_HOME`, override with `TICKMARK_STORE`). A project is the git
root when there is one, the working directory otherwise — so two repos never
share a list.

The file is plain JSON on purpose. A status line, a shell prompt or another tool
can read it directly without going through `tk`. A `roots.json` index maps
working directories to project roots, so a status line can find the right list
without shelling out to `git` on every repaint.

Display language follows your shell locale (English, or French when `LANG`
starts with `fr`). Command names and JSON keys never change, so the instructions
you give an agent stay the same either way.

## What this is not

It is **not** a task manager, an issue tracker, or memory for the agent. The
list is per project and lives for the length of the work — it is a progress
display for the human in the loop. If you want your agent to keep durable state
across sessions, use a real tracker; if you want to see what it's doing right
now, use this.

## Requirements

Python 3.6+. No packages. Works anywhere a shell does.

## License

MIT

## Status lines

Ready-made snippets for Claude Code, starship, tmux and powerlevel10k, all
reading `roots.json` directly with no `git`/`tk` call per repaint: see
[`integrations/`](integrations/).
