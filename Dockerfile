# syntax=docker/dockerfile:1

# ---- base: runtime dependencies + app code (shared by test and runtime) ----
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app
WORKDIR /app

# Install only [project.dependencies], read straight from pyproject.toml.
# This layer is cached until pyproject.toml changes.
COPY pyproject.toml .
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > requirements.txt \
    && pip install -r requirements.txt

COPY app/ app/

# ---- test: adds dev dependencies, tests and tools; runs pytest ----
FROM base AS test
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['optional-dependencies']['dev']))" > requirements-dev.txt \
    && pip install -r requirements-dev.txt
COPY tests/ tests/
CMD ["python", "-m", "pytest"]

# ---- runtime: no dev dependencies, runs as a non-root user ----
FROM base AS runtime
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
