import { dag, Container, Directory, Secret, Service, object, func } from "@dagger.io/dagger"

const PYTHON_IMAGE = "python:3.11-slim-bookworm"
const POSTGRES_IMAGE = "postgres:18-alpine"
const REDIS_IMAGE = "redis:7-alpine"
const CURL_IMAGE = "curlimages/curl:8.11.1"
const CADDY_IMAGE = "caddy:2-alpine"

const JAVAFO_BANNER = "JaVaFo (rrweb.org/javafo) - Rel. 2.2 (Build 3223)"

const GHCR_REGISTRY = "ghcr.io"
const GHCR_IMAGE_PREFIX = "lichess4545"

const TEST_POSTGRES_DB = "heltour_lichess4545"
const TEST_POSTGRES_USER = "heltour_lichess4545"
const TEST_POSTGRES_PASSWORD = "heltour_dev_password"

const GUNICORN_ARGS = [
  "gunicorn",
  "heltour.wsgi:application",
  "--bind",
  "0.0.0.0:8000",
  "--workers",
  "4",
  "--threads",
  "2",
  "--worker-class",
  "sync",
  "--worker-tmp-dir",
  "/dev/shm",
  "--log-file",
  "-",
  "--access-logfile",
  "-",
  "--error-logfile",
  "-",
]

function javafoVerifyScript(): string {
  return [
    `output=$(java -jar /app/thirdparty/javafo.jar 2>&1)`,
    `echo "$output" | grep -q "${JAVAFO_BANNER}" || (echo "JavaFo test failed. Expected '${JAVAFO_BANNER}', got: $output" && exit 1)`,
  ].join(" && ")
}

