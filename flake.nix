{
  description = "heltour, the Lichess4545 league manager, as a container image";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    dull-nix.url = "github:dull-ca/nix";
  };

  outputs = { self, nixpkgs, flake-utils, dull-nix }:
    flake-utils.lib.eachSystem [ "x86_64-linux" ] (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ dull-nix.overlays.default ];
        };
        inherit (pkgs) lib;

        python = pkgs.python311;
        jre = pkgs.jre_minimal.override { jdk = pkgs.jdk21_headless; };
        version = (lib.importTOML ./pyproject.toml).tool.poetry.version;
        mediaRoot = "/var/lib/heltour/media";

        manylinuxPlatforms =
          [ "manylinux1_x86_64" "manylinux2010_x86_64" "manylinux2014_x86_64" ]
          ++ map (minor: "manylinux_2_${toString minor}_x86_64")
            (lib.range 5 (lib.toInt (lib.versions.minor pkgs.glibc.version)));

        poetry = pkgs.poetry.withPlugins (plugins: [ plugins.poetry-plugin-export ]);

        pythonDeps = pkgs.stdenvNoCC.mkDerivation {
          name = "heltour-python-deps-${lib.substring 0 16 (builtins.hashFile "sha256" ./poetry.lock)}";
          src = lib.fileset.toSource {
            root = ./.;
            fileset = lib.fileset.unions [ ./pyproject.toml ./poetry.lock ];
          };
          nativeBuildInputs = [ poetry (python.withPackages (ps: [ ps.pip ])) ];
          buildPhase = ''
            export HOME=$TMPDIR
            export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
            poetry export --only main --format requirements.txt --output requirements.txt
            python -m pip download \
              --no-deps \
              --require-hashes \
              --disable-pip-version-check \
              --no-cache-dir \
              ${lib.concatMapStringsSep " " (platform: "--platform ${platform}") manylinuxPlatforms} \
              --python-version ${python.pythonVersion} \
              --implementation cp \
              --abi cp${lib.replaceStrings [ "." ] [ "" ] python.pythonVersion} \
              --requirement requirements.txt \
              --dest $out
          '';
          dontInstall = true;
          dontFixup = true;
          outputHashMode = "recursive";
          outputHashAlgo = "sha256";
          outputHash = lib.trim (builtins.readFile ./python-deps.hash);
        };

        venv = pkgs.stdenv.mkDerivation {
          name = "heltour-venv";
          dontUnpack = true;
          nativeBuildInputs = [ python pkgs.autoPatchelfHook ];
          buildInputs = [ pkgs.stdenv.cc.cc.lib pkgs.zlib ];
          installPhase = ''
            export HOME=$TMPDIR
            python -m venv $out
            PYTHONPATH=${python.pkgs.setuptools}/${python.sitePackages}:${python.pkgs.wheel}/${python.sitePackages} \
              $out/bin/python -m pip install \
                --no-index \
                --no-deps \
                --no-build-isolation \
                --no-cache-dir \
                --disable-pip-version-check \
                ${pythonDeps}/*
          '';
        };

        app = lib.fileset.toSource {
          root = ./.;
          fileset = lib.fileset.unions [ ./heltour ./manage.py ./thirdparty ];
        };

        static = pkgs.runCommand "heltour-static" { } ''
          cd ${app}
          export HOME=$TMPDIR PYTHONDONTWRITEBYTECODE=1 STATIC_ROOT=$out
          export SECRET_KEY=build DATABASE_URL=postgresql://build@localhost/build
          ${venv}/bin/python manage.py compilescss --use-storage
          ${venv}/bin/python manage.py collectstatic --noinput
        '';

        caddyfile = name: media: pkgs.writeText name ''
          {
          	admin off
          	auto_https off
          	persist_config off
          }

          :8080 {
          	handle_path /static/* {
          		root * ${static}
          		file_server
          	}
          ${media}
          	handle {
          		reverse_proxy web:8000
          	}
          }
        '';

        siteCaddyfile = caddyfile "Caddyfile" "";

        mediaCaddyfile = caddyfile "Caddyfile.media" ''

          	handle_path /media/* {
          		rewrite * {$MEDIA_ORIGIN_PATH}{uri}
          		reverse_proxy {$MEDIA_ORIGIN_UPSTREAM} {
          			header_up Host {upstream_hostport}
          			header_up -Cookie
          			header_up -Authorization
          		}
          	}
        '';

        command = name: runtimeInputs: text: pkgs.writeShellApplication {
          inherit name runtimeInputs;
          text = ''
            cd ${app}
            ${text}
          '';
        };

        commands = pkgs.symlinkJoin {
          name = "heltour-commands";
          paths = [
            (command "heltour-web" [ venv ] ''
              exec gunicorn heltour.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 300 --worker-tmp-dir /dev/shm --access-logfile - "$@"
            '')
            (command "heltour-apiworker" [ venv ] ''
              export HELTOUR_APP=api_worker
              exec gunicorn heltour.wsgi:application --bind 0.0.0.0:8880 --workers 2 --timeout 60 --worker-tmp-dir /dev/shm --access-logfile - "$@"
            '')
            (command "heltour-celery" [ venv ] ''
              exec celery --app heltour worker --beat --concurrency 4 --loglevel INFO -O fair "$@"
            '')
            (command "heltour-migrate" [ venv ] ''
              python manage.py migrate --noinput
              exec python manage.py invalidate all
            '')
            (command "heltour-manage" [ venv ] ''
              exec python manage.py "$@"
            '')
            (command "heltour-caddy" [ pkgs.caddy ] ''
              if [ -z "''${MEDIA_ORIGIN_URL:-}" ]; then
                exec caddy run --adapter caddyfile --config ${siteCaddyfile}
              fi
              origin="''${MEDIA_ORIGIN_URL%/}"
              authority="''${origin#*://}"
              authority="''${authority%%/*}"
              path="''${origin#*://"$authority"}"
              export MEDIA_ORIGIN_UPSTREAM="''${origin%%://*}://$authority"
              export MEDIA_ORIGIN_PATH="$path"
              exec caddy run --adapter caddyfile --config ${mediaCaddyfile}
            '')
          ];
        };

        container = pkgs.dockerTools.buildLayeredImage {
          name = "heltour";
          tag = "latest";
          contents = [ pkgs.dockerTools.fakeNss pkgs.dockerTools.caCertificates pkgs.dockerTools.binSh commands ];
          extraCommands = "mkdir -m 1777 tmp";
          fakeRootCommands = ''
            mkdir -p .${mediaRoot}
            chown 65534:65534 .${mediaRoot}
          '';
          config = {
            Cmd = [ "heltour-web" ];
            User = "nobody";
            Env = [
              "HOME=/tmp"
              "SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt"
              "PYTHONDONTWRITEBYTECODE=1"
              "PYTHONUNBUFFERED=1"
              "DJANGO_SETTINGS_MODULE=heltour.settings"
              "HELTOUR_VERSION=${version}"
              "STATIC_ROOT=${static}"
              "MEDIA_ROOT=${mediaRoot}"
              "JAVAFO_COMMAND=${jre}/bin/java -jar ${app}/thirdparty/javafo.jar"
              "XDG_CONFIG_HOME=/tmp"
              "XDG_DATA_HOME=/tmp"
            ];
            Labels."org.opencontainers.image.source" = "https://github.com/Lichess4545/heltour";
          };
        };

        javafo = pkgs.runCommand "heltour-javafo-check" { } ''
          ${jre}/bin/java -jar ${app}/thirdparty/javafo.jar > banner 2>&1 || true
          grep -F 'JaVaFo (rrweb.org/javafo)' banner
          touch $out
        '';

        django = pkgs.runCommand "heltour-django-check" { } ''
          cd ${app}
          export HOME=$TMPDIR PYTHONDONTWRITEBYTECODE=1
          export SECRET_KEY=check DATABASE_URL=postgresql://check@localhost/check
          ${venv}/bin/python manage.py check --deploy --fail-level ERROR
          touch $out
        '';
      in
      {
        checks = {
          inherit container javafo django;
          release-guards-hold = pkgs.releaseGuardsTest;
        };

        packages = {
          inherit container;
          default = container;
          python-deps = pythonDeps;
          release = pkgs.mkReleaseCommand {
            repositoryUrl = "https://github.com/Lichess4545/heltour";
            hooks = ./ci/release-hooks.sh;
            releaseWorkflow = "release.yml";
          };
          release-guards = pkgs.releaseGuards;
        };
      });
}
