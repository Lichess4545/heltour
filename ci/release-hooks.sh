#!/usr/bin/env bash
set -euo pipefail

readonly published_image=ghcr.io/lichess4545/heltour
readonly version_pattern='^version = ".*"$'
readonly image_pattern="^(x-image: &image $published_image:).*$"
readonly staging_stack=deploy/staging/compose.yml
readonly prod_stack=deploy/prod/compose.yml

refuse() {
  if [[ ${GITHUB_ACTIONS-} == true ]]; then
    printf '::error::%s\n' "$*" >&2
  else
    printf 'refusing to release: %s\n' "$*" >&2
  fi
  return 1
}

assert_ready() {
  local stack
  (($(grep -cE "$version_pattern" pyproject.toml) == 1)) \
    || refuse "pyproject.toml must have exactly one 'version = \"...\"' line"
  for stack in "$staging_stack" "$prod_stack"; do
    (($(grep -cE "$image_pattern" "$stack") == 1)) \
      || refuse "$stack must have exactly one 'x-image: &image $published_image:' line"
  done
}

assert_unpublished() {
  local version=${1-} reference="docker://$published_image:${1#v}"
  local -a skopeo=(skopeo) authfile=()
  command -v skopeo >/dev/null 2>&1 || skopeo=(nix run nixpkgs#skopeo --)
  if [[ -n ${GHCR_AUTHFILE-} ]]; then authfile=(--authfile "$GHCR_AUTHFILE"); fi
  "${skopeo[@]}" inspect --no-tags "${authfile[@]}" "$reference" >/dev/null 2>&1 || return 0
  refuse "$published_image:${version#v} is already published"
}

describe() {
  local version=${1-} latest
  if release-guards is-stable "$version"; then
    latest="moves to $version"
  else
    latest="unchanged -- $version is a prerelease"
  fi
  printf '%-9s %s:%s\n' image "$published_image" "${version#v}"
  printf '%-9s %s\n' ':latest' "$latest"
  printf '%-9s %s\n' staging "$staging_stack deploys ${version#v}"
  if release-guards is-stable "$version"; then
    printf '%-9s %s\n' prod "$prod_stack deploys ${version#v}"
  else
    printf '%-9s %s\n' prod "$prod_stack unchanged"
  fi
}

set_version() {
  local version=${1-}
  assert_ready
  sed -i -E "s|$version_pattern|version = \"${version#v}\"|" pyproject.toml
  sed -i -E "s|$image_pattern|\\1${version#v}|" "$staging_stack"
  printf 'pyproject.toml\n%s\n' "$staging_stack"
  if release-guards is-stable "$version"; then
    sed -i -E "s|$image_pattern|\\1${version#v}|" "$prod_stack"
    printf '%s\n' "$prod_stack"
  fi
}

case ${1-} in
  assert-ready) assert_ready ;;
  assert-unpublished) assert_unpublished "${2-}" ;;
  describe) describe "${2-}" ;;
  set-version) set_version "${2-}" ;;
  image) printf '%s\n' "$published_image" ;;
  *)
    printf 'usage: release-hooks {assert-ready|assert-unpublished|describe|set-version|image} ARGUMENT\n' >&2
    exit 2
    ;;
esac
