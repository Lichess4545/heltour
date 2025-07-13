{
  description = "Litour development environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:

    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };
      in {

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Shells
            fish

            # Python and package management
            python311 # Python 3.11 for compatibility
            poetry

            # Build dependencies for Python packages
            postgresql # For psycopg2 headers
            libffi # For cryptography

            # Image libraries for Pillow
            libjpeg # JPEG support
            libpng # PNG support
            libtiff # TIFF support
            libwebp # WebP support
            freetype # Font support
            lcms2 # Color management
            openjpeg # JPEG 2000 support
            zlib # Common dependency

            # Basic dev tools
            git
            curl
            wget
            which
            
            # Ruby and sass for SCSS compilation
            ruby_3_2
            bundler

            # Modern CLI tools
            glow # Markdown viewer
            eza # Better ls
            fd # Better find
            bat # Better cat
            btop # Better top
            lazygit # Git TUI
            zoxide # Smart cd
            dust # Better du
            starship # Better prompt
            ripgrep # Better grep (rg command)
            sd # Better sed
            procs # Better ps
            jq # JSON processing
            yq # YAML processing
            tree # Directory visualization

            flatpak # For lakin's sanity
            openssh # Fo lakin's saniyt
          ];

          shellHook = ''
            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:${pkgs.postgresql.lib}/lib:${pkgs.libjpeg}/lib:${pkgs.libpng}/lib:${pkgs.libtiff}/lib:${pkgs.libwebp}/lib:${pkgs.freetype}/lib:${pkgs.lcms2}/lib:${pkgs.openjpeg}/lib:$LD_LIBRARY_PATH"
            export LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:${pkgs.postgresql.lib}/lib:${pkgs.libjpeg}/lib:${pkgs.libpng}/lib:${pkgs.libtiff}/lib:${pkgs.libwebp}/lib:${pkgs.freetype}/lib:${pkgs.lcms2}/lib:${pkgs.openjpeg}/lib:$LIBRARY_PATH"
            
            # Set up Ruby gems directory
            export GEM_HOME="$PWD/.gems"
            export GEM_PATH="$GEM_HOME:$GEM_PATH"
            export PATH="$GEM_HOME/bin:$PATH"
            
            # Install sass gem if not already installed
            if ! gem list sass -i > /dev/null 2>&1; then
              echo "Installing sass gem..."
              gem install sass
            fi

            # PostgreSQL client configuration
            export PGHOST=localhost
            export PGPORT=5432

            # Set up Python virtual environment
            VENV_DIR=".venv"

            # Check if we need to recreate the venv (e.g., Python version mismatch)
            if [ -d "$VENV_DIR" ]; then
              VENV_PYTHON=$("$VENV_DIR/bin/python" --version 2>/dev/null || echo "none")
              EXPECTED_PYTHON=$(python3.11 --version)
              if [ "$VENV_PYTHON" != "$EXPECTED_PYTHON" ]; then
                echo "Python version mismatch. Recreating virtual environment..."
                rm -rf "$VENV_DIR"
              fi
            fi

            if [ ! -d "$VENV_DIR" ]; then
              echo "Creating virtual environment..."
              python3.11 -m venv "$VENV_DIR" --prompt="(litour)"
            fi

            # Activate virtual environment
            source "$VENV_DIR/bin/activate"

            # Install/update dependencies if needed
            if [ ! -f "$VENV_DIR/.poetry_installed" ] || [ "pyproject.toml" -nt "$VENV_DIR/.poetry_installed" ]; then
              echo "Installing/updating Python dependencies..."
              poetry install
              touch "$VENV_DIR/.poetry_installed"
            fi

            # Initialize zoxide
            eval "$(zoxide init bash)"

            # Modern tool aliases
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
            echo "Virtual environment: $VIRTUAL_ENV"
            echo ""
            echo "Common commands:"
            echo "  invoke runserver  # Run Django development server"
            echo "  invoke test       # Run tests"
            echo "  invoke migrate    # Run database migrations"
            echo ""
            echo "Switch to fish shell: exec fish"
            echo "Modern CLI tools are available with aliases (ls→eza, cat→bat, etc.)"

            # Optional: auto-switch to fish shell
            # Uncomment the next line if you want to automatically enter fish shell
            # [[ $- == *i* ]] && [[ -z "$IN_NIX_SHELL_FISH" ]] && IN_NIX_SHELL_FISH=1 exec fish
          '';
        };
      });
}

