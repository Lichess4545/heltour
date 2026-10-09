{ pkgs, ... }:

let
  jre = pkgs.jre_minimal.override { jdk = pkgs.jdk21_headless; };
in
{
  languages.python = {
    enable = true;
    package = pkgs.python311;
    manylinux.enable = true;
    poetry = {
      enable = true;
      install = {
        enable = true;
        onlyGroups = [ "main" ];
      };
      activate.enable = true;
    };
  };

  services.postgres = {
    enable = true;

    # devenv's default is socket-only, so opt into TCP on the loopback.
    listen_addresses = "127.0.0.1";

    # Created once, when the data dir is first initialized by `devenv up`.
    initialScript = ''
      CREATE USER heltour_lichess4545 WITH PASSWORD 'sown shuts combiner chattels' SUPERUSER;
      CREATE DATABASE heltour_lichess4545 OWNER heltour_lichess4545;
    '';
  };

  env.JAVAFO_COMMAND = "${jre}/bin/java -jar ./thirdparty/javafo.jar";

  packages = [
    pkgs.gh
    pkgs.git-cliff
    pkgs.skopeo
  ];

  scripts.release.exec = ''cd "$DEVENV_ROOT" && exec nix run "$DEVENV_ROOT#release" -- "$@"'';
}
