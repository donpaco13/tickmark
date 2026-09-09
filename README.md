# tickmark

![tk add, tk go 1, tk next updating a live checklist in the terminal](assets/demo.svg)

You can't tell where your agent is. It's mid-task, the terminal is a wall of
scrolling text, and the only status update arrives as a summary once the work
is already done. Agents that ship a native todo tool don't have this problem:
they render a live checklist you can glance at. Most do now — the table below
says which. Some still don't, and that's where you're flying blind.

`tk` gives those one. No API, no daemon, no plugin system: one Python file
with no dependencies, called as a shell command.

## Install

```sh
git clone https://github.com/donpaco13/tickmark
cd tickmark && ./install.sh
```

This copies `tk` to `~/.local/bin` and tells you which agent instruction files
it found. Then append [`AGENTS.md`](AGENTS.md) to the one your agent reads:

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
| `tk` | show the list |
| `tk --json` | show the list as JSON |

Every command reprints the full list, so a single call both records the change
and shows the state. That matters: it's one tool call for the agent instead of
two, which is the difference between an agent that keeps the list up to date and
one that stops bothering.

The step in progress shows how long it has been running, at the end of its own
line: `▸ 2 patcher le handler  2m14s`. A step stuck for eight minutes says
so before you think to ask. It adds no line to the output, and it drops out
rather than eat into the subject when the terminal is too narrow for both.

## How it works

State lives in one JSON file per project, under `~/.local/share/tickmark`
(honours `XDG_DATA_HOME`, override with `TICKMARK_STORE`). A project is the git
root when there is one, the working directory otherwise — so two repos never
share a list.

Several agents working in one checkout share that list. Give each its own by
setting `TICKMARK_SESSION` when you launch it (`TICKMARK_SESSION=$AGENT_ID`);
unlike `TICKMARK_STORE`, it splits only the task file and leaves the shared
`roots.json` index in place, so status lines keep working.

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

## Status lines

Ready-made snippets for Claude Code, starship, tmux and powerlevel10k, all
reading `roots.json` directly with no `git`/`tk` call per repaint: see
[`integrations/`](integrations/).

## Requirements

Python 3.6+. No packages. Works anywhere a shell does.

## License

MIT
