#!/usr/bin/env sh
# tickmark installer — copies `tk` onto your PATH and shows each agent where to
# read its instructions. It never edits a config file without printing what it
# is about to do.
set -eu

BIN="${TICKMARK_BIN:-$HOME/.local/bin}"
SRC="$(cd "$(dirname "$0")" && pwd)"

command -v python3 >/dev/null 2>&1 || {
  echo "tickmark needs python3 on your PATH." >&2
  exit 1
}

mkdir -p "$BIN"
cp "$SRC/tk" "$BIN/tk"
chmod +x "$BIN/tk"
echo "Installed $BIN/tk"

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "  ! $BIN is not on your PATH. Add it to your shell profile." ;;
esac

echo
echo "Next: paste AGENTS.md into the instruction file your agent reads."
echo

found=0
for f in \
  "$HOME/.claude/CLAUDE.md" \
  "$HOME/.codex/AGENTS.md" \
  "$HOME/.config/opencode/AGENTS.md" \
  "$HOME/.gemini/GEMINI.md" \
  "$HOME/.config/crush/CRUSH.md" \
  "$HOME/.aider.conf.yml"
do
  if [ -e "$f" ]; then
    echo "  found  $f"
    found=1
  fi
done
[ "$found" -eq 1 ] || echo "  (no known agent instruction file found — see the README)"

echo
echo "  cat $SRC/AGENTS.md >> <that file>"
echo
echo "Then check it works:  tk add \"first step\" && tk"
