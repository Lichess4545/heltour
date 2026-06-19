variable "TAG" {
  default = "latest"
}

variable "REGISTRY" {
  default = ""
}

variable "GITHUB_SHORT_SHA" {
  default = "unknown"
}

# Toggle for the registry-cache fallback. CI sets this to "1" so the
# bake reads/writes layer cache through ghcr.io alongside GHA. Local
# `docker buildx bake` leaves it empty and only uses the GHA scope (or
# nothing, when GHA isn't reachable).
variable "REGISTRY_CACHE" {
  default = ""
}

function "tag" {
  params = [name]
  result = ["${lower(REGISTRY)}${REGISTRY != "" ? "/" : ""}${name}:${TAG}"]
}

# Per-target cache sources. We always try the GHA scope (cheap and
# branch-aware), and additionally fall back to a registry-stored cache
# when CI is configured for it — this lets a fresh PR runner with no
# GHA cache still pull layers from whatever master last published.
function "cache_from" {
  params = [name]
  result = concat(
    ["type=gha,scope=${name}"],
    REGISTRY_CACHE != "" ? ["type=registry,ref=${lower(REGISTRY)}${REGISTRY != "" ? "/" : ""}${name}:buildcache"] : [],
  )
}

# Per-target cache sinks. `mode=max` exports every intermediate layer,
# not just the final image, so subsequent builds can reuse them even
# when only late stages change. Registry cache is only written when
# explicitly enabled to avoid PR runs polluting the shared cache image.
function "cache_to" {
  params = [name]
  result = concat(
    ["type=gha,mode=max,scope=${name}"],
    REGISTRY_CACHE == "push" ? ["type=registry,ref=${lower(REGISTRY)}${REGISTRY != "" ? "/" : ""}${name}:buildcache,mode=max"] : [],
  )
}

group "verify" {
  targets = ["web-verify", "javafo-verify"]
}

group "default" {
  targets = ["base", "verify", "litour-caddy", "litour-web", "litour-api-worker", "litour-api", "litour-ui", "litour-celery", "litour-watcher", "litour-migrate"]
}

group "production" {
  targets = ["litour-caddy", "litour-web", "litour-api-worker", "litour-api", "litour-ui", "litour-celery", "litour-watcher", "litour-migrate"]
}

target "base" {
  context = "."
  dockerfile = "docker/Dockerfile.base"
  tags = tag("litour-base")
  cache-from = cache_from("litour-base")
  cache-to = cache_to("litour-base")
}

target "web-verify" {
  context = "."
  dockerfile = "docker/Dockerfile.web-verify"
  tags = tag("litour-verify")
  contexts = {
    base = "target:base"
  }
  cache-only = true
  cache-from = cache_from("litour-verify")
  cache-to = cache_to("litour-verify")
}

target "litour-caddy" {
  context = "."
  dockerfile = "docker/Dockerfile.caddy"
  target = "caddy"
  tags = tag("litour-caddy")
  contexts = {
    base = "target:base"
  }
  cache-from = cache_from("litour-caddy")
  cache-to = cache_to("litour-caddy")
}

target "litour-web" {
  context = "."
  dockerfile = "docker/Dockerfile.web"
  target = "web"
  tags = tag("litour-web")
  contexts = {
    base = "target:base"
  }
  args = {
    GITHUB_SHORT_SHA = GITHUB_SHORT_SHA
  }
  cache-from = cache_from("litour-web")
  cache-to = cache_to("litour-web")
}

target "javafo-verify" {
  context = "."
  dockerfile = "docker/Dockerfile.web"
  target = "web-verify"
  tags = tag("litour-javafo-verify")
  contexts = {
    base = "target:base"
  }
  cache-only = true
  cache-from = cache_from("litour-javafo-verify")
  cache-to = cache_to("litour-javafo-verify")
}

target "litour-api-worker" {
  context = "."
  dockerfile = "docker/Dockerfile.apiworker"
  tags = tag("litour-api-worker")
  contexts = {
    base = "target:base"
  }
  args = {
    GITHUB_SHORT_SHA = GITHUB_SHORT_SHA
  }
  cache-from = cache_from("litour-api-worker")
  cache-to = cache_to("litour-api-worker")
}

target "litour-api" {
  context = "."
  dockerfile = "docker/Dockerfile.api"
  tags = tag("litour-api")
  contexts = {
    base = "target:base"
  }
  args = {
    GITHUB_SHORT_SHA = GITHUB_SHORT_SHA
  }
  cache-from = cache_from("litour-api")
  cache-to = cache_to("litour-api")
}

target "litour-ui" {
  context = "."
  dockerfile = "docker/Dockerfile.ui"
  tags = tag("litour-ui")
  # `openapi.json` is gitignored — it's generated during the Python
  # build inside `litour-base`. We pull it from there as a build context
  # so the UI image doesn't need a host-side pre-step in CI.
  contexts = {
    base = "target:base"
  }
  args = {
    GITHUB_SHORT_SHA = GITHUB_SHORT_SHA
  }
  cache-from = cache_from("litour-ui")
  cache-to = cache_to("litour-ui")
}

target "litour-celery" {
  context = "."
  dockerfile = "docker/Dockerfile.celery"
  tags = tag("litour-celery")
  contexts = {
    base = "target:base"
  }
  cache-from = cache_from("litour-celery")
  cache-to = cache_to("litour-celery")
}

target "litour-watcher" {
  context = "."
  dockerfile = "docker/Dockerfile.watcher"
  tags = tag("litour-watcher")
  contexts = {
    base = "target:base"
  }
  cache-from = cache_from("litour-watcher")
  cache-to = cache_to("litour-watcher")
}

target "litour-migrate" {
  context = "."
  dockerfile = "docker/Dockerfile.migrate"
  tags = tag("litour-migrate")
  contexts = {
    base = "target:base"
  }
  cache-from = cache_from("litour-migrate")
  cache-to = cache_to("litour-migrate")
}
