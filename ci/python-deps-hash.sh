#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if output=$(nix build --no-link .#python-deps 2>&1); then
  exit 0
fi

hash=$(grep -oP 'got:\s+\Ksha256-\S+' <<<"$output") || {
  printf '%s\n' "$output" >&2
  exit 2
}
printf '%s\n' "$hash" >python-deps.hash
printf 'python-deps.hash updated to %s\n' "$hash" >&2
exit 1
