#!/usr/bin/env bash
set -euo pipefail

readonly published_image=ghcr.io/lichess4545/heltour
readonly version_pattern='^version = ".*"$'
readonly image_pattern="^(x-image: &image $published_image:)(.*)$"
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
  (($(grep -cE "$version_pattern" pyproject.toml) == 1)) \
    || refuse "pyproject.toml must have exactly one 'version = \"...\"' line"
  (($(grep -cE "$image_pattern" "$prod_stack") == 1)) \
    || refuse "$prod_stack must have exactly one 'x-image: &image $published_image:' line"
}

is_published() {
  local reference="docker://$published_image:${1#v}"
  local -a skopeo=(skopeo) authfile=()
  command -v skopeo >/dev/null 2>&1 || skopeo=(nix run nixpkgs#skopeo --)
  if [[ -n ${GHCR_AUTHFILE-} ]]; then authfile=(--authfile "$GHCR_AUTHFILE"); fi
  "${skopeo[@]}" inspect --no-tags "${authfile[@]}" "$reference" >/dev/null 2>&1
}

assert_unpublished() {
  local version=${1-}
  is_published "$version" || return 0
  refuse "$published_image:${version#v} is already published"
}

assert_published() {
  local version=${1-}
  is_published "$version" && return 0
  refuse "$published_image:${version#v} is not published"
}

deployed_version() {
  assert_ready
  sed -n -E "s|$image_pattern|\\2|p" "$prod_stack"
}

set_prod_image() {
  local version=${1#v}
  assert_ready
  [[ $(deployed_version) == "$version" ]] && return 0
  sed -i -E "s|$image_pattern|\\1$version|" "$prod_stack"
  printf '%s\n' "$prod_stack"
}

describe() {
  local version=v${1#v} latest
  if release-guards is-stable "$version"; then
    latest="moves to $version"
  else
    latest="unchanged -- $version is a prerelease"
  fi
  printf '%-9s %s:%s\n' image "$published_image" "${version#v}"
  printf '%-9s %s\n' ':latest' "$latest"
  if release-guards is-stable "$version"; then
    printf '%-9s %s\n' prod "deploy.yml deploys ${version#v} after publishing"
  else
    printf '%-9s %s\n' prod "$prod_stack unchanged"
  fi
}

set_version() {
  local version=v${1#v}
  assert_ready
  sed -i -E "s|$version_pattern|version = \"${version#v}\"|" pyproject.toml
  printf 'pyproject.toml\n'
}

case ${1-} in
  assert-ready) assert_ready ;;
  assert-unpublished) assert_unpublished "${2-}" ;;
  assert-published) assert_published "${2-}" ;;
  deployed-version) deployed_version ;;
  set-prod-image) set_prod_image "${2-}" ;;
  describe) describe "${2-}" ;;
  set-version) set_version "${2-}" ;;
  image) printf '%s\n' "$published_image" ;;
  *)
    printf 'usage: release-hooks {assert-ready|assert-unpublished|assert-published|describe|set-version|deployed-version|set-prod-image|image} ARGUMENT\n' >&2
    exit 2
    ;;
esac
