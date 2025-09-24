FROM python:3.11-slim-bookworm

# Accept build arguments
ARG GITHUB_SHORT_SHA=unknown

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    HELTOUR_VERSION=${GITHUB_SHORT_SHA}

# Install system dependencies including Java for javafo.jar
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    git \
    build-essential \
    ruby \
    ruby-dev \
    postgresql-client \
    openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Install Ruby sass for SCSS compilation
RUN gem install sass

# Set up non-root user
RUN useradd -m -u 1000 litour

# Set working directory
WORKDIR /app

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install Python dependencies
RUN poetry install --no-root --only main

# Copy application code
COPY --chown=litour:litour . .

# Install the application and compile static files
ENV DEBUG=False
ENV DATABASE_URL=postgresql://dummy:dummy@localhost:5432/dummy
ENV STATIC_ROOT=/app/static
ENV SECRET_KEY="temporary-key-for-static-compilation"

RUN poetry install --only main && \
    mkdir -p /app/static && \
    python manage.py compilescss && \
    python manage.py collectstatic --noinput

# Verify javafo.jar works correctly (for pairing generation)
RUN output=$(java -jar /app/thirdparty/javafo.jar 2>&1) && \
    echo "$output" | grep -q "JaVaFo (rrweb.org/javafo) - Rel. 2.2 (Build 3223)" || \
    (echo "JavaFo test failed. Expected 'JaVaFo (rrweb.org/javafo) - Rel. 2.2 (Build 3223)', got: $output" && exit 1)

# Switch to non-root user
USER litour

# Expose both web server and API worker ports
EXPOSE 8000 8880

# Default to web server mode
# This image can also run:
# - API worker: set command to run gunicorn on port 8880 with HELTOUR_APP=api_worker
# - Celery worker: set command to ["celery", "-A", "heltour", "worker", "-l", "info", "-E", "-B"]
CMD ["gunicorn", "heltour.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--threads", "2", \
     "--worker-class", "sync", \
     "--worker-tmp-dir", "/dev/shm", \
     "--log-file", "-", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
