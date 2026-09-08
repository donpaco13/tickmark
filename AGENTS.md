# Session task tracking

**Before doing anything else on a task with more than one step, run `tk add` with
the steps.** Then keep it current as you go. This is the checklist the person
watching reads to see where the work is; a narrated recap at the end does not
replace it.

```
tk add "<step>" "<step>" "<step>"   lay out the steps, before starting work
tk go <n>                           when you start step n
tk ok <n>                           when step n is genuinely finished
tk next                             finish the current step and start the next
tk                                  reprint the list
```

Rules:

- **Give `tk` its own command. Never chain it with `&&`, and never bundle
  several `tk` calls into one command** — a checklist that jumps three steps at
  once shows nothing. One call, one state change, one redraw.
- Mark a step done after the work is done, never in the same command that does it.
- One step in progress at a time.
- If this CLI already prints a live checklist of its own, use that instead and
  ignore this file.
- The list is per project. Several agents in one checkout share it unless
  whoever launches them sets `TICKMARK_SESSION` differently for each. It is a
  progress display, not a backlog.
