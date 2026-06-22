FROM python:3.14-slim

WORKDIR /app

# Install dependencies first so this layer is cached across source changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project. `src` is importable as a top-level package because the
# tests run from /app (on sys.path via `python -m`).
COPY . .

# Run the whole suite by default. With REDIS_HOST set (see docker-compose),
# the Redis integration tests hit a real Redis instead of skipping.
CMD ["python", "-m", "pytest", "-v"]
