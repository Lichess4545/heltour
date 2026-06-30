{ pkgs, ... }:

{
  services.postgres = {
    enable = true;

    # The app connects over TCP to localhost:5432 (heltour/settings_default.py).
    # devenv's default is socket-only, so opt into TCP on the loopback.
    listen_addresses = "127.0.0.1";

    # Created once, when the data dir is first initialized by `devenv up`.
    # Matches DATABASES['default'] in heltour/settings_default.py.
    initialScript = ''
      CREATE USER heltour_lichess4545 WITH PASSWORD 'sown shuts combiner chattels' SUPERUSER;
      CREATE DATABASE heltour_lichess4545 OWNER heltour_lichess4545;
    '';
  };
}
