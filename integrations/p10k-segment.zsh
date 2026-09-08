# tickmark segment for powerlevel10k.
#
# p10k segments are zsh functions, not command strings, so this is the one
# integration that needs its own file instead of a one-line config snippet.
# See ../README.md for where to source it and how to enable the segment.

function prompt_tk() {
  local out
  out=$(python3 "${TK_STATUS_PY:-$HOME/.local/bin/tk-status.py}" 2>/dev/null)
  [[ -z $out ]] && return
  p10k segment -f 208 -t "$out"
}
