.PHONY: docker-build server migrate collectstatic init docker-run up up-deps celery loaddata dbshell shell

export DJANGO_DB_HOST=127.0.0.1
export DJANGO_DB_PORT=5432
export DJANGO_DB_NAME=local
export DJANGO_DB_USER=local
export DJANGO_DB_PASS=password
export DJANGO_SETTINGS_MODULE=heltour.settings_development
export DJANGO_CACHE_URL=redis://127.0.0.1:6379/1
export DJANGO_CACHEOPS_URL=redis://127.0.0.1:6379/1
export CELERY_BROKER_URL=redis://127.0.0.1:6379/2

test:
	python manage.py test

server:
	python manage.py runserver

celery:
	celery -A heltour worker -B -c 1 --loglevel INFO -O fair

migrate:
	python manage.py migrate

dbshell:
	python manage.py dbshell

shell:
	python manage.py shell

collectstatic:
	python manage.py collectstatic

createsuperuser:
	python manage.py createsuperuser

loaddata:
	python manage.py loaddata users leagues

init: collectstatic migrate createsuperuser

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

up-deps-d:
	docker compose up -d redis postgres 
