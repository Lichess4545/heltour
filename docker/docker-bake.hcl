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

group "default" {
  targets = ["verify", "litour-web", "litour-api-worker", "litour-celery"]
}

group "production" {
  targets = ["litour-web", "litour-api-worker", "litour-celery"]
}

target "base" {
  context = "."
  dockerfile = "docker/Dockerfile.base"
  tags = tag("litour-base")
}

target "verify" {
  context = "."
  dockerfile = "docker/Dockerfile.verify"
  tags = tag("litour-verify")
  contexts = {
    base = "target:base"
  }
  cache-only = true
}

target "litour-web" {
  context = "."
  dockerfile = "docker/Dockerfile.django"
  tags = tag("litour-web")
  contexts = {
    base = "target:base"
  }
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