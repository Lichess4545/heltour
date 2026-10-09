{ pkgs, config, ... }:

let
  postgresUser = "heltour_lichess4545";
  postgresPassword = "sown shuts combiner chattels";
  postgresDatabase = "heltour_lichess4545";
  postgresPort = config.processes.postgres.ports.main.value;
  redisPort = config.processes.redis.ports.main.value;
  mailpitSmtpPort = config.processes.mailpit.ports.smtp.value;
  djangoPort = config.processes.django.ports.http.value;
  apiworkerPort = config.processes.apiworker.ports.http.value;

  databaseUrl = "postgresql://${postgresUser}:${builtins.replaceStrings [ " " ] [ "%20" ] postgresPassword}@127.0.0.1:${toString postgresPort}/${postgresDatabase}";
  redisUrl = "redis://127.0.0.1:${toString redisPort}/1";
  jre = pkgs.jre_minimal.override { jdk = pkgs.jdk21_headless; };
  servicesFirst = [ "devenv:processes:postgres" "devenv:processes:redis" ];
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
      CREATE USER ${postgresUser} WITH PASSWORD '${postgresPassword}' SUPERUSER;
      CREATE DATABASE ${postgresDatabase} OWNER ${postgresUser};
    '';
  };

  services.redis = {
    enable = true;
    bind = "127.0.0.1";
  };

  services.mailpit.enable = true;

  env = {
    DATABASE_URL = databaseUrl;
    REDIS_URL = redisUrl;
    BROKER_URL = redisUrl;
    EMAIL_HOST = "127.0.0.1";
    EMAIL_PORT = toString mailpitSmtpPort;
    EMAIL_USE_TLS = "False";
    API_WORKER_HOST = "http://localhost:${toString apiworkerPort}";
    CSRF_TRUSTED_ORIGINS = "http://localhost:${toString djangoPort},http://127.0.0.1:${toString djangoPort}";
    JAVAFO_COMMAND = "${jre}/bin/java -jar ./thirdparty/javafo.jar";
  };

  processes = {
    django = {
      exec = ''exec python manage.py runserver "127.0.0.1:${toString djangoPort}"'';
      ports.http.allocate = 8000;
      after = servicesFirst;
    };
    apiworker = {
      exec = ''HELTOUR_APP=api_worker exec python manage.py runserver "127.0.0.1:${toString apiworkerPort}"'';
      ports.http.allocate = 8880;
      after = servicesFirst;
    };
    celery = {
      exec = "exec celery --app heltour worker --loglevel INFO";
      after = servicesFirst;
    };
  };

  packages = [
    pkgs.gh
    pkgs.git-cliff
    pkgs.skopeo
  ];

  scripts.release.exec = ''cd "$DEVENV_ROOT" && exec nix run "$DEVENV_ROOT#release" -- "$@"'';
}
