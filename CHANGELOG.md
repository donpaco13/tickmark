# Changelog

All notable changes to tickmark are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/); version numbers
follow [SemVer](https://semver.org/).

## [Unreleased]

### Changed

- The README leads with who the tool is for, and answers Amp's case for
  removing TODOs ([TODOs Are Done](https://ampcode.com/news/todos-are-done))
  instead of stepping around it: the cost they measured is real and quadratic
  here too, which is why the status line, not the transcript, is the surface
  the tool is built for.
- `AGENTS.md` states the "your CLI may already have a checklist" condition as
  its first rule, and caps the list at six steps.

### In progress, not merged

The first install by someone other than the author — Maxence, on Windows 11 and
PowerShell, watching Antigravity CLI (`agy`) work a real project — turned up six
defects. He patched them locally rather than drop the tool. Three workstreams
are folding the fixes back in; the items below describe what is broken today.

Windows:

- `install.sh` is a POSIX shell script, so Windows has no supported install
  path. `tk` has to be put on `PATH` by hand.
- Console output raises `UnicodeEncodeError` on a cp1252 code page — `tk` never
  reconfigures `sys.stdout` to UTF-8 — and a status line that crashes in the
  background just renders empty, with no error anywhere.

Core:

- `project_root()` shells out to `git rev-parse --show-toplevel` and falls back
  to `os.getcwd()` when that fails. With `git` missing from `PATH`, common on
  Windows, the fallback is silent, so walking into a subdirectory quietly moves
  the agent onto a different list.

Status line:

- `integrations/tk-status.py` shows one task: it picks a single entry with
  `next()` and cuts it at `MAX_LABEL = 40`. Finished and upcoming steps are
  invisible.
- Under `--stdin-json` it reads `cwd` and discards the rest of the host's
  payload, so the CLI's own status line — model, quota, reset, context use —
  vanishes behind it.
- It assumes a status line is one condensed line, with no way to draw the
  checklist vertically under the prompt.

## [1.0.0] - TBD

Initial public release.

### Fixed

- `install.sh` and `tk` are now committed as executable (`100755`); the
  `./install.sh` step from the README no longer fails on a fresh clone
  (9cca620).

### Added

- `tk`, a single-file, dependency-free CLI checklist for coding agents.
- `install.sh`, a local installer for a cloned checkout.
- `AGENTS.md`, the instructions block agents append to their own config.
