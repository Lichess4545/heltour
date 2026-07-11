{ pkgs, lib, ... }:

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
      CREATE USER heltour_lichess4545 WITH PASSWORD 'heltour_dev_password' SUPERUSER;
      CREATE DATABASE heltour_lichess4545 OWNER heltour_lichess4545;
    '';
  };

  services.redis = {
    enable = true;
    bind = "127.0.0.1";
    port = 6379;
  };

  services.mailpit.enable = true;

  processes = {
    django.exec = "invoke runserver";
    apiworker.exec = "invoke runapiworker";
    celery.exec = "invoke celery";
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
    echo "Django:     http://localhost:8000"
    echo "API worker: http://localhost:8880"
    echo "Mailpit:    http://localhost:8025"
    echo ""
    echo "Switch to fish shell: exec fish"
  '';
}
