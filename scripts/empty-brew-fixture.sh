#!/bin/sh
# An empty tap for upstream CLI fixtures that inherit the runner PATH.
# Explicit per-test CABOODLE_BREW programs still take precedence.
set -eu
if [ "$#" = 2 ] && [ "$1" = update ] && [ "$2" = --quiet ]; then
  exit 0
fi
if [ "$#" = 3 ] && [ "$1" = info ] && [ "$2" = --json=v2 ]; then
  case "$3" in
    scbrown/tap/*) printf '%s\n' '{"formulae":[]}'; exit 0 ;;
  esac
fi
echo 'empty-tap fixture refuses unexpected Brew operation' >&2
exit 93
