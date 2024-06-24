.PHONY: docker

server:
	python manage.py runserver

docker-build:
	docker build --target app -t lichess4545/heltour:latest .
	docker build --target static -t lichess4545/heltour-static:latest .

docker-run:
	docker run -p 8000:8000 lichess4545/heltour:latest
	docker run -p 8001:80 lichess4545/heltour-static:latest

