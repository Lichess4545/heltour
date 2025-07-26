variable "TAG" {
  default = "latest"
}

variable "REGISTRY" {
  default = ""
}

function "tag" {
  params = [name]
  result = ["${lower(REGISTRY)}${REGISTRY != "" ? "/" : ""}${name}:${TAG}"]
}

group "verify" {
  targets = ["web-verify", "javafo-verify"]
}

group "default" {
  targets = ["base", "verify", "litour-web", "litour-api-worker", "litour-celery"]
}

group "production" {
  targets = ["litour-web", "litour-api-worker", "litour-celery"]
}

target "base" {
  context = "."
  dockerfile = "docker/Dockerfile.base"
  tags = tag("litour-base")
}

target "web-verify" {
  context = "."
  dockerfile = "docker/Dockerfile.web-verify"
  contexts = {
    base = "target:base"
  }
  cache-only = true
}

target "litour-web" {
  context = "."
  dockerfile = "docker/Dockerfile.web"
  target = "web"
  tags = tag("litour-web")
  contexts = {
    base = "target:base"
  }
}

target "javafo-verify" {
  context = "."
  dockerfile = "docker/Dockerfile.web"
  target = "web-verify"
  contexts = {
    base = "target:base"
  }
  cache-only = true
}

target "litour-api-worker" {
  context = "."
  dockerfile = "docker/Dockerfile.apiworker"
  tags = tag("litour-api-worker")
  contexts = {
    base = "target:base"
  }
}

target "litour-celery" {
  context = "."
  dockerfile = "docker/Dockerfile.celery"
  tags = tag("litour-celery")
  contexts = {
    base = "target:base"
  }
}
