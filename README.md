# tickmark

![tk add, tk go 1, tk next updating a live checklist in the terminal](assets/demo.svg)

Your agent is eight minutes into a task and you can't tell where it is. The
terminal is a wall of scrolling text, and the only status report arrives once
the work is already done.

Ten of the seventeen terminal agents in the table below print a live checklist
of their own. Five don't — `agy`, Aider, Goose, Amp, Cline CLI — and there the
transcript is all you get. Where a native list does exist it lives in the
scroll or in the agent's own TUI: you have to be watching that pane, it costs
lines every time it updates, and none of the ten shows how long the step in
progress has been running.

`tk` writes the list to a JSON file instead of printing it at you. A status
line reads that file and repaints in place: no added lines, no tokens, and a
step stuck for four minutes says so before you think to ask. One Python file,
no dependencies, called as a shell command.

## Amp removed their TODOs

Amp shipped TODOs, then [took them out](https://ampcode.com/news/todos-are-done)
on 12 January 2026. Their reason: the agent tracks its own work in a single
thread fine without them, and the list cost time, tokens and screen space.

The cost is real, and worse than it looks. One `tk` render is N+1 lines and the
agent calls it about 2N+2 times, so the list burns roughly 2(N+1)² lines of
scrollback. Measured in real `agy` sessions: 21% of all tool output at five
steps, 28% at eight. Anything that prints a checklist into the transcript pays
that, `tk` included.

Amp asked whether the agent needs a TODO list to do its work. It doesn't. `tk`
is for the person watching, and the surface it was built for is the status line,
which repaints one line in place, adds no scrollback and never enters the
model's context.

Two consequences, and the second one had to be measured before anyone believed
it:

- Keep the list short. Six steps is where the in-stream cost stops being worth
  it. An agent that wants twelve wanted three phases.
- The live duration only exists in a status line. An agent calls `tk` at the
  transitions and nowhere in between, so nothing in the transcript catches a
  step mid-flight: eight readings out of eight in the measured session said
  `0s`. What a step took is written down when it closes, so the transcript and
  `tk stats` do carry it, after the fact.

## Install

```sh
git clone https://github.com/donpaco13/tickmark
cd tickmark && ./install.sh
```

This copies `tk` to `~/.local/bin` and tells you which agent instruction files
it found. `install.sh` is a POSIX shell script. On Windows, run `.\install.ps1`
instead — it does the same thing natively, plus a `tk.cmd` wrapper and the
`PATH` entry. If your execution policy blocks it:
`powershell -ExecutionPolicy Bypass -File install.ps1`.

Then append [`AGENTS.md`](AGENTS.md) to the file your agent reads — if it needs
it:

| Agent | Instruction file | Native checklist? | Source |
| --- | --- | --- | --- |
| Antigravity CLI (`agy`) | `AGENTS.md` | no — `tk` is for this | its `init` event lists 57 tools, none a checklist |
| Aider | `CONVENTIONS.md`, loaded with `--read` | no — no todo tool, no todo command | [in-chat commands](https://aider.chat/docs/usage/commands.html) |
| Amp | `AGENTS.md` | no — had TODOs since mid-2025, removed them on 12 Jan 2026 | [TODOs Are Done](https://ampcode.com/news/todos-are-done) |
| Cline CLI | `.clinerules/` | no — Focus Chain ships in the VS Code extension, not the CLI | [focus-chain lives under `apps/vscode`](https://github.com/cline/cline/tree/main/apps/vscode/src/core/task/focus-chain) |
| Goose | `.goosehints` or `AGENTS.md` | no — platform extensions stop at analyze, developer, memory, orchestrator | [`platform_extensions/`](https://github.com/block/goose/tree/main/crates/goose/src/agents/platform_extensions) |
| Cursor CLI (`cursor-agent`) | `AGENTS.md` or `.cursor/rules` | unclear — the agent sends `cursor/update_todos` over ACP, but nothing says its own TUI draws them | [ACP reference](https://cursor.com/docs/cli/acp) |
| GitHub Copilot CLI | `AGENTS.md` or `.github/copilot-instructions.md` | unclear — plan mode is documented, a live checklist is not; release notes mention a todo count in the autopilot goal panel | [v1.0.81 release notes](https://github.com/github/copilot-cli/releases/tag/v1.0.81) |
| Claude Code | — | yes — `TaskCreate`/`TaskUpdate` | ships with the CLI |
| Codex | — | yes — `update_plan`, drawn as "Updated Plan" | [`plan_tool.rs`](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/plan_tool.rs) |
| Continue CLI (`cn`) | — | yes — `writeChecklist` | [`ChecklistDisplay.tsx`](https://github.com/continuedev/continue/blob/main/extensions/cli/src/ui/components/ChecklistDisplay.tsx) |
| Crush | — | yes — todos tool with its own TUI renderer | [`ui/chat/todos.go`](https://github.com/charmbracelet/crush/blob/main/internal/ui/chat/todos.go) |
| Droid (Factory) | — | yes — `todoDisplayMode` setting | [Droid CLI settings](https://docs.factory.ai/droid-cli/settings) |
| Gemini CLI | — | yes — `write_todos`, full list on Ctrl+T | [todos.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/todos.md) |
| Kilo Code TUI | — | yes — `todowrite`, sidebar list | [`sidebar/todo.tsx`](https://github.com/Kilo-Org/kilocode/blob/main/packages/tui/src/feature-plugins/sidebar/todo.tsx) |
| opencode | — | yes — `todowrite`/`todoread` | 148 hits in the binary; its system prompt asks for them "VERY frequently" |
| Qwen Code | — | yes — `todo_write` with a sticky list | [todo-write.md](https://github.com/QwenLM/qwen-code/blob/main/docs/developers/tools/todo-write.md) |
| Roo Code CLI | — | yes — `update_todo_list` | [`TodoDisplay.tsx`](https://github.com/RooCodeInc/Roo-Code/blob/main/apps/cli/src/ui/components/TodoDisplay.tsx) |
| anything else | whatever file it loads at startup | check first | — |

Where the answer is yes, use the agent's own tool. `tk` has nothing to add
there. Windsurf is an IDE, not a CLI agent, so there is nothing to append.

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
| `tk stats` | how long the finished tasks took |
| `tk` | show the list |
| `tk --json` | show the list as JSON |

Every command reprints the full list, so a single call both records the change
and shows the state. That matters: it's one tool call for the agent instead of
two, which is the difference between an agent that keeps the list up to date and
one that stops bothering.

The step in progress carries how long it has been running, at the end of its own
line: `▸ 2 patcher le handler  2m14s`. Closing it writes that number down, so
the line still reads `✔ 2 patcher le handler  2m14s` afterwards, and `tk stats`
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
▸ 3 [Scanner] Lancer le scan des portails  43s
```

Set `TICKMARK_AGENT` when you launch a sub-agent and it tags its own work with
no flag to pass; `--agent` overrides it call by call.

## Status lines

Where the list is meant to be read, repainted on every prompt redraw. A host
that accepts several lines (Claude Code, Antigravity CLI) gets the whole
checklist, under a header carrying what its own bar was showing before `tk` took
the space: model, quota buckets, context window.

```
Gemini 3.8 Flash │ 5h 72% (reset 3h24m) │ W 92% │ ctx 11% │ 2/5
✔ 1 Configurer les filtres de stage  2m30s
✔ 2 Integrer les 23 firmes dans portals.yml  6m12s
▸ 3 [Scanner] Lancer le scan des portails  43s
○ 4 Trier les offres retenues
○ 5 Generer les CV adaptes
```

Past eight tasks it folds to a fixed nine lines: the two before the active task,
the active one, the three after, and a count of what was folded at each end.
tmux and a powerlevel10k segment are one line by construction, so they get the
compact form instead:

```
2/5 ▸ Lancer le scan des portails 43s
```

Ready-made snippets for Claude Code, Antigravity CLI, starship, tmux and
powerlevel10k, all reading `roots.json` directly with no `git`/`tk` call per
repaint: see [`integrations/`](integrations/).

## How it works

State lives in one JSON file per project, under `~/.local/share/tickmark`
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
list is per project and lives for the length of the work — it is a progress
display for the human in the loop. If you want your agent to keep durable state
across sessions, use a real tracker; if you want to see what it's doing right
now, use this.

## Requirements

Python 3.6+. No packages. macOS, Linux and Windows.

## License

MIT
