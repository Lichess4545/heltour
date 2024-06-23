FROM python:3.11-slim
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

CMD ["gunicorn", "-t", "300", "-w", "4", "heltour.wsgi:application"]

