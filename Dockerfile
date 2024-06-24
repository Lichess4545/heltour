FROM python:3.11-slim as build

WORKDIR /usr/src/heltour

RUN apt-get update && \
    apt-get install -y gcc libpq-dev libffi-dev && \
    apt-get clean 

RUN pip install poetry
RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./

RUN poetry install --with server

COPY manage.py .
COPY heltour/ ./heltour

RUN poetry install
RUN python manage.py collectstatic

FROM nginx as static
COPY --from=collectstatic /usr/src/heltour/static /usr/share/nginx/html

FROM build as app
CMD ["gunicorn", "-t", "300", "-w", "4", "-b", "0.0.0.0:8000", "heltour.wsgi:application"]

