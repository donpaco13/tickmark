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
echo "Next: use AGENTS.md only with a CLI that has no native progress view."
echo "  See README.md for the integration rule and the CLI-specific location."
echo
echo "Then check it works:  tk add \"first step\" && tk"
