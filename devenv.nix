{ pkgs, lib, ... }:

let
  nativeLibs = [
    pkgs.stdenv.cc.cc.lib
    pkgs.zlib
    pkgs.postgresql.lib
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
    # Shells
    fish

    # Build dependencies for Python packages
    postgresql # psycopg2 headers
    libffi # cryptography

    # Image libraries for Pillow
    libjpeg
    libpng
    libtiff
    libwebp
    freetype
    lcms2
    openjpeg
    zlib

    # Basic dev tools
    git
    curl
    wget
    which

    # JS/TS toolchain for frontend/api-client (IIFE bundle for Django) and frontend/ui (Next.js)
    bun
    nodejs_20

    # Reverse proxy for the prod-shape dev URL (`/v2/*` → Next.js, `/` → Django).
    caddy

    # Watcher used by the api-schema-watch process below.
    watchexec

    # Modern CLI tools
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

    # Image optimization
    imagemagick
    pngquant

    # Deployment
    flyctl

    # Misc
    flatpak
    openssh
    jre21_minimal # javafo
  ];

  # Auto-load .env into the shell so processes inherit LITOUR_API_BASE_URL,
  # NEXT_PUBLIC_LITOUR_API_URL, DATABASE_URL, etc.
  dotenv.enable = true;

  # Pin javafo to the Nix-provided JRE. Without this, `java` resolves to
  # /usr/bin/java which then mis-loads libjli.so from .devenv/profile/lib
  # (a jre21_minimal lib that's on LD_LIBRARY_PATH) and prints a noisy
  # "no version information available" warning on every invocation.
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

  languages.ruby = {
    enable = true;
    package = pkgs.ruby_3_3;
  };

  services.postgres = {
    enable = true;
    package = pkgs.postgresql_15;
    listen_addresses = "127.0.0.1";
    port = 5432;
    initialDatabases = [ { name = "heltour"; } ];
    initialScript = ''
      CREATE USER heltour WITH PASSWORD 'heltour_dev_password' SUPERUSER;
      GRANT ALL PRIVILEGES ON DATABASE heltour TO heltour;
    '';
  };

  services.redis = {
    enable = true;
    bind = "127.0.0.1";
    port = 6379;
  };

  services.mailpit = {
    enable = true;
    # SMTP on 1025, web UI on http://localhost:8025
  };

  # `devenv up` runs all of these alongside the services above.
  processes = {
    django.exec = "invoke runserver";
    apiworker.exec = "invoke runapiworker";
    runapi.exec = "invoke runapi";
    celery.exec = "invoke celery";
    watch-games.exec = "invoke watch-games";

    # Next.js dev server for frontend/ui (HMR built in). The UI consumes
    # `@litour/api-client` from source via `transpilePackages` in
    # next.config.ts — no separate build step needed in dev.
    ui.exec = "cd frontend/ui && bun run dev";

    # Rebuild the api-client IIFE bundle into Django statics on every TS change
    # so the legacy Django pairings page picks up edits without a manual step.
    api-client-iife-watch.exec = ''
      cd frontend/api-client && \
      bun run bundle:watch
    '';

    # When FastAPI routes / DTOs / pydantic schemas change, re-export
    # openapi.json and regenerate the typed TS client (`generated.ts`). Next's
    # HMR + the iife-watch process pick up the regenerated source directly
    # (no intermediate `dist/` build to race against).
    api-schema-watch.exec = ''
      watchexec \
        --watch heltour/api \
        --exts py \
        --debounce 500 \
        --on-busy-update queue \
        -- 'invoke openapi && (cd frontend/api-client && bun run generate)'
    '';

    # Local Caddy: gateway on :8080 mirroring prod's path layout.
    # Visit http://localhost:8080/ for Django, /v2/<league>/<event>/round/<n>/matches
    # for the Next.js UI, /v2/api/* for FastAPI. Hitting Django (:8000), FastAPI
    # (:8001), or Next.js (:3000) directly still works for debugging.
    caddy.exec = "caddy run --config dev/Caddyfile --adapter caddyfile";
  };

  enterShell = ''
    # Native library paths so Python wheels built against system libs resolve at runtime.
    export LD_LIBRARY_PATH="${lib.makeLibraryPath nativeLibs}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export LIBRARY_PATH="${lib.makeLibraryPath nativeLibs}''${LIBRARY_PATH:+:$LIBRARY_PATH}"

    # Project-local Ruby gems for sass.
    export GEM_HOME="$PWD/.gems"
    export GEM_PATH="$GEM_HOME''${GEM_PATH:+:$GEM_PATH}"
    export PATH="$GEM_HOME/bin:$PATH"

    if ! gem list sass -i > /dev/null 2>&1; then
      echo "Installing sass gem..."
      gem install sass
    fi

    # First-time install of frontend workspace deps so `devenv up` can start the
    # ui + watch processes immediately. The api-client `dist/` is built on
    # demand by the `ui` process itself (see `processes.ui` above), so a fresh
    # `devenv up` works without re-entering the shell.
    if [ -d frontend ] && [ ! -d frontend/node_modules ]; then
      echo "Installing frontend deps with bun..."
      (cd frontend && bun install)
    fi

    # Next.js auto-loads .env files from its own cwd, not the repo root. Symlink
    # the workspace UI's .env to the repo-root one so a single file at the
    # project root remains the source of truth and `next dev` picks up changes
    # without needing `@next/env` config tricks or a re-source of the shell.
    if [ -f .env ] && [ -d frontend/ui ] && [ ! -e frontend/ui/.env ]; then
      ln -s ../../.env frontend/ui/.env
    fi

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

    echo "Litour development environment"
    echo "================================"
    echo "Python: $(python --version)"
    echo "Poetry: $(poetry --version)"
    echo "Bun:    $(bun --version)"
    echo ""
    echo "Common commands:"
    echo "  devenv up         # Start postgres, redis, mailpit, django, apiworker,"
    echo "                    # runapi, celery, watch-games, ui, api-client-iife-watch, caddy"
    echo "  invoke migrate    # Run database migrations"
    echo "  invoke test       # Run tests"
    echo ""
    echo "URLs:"
    echo "  Caddy gateway (prod-shape): http://localhost:8080  (Django at /, Next.js at /v2/*)"
    echo "  Django direct:              http://localhost:8000"
    echo "  FastAPI direct:             http://localhost:8001  (docs at /docs)"
    echo "  Next.js direct:             http://localhost:3000  (basePath /v2 in dev)"
    echo "  Mailpit:                    http://localhost:8025"
    echo ""
    echo "Switch to fish shell: exec fish"
  '';
}
