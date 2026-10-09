{ pkgs, ... }:

{
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

  packages = [
    pkgs.gh
    pkgs.git-cliff
    pkgs.skopeo
  ];

  scripts.release.exec = ''cd "$DEVENV_ROOT" && exec nix run "$DEVENV_ROOT#release" -- "$@"'';
}
