# Changelog

All notable changes to tickmark are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/); version numbers
follow [SemVer](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-09-28

### Changed

- The README leads with who the tool is for, and answers Amp's case for
  removing TODOs ([TODOs Are Done](https://ampcode.com/news/todos-are-done))
  instead of stepping around it: the cost they measured is real and quadratic
  here too, which is why the status line, not the transcript, is the surface
  the tool is built for.
- `AGENTS.md` states the "your CLI may already have a checklist" condition as
  its first rule, and caps the list at six steps.

### Fixed

- Added a supported PowerShell install path for Windows and kept installers
  from changing an agent's native task or status configuration.
- Made command and status-line output resilient to legacy Windows console
  encodings, malformed stored entries, missing `git`, and corrupt timestamps.
- Made the status-line integration preserve the host's session segments and
  render the full checklist by default, with `--compact` for one-line hosts.

## [1.0.0] - 2026-09-14

Initial public release.

### Fixed

- `install.sh` and `tk` are now committed as executable (`100755`); the
  `./install.sh` step from the README no longer fails on a fresh clone
  (9cca620).

### Added

- `tk`, a single-file, dependency-free CLI checklist for coding agents.
- `install.sh`, a local installer for a cloned checkout.
- `AGENTS.md`, the instructions block agents append to their own config.
