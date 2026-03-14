# Builder stage
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

ENV PATH="$POETRY_HOME/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gcc g++ \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
# Note: poetry.lock will be copied if it exists in the next step or we can add it here
# For now, we'll assume it exists or will be generated.
COPY poetry.lock* ./

RUN if [ -f poetry.lock ]; then \
        poetry install --no-root --only main; \
    else \
        poetry lock --no-update && poetry install --no-root --only main; \
    fi

# Final stage
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && mkdir -p /app/outputs /app/data \
    && chown -R appuser:appuser /app

COPY --from=builder /app/.venv /app/.venv
COPY . /app

# Ensure correct permissions for the non-root user
RUN chown -R appuser:appuser /app

USER appuser

# Default command
CMD ["python", "app.py"]
