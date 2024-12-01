.PHONY: docker

export DJANGO_DB_HOST=127.0.0.1
export DJANGO_DB_PORT=5432
export DJANGO_DB_USER=local
export DJANGO_DB_PASS=password
export DJANGO_SETTINGS_MODULE=heltour.settings_development


server:
	python ./manage.py runserver


migrate:
	python ./manage.py migrate

collectstatic:
	python ./manage.py collectstatic

init: collectstatic migrate

docker-build:
	docker build --target app -t lichess4545/heltour:latest .
	docker build --target static -t lichess4545/heltour-static:latest .

docker-run:
	docker run -p 8000:8000 lichess4545/heltour:latest
	docker run -p 8001:80 lichess4545/heltour-static:latest

up:
	docker compose up

up-deps:
	docker compose up redis postgres
