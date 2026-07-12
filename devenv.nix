{ pkgs, lib, config, ... }:

let
  # Matches what psycopg2-binary and pillow (pinned in pyproject.toml) link
  # against at import time; exported as LD_LIBRARY_PATH below.
  nativeLibs = [
    pkgs.stdenv.cc.cc.lib
    pkgs.zlib
    pkgs.postgresql_18.lib
    pkgs.libjpeg
    pkgs.libpng
    pkgs.libtiff
    pkgs.libwebp
    pkgs.freetype
    pkgs.lcms2
    pkgs.openjpeg
  ];

  postgresUser = "heltour_lichess4545";
  postgresPassword = "heltour_dev_password";
  postgresDatabase = "heltour_lichess4545";
  # devenv's port allocator tries these base ports first and shifts to the
  # next free one if occupied (e.g. by another project's devenv). Reading
  # back the *.value the allocator actually bound, rather than the base
  # port, keeps DATABASE_URL/REDIS_URL/BROKER_URL/EMAIL_* correct even when
  # it shifts. See docs/adr for the full rationale.
  postgresPort = config.env.PGPORT;
  redisDb = "1";
  redisPort = config.processes.redis.ports.main.value;
  mailpitSmtpPort = config.processes.mailpit.ports.smtp.value;
  mailpitUiPort = config.processes.mailpit.ports.ui.value;
  # Same allocator as the DB/broker ports: django/apiworker declare a base
  # HTTP port below and devenv shifts off it when taken. Reading the bound
  # *.value feeds the shifted port into both the runserver command and the
  # API_WORKER_HOST/CSRF_TRUSTED_ORIGINS the app builds from it.
  djangoPort = config.processes.django.ports.http.value;
  apiworkerPort = config.processes.apiworker.ports.http.value;

  databaseUrl = "postgresql://${postgresUser}:${postgresPassword}@127.0.0.1:${toString postgresPort}/${postgresDatabase}";
  redisUrl = "redis://127.0.0.1:${toString redisPort}/${redisDb}";
  apiWorkerHost = "http://localhost:${toString apiworkerPort}";
  csrfTrustedOrigins = "http://localhost:${toString djangoPort},http://127.0.0.1:${toString djangoPort}";
