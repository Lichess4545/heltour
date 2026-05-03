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
    celery.exec = "invoke celery";
    watch-games.exec = "invoke watch-games";
  };

  enterShell = ''
    # Native library paths so Python wheels built against system libs resolve at runtime
    export LD_LIBRARY_PATH="${lib.makeLibraryPath nativeLibs}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export LIBRARY_PATH="${lib.makeLibraryPath nativeLibs}''${LIBRARY_PATH:+:$LIBRARY_PATH}"

    # Project-local Ruby gems for sass
    export GEM_HOME="$PWD/.gems"
    export GEM_PATH="$GEM_HOME''${GEM_PATH:+:$GEM_PATH}"
    export PATH="$GEM_HOME/bin:$PATH"

    if ! gem list sass -i > /dev/null 2>&1; then
      echo "Installing sass gem..."
      gem install sass
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
    echo ""
    echo "Common commands:"
    echo "  devenv up         # Start postgres, redis, mailpit, django, apiworker, celery"
    echo "  invoke migrate    # Run database migrations"
    echo "  invoke test       # Run tests"
    echo ""
    echo "Mailpit UI: http://localhost:8025"
    echo "Switch to fish shell: exec fish"
    echo "Modern CLI tools are available with aliases (ls→eza, cat→bat, etc.)"
  '';
}
