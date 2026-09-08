#!/usr/bin/env sh
# tickmark remote installer — downloads a released `tk` binary, verifies it
# against the release's published checksum, then installs it. Never runs
# unverified code: if the checksum doesn't match, or no sha256 tool is on
# PATH to check it, this aborts instead of installing.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/donpaco13/tickmark/main/packaging/get.sh | sh
#   TICKMARK_VERSION=1.0.0 curl -fsSL .../get.sh | sh   # pin a version
set -eu

REPO="donpaco13/tickmark"
BIN="${TICKMARK_BIN:-$HOME/.local/bin}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

command -v curl >/dev/null 2>&1 || { echo "tickmark needs curl on your PATH." >&2; exit 1; }

if [ -n "${TICKMARK_VERSION:-}" ]; then
  VERSION="$TICKMARK_VERSION"
else
  VERSION="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name": *"v?([^"]+)".*/\1/')"
fi
[ -n "$VERSION" ] || {
  echo "Could not resolve a tickmark version from GitHub. Set TICKMARK_VERSION explicitly." >&2
  exit 1
}

BASE="https://github.com/$REPO/releases/download/v$VERSION"
echo "Fetching tickmark $VERSION..."
curl -fsSL "$BASE/tk" -o "$TMP/tk"
curl -fsSL "$BASE/tk.sha256" -o "$TMP/tk.sha256"

echo "Verifying checksum..."
if command -v sha256sum >/dev/null 2>&1; then
  ( cd "$TMP" && sha256sum -c tk.sha256 )
elif command -v shasum >/dev/null 2>&1; then
  ( cd "$TMP" && shasum -a 256 -c tk.sha256 )
else
  echo "No sha256sum or shasum found — cannot verify the download, aborting." >&2
  exit 1
fi

mkdir -p "$BIN"
cp "$TMP/tk" "$BIN/tk"
chmod +x "$BIN/tk"
echo "Installed $BIN/tk ($VERSION)"

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "  ! $BIN is not on your PATH. Add it to your shell profile." ;;
esac

echo
echo "Next: paste AGENTS.md into the instruction file your agent reads."
echo "  curl -fsSL https://raw.githubusercontent.com/$REPO/main/AGENTS.md >> <that file>"
echo
echo "Then check it works:  tk add \"first step\" && tk"
