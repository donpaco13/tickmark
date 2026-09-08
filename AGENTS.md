# Session task tracking

You do not have a native todo tool in this CLI. Use `tk` instead — it prints a
live checklist in the terminal so the person watching can see where the work is,
instead of a wall of text and a summary at the end.

**Whenever a task takes more than one step, lay the steps out before starting.**
Do not wait to be asked, and do not replace the checklist with a narrated recap
at the end of your answer.

```
tk add "<step>" "<step>" "<step>"   lay out the steps up front
tk go <n>                           when you start step n
tk ok <n>                           when step n is genuinely finished
tk next                             finish the current step and start the next
tk                                  reprint the list
```

Every command reprints the whole list, so one call both records the change and
shows the state — never call `tk` twice in a row to check your own work.

Rules:

- One step in progress at a time.
- Mark a step done only when it is actually done, not when you plan to do it.
- The list is per project and per session. It is a progress display, not a
  backlog: it does not replace whatever issue tracker the project uses.