in
{
  packages = with pkgs; [
    fish

    postgresql_18 # pg_dump/pg_restore/headers; keep in sync with services.postgres.package below
    libffi

    libjpeg
    libpng
    libtiff
    libwebp
    freetype
    lcms2
    openjpeg
    zlib

    git
    curl
    wget
    which

    glow
    eza
    fd
    bat
    btop
    lazygit
    zoxide
    dust
    starship
    ruff
    ripgrep
    sd
    procs
    jq
    yq
    tree

    imagemagick
    pngquant

    flyctl

    flatpak
    openssh
    jre21_minimal
  ];

  dotenv.enable = true;

  # Pinned to the Nix-provided JRE so `java` doesn't fall through to a system
  # /usr/bin/java, which would pick up an incompatible libjli.so off
  # LD_LIBRARY_PATH below. thirdparty/javafo.jar is vendored in this repo (ADR 0013).
  env.JAVAFO_COMMAND = "${pkgs.jre21_minimal}/bin/java -jar ./thirdparty/javafo.jar";

  languages.python = {
    enable = true;
    package = pkgs.python311;
    poetry = {
      enable = true;
      install.enable = true;
      activate.enable = true;
    };
  };

  languages.javascript = {
    enable = true;
  };

  services.postgres = {
    enable = true;
    # Must stay in sync with nativeLibs' postgresql_18.lib and the client
    # package above. Bumping the major version needs `rm -rf
    # .devenv/state/postgres` first — the on-disk data dir isn't
    # forward-compatible across major versions and devenv won't wipe it for you.
    package = pkgs.postgresql_18;
    listen_addresses = "127.0.0.1";
    port = 5432;
    # SUPERUSER + OWNER rather than litour's GRANT-to-non-owner role: on PG15+
    # the public schema is owned by pg_database_owner, so GRANT ALL PRIVILEGES
    # ON DATABASE alone doesn't include CREATE on public, and `manage.py
    # migrate` fails with "permission denied for schema public". Owning the
    # database sidesteps that.
    initialScript = ''
      CREATE USER ${postgresUser} WITH PASSWORD '${postgresPassword}' SUPERUSER;
      CREATE DATABASE ${postgresDatabase} OWNER ${postgresUser};
    '';
  };

  services.redis = {
    enable = true;
    bind = "127.0.0.1";
    port = 6379;
  };

  services.mailpit.enable = true;

  # Single source of truth for the dev DB/broker/mail URLs: built from the
  # ports devenv's allocator actually bound (see the `let` block above), not
  # the fixed ports from .env.example. mkDefault-priority dotenv values from
  # .env lose to these, so a stale DATABASE_URL left in .env can't shadow
  # wherever postgres/redis/mailpit actually came up.
  env.DATABASE_URL = databaseUrl;
  env.REDIS_URL = redisUrl;
  env.BROKER_URL = redisUrl;
  env.EMAIL_HOST = "127.0.0.1";
  env.EMAIL_PORT = mailpitSmtpPort;
  # django/celery reach the apiworker through API_WORKER_HOST; CSRF checks the
  # browser origin against CSRF_TRUSTED_ORIGINS. Both carry the HTTP port, so
  # both are derived from the same allocated values, not the fixed 8000/8880.
  env.API_WORKER_HOST = apiWorkerHost;
  env.CSRF_TRUSTED_ORIGINS = csrfTrustedOrigins;

  processes = {
    django = {
      exec = "invoke runserver --port ${toString djangoPort}";
      ports.http.allocate = 8000;
      after = [ "devenv:processes:postgres" "devenv:processes:redis" ];
    };
    apiworker = {
      exec = "invoke runapiworker --port ${toString apiworkerPort}";
      ports.http.allocate = 8880;
      after = [ "devenv:processes:postgres" "devenv:processes:redis" ];
    };
    celery = {
      exec = "invoke celery";
      after = [ "devenv:processes:postgres" "devenv:processes:redis" ];
    };
  };

  enterShell = ''
    # nativeLibs above, so psycopg2/pillow find their shared libs at runtime.
    export LD_LIBRARY_PATH="${lib.makeLibraryPath nativeLibs}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export LIBRARY_PATH="${lib.makeLibraryPath nativeLibs}''${LIBRARY_PATH:+:$LIBRARY_PATH}"

    eval "$(zoxide init bash)"

    alias ls='eza'
    alias ll='eza -la'
    alias la='eza -a'
    alias lt='eza --tree'
    alias find='fd'
    alias cat='bat'
    alias cd='z'
    alias du='dust'
    alias ps='procs'
    alias grep='rg'
    alias sed='sd'

    echo "heltour development environment"
    echo "================================"
    echo "Python: $(python --version)"
    echo "Poetry: $(poetry --version)"
    echo ""
    echo "devenv up starts postgres, redis, mailpit, django, apiworker, celery"
    echo "invoke migrate runs database migrations"
    echo "invoke test runs the test suite"
    echo ""
    echo "Postgres:   127.0.0.1:${toString postgresPort}/${postgresDatabase} (shifts if occupied; DATABASE_URL follows it)"
    echo "Redis:      127.0.0.1:${toString redisPort}/${redisDb} (shifts if occupied; REDIS_URL/BROKER_URL follow it)"
    echo "Django:     http://localhost:${toString djangoPort} (shifts if occupied; CSRF_TRUSTED_ORIGINS follows it)"
    echo "API worker: ${apiWorkerHost} (shifts if occupied; API_WORKER_HOST follows it)"
    echo "Mailpit:    http://127.0.0.1:${toString mailpitUiPort} (SMTP 127.0.0.1:${toString mailpitSmtpPort})"
    echo ""
    echo "Switch to fish shell: exec fish"
  '';
}
