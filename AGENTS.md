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

- **Never mark a step done in the command that performs it.** `tk ok 3` inside
  the command running the test claims the step passed before the test has said
  anything. Either run the work first and mark it after, or gate the marking on
  success: `pytest && tk ok 3`. The list has to be true before it is convenient.
- Don't collapse several steps into one command when work happens between them —
  a checklist that jumps three states at once shows nobody anything.
- One step in progress at a time.
- If this CLI already prints a live checklist of its own, use that instead and
  ignore this file.
- The list is per project. Several agents in one checkout share it unless
  whoever launches them sets `TICKMARK_SESSION` differently for each. It is a
  progress display, not a backlog.