function resolvePublishTag(ref: string, eventName: string, prNumber: string, defaultBranchRef: string): string {
  if (ref === defaultBranchRef) {
    return "latest"
  }
  if (eventName === "pull_request") {
    return `pr-${prNumber}`
  }
  return ref
    .replace(/^refs\/heads\//, "")
    .replace(/[^a-zA-Z0-9._-]/g, "-")
}

@object()
export class Heltour {
  @func()
  postgresService(): Service {
    return dag
      .container()
      .from(POSTGRES_IMAGE)
      .withEnvVariable("POSTGRES_DB", TEST_POSTGRES_DB)
      .withEnvVariable("POSTGRES_USER", TEST_POSTGRES_USER)
      .withEnvVariable("POSTGRES_PASSWORD", TEST_POSTGRES_PASSWORD)
      .withExposedPort(5432)
      .asService({ useEntrypoint: true })
  }

  @func()
  redisService(): Service {
    return dag.container().from(REDIS_IMAGE).withExposedPort(6379).asService({ useEntrypoint: true })
  }

  @func()
  async test(source: Directory): Promise<string> {
    return this.testRunner(source).stdout()
  }

  private testRunner(source: Directory): Container {
    return dag
      .container()
      .from(PYTHON_IMAGE)
      .withExec([
        "sh",
        "-c",
        "apt-get update && apt-get install -y --no-install-recommends gcc g++ libpq-dev && rm -rf /var/lib/apt/lists/*",
      ])
      .withExec(["pip", "install", "--no-cache-dir", "poetry"])
      .withMountedCache("/root/.cache/pypoetry", dag.cacheVolume("heltour-poetry"))
      .withDirectory("/app", source, { exclude: [".git", "**/__pycache__", "**/*.pyc"] })
      .withWorkdir("/app")
      .withServiceBinding("postgres", this.postgresService())
      .withServiceBinding("redis", this.redisService())
      .withEnvVariable("SECRET_KEY", "change-me-in-production")
      .withEnvVariable("DEBUG", "True")
      .withEnvVariable("ALLOWED_HOSTS", "localhost,127.0.0.1")
      .withEnvVariable("CSRF_TRUSTED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
      .withEnvVariable("LINK_PROTOCOL", "http")
      .withEnvVariable(
        "DATABASE_URL",
        `postgresql://${TEST_POSTGRES_USER}:${TEST_POSTGRES_PASSWORD}@postgres:5432/${TEST_POSTGRES_DB}`,
      )
      .withEnvVariable("REDIS_URL", "redis://redis:6379/1")
      .withEnvVariable("BROKER_URL", "redis://redis:6379/1")
      .withEnvVariable("HELTOUR_APP", "tournament")
      .withEnvVariable("HELTOUR_ENV", "dev")
      .withExec(["poetry", "install", "--no-interaction", "--no-root"])
      .withExec(["poetry", "run", "python", "manage.py", "test", "--settings=heltour.test_settings"])
  }

  @func()
  base(source: Directory): Container {
    return source.dockerBuild({ dockerfile: "docker/Dockerfile.base" })
  }

  @func()
  web(source: Directory, githubShortSha = "unknown"): Container {
    return this.base(source)
      .withExposedPort(8000)
      .withEnvVariable("DJANGO_SETTINGS_MODULE", "heltour.settings")
      .withEnvVariable("PYTHONUNBUFFERED", "1")
      .withEnvVariable("HELTOUR_VERSION", githubShortSha)
      .withDefaultArgs(GUNICORN_ARGS)
  }

  @func()
  apiWorker(source: Directory, githubShortSha = "unknown"): Container {
    return this.base(source)
      .withExposedPort(8880)
      .withEnvVariable("PYTHONUNBUFFERED", "1")
      .withEnvVariable("DJANGO_SETTINGS_MODULE", "heltour.settings")
      .withEnvVariable("HELTOUR_APP", "api_worker")
      .withEnvVariable("HELTOUR_VERSION", githubShortSha)
      .withDefaultArgs(GUNICORN_ARGS)
  }

  @func()
  celery(source: Directory): Container {
    return this.base(source)
      .withEnvVariable("PYTHONUNBUFFERED", "1")
      .withEnvVariable("DJANGO_SETTINGS_MODULE", "heltour.settings")
      .withDefaultArgs(["celery", "-A", "heltour", "worker", "-l", "info", "-E", "-B"])
  }

  @func()
  migrate(source: Directory): Container {
    return this.base(source)
      .withEnvVariable("DJANGO_SETTINGS_MODULE", "heltour.settings")
      .withEnvVariable("PYTHONUNBUFFERED", "1")
      .withDefaultArgs([
        "sh",
        "-c",
        "pg_isready --dbname=$(cat $DATABASE_URL_FILE) --timeout=60 || pg_isready --dbname=$DATABASE_URL --timeout=60 && python manage.py migrate",
      ])
  }

  @func()
  caddy(source: Directory): Container {
    return dag
      .container()
      .from(CADDY_IMAGE)
      .withDirectory("/public/static", this.base(source).directory("/app/static"))
      .withFile("/etc/caddy/Caddyfile", source.file("docker/Caddyfile"))
  }

  @func()
  async verifyDjangoSuite(source: Directory): Promise<string> {
    return this.base(source)
      .withUser("root")
      .withExec(["sh", "-c", "apt-get update && apt-get install -y redis-server && rm -rf /var/lib/apt/lists/*"])
      .withUser("heltour")
      .withEnvVariable("DJANGO_SETTINGS_MODULE", "heltour.test_settings")
      .withEnvVariable("PYTHONUNBUFFERED", "1")
      .withEnvVariable("DEBUG", "True")
      .withEnvVariable("SECRET_KEY", "test-secret-key-only-for-testing")
      .withEnvVariable("ALLOWED_HOSTS", "*")
      .withEnvVariable("DATABASE_URL", "sqlite:///db.sqlite3")
      .withEnvVariable("REDIS_URL", "redis://localhost:6379/0")
      .withEnvVariable("BROKER_URL", "redis://localhost:6379/1")
      .withEnvVariable("HELTOUR_ENV", "test")
      .withExec([
        "sh",
        "-c",
        "redis-server --port 6379 --bind 127.0.0.1 --daemonize yes && sleep 1 && python manage.py test --settings=heltour.test_settings --failfast",
      ])
      .stdout()
  }

  @func()
  async verifyJavafo(container: Container): Promise<string> {
    return container.withExec(["sh", "-c", javafoVerifyScript()]).stdout()
  }

  private namedImages(source: Directory, githubShortSha: string): [string, Container][] {
    return [
      ["heltour-base", this.base(source)],
      ["heltour-caddy", this.caddy(source)],
      ["heltour-web", this.web(source, githubShortSha)],
      ["heltour-api-worker", this.apiWorker(source, githubShortSha)],
      ["heltour-celery", this.celery(source)],
      ["heltour-migrate", this.migrate(source)],
    ]
  }

  private async verifyAndBuild(
    source: Directory,
    githubShortSha: string,
  ): Promise<{ report: string; images: [string, Container][] }> {
    const images = this.namedImages(source, githubShortSha)

    const [djangoSuite, javafoWeb, javafoCelery] = await Promise.all([
      this.verifyDjangoSuite(source),
      this.verifyJavafo(this.web(source, githubShortSha)),
      this.verifyJavafo(this.celery(source)),
    ])

    await Promise.all(images.map(([, container]) => container.sync()))

    const report = [
      "web-verify (django suite):",
      djangoSuite,
      "javafo-verify (web image):",
      javafoWeb,
      "celery-javafo-verify (celery image):",
      javafoCelery,
      "images built: heltour-base, heltour-web, heltour-api-worker, heltour-celery, heltour-migrate, heltour-caddy",
    ].join("\n")

    return { report, images }
  }

  @func()
  async build(source: Directory, githubShortSha = "unknown"): Promise<string> {
    const { report } = await this.verifyAndBuild(source, githubShortSha)
    return report
  }

  @func()
  async publish(
    source: Directory,
    ref: string,
    eventName: string,
    registryUsername: string,
    registryPassword: Secret,
    prNumber = "",
    githubSha = "unknown",
    defaultBranchRef = "refs/heads/master",
  ): Promise<string> {
    const githubShortSha = githubSha.slice(0, 7)
    const { images } = await this.verifyAndBuild(source, githubShortSha)

    const tag = resolvePublishTag(ref, eventName, prNumber, defaultBranchRef)
    const registry = `${GHCR_REGISTRY}/${GHCR_IMAGE_PREFIX}`

    const published: string[] = []
    for (const [name, container] of images) {
      const address = `${registry}/${name}:${tag}`
      const publishedRef = await container
        .withRegistryAuth(GHCR_REGISTRY, registryUsername, registryPassword)
        .publish(address)
      published.push(publishedRef)
    }

    return published.join("\n")
  }

  @func()
  async deploy(environment: string, service: string, url: Secret): Promise<string> {
    const status = await dag
      .container()
      .from(CURL_IMAGE)
      .withSecretVariable("DEPLOY_URL", url)
      .withExec([
        "sh",
        "-c",
        'curl --silent --write-out "%{http_code}" --fail-with-body --request POST "$DEPLOY_URL"',
      ])
      .stdout()

    return `${environment}/${service}: ${status}`
  }
}
