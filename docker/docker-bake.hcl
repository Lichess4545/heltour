variable "TAG" {
  default = "latest"
}

variable "REGISTRY" {
  default = ""
}

variable "GITHUB_SHORT_SHA" {
  default = "unknown"
}

variable "REGISTRY_CACHE" {
  default = ""
}

function "tag" {
  params = [name]
  result = ["${lower(REGISTRY)}${REGISTRY != "" ? "/" : ""}${name}:${TAG}"]
}

# Always try the GHA cache scope (cheap, branch-aware). Additionally read from a
# registry-stored cache when REGISTRY_CACHE is set, so a fresh runner with no GHA
# cache can still pull layers from whatever was last pushed.
function "cache_from" {
  params = [name]
  result = concat(
    ["type=gha,scope=${name}"],
    REGISTRY_CACHE != "" ? ["type=registry,ref=${lower(REGISTRY)}${REGISTRY != "" ? "/" : ""}${name}:buildcache"] : [],
  )
}

# Registry cache is only written when REGISTRY_CACHE="push" (not merely set), so
# ordinary CI runs can read the shared cache without every branch overwriting it.
function "cache_to" {
  params = [name]
  result = concat(
    ["type=gha,mode=max,scope=${name}"],
    REGISTRY_CACHE == "push" ? ["type=registry,ref=${lower(REGISTRY)}${REGISTRY != "" ? "/" : ""}${name}:buildcache,mode=max"] : [],
  )
}

group "verify" {
  targets = ["web-verify", "javafo-verify", "celery-javafo-verify"]
}

group "default" {
  targets = ["base", "verify", "heltour-caddy", "heltour-web", "heltour-api-worker", "heltour-celery", "heltour-migrate"]
}

group "production" {
  targets = ["heltour-caddy", "heltour-web", "heltour-api-worker", "heltour-celery", "heltour-migrate"]
}

target "base" {
  context = "."
  dockerfile = "docker/Dockerfile.base"
  tags = tag("heltour-base")
  cache-from = cache_from("heltour-base")
  cache-to = cache_to("heltour-base")
}

# Runs the Django test suite (see Dockerfile.web-verify). Not to be confused with
# the "web-verify" stage inside Dockerfile.web, which javafo-verify below builds.
# cache-only: the point is to fail the build if tests fail — the resulting image is
# never run or pushed.
target "web-verify" {
  context = "."
  dockerfile = "docker/Dockerfile.web-verify"
  tags = tag("heltour-verify")
  contexts = {
    base = "target:base"
  }
  cache-only = true
  cache-from = cache_from("heltour-verify")
  cache-to = cache_to("heltour-verify")
}

target "heltour-caddy" {
  context = "."
  dockerfile = "docker/Dockerfile.caddy"
  target = "caddy"
  tags = tag("heltour-caddy")
  contexts = {
    base = "target:base"
  }
  cache-from = cache_from("heltour-caddy")
  cache-to = cache_to("heltour-caddy")
}

target "heltour-web" {
  context = "."
  dockerfile = "docker/Dockerfile.web"
  target = "web"
  tags = tag("heltour-web")
  contexts = {
    base = "target:base"
  }
  args = {
    GITHUB_SHORT_SHA = GITHUB_SHORT_SHA
  }
  cache-from = cache_from("heltour-web")
  cache-to = cache_to("heltour-web")
}

# Smoke-tests the vendored javafo.jar (see the web-verify stage in Dockerfile.web).
target "javafo-verify" {
  context = "."
  dockerfile = "docker/Dockerfile.web"
  target = "web-verify"
  tags = tag("heltour-javafo-verify")
  contexts = {
    base = "target:base"
  }
  cache-only = true
  cache-from = cache_from("heltour-javafo-verify")
  cache-to = cache_to("heltour-javafo-verify")
}

target "heltour-api-worker" {
  context = "."
  dockerfile = "docker/Dockerfile.apiworker"
  tags = tag("heltour-api-worker")
  contexts = {
    base = "target:base"
  }
  args = {
    GITHUB_SHORT_SHA = GITHUB_SHORT_SHA
  }
  cache-from = cache_from("heltour-api-worker")
  cache-to = cache_to("heltour-api-worker")
}

target "heltour-celery" {
  context = "."
  dockerfile = "docker/Dockerfile.celery"
  target = "celery"
  tags = tag("heltour-celery")
  contexts = {
    base = "target:base"
  }
  cache-from = cache_from("heltour-celery")
  cache-to = cache_to("heltour-celery")
}

target "celery-javafo-verify" {
  context = "."
  dockerfile = "docker/Dockerfile.celery"
  target = "celery-verify"
  tags = tag("heltour-celery-javafo-verify")
  contexts = {
    base = "target:base"
  }
  cache-only = true
  cache-from = cache_from("heltour-celery-javafo-verify")
  cache-to = cache_to("heltour-celery-javafo-verify")
}

target "heltour-migrate" {
  context = "."
  dockerfile = "docker/Dockerfile.migrate"
  tags = tag("heltour-migrate")
  contexts = {
    base = "target:base"
  }
  cache-from = cache_from("heltour-migrate")
  cache-to = cache_to("heltour-migrate")
}
